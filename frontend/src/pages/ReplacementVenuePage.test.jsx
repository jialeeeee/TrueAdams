import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ReplacementVenuePage from "./ReplacementVenuePage.jsx";

// Frontend cases for SCRUM-89 (IS212-US89-TC1 to TC6, TC14, TC17) in
// docs/test-cases/SCRUM-89-replacement-venue.md. Responses mirror
// backend/tests/test_venue_replacement.py and the existing venue search and suitability APIs.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const FLAG = "Venue unavailable: replacement needed";
const CONTEXT = {
  booking: {
    id: 901, status: "confirmed", flag: FLAG,
    venue: { id: 1, name: "Orchard Hall", location: "12 Orchard Road" },
    start_time: "2027-11-20T10:00:00", end_time: "2027-11-20T12:00:00",
  },
  event: { id: 7, title: "Harbour Lights Festival", expected_attendance: 80,
    venue_requirements: "Open-air waterfront space" },
};
const VENUES = { venues: [
  { id: 1, name: "Orchard Hall", location: "12 Orchard Road", capacity: 400 },
  { id: 2, name: "Marina Room", location: "Level 2", capacity: 50 },
  { id: 3, name: "Harbour Room", location: "Dock Road", capacity: 120 },
  { id: 4, name: "Bay Hall", location: "Bay Road", capacity: 400 },
], message: null };
// The venues free at the booking's time (the same search as for a new booking).
const AVAILABLE = { venues: [{ id: 2 }, { id: 3 }], message: null };
const MISMATCH = {
  event: { id: 7, title: "Harbour Lights Festival" }, venue: { id: 2, name: "Marina Room" },
  checks: [{ requirement: "attendance", item: null, label: "Attendance", status: "mismatch",
    detail: "The event expects 80 people but the venue holds 50." }],
  overall: "does_not_meet", summary: "Does not meet all the checked requirements",
};

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function serve({ context = CONTEXT, failure = null } = {}) {
  apiClient.get.mockImplementation(async (url, config) => {
    if (url === "/venues/bookings/901/replacement") {
      if (failure) throw failure;
      return { data: context };
    }
    if (url === "/venues/") return { data: VENUES };
    if (url === "/venues/search") return { data: AVAILABLE };
    if (url === "/events/7/venue-suitability") {
      expect(config.params.venue_id).toBe(2);
      return { data: MISMATCH };
    }
    throw new Error(`unexpected GET ${url}`);
  });
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/bookings/901/replacement"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="/bookings/:bookingId/replacement" element={<ReplacementVenuePage />} /></Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  Object.values(apiClient).forEach((fn) => fn.mockReset());
  serve();
});

describe("searching for a replacement venue", () => {
  it("TC2: shows the same event and its times, which cannot be changed", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: /Harbour Lights Festival/ })).toBeTruthy();
    expect(screen.getByText("Replacing: Orchard Hall, 2027-11-20 10:00 to 2027-11-20 12:00")).toBeTruthy();
    expect(screen.getByText("Expected attendance: 80")).toBeTruthy();
    expect(screen.getByText("Venue requirements: Open-air waterfront space")).toBeTruthy();
    expect(screen.queryByLabelText("Start")).toBeNull();
    expect(screen.queryByLabelText("End")).toBeNull();
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith("/venues/search", {
      params: { date: "2027-11-20", start: "10:00", end: "12:00" },
    }));
  });

  it("marks which venues are free at that time", async () => {
    renderPage();
    const select = await screen.findByLabelText("Venue");
    await waitFor(() => expect(screen.getByRole("option", { name: /Harbour Room/ }).textContent)
      .toContain("available"));

    expect(screen.getByRole("option", { name: /Bay Hall/ }).textContent).toContain("not available");
    expect(select.value).toBe("");
  });

  it("TC6: shows when the chosen venue does not suit the event", async () => {
    const user = renderPage();
    await user.selectOptions(await screen.findByLabelText("Venue"), "2");

    expect(await screen.findByText("Does not meet all the checked requirements")).toBeTruthy();
    expect(screen.getByText(/Attendance: Mismatch/).textContent).toContain("The event expects 80 people but the venue holds 50.");
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});

describe("requesting the replacement", () => {
  it("TC1: sends only the venue and shows the pending request linked to the booking", async () => {
    apiClient.post.mockResolvedValue({ data: {
      message: "Your replacement request for Harbour Room was sent to Venue Staff.",
      booking: { id: 905, status: "pending", venue: { id: 3, name: "Harbour Room" },
        start_time: "2027-11-20T10:00:00", end_time: "2027-11-20T12:00:00",
        replaces: { id: 901, venue: { id: 1, name: "Orchard Hall" } } },
    } });
    const user = renderPage();
    await user.selectOptions(await screen.findByLabelText("Venue"), "3");
    await user.click(screen.getByRole("button", { name: "Submit request" }));

    expect(apiClient.post).toHaveBeenCalledWith("/venues/bookings/901/replacement", { venue_id: 3 });
    expect((await screen.findByRole("status")).textContent).toContain("sent to Venue Staff");
    expect(screen.getByText("Venue: Harbour Room")).toBeTruthy();
    expect(screen.getByText("Status: Pending")).toBeTruthy();
    expect(screen.getByText("Replaces booking 901 (Orchard Hall)")).toBeTruthy();
  });

  it("TC4: asks for a venue and sends nothing without one", async () => {
    const user = renderPage();
    await screen.findByLabelText("Venue");
    await user.click(screen.getByRole("button", { name: "Submit request" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Select a venue.");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("TC5: shows the clash and keeps the chosen venue", async () => {
    apiClient.post.mockRejectedValue(httpFailure(409, {
      error: "This booking can't be requested because it clashes with other arrangements at Bay Hall.",
      reason: "conflict", conflicts: [],
    }));
    const user = renderPage();
    await user.selectOptions(await screen.findByLabelText("Venue"), "4");
    await user.click(screen.getByRole("button", { name: "Submit request" }));

    expect((await screen.findByRole("alert")).textContent).toContain("clashes with other arrangements");
    expect(screen.getByLabelText("Venue").value).toBe("4");
  });

  it("TC17: a failed save says no request was created and keeps the choice", async () => {
    apiClient.post.mockRejectedValue(httpFailure(503, {
      error: "Your replacement request was not sent. Please try again.", retryable: true,
    }));
    const user = renderPage();
    await user.selectOptions(await screen.findByLabelText("Venue"), "3");
    await user.click(screen.getByRole("button", { name: "Submit request" }));

    expect((await screen.findByRole("alert")).textContent).toContain("was not sent");
    expect(screen.getByLabelText("Venue").value).toBe("3");
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("who can ask, and for which booking", () => {
  it("TC14: someone who is not the event's coordinator gets the refusal and no form", async () => {
    serve({ failure: httpFailure(403, { error: "Only the event's assigned coordinator can request a replacement venue." }) });
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("Only the event's assigned coordinator");
    expect(screen.queryByLabelText("Venue")).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit request" })).toBeNull();
  });

  it("TC3: a booking that is not flagged shows the reason and no form", async () => {
    serve({ failure: httpFailure(409, { error: "This booking is not flagged as needing a replacement venue.", reason: "not_flagged" }) });
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("not flagged");
    expect(screen.queryByLabelText("Venue")).toBeNull();
  });
});
