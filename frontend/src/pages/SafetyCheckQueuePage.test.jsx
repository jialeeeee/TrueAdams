// SCRUM-90 TC-90-05..07: docs/test-cases/SCRUM-90-safety-check-queue.md and
// backend/tests/test_safety_check_queue_unit.py. Proposed route/payload contract.
// Render App so RED detects missing functionality without importing a missing page.
import { StrictMode } from "react";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App.jsx";
import apiClient from "../api/client.js";
import singaporeTime from "../utils/singaporeTime.js";

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const WORKSHOP = {
  id: 1, title: "Reserved workshop", start_time: "2026-12-12T17:00:00",
  end_time: "2026-12-12T20:00:00", expected_attendance: 60,
  venues: [{ id: 10, name: "Aurora Hall" }],
  equipment: [{ equipment_type: "Microphone", quantity: 2, reserved_quantity: 2 }],
};
const LIST = { events: [WORKSHOP, { ...WORKSHOP, id: 2, title: "No equipment meeting", equipment: [] }], message: null };
const EMPTY = "There are no events awaiting a safety check.";
const DENIED = "Only Safety Officers can view events awaiting a safety check.";
const LOAD_FAILED = "The safety check list could not be loaded. Please try again.";

function openPage(strict = false) {
  sessionStorage.setItem("access_token", "scrum-90-test-token");
  const page = (
    <MemoryRouter initialEntries={["/events/safety-checks"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </MemoryRouter>
  );
  render(strict ? <StrictMode>{page}</StrictMode> : page);
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("SCRUM-90 safety check queue", () => {
  // TC-90-05 / AC1, AC2: backend owns eligibility; the page renders its list.
  it("opens the route, shows event details, and explains an empty queue", async () => {
    apiClient.get.mockResolvedValue({ data: LIST });
    openPage();

    await screen.findByRole("heading", { name: "Events awaiting a safety check" });
    const title = screen.getByText(WORKSHOP.title);
    const row = within(title.closest("li, tr"));
    expect(row.getByText(/Aurora Hall/)).toBeTruthy();
    expect(row.getByText((text) => text.includes(singaporeTime(WORKSHOP.start_time)))).toBeTruthy();
    expect(row.getByText(/60/)).toBeTruthy();
    expect(row.getByText(/2\s*×\s*Microphone|Microphone[^\n]*\b2\b/)).toBeTruthy();
    const meeting = within(screen.getByText("No equipment meeting").closest("li, tr"));
    expect(meeting.getByText(/no equipment required/i)).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/safety-checks");

    cleanup();
    apiClient.get.mockResolvedValue({ data: { events: [], message: EMPTY } });
    openPage();
    expect(await screen.findByText(EMPTY)).toBeTruthy();
    expect(screen.queryByText(WORKSHOP.title)).toBeNull();
  });

  // TC-90-06 / AC3: absence alone cannot pass; the API refusal must be visible.
  it("shows the authorization refusal without exposing event information", async () => {
    apiClient.get.mockRejectedValue({ response: { status: 403, data: { error: DENIED } } });
    openPage();

    await screen.findByRole("heading", { name: "Events awaiting a safety check" });
    expect((await screen.findByRole("alert")).textContent).toBe(DENIED);
    expect(screen.queryByText(WORKSHOP.title)).toBeNull();
    expect(screen.queryByText(/Aurora Hall/)).toBeNull();
    expect(screen.queryByText(/Microphone/)).toBeNull();
    expect(apiClient.get).toHaveBeenCalledWith("/events/safety-checks");
  });

  // TC-90-07 / AC4: a previous success must not remain visible after a failed load.
  it("clears previously loaded data on failure and explains an initial failure", async () => {
    apiClient.get.mockResolvedValueOnce({ data: LIST }).mockRejectedValueOnce({
      response: { status: 503, data: { error: LOAD_FAILED, retryable: true } },
    });
    const user = openPage();

    await screen.findByRole("heading", { name: "Events awaiting a safety check" });
    await screen.findByText(WORKSHOP.title);
    await user.click(screen.getByRole("button", { name: /refresh/i }));
    expect((await screen.findByRole("alert")).textContent).toBe(LOAD_FAILED);
    expect(screen.queryByText(WORKSHOP.title)).toBeNull();
    expect(screen.queryByText("No equipment meeting")).toBeNull();
    expect(screen.queryByText(/Aurora Hall/)).toBeNull();

    cleanup();
    apiClient.get.mockRejectedValue({ response: { status: 503, data: { error: LOAD_FAILED, retryable: true } } });
    openPage();
    expect((await screen.findByRole("alert")).textContent).toBe(LOAD_FAILED);
    expect(screen.queryByText(WORKSHOP.title)).toBeNull();
  });

  // TC-90-08 / AC4: main.jsx's StrictMode can leave an initial request pending
  // while a later load succeeds and the user refreshes the queue.
  it("ignores older results and errors after a newer refresh", async () => {
    for (const outcome of ["success", "failure"]) {
      let resolveOlder;
      let rejectOlder;
      const older = new Promise((resolve, reject) => {
        resolveOlder = resolve;
        rejectOlder = reject;
      });
      apiClient.get.mockReset();
      apiClient.get.mockReturnValueOnce(older)
        .mockResolvedValueOnce({ data: LIST })
        .mockResolvedValueOnce({ data: { events: [], message: EMPTY } });
      const user = openPage(true);
      await screen.findByText(WORKSHOP.title);
      await user.click(screen.getByRole("button", { name: /refresh/i }));
      await screen.findByText(EMPTY);
      await act(async () => {
        if (outcome === "success") resolveOlder({ data: LIST });
        else rejectOlder({ response: { status: 503, data: { error: LOAD_FAILED } } });
      });
      expect(screen.getByText(EMPTY)).toBeTruthy();
      expect(screen.queryByText(WORKSHOP.title)).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();
      cleanup();
    }
  });
});
