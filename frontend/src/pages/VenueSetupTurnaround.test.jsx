import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenueAvailabilityPage from "./VenueAvailabilityPage.jsx";
import VenueBookingRequestPage from "./VenueBookingRequestPage.jsx";
import VenueBookingRequestsPage from "./VenueBookingRequestsPage.jsx";

// Screen cases IS212-US84-TC1, TC4, TC6, TC10 and TC11 in the "Sprint 3 test cases" sheet
// (docs/test-cases/SCRUM-84-setup-and-turnaround-time.md). Responses mirror
// backend/tests/test_venue_setup_turnaround.py.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const DAY = "2027-03-12";
const PERIOD = {
  type: "booking", id: 201, start: `${DAY}T09:30:00`, end: `${DAY}T12:45:00`, reason: null,
  event_start: `${DAY}T10:00:00`, event_end: `${DAY}T12:00:00`,
  setup: { start: `${DAY}T09:30:00`, end: `${DAY}T10:00:00`, minutes: 30 },
  turnaround: { start: `${DAY}T12:00:00`, end: `${DAY}T12:45:00`, minutes: 45 },
};

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("availability calendar (TC1, TC4)", () => {
  it("lists the occupied period with its setup and turnaround labelled", async () => {
    apiClient.get.mockImplementation(async (url) => {
      if (url === "/venues/") {
        return { data: { venues: [{ id: 3, name: "Aurora Ballroom", location: "L3", capacity: 400 }], message: null } };
      }
      return { data: { venue_id: 3, from: DAY, to: DAY, periods: [PERIOD], days: [{ date: DAY, slots: [] }] } };
    });
    render(
      <MemoryRouter initialEntries={["/venues/availability"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes><Route path="/venues/availability" element={<VenueAvailabilityPage />} /></Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Venue"), "3");
    await user.type(screen.getByLabelText("From"), DAY);
    await user.click(screen.getByRole("button", { name: "View availability" }));
    const list = await screen.findByRole("list", { name: "Bookings and unavailable periods" });
    expect(list.textContent).toContain("setup 09:30 to 10:00, turnaround 12:00 to 12:45");
    expect(list.textContent).toContain("Confirmed booking");
  });
});

describe("venue request form (TC6, TC10)", () => {
  const planning = {
    id: 7, title: "Harbour Lights Festival", status: "approved",
    start_time: `${DAY}T13:00:00`, end_time: `${DAY}T15:00:00`,
    expected_attendance: 250, venue_requirements: "Stage power", venue: null,
  };

  it("sends the setup and turnaround and shows the labelled conflict, keeping the entries", async () => {
    apiClient.get.mockImplementation(async (url) => {
      if (url === "/events/7/planning") return { data: planning };
      return { data: { venues: [{ id: 3, name: "Aurora Ballroom", location: "L3", capacity: 400 }], message: null } };
    });
    apiClient.post.mockRejectedValue(httpFailure(409, {
      error: "This booking can't be requested because it clashes with other arrangements at Aurora Ballroom.",
      reason: "conflict", occupied: { start: `${DAY}T12:30:00`, end: `${DAY}T15:45:00` },
      conflicts: [PERIOD],
    }));
    render(
      <MemoryRouter initialEntries={["/events/7/venue-request"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes><Route path="/events/:eventId/venue-request" element={<VenueBookingRequestPage />} /></Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: /request a venue/i });
    await user.selectOptions(screen.getByLabelText("Venue"), "3");
    await user.clear(screen.getByLabelText(/Setup time/));
    await user.type(screen.getByLabelText(/Setup time/), "30");
    await user.clear(screen.getByLabelText(/Turnaround time/));
    await user.type(screen.getByLabelText(/Turnaround time/), "45");
    await user.click(screen.getByRole("button", { name: "Submit request" }));

    expect(apiClient.post).toHaveBeenCalledWith("/venues/bookings", expect.objectContaining({
      setup_minutes: "30", turnaround_minutes: "45", venue_id: 3,
    }));
    expect((await screen.findByRole("alert")).textContent).toContain("clashes with other arrangements");
    expect(screen.getByText(`Your request would occupy the venue ${DAY} 12:30 to ${DAY} 15:45.`)).toBeTruthy();
    const conflicts = screen.getByRole("list", { name: "Conflicts" });
    expect(conflicts.textContent).toContain(
      `Confirmed booking: ${DAY} 09:30 to ${DAY} 12:45 (setup 09:30 to 10:00, turnaround 12:00 to 12:45)`);
    // The entered details stay so the request can be changed and sent again.
    expect(screen.getByLabelText(/Setup time/).value).toBe("30");
    expect(screen.getByLabelText("Venue").value).toBe("3");
  });
});

describe("Venue Staff review list (TC11)", () => {
  it("shows the occupied period with setup and turnaround", async () => {
    apiClient.get.mockResolvedValue({ data: { message: null, bookings: [{
      id: 301, status: "pending",
      event: { id: 7, title: "Harbour Lights Festival", expected_attendance: 250 },
      venue: { id: 3, name: "Aurora Ballroom", location: "L3" },
      start_time: `${DAY}T10:00:00`, end_time: `${DAY}T12:00:00`,
      setup_minutes: 30, turnaround_minutes: 45,
      occupied_start: `${DAY}T09:30:00`, occupied_end: `${DAY}T12:45:00`,
      venue_requirements: "Stage power",
      requested_by: { id: 2, email: "alice@x.test" }, requested_at: "2026-10-14T03:00:00",
      conflicts: [PERIOD],
    }] } });
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <VenueBookingRequestsPage />
      </MemoryRouter>,
    );
    const item = await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    expect(item.textContent).toContain(`Requested: ${DAY} 10:00 to ${DAY} 12:00`);
    expect(item.textContent).toContain(
      `Occupied: ${DAY} 09:30 to ${DAY} 12:45 (setup 30 min, turnaround 45 min)`);
    expect(item.textContent).toContain("setup 09:30 to 10:00, turnaround 12:00 to 12:45");
  });
});
