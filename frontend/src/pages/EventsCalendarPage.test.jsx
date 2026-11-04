import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EventsCalendarPage from "./EventsCalendarPage.jsx";

// CF09 frontend cases TC-CF09-09 to TC-CF09-11 in docs/test-cases/CF09-events-calendar.md.
// Responses mirror backend/tests/test_events_calendar.py:
//   GET /venues/calendar?from&to -> { from, to, events: [{ id, title, status, start_time,
//     end_time, venues: [{ id, name, booking_status, start_time, end_time }], coordinator,
//     managed }], message }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const ALICE = { id: 2, email: "alice@test.invalid" };
const EVENTS = [
  { id: 1, title: "Harbour Talk", status: "approved", start_time: "2027-06-10T10:00:00",
    end_time: "2027-06-10T12:00:00", coordinator: ALICE, managed: true,
    venues: [{ id: 5, name: "Hall A", booking_status: "confirmed", start_time: "2027-06-10T10:00:00", end_time: "2027-06-10T12:00:00" },
      { id: 6, name: "Annex", booking_status: "tentative", start_time: "2027-06-10T09:00:00", end_time: "2027-06-10T11:00:00" }] },
  { id: 2, title: "Night Market", status: "confirmed", start_time: "2027-06-10T22:00:00",
    end_time: "2027-06-11T02:00:00", coordinator: { id: 3, email: "ben@test.invalid" }, managed: false,
    venues: [] },
  { id: 3, title: "Book Fair", status: "submitted", start_time: "2027-06-12T09:00:00",
    end_time: "2027-06-12T17:00:00", coordinator: null, managed: false, venues: [] },
];
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <EventsCalendarPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

async function choose(user, from, to) {
  await user.type(screen.getByLabelText("From"), from);
  if (to) await user.type(screen.getByLabelText("To (optional)"), to);
  await user.click(screen.getByRole("button", { name: "Show events" }));
}

describe("EventsCalendarPage (CF09)", () => {
  beforeEach(() => vi.clearAllMocks());

  // TC-CF09-09 · A2, A3, A4
  it("shows every event by day, with its venues, status and coordinator", async () => {
    apiClient.get.mockResolvedValue({ data: { from: "2027-06-10", to: "2027-06-12", events: EVENTS, message: null } });
    const user = renderPage();

    await choose(user, "2027-06-10", "2027-06-12");

    expect(apiClient.get).toHaveBeenCalledWith("/venues/calendar", { params: { from: "2027-06-10", to: "2027-06-12" } });
    const first = await screen.findByRole("region", { name: "Thu 10 Jun 2027" });
    const items = within(first).getAllByRole("listitem").filter((item) => item.parentElement.parentElement === first);
    expect(items).toHaveLength(2);
    expect(within(first).getByRole("link", { name: "Harbour Talk" }).getAttribute("href")).toBe("/events/1/planning");
    expect(within(first).getByText("10/06/2027 10:00 SGT to 10/06/2027 12:00 SGT")).toBeTruthy();
    expect(within(first).getByText(`Coordinator: ${ALICE.email}`)).toBeTruthy();
    const venues = within(first).getByRole("list", { name: "Venues for Harbour Talk" });
    expect(within(venues).getAllByRole("listitem").map((item) => item.textContent))
      .toEqual(["Hall A (Confirmed)", "Annex (Tentative)"]);
    // Not this coordinator's event: shown, but not opened.
    expect(within(first).queryByRole("link", { name: "Night Market" })).toBeNull();
    expect(within(first).getByText("Night Market")).toBeTruthy();
    expect(within(first).getByText("No venue booked or requested yet.")).toBeTruthy();
    const third = screen.getByRole("region", { name: "Sat 12 Jun 2027" });
    expect(within(third).getByText("Status: Submitted")).toBeTruthy();
    expect(within(third).getByText("Coordinator: Not assigned yet")).toBeTruthy();
  });

  // TC-CF09-10 · A2, A5
  it("asks for a start date, sends only it when there is no end, and says when nothing is planned", async () => {
    apiClient.get.mockResolvedValue({ data: { from: "2031-01-01", to: "2031-01-01", events: [],
      message: "No events are planned for these dates." } });
    const user = renderPage();

    await user.click(screen.getByRole("button", { name: "Show events" }));
    expect(screen.getByRole("alert").textContent).toBe("Choose a start date.");
    expect(apiClient.get).not.toHaveBeenCalled();

    await choose(user, "2031-01-01");
    expect(apiClient.get).toHaveBeenCalledWith("/venues/calendar", { params: { from: "2031-01-01" } });
    expect(await screen.findByText("No events are planned for these dates.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // TC-CF09-11 · A5, A6
  it("explains a refused range or a failed load, and offers Retry only when it can help", async () => {
    apiClient.get
      .mockRejectedValueOnce(failed(400, { error: "Choose a range of at most 31 days." }))
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce({ data: { from: "2027-06-10", to: "2027-06-10", events: EVENTS.slice(0, 1), message: null } });
    const user = renderPage();

    await choose(user, "2027-06-01", "2027-07-15");
    expect((await screen.findByRole("alert")).textContent).toBe("Choose a range of at most 31 days.");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Show events" }));
    expect((await screen.findByRole("alert")).textContent)
      .toBe("The events calendar could not be loaded. Check your connection and try again.");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Harbour Talk" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
