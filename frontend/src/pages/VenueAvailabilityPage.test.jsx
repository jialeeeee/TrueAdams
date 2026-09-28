import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenueAvailabilityPage from "./VenueAvailabilityPage.jsx";

// Frontend parts of the cases in docs/test-cases/SCRUM-36-venue-availability.md.
// The API itself is covered by backend/tests/test_scrum36_venue_availability.py;
// these check what the user sees. Responses mirror that API's contract.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const VENUES = {
  data: {
    venues: [
      { id: 1, name: "Aurora Ballroom", location: "Level 3, Marina Tower", capacity: 400, is_available: true },
      { id: 2, name: "Civic Hall", location: "12 Civic Road", capacity: 80, is_available: true },
    ],
    message: null,
  },
};

const slot = (start, end, status, date = "2026-10-15") => ({
  start: `${date}T${start}:00`,
  end: end === "24:00" ? "2026-10-16T00:00:00" : `${date}T${end}:00`,
  status,
});

// The "Expected calendar for Aurora Ballroom on Thu 15 Oct" from the test cases.
const AURORA_15_OCT = {
  data: {
    venue_id: 1, from: "2026-10-15", to: "2026-10-15",
    periods: [
      { type: "booking", id: 11, start: "2026-10-15T10:00:00", end: "2026-10-15T12:00:00", reason: null },
      { type: "block", id: 23, start: "2026-10-15T11:00:00", end: "2026-10-15T13:00:00", reason: "AV rigging" },
      { type: "booking", id: 12, start: "2026-10-15T14:00:00", end: "2026-10-15T16:00:00", reason: null },
      { type: "block", id: 21, start: "2026-10-15T16:00:00", end: "2026-10-15T17:00:00", reason: "Floor polishing" },
    ],
    days: [{
      date: "2026-10-15",
      slots: [
        slot("00:00", "08:00", "outside_operating_hours"),
        slot("08:00", "10:00", "available"),
        slot("10:00", "13:00", "unavailable"),
        slot("13:00", "14:00", "available"),
        slot("14:00", "17:00", "unavailable"),
        slot("17:00", "23:00", "available"),
        slot("23:00", "24:00", "outside_operating_hours"),
      ],
    }],
    message: null,
  },
};

function httpFailure(status, error) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true,
    response: { status, data: { error, ...(status === 503 ? { retryable: true } : {}) } },
  });
}

