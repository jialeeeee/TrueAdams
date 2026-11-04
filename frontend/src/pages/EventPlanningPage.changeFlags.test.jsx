// SCRUM-70 TC-70-43; docs/test-cases/SCRUM-70-review-change-request.md and
// backend/tests/test_change_request_review.py (BookingFlagTests). The planning view adds
//   venue_bookings[].change_flag: { label, reasons, change_request_id, flagged_at }
// only while a booking awaits the coordinator's decision, and the coordinator keeps one
// with POST /events/<id>/venue-bookings/<booking id>/keep -> { message, booking_id }.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EventPlanningPage from "./EventPlanningPage.jsx";

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const LABEL = "Affected by an accepted change: keep it, or cancel or rebook it";
const REASON = "Booked for the current date and time; it isn't moved automatically.";
const booking = (id, name, extra = {}) => ({
  id, venue: { id: id * 10, name, location: "Level 1" }, status: "confirmed",
  start_time: "2026-12-05T18:00:00", end_time: "2026-12-05T23:00:00",
  setup_minutes: 0, turnaround_minutes: 0, hold_expires_at: null, hold_expired: null, ...extra,
});
const FLAG = { label: LABEL, reasons: [REASON], change_request_id: 31, flagged_at: "2026-10-28T03:00:00" };
const EVENT = {
  id: 7, title: "Charity Gala", status: "approved", start_time: "2026-12-06T18:00:00",
  end_time: "2026-12-06T23:30:00", coordinator: { id: 2, email: "alice@test.invalid" },
  organiser: { id: 4, email: "dana@test.invalid" }, not_recorded: [],
  venue_bookings: [booking(51, "Grand Ballroom", { change_flag: FLAG }), booking(52, "Garden Room")],
};
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/planning"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/planning" element={<EventPlanningPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

describe("EventPlanningPage bookings flagged by an accepted change (SCRUM-70 AC10)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiClient.get.mockResolvedValue({ data: EVENT });
  });

  // TC-70-43 · AC10
  it("shows why a booking is flagged and how to decide on it", async () => {
    renderPage();

    const flag = await screen.findByRole("region", { name: "Change affecting Grand Ballroom" });
    expect(within(flag).getByText(LABEL)).toBeTruthy();
    expect(within(flag).getByText(REASON)).toBeTruthy();
    expect(within(flag).getByRole("button", { name: "Keep this booking" })).toBeTruthy();
    expect(within(flag).getByRole("link", { name: "Cancel or rebook it" }).getAttribute("href"))
      .toBe("/events/7/venue-request");
    expect(screen.queryByRole("region", { name: "Change affecting Garden Room" })).toBeNull();
  });

  // TC-70-43 · AC10
  it("keeps the booking and stops showing the flag", async () => {
    const message = "You kept the booking at Grand Ballroom. It is no longer flagged.";
    apiClient.post.mockResolvedValue({ data: { message, booking_id: 51 } });
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Keep this booking" }));

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/venue-bookings/51/keep", {});
    expect((await screen.findByRole("status")).textContent).toBe(message);
    expect(screen.queryByRole("region", { name: "Change affecting Grand Ballroom" })).toBeNull();
    expect(screen.getByText("Garden Room, Level 1")).toBeTruthy();
  });

  // TC-70-43 · AC10, AC6
  it("explains a refused or failed decision and lets the coordinator try again", async () => {
    apiClient.post
      .mockRejectedValueOnce(failed(409, { error: "This booking isn't waiting for a decision. Refresh the page." }))
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockRejectedValueOnce(failed(503, { error: "   " }));
    const user = renderPage();
    const keep = await screen.findByRole("button", { name: "Keep this booking" });

    await user.click(keep);
    expect((await screen.findByRole("alert")).textContent)
      .toBe("This booking isn't waiting for a decision. Refresh the page.");
    await user.click(keep);
    expect((await screen.findByRole("alert")).textContent)
      .toBe("Your decision was not saved. Check your connection and try again.");
    await user.click(keep);
    expect((await screen.findByRole("alert")).textContent)
      .toBe("Your decision was not saved. Check your connection and try again.");
    expect(screen.getByRole("region", { name: "Change affecting Grand Ballroom" })).toBeTruthy();
  });
});
