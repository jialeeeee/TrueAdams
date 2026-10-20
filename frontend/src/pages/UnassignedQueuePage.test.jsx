import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import UnassignedQueuePage from "./UnassignedQueuePage.jsx";

// Frontend cases TC-81-35 to TC-81-37 in docs/test-cases/SCRUM-81-unassigned-queue.md.
// The API itself is covered by backend/tests/test_unassigned_queue.py; responses
// mirror its contract: GET /events/queue -> { events, message }.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const DANA = { id: 4, email: "dana.organiser@connectsphere.test" };
const EVAN = { id: 5, email: "evan.organiser@connectsphere.test" };
const EVENTS = [
  { id: 2, title: "Alumni Mixer", start_time: "2026-11-20T18:30:00", status: "submitted",
    organiser: EVAN, submitted_at: "2026-10-08T14:00:00" },
  { id: 1, title: "Harbour Lights Festival", start_time: "2026-12-12T17:00:00", status: "submitted",
    organiser: DANA, submitted_at: "2026-10-10T09:00:00" },
  { id: 3, title: null, start_time: null, status: "submitted",
    organiser: DANA, submitted_at: "2026-10-12T08:00:00" },
  { id: 4, title: "Legacy Forum", start_time: "2026-11-25T09:00:00", status: "submitted",
    organiser: EVAN, submitted_at: null },
];
const loaded = (events = EVENTS, message = null) => ({ data: { events, message } });
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

const LOAD_FAILED = "The queue could not be loaded. Please try again.";

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <UnassignedQueuePage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const item = (name) => within(screen.getByRole("link", { name }).closest("li"));

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-81 the Lead's unassigned queue", () => {
  it("lists each waiting event with its basic information", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Waiting events" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/queue");

    await screen.findByRole("link", { name: "Harbour Lights Festival" });
    const festival = item("Harbour Lights Festival");
    expect(festival.getByText(`Organiser: ${DANA.email}`)).toBeTruthy();
    // Singapore time, shown as recorded rather than converted.
    expect(festival.getByText("Proposed date: 2026-12-12 17:00")).toBeTruthy();
    // Submission times are UTC, shown in local time.
    expect(festival.getByText(`Submitted: ${formatSavedAt("2026-10-10T09:00:00")}`)).toBeTruthy();
    expect(item("Alumni Mixer").getByText(`Organiser: ${EVAN.email}`)).toBeTruthy();
  });

  it("keeps the order received and links each name to its assignment page", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    await screen.findByRole("link", { name: "Alumni Mixer" });
    const links = screen.getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual([
      "Alumni Mixer", "Harbour Lights Festival", "Not recorded", "Legacy Forum",
    ]);
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/events/2/assign", "/events/1/assign", "/events/3/assign", "/events/4/assign",
    ]);
  });

  it("shows missing values as Not recorded", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    await screen.findByRole("link", { name: "Not recorded" });
    expect(item("Not recorded").getByText("Proposed date: Not recorded")).toBeTruthy();
    expect(item("Legacy Forum").getByText("Submitted: Not recorded")).toBeTruthy();
  });

  it("shows the server's message when the queue is empty", async () => {
    const message = "No event requests are waiting for a coordinator.";
    apiClient.get.mockResolvedValue(loaded([], message));
    renderPage();

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("denies anyone else without showing events or a retry", async () => {
    const denied = "Only Event Coordinator Leads can view the queue.";
    apiClient.get.mockRejectedValue(failed(403, { error: denied }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(denied);
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("tells the Lead when the queue cannot be loaded, and retries", async () => {
    apiClient.get
      .mockRejectedValueOnce(failed(503, { error: LOAD_FAILED, retryable: true }))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(LOAD_FAILED);
    expect(screen.queryByRole("list")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Alumni Mixer" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The queue could not be loaded. Check your connection and try again.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  // SCRUM-80 TC-80-06: main.jsx uses StrictMode, which can overlap initial loads.
  it.each([
    [503, LOAD_FAILED, true],
    [403, "Only Event Coordinator Leads can view the queue.", false],
  ])("removes previously loaded events when an overlapping load fails with %s", async (status, message, retryable) => {
    let rejectLoad;
    apiClient.get
      .mockResolvedValueOnce(loaded())
      .mockReturnValueOnce(new Promise((resolve, reject) => { rejectLoad = reject; }));
    render(
      <StrictMode>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <UnassignedQueuePage />
        </MemoryRouter>
      </StrictMode>,
    );

    await screen.findByRole("link", { name: "Alumni Mixer" });
    expect(apiClient.get).toHaveBeenCalledTimes(2);
    await act(async () => {
      rejectLoad(failed(status, { error: message, retryable }));
    });

    expect(screen.getByRole("alert").textContent).toContain(message);
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.queryByText(`Organiser: ${EVAN.email}`)).toBeNull();
    expect(Boolean(screen.queryByRole("button", { name: "Retry" }))).toBe(retryable);
  });
});
