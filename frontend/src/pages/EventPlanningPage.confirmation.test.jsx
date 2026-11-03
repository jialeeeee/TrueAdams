// SCRUM-93 TC-93-05/06; docs/test-cases/SCRUM-93-confirm-event.md and
// backend/tests/test_event_confirmation.py. Additive confirmation API.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EventPlanningPage from "./EventPlanningPage.jsx";

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const COORDINATOR = { id: 2, email: "current@test.invalid" };
const EVENT = {
  id: 1,
  title: "Confirmation workshop",
  status: "approved",
  start_time: "2030-01-16T17:00:00",
  end_time: "2030-01-16T19:00:00",
  coordinator: COORDINATOR,
  organiser: { id: 4, email: "owner@test.invalid" },
  venue_bookings: [{
    id: 20,
    venue: { id: 10, name: "Hall A", location: "Level 1" },
    status: "confirmed",
    start_time: "2030-01-16T17:00:00",
    end_time: "2030-01-16T19:00:00",
    setup_minutes: 0,
    turnaround_minutes: 0,
    hold_expires_at: null,
    hold_expired: false,
  }],
  safety_check: {
    decision: "approved",
    officer: { id: 5, email: "officer@test.invalid" },
    comment: null,
    decided_at: "2030-01-15T09:00:00",
  },
  not_recorded: [],
};
const SUCCESS = {
  status: "confirmed",
  message: "Event confirmed.",
  confirmation: { coordinator: COORDINATOR, confirmed_at: "2026-10-29T04:00:00" },
};

// A venue booking can already say Confirmed; inspect the event's labelled status.
const eventStatus = () => screen.getAllByRole("term")
  .find((term) => term.textContent === "Status").nextElementSibling.textContent;

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/1/planning"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Link to="/events/2/planning">Open second event</Link>
      <Routes>
        <Route path="/events/:eventId/planning" element={<EventPlanningPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
  // Successful planning access is already restricted to the assigned coordinator.
  sessionStorage.setItem("user", JSON.stringify({ ...COORDINATOR, role: "coordinator" }));
  apiClient.get.mockResolvedValue({ data: EVENT });
});

describe("SCRUM-93 confirmation on the existing planning page", () => {
  // TC-93-05 / AC1, AC3.
  it("lets the assigned coordinator confirm and shows success with the confirmed status", async () => {
    apiClient.post.mockResolvedValue({ data: SUCCESS });
    const user = renderPage();
    await screen.findByRole("heading", { name: EVENT.title });
    expect(apiClient.get).toHaveBeenCalledWith("/events/1/planning");
    apiClient.get.mockResolvedValue({ data: { ...EVENT, ...SUCCESS } });
    await user.click(screen.getByRole("button", { name: /mark.*confirmed|confirm event/i }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/events/1/confirm", {}));
    expect(await screen.findByText("Event confirmed.")).toBeTruthy();
    await waitFor(() => expect(eventStatus()).toBe("Confirmed"));
  });

  // TC-93-07 / AC3: the same mounted route must ignore the previous event's save.
  it("ignores a confirmation response after navigating to another event", async () => {
    let completeConfirmation;
    apiClient.post.mockReturnValueOnce(new Promise((resolve) => {
      completeConfirmation = resolve;
    }));
    const secondEvent = { ...EVENT, id: 2, title: "Second workshop" };
    apiClient.get.mockResolvedValueOnce({ data: EVENT })
      .mockResolvedValueOnce({ data: secondEvent });
    const user = renderPage();
    await screen.findByRole("heading", { name: EVENT.title });
    await user.click(screen.getByRole("button", { name: /mark.*confirmed|confirm event/i }));
    expect(apiClient.post).toHaveBeenCalledWith("/events/1/confirm", {});

    await user.click(screen.getByRole("link", { name: "Open second event" }));
    await screen.findByRole("heading", { name: secondEvent.title });
    expect(apiClient.get).toHaveBeenLastCalledWith("/events/2/planning");
    await act(async () => completeConfirmation({ data: SUCCESS }));

    expect(screen.getByRole("heading", { name: secondEvent.title })).toBeTruthy();
    expect(eventStatus()).toBe("Approved");
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: /mark.*confirmed|confirm event/i }).disabled).toBe(false);
    expect(apiClient.post).toHaveBeenCalledTimes(1);
  });

  // TC-93-06 / AC2, AC4: two server responses, same interaction; no eligibility logic in React.
  it.each([
    [409, { error: "Cannot confirm: Approved safety check is missing.", missing: ["Approved safety check"] }],
    [503, { error: "The event was not confirmed. Please try again.", retryable: true }],
  ])("shows the %s refusal without falsely confirming and permits another attempt", async (status, data) => {
    apiClient.post.mockRejectedValueOnce({ response: { status, data } });
    const user = renderPage();
    await screen.findByRole("heading", { name: EVENT.title });
    await user.click(screen.getByRole("button", { name: /mark.*confirmed|confirm event/i }));
    expect((await screen.findByRole("alert")).textContent).toContain(data.error);
    expect(eventStatus()).toBe("Approved");
    expect(screen.queryByText("Event confirmed.")).toBeNull();
    apiClient.post.mockResolvedValueOnce({ data: SUCCESS });
    apiClient.get.mockResolvedValue({ data: { ...EVENT, ...SUCCESS } });
    await user.click(screen.getByRole("button", { name: /mark.*confirmed|confirm event/i }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(eventStatus()).toBe("Confirmed"));
  });
});

describe("SCRUM-93 confirmation edge cases", () => {
  it("ignores a failed confirmation after navigating to another event", async () => {
    let failConfirmation;
    apiClient.post.mockReturnValueOnce(new Promise((_, reject) => { failConfirmation = reject; }));
    const secondEvent = { ...EVENT, id: 2, title: "Second workshop" };
    apiClient.get.mockResolvedValueOnce({ data: EVENT }).mockResolvedValueOnce({ data: secondEvent });
    const user = renderPage();
    await screen.findByRole("heading", { name: EVENT.title });
    await user.click(screen.getByRole("button", { name: /mark.*confirmed|confirm event/i }));

    await user.click(screen.getByRole("link", { name: "Open second event" }));
    await screen.findByRole("heading", { name: secondEvent.title });
    await act(async () => failConfirmation({ response: { status: 409, data: { error: "Not ready." } } }));

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: /mark.*confirmed|confirm event/i }).disabled).toBe(false);
  });

  it("explains a failure that has no message from the server", async () => {
    apiClient.post.mockRejectedValueOnce(new Error("Network Error"));
    const user = renderPage();
    await screen.findByRole("heading", { name: EVENT.title });

    await user.click(screen.getByRole("button", { name: /mark.*confirmed|confirm event/i }));

    expect((await screen.findByRole("alert")).textContent).toBe("The event was not confirmed. Please try again.");
  });
});

describe("SCRUM-91/53 planning page with missing details", () => {
  it("says what is not recorded rather than leaving it blank", async () => {
    apiClient.get.mockResolvedValue({
      data: { ...EVENT, title: "", safety_check: { ...EVENT.safety_check, officer: null, decided_at: null } },
    });
    renderPage();

    expect(await screen.findByRole("heading", { level: 1, name: "Not recorded" })).toBeTruthy();
    const safety = within(screen.getByRole("region", { name: "Safety check" }));
    expect(safety.getByText("Safety Officer: Not recorded")).toBeTruthy();
    expect(safety.getByText("Decided: Not recorded")).toBeTruthy();
  });

  it("explains a load failure that has no message from the server, and offers a retry", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent)
      .toBe("The event's information could not be loaded. Check your connection and try again.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
