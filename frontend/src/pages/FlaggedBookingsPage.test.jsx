import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import FlaggedBookingsPage from "./FlaggedBookingsPage.jsx";

// Frontend cases for SCRUM-84 AC5 (IS212-US84-TC18) in
// docs/test-cases/SCRUM-84-setup-and-turnaround-time.md: Venue Staff's list of bookings
// flagged "Setup or turnaround conflict" (GET /api/venues/flagged-bookings). Responses mirror
// backend/tests/test_venue_setup_turnaround.py.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const DAY = "2027-11-20";
const FLAGGED = {
  id: 501, status: "confirmed", flag: "Setup or turnaround conflict",
  event: { id: 7, title: "Harbour Lights Festival" },
  venue: { id: 3, name: "Aurora Ballroom", location: "Level 3, Marina Tower" },
  start_time: `${DAY}T10:00:00`, end_time: `${DAY}T12:00:00`,
  occupied_start: `${DAY}T09:45:00`, occupied_end: `${DAY}T13:00:00`,
  setup: { start: `${DAY}T09:45:00`, end: `${DAY}T10:00:00`, minutes: 15 },
  turnaround: { start: `${DAY}T12:00:00`, end: `${DAY}T13:00:00`, minutes: 60 },
  overlaps: [502], flagged_at: "2026-11-01T02:00:00",
};

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <FlaggedBookingsPage />
    </MemoryRouter>,
  );
}

describe("Bookings flagged for a setup or turnaround conflict (TC18)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists each flagged booking with its occupied period and what it overlaps", async () => {
    apiClient.get.mockResolvedValue({ data: { bookings: [FLAGGED], message: null } });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Setup or turnaround conflicts" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/venues/flagged-bookings");
    const item = await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    expect(item.textContent).toContain("Setup or turnaround conflict");
    expect(item.textContent).toContain("Venue: Aurora Ballroom, Level 3, Marina Tower");
    expect(item.textContent).toContain(`Event time: ${DAY} 10:00 to ${DAY} 12:00`);
    expect(item.textContent).toContain(`Occupied: ${DAY} 09:45 to ${DAY} 13:00`);
    expect(item.textContent).toContain("setup 09:45 to 10:00, turnaround 12:00 to 13:00");
    expect(item.textContent).toContain("Status: Confirmed");
    expect(item.textContent).toContain("Overlaps booking 502");
  });

  it("says so when nothing is flagged", async () => {
    apiClient.get.mockResolvedValue({
      data: { bookings: [], message: "No bookings are flagged for a setup or turnaround conflict." },
    });
    renderPage();

    expect(await screen.findByText("No bookings are flagged for a setup or turnaround conflict.")).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("explains a failed load and retries", async () => {
    apiClient.get.mockRejectedValueOnce(httpFailure(503, {
      error: "Flagged bookings could not be loaded. Please try again.", retryable: true,
    }));
    apiClient.get.mockResolvedValue({ data: { bookings: [FLAGGED], message: null } });
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("listitem", { name: "Harbour Lights Festival" })).toBeTruthy();
  });

  it("labels a booking without an event by its number", async () => {
    apiClient.get.mockResolvedValue({ data: { bookings: [{ ...FLAGGED, event: null }], message: null } });
    renderPage();

    expect(await screen.findByRole("listitem", { name: "Booking 501" })).toBeTruthy();
  });
});

describe("Flagged bookings with missing details", () => {
  it("names the venue alone when its location is not recorded", async () => {
    apiClient.get.mockResolvedValue({ data: { bookings: [{ ...FLAGGED, venue: { ...FLAGGED.venue, location: null } }], message: null } });
    renderPage();

    expect(await screen.findByText("Venue: Aurora Ballroom")).toBeTruthy();
  });
});
