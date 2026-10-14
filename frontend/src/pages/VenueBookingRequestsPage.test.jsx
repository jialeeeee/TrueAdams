import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenueBookingRequestsPage from "./VenueBookingRequestsPage.jsx";

// Frontend case TC-39-20 in docs/test-cases/SCRUM-39-venue-booking-request.md:
// Venue Staff's list of pending requests (GET /api/venues/bookings).

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

const BOOKING = {
  id: 11, status: "pending",
  event: { id: 7, title: "Harbour Lights Festival", expected_attendance: 250 },
  venue: { id: 3, name: "Aurora Ballroom", location: "Level 3, Marina Tower" },
  start_time: "2027-03-12T16:00:00", end_time: "2027-03-12T22:30:00",
  venue_requirements: "Open-air waterfront space for 250, stage power",
  requested_by: { id: 2, email: "alice.coordinator@connectsphere.test" },
  requested_at: "2026-10-14T03:00:00",
};

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <VenueBookingRequestsPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-39 venue booking requests for Venue Staff", () => {
  it("lists each pending request with what Venue Staff need to assess it", async () => {
    apiClient.get.mockResolvedValue({ data: { bookings: [BOOKING], message: null } });
    renderPage();

    const item = await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    expect(apiClient.get).toHaveBeenCalledWith("/venues/bookings");
    const text = item.textContent;
    expect(text).toContain("Venue: Aurora Ballroom, Level 3, Marina Tower");
    expect(text).toContain("Requested: 2027-03-12 16:00 to 2027-03-12 22:30");
    expect(text).toContain("Expected attendance: 250");
    expect(text).toContain("Requirements: Open-air waterfront space for 250, stage power");
    expect(text).toContain(`Requested by alice.coordinator@connectsphere.test on ${localTime("2026-10-14T03:00:00")}`);
    expect(text).toContain("Status: Pending");
  });

  it("shows the empty state", async () => {
    apiClient.get.mockResolvedValue({ data: { bookings: [], message: "There are no pending venue requests." } });
    renderPage();
    expect(await screen.findByText("There are no pending venue requests.")).toBeTruthy();
  });

  it("shows a retryable error when the requests cannot be loaded", async () => {
    apiClient.get
      .mockRejectedValueOnce(Object.assign(new Error("fail"), {
        response: { status: 503, data: { error: "Venue requests could not be loaded. Please try again.", retryable: true } },
      }))
      .mockResolvedValueOnce({ data: { bookings: [BOOKING], message: null } });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("listitem", { name: "Harbour Lights Festival" })).toBeTruthy();
  });
});
