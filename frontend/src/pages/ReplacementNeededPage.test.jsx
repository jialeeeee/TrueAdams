import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ReplacementNeededPage from "./ReplacementNeededPage.jsx";

// Frontend case for SCRUM-88 AC2 (IS212-US88-TC9) in
// docs/test-cases/SCRUM-88-venue-becomes-unavailable.md: Venue Staff's list of confirmed
// bookings flagged "Venue unavailable: replacement needed" (GET /api/venues/replacement-needed).
// Responses mirror backend/tests/test_venue_unavailable.py.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const FLAGGED = {
  id: 801, status: "confirmed", flag: "Venue unavailable: replacement needed",
  event: { id: 7, title: "Harbour Lights Festival" },
  venue: { id: 1, name: "Orchard Hall", location: "12 Orchard Road" },
  start_time: "2027-11-20T10:00:00", end_time: "2027-11-20T12:00:00",
  period: { id: 3, reason: "Floor renovation", start_time: "2027-11-20T09:00:00", end_time: "2027-11-20T18:00:00" },
  flagged_at: "2026-11-01T02:00:00",
};

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ReplacementNeededPage />
    </MemoryRouter>,
  );
}

describe("Bookings that need a replacement venue (TC9)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists each flagged booking with its event, venue, times and the unavailable period", async () => {
    apiClient.get.mockResolvedValue({ data: { bookings: [FLAGGED], message: null } });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Replacement venues needed" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/venues/replacement-needed");
    const item = await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    expect(item.textContent).toContain("Venue unavailable: replacement needed");
    expect(item.textContent).toContain("Venue: Orchard Hall, 12 Orchard Road");
    expect(item.textContent).toContain("Booked: 2027-11-20 10:00 to 2027-11-20 12:00");
    expect(item.textContent).toContain("Status: Confirmed");
    expect(item.textContent).toContain("Unavailable: 2027-11-20 09:00 to 2027-11-20 18:00 (Floor renovation)");
  });

  it("says when no booking needs a replacement", async () => {
    apiClient.get.mockResolvedValue({
      data: { bookings: [], message: "No bookings need a replacement venue." },
    });
    renderPage();

    expect(await screen.findByText("No bookings need a replacement venue.")).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("explains a failed load and retries", async () => {
    apiClient.get.mockRejectedValueOnce(httpFailure(503, {
      error: "Bookings needing a replacement could not be loaded. Please try again.", retryable: true,
    }));
    apiClient.get.mockResolvedValue({ data: { bookings: [FLAGGED], message: null } });
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("listitem", { name: "Harbour Lights Festival" })).toBeTruthy();
  });
});