async function renderPage() {
  render(
    <MemoryRouter initialEntries={["/venues/availability"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/venues/availability" element={<VenueAvailabilityPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("option", { name: "Aurora Ballroom" });
  return userEvent.setup();
}

async function view(user, { venue = "Aurora Ballroom", from = "2026-10-15", to } = {}) {
  if (venue) await user.selectOptions(screen.getByLabelText("Venue"), venue);
  if (from) await user.type(screen.getByLabelText("From"), from);
  if (to) await user.type(screen.getByLabelText("To (optional)"), to);
  await user.click(screen.getByRole("button", { name: "View availability" }));
}

const availabilityCalls = () =>
  apiClient.get.mock.calls.filter(([url]) => url.endsWith("/availability"));

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset();
  vi.mocked(apiClient.get).mockResolvedValueOnce(VENUES);
});

describe("VenueAvailabilityPage", () => {
  // TC-36-01 · AC1, AC2, AC3, AC4 — the calendar shows every period and slot.
  it("shows bookings, blocks and the day's slots for the selected venue", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(AURORA_15_OCT);
    const user = await renderPage();

    await view(user);

    expect(apiClient.get).toHaveBeenCalledWith("/venues/1/availability", {
      params: { from: "2026-10-15" },
    });
    const periods = within(await screen.findByRole("list", { name: /bookings and unavailable/i }));
    expect(periods.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Confirmed booking: Thu 15 Oct 2026, 10:00 to Thu 15 Oct 2026, 12:00",
      "Recorded block: Thu 15 Oct 2026, 11:00 to Thu 15 Oct 2026, 13:00 (AV rigging)",
      "Confirmed booking: Thu 15 Oct 2026, 14:00 to Thu 15 Oct 2026, 16:00",
      "Recorded block: Thu 15 Oct 2026, 16:00 to Thu 15 Oct 2026, 17:00 (Floor polishing)",
    ]);
    const day = within(screen.getByRole("region", { name: "Thu 15 Oct 2026" }));
    expect(day.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "00:00–08:00 Outside operating hours",
      "08:00–10:00 Available",
      "10:00–13:00 Unavailable",
      "13:00–14:00 Available",
      "14:00–17:00 Unavailable",
      "17:00–23:00 Available",
      "23:00–24:00 Outside operating hours",
    ]);
  });

  // TC-36-03 · AC1 — a date range sends both dates.
  it("sends the end date for a date range", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(AURORA_15_OCT);
    const user = await renderPage();

    await view(user, { to: "2026-10-17" });

    expect(apiClient.get).toHaveBeenLastCalledWith("/venues/1/availability", {
      params: { from: "2026-10-15", to: "2026-10-17" },
    });
  });

  // TC-36-06 · AC1 — no venue selected: a prompt, and no request or calendar.
  it("asks for a venue when none is selected", async () => {
    const user = await renderPage();

    await view(user, { venue: null });

    expect(screen.getByRole("alert").textContent).toContain("Select a venue.");
    expect(availabilityCalls()).toHaveLength(0);
    expect(screen.queryByRole("article", { name: /calendar/i })).toBeNull();
  });

  // TC-36-04, TC-36-08, TC-36-09 · AC1 — the server's refusal is shown, with no calendar.
  it("shows the server's message when the request is refused", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(
      httpFailure(400, "The end date must be on or after the start date."),
    );
    const user = await renderPage();

    await view(user, { from: "2026-10-17", to: "2026-10-15" });

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The end date must be on or after the start date.",
    );
    expect(screen.queryByRole("article", { name: /calendar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  // TC-36-17 · AC3, AC4 — nothing recorded is an empty state, not an error.
  it("shows the empty-state message when nothing is recorded", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        venue_id: 1, from: "2026-10-19", to: "2026-10-19", periods: [],
        days: [{ date: "2026-10-19", slots: [slot("00:00", "24:00", "available", "2026-10-19")] }],
        message: "No bookings or blocks are recorded for this period.",
      },
    });
    const user = await renderPage();

    await view(user, { from: "2026-10-19" });

    expect(await screen.findByText("No bookings or blocks are recorded for this period.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // TC-36-22 to TC-36-25 · AC5 — Refresh shows the saved change.
  it("refreshes the calendar to show a saved change", async () => {
    const confirmed = structuredClone(AURORA_15_OCT);
    confirmed.data.periods.push(
      { type: "booking", id: 13, start: "2026-10-15T18:00:00", end: "2026-10-15T20:00:00", reason: null },
    );
    vi.mocked(apiClient.get).mockResolvedValueOnce(AURORA_15_OCT).mockResolvedValueOnce(confirmed);
    const user = await renderPage();
    await view(user);
    const periods = await screen.findByRole("list", { name: /bookings and unavailable/i });
    expect(within(periods).getAllByRole("listitem")).toHaveLength(4);

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByText(/Thu 15 Oct 2026, 18:00/)).toBeTruthy();
    expect(availabilityCalls()).toHaveLength(2);
  });

  // TC-36-27 · AC6 — a load failure is an error with Retry, never a calendar.
  it("shows an error with Retry, and no calendar, when loading fails", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(
      httpFailure(503, "Venue information could not be loaded. Please try again."),
    );
    const user = await renderPage();

    await view(user);

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.queryByRole("article", { name: /calendar/i })).toBeNull();
    expect(screen.queryByText(/Available/)).toBeNull();
  });

  // TC-36-29 · AC6 — Retry loads the calendar once the service is back.
  it("loads the calendar on Retry", async () => {
    vi.mocked(apiClient.get)
      .mockRejectedValueOnce(httpFailure(503, "Venue information could not be loaded. Please try again."))
      .mockResolvedValueOnce(AURORA_15_OCT);
    const user = await renderPage();
    await view(user);

    await user.click(await screen.findByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("region", { name: "Thu 15 Oct 2026" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // TC-36-30 · AC5, AC6 — a failed refresh removes the old calendar.
  it("does not keep showing the old calendar when a refresh fails", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce(AURORA_15_OCT)
      .mockRejectedValueOnce(httpFailure(503, "Venue information could not be loaded. Please try again."));
    const user = await renderPage();
    await view(user);
    await screen.findByRole("region", { name: "Thu 15 Oct 2026" });

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    expect(screen.queryByRole("region", { name: "Thu 15 Oct 2026" })).toBeNull();
  });

  // TC-36-21 · AC4 — unrecorded hours are labelled, not shown as available (proposed, Q4).
  it("labels time with unrecorded operating hours", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        venue_id: 1, from: "2026-10-15", to: "2026-10-15", periods: [],
        days: [{ date: "2026-10-15", slots: [slot("00:00", "24:00", "hours_not_recorded")] }],
        message: "No bookings or blocks are recorded for this period.",
      },
    });
    const user = await renderPage();

    await view(user);

    expect(await screen.findByText(/Operating hours not recorded/)).toBeTruthy();
    expect(screen.queryByText(/Available/)).toBeNull();
  });
});
