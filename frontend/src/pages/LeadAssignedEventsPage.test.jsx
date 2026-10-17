import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import LeadAssignedEventsPage from "./LeadAssignedEventsPage.jsx";

// Frontend cases TC-83-18 to TC-83-22 in
// docs/test-cases/SCRUM-83-lead-assigned-events.md. The API itself is covered by
// backend/tests/test_lead_assigned_events.py; responses mirror its contract.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const ALICE = { id: 11, email: "alice.coordinator@connectsphere.test" };
const BEN = { id: 12, email: "ben.coordinator@connectsphere.test" };
const EVENTS = [
  { id: 3, title: "Charity Fun Run", start_time: "2026-11-05T07:00:00", status: "under_review", coordinator: ALICE },
  { id: 2, title: "Alumni Mixer", start_time: "2026-11-20T18:30:00", status: "approved", coordinator: BEN },
  { id: 4, title: "Year-End Showcase", start_time: "2026-11-30T19:00:00", status: "confirmed", coordinator: BEN },
  { id: 1, title: "Harbour Lights Festival", start_time: "2026-12-12T17:00:00", status: "submitted", coordinator: ALICE },
  { id: 5, title: null, start_time: null, status: "submitted", coordinator: ALICE },
];
const BENS_EVENTS = EVENTS.filter((event) => event.coordinator === BEN);

const loaded = (events = EVENTS, message = null, coordinators = [ALICE, BEN]) => ({
  data: { events, coordinators, message },
});
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

const LOAD_FAILED = "The events you assigned could not be loaded. Please try again.";
const DENIED = "Only Event Coordinator Leads can view the events they assigned.";

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <LeadAssignedEventsPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const item = (name) => within(screen.getByRole("heading", { name }).closest("li"));
const eventNames = () =>
  screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
const coordinatorBox = () => screen.getByRole("combobox", { name: "Coordinator" });

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-83 events a Lead assigned", () => {
  it("lists each event with its name, coordinator, proposed date and status", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Events I assigned" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/supervised", { params: {} });

    await screen.findByRole("heading", { name: "Harbour Lights Festival" });
    const festival = item("Harbour Lights Festival");
    expect(festival.getByText(`Coordinator: ${ALICE.email}`)).toBeTruthy();
    // Singapore time, shown as recorded rather than converted.
    expect(festival.getByText("Proposed date: 2026-12-12 17:00")).toBeTruthy();
    expect(festival.getByText("Status: Submitted")).toBeTruthy();
    expect(item("Alumni Mixer").getByText(`Coordinator: ${BEN.email}`)).toBeTruthy();
    expect(item("Charity Fun Run").getByText("Status: Under review")).toBeTruthy();
    expect(item("Year-End Showcase").getByText("Status: Confirmed")).toBeTruthy();
  });

  it("keeps the order received", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    await screen.findByRole("heading", { name: "Alumni Mixer" });
    expect(eventNames()).toEqual([
      "Charity Fun Run", "Alumni Mixer", "Year-End Showcase", "Harbour Lights Festival",
      "Not recorded",
    ]);
  });

  // SCRUM-82 TC-82-13 · AC1 — each event starts a reassignment.
  it("links each event to its reassign page", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    await screen.findByRole("heading", { name: "Alumni Mixer" });
    for (const event of EVENTS) {
      const row = item(event.title || "Not recorded");
      expect(row.getByRole("link", { name: "Reassign coordinator" }).getAttribute("href"))
        .toBe(`/events/${event.id}/change-coordinator`);
    }
  });

  it("shows a missing name and proposed date as Not recorded", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    await screen.findByRole("heading", { name: "Not recorded" });
    expect(item("Not recorded").getByText("Proposed date: Not recorded")).toBeTruthy();
    expect(item("Not recorded").getByText(`Coordinator: ${ALICE.email}`)).toBeTruthy();
  });

  it("filters the list by coordinator and can show everyone again", async () => {
    apiClient.get
      .mockResolvedValueOnce(loaded())
      .mockResolvedValueOnce(loaded(BENS_EVENTS))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    await screen.findByRole("heading", { name: "Alumni Mixer" });
    expect(within(coordinatorBox()).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "All coordinators", ALICE.email, BEN.email,
    ]);

    await user.selectOptions(coordinatorBox(), BEN.email);
    expect(apiClient.get).toHaveBeenLastCalledWith("/events/supervised", {
      params: { coordinator_id: String(BEN.id) },
    });
    expect(await screen.findByRole("heading", { name: "Year-End Showcase" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Charity Fun Run" })).toBeNull();
    expect(eventNames()).toEqual(["Alumni Mixer", "Year-End Showcase"]);

    await user.selectOptions(coordinatorBox(), "All coordinators");
    expect(apiClient.get).toHaveBeenLastCalledWith("/events/supervised", { params: {} });
    expect(await screen.findByRole("heading", { name: "Charity Fun Run" })).toBeTruthy();
  });

  it("shows the server's message when a coordinator has none of the Lead's events", async () => {
    const message = "None of your active events are assigned to this coordinator.";
    apiClient.get
      .mockResolvedValueOnce(loaded())
      .mockResolvedValueOnce(loaded([], message));
    const user = renderPage();

    await screen.findByRole("heading", { name: "Alumni Mixer" });
    await user.selectOptions(coordinatorBox(), ALICE.email);

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
    expect(coordinatorBox().value).toBe(String(ALICE.id));
  });

  it("shows the empty state when the Lead has assigned no active events", async () => {
    const message = "You have no active events with a coordinator you assigned.";
    apiClient.get.mockResolvedValue(loaded([], message, []));
    renderPage();

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("denies anyone else without showing any event data or a retry", async () => {
    apiClient.get.mockRejectedValue(failed(403, { error: DENIED }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(DENIED);
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("tells the Lead when the list cannot be loaded, shows no list, and retries", async () => {
    apiClient.get
      .mockRejectedValueOnce(failed(503, { error: LOAD_FAILED, retryable: true }))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(LOAD_FAILED);
    expect(screen.queryByRole("list")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Alumni Mixer" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("removes a list it was showing when a reload fails, and retries the same filter", async () => {
    apiClient.get
      .mockResolvedValueOnce(loaded())
      .mockRejectedValueOnce(failed(503, { error: LOAD_FAILED, retryable: true }))
      .mockResolvedValueOnce(loaded(BENS_EVENTS));
    const user = renderPage();

    await screen.findByRole("heading", { name: "Alumni Mixer" });
    await user.selectOptions(coordinatorBox(), BEN.email);

    expect((await screen.findByRole("alert")).textContent).toContain(LOAD_FAILED);
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Charity Fun Run" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(apiClient.get).toHaveBeenLastCalledWith("/events/supervised", {
      params: { coordinator_id: String(BEN.id) },
    });
    expect(await screen.findByRole("heading", { name: "Year-End Showcase" })).toBeTruthy();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The events you assigned could not be loaded. Check your connection and try again.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });
});
