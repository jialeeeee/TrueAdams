import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import RegistrationOverviewPage from "./RegistrationOverviewPage.jsx";

// Frontend cases TC-72-16 to TC-72-20 in
// docs/test-cases/SCRUM-72-coordinator-view-registration-information.md. The API itself is
// covered by backend/tests/test_coordinator_registrations.py; responses mirror its contract.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const OVERVIEW = {
  event: {
    id: 7, title: "Alumni Mixer", start_time: "2026-11-20T18:30:00", end_time: "2026-11-20T21:00:00",
    status: "approved", expected_attendance: 60, venue: { name: "Harbour Hall", capacity: 120 },
  },
  registration: {
    capacity: 50, registered_count: 2, slots_remaining: 48, withdrawn_count: 1, cancelled_count: 1,
    opens_at: "2026-10-01T09:00:00", closes_at: "2026-11-15T18:00:00",
  },
  message: null,
};
const NOTHING_YET = {
  event: {
    id: 9, title: "Winter Networking Night", start_time: "2026-11-01T09:00:00",
    end_time: "2026-11-01T11:00:00", status: "submitted", expected_attendance: null, venue: null,
  },
  registration: {
    capacity: null, registered_count: 0, slots_remaining: null, withdrawn_count: 0,
    cancelled_count: 0, opens_at: null, closes_at: null,
  },
  message: "No one has registered for this event yet.",
};
const failure = (status, error, extra = {}) => Object.assign(new Error("fail"), {
  response: { status, data: { error, ...extra } },
});
const UNAVAILABLE = "The registration information for this event could not be loaded. Please try again.";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((succeed, fail) => { resolve = succeed; reject = fail; });
  return { promise, resolve, reject };
}

function renderPage(path = "/events/7/registration-overview") {
  render(
    <MemoryRouter initialEntries={[path]}
                  future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Link to="/events/9/registration-overview">Another event</Link>
      <Routes>
        <Route path="/events/:eventId/registration-overview" element={<RegistrationOverviewPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-72 an event's registration overview", () => {
  it("shows the figures needed for coordination", async () => {
    apiClient.get.mockResolvedValue({ data: OVERVIEW });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Alumni Mixer" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/registration-overview");
    for (const line of [
      "Starts: 2026-11-20 18:30",
      "Ends: 2026-11-20 21:00",
      "Status: Approved",
      "Expected attendance: 60",
      "Venue: Harbour Hall (holds 120)",
      "Registrations: 2",
      "Capacity: 50",
      "Remaining places: 48",
      "Withdrawn: 1",
      "Cancelled: 1",
      "Registration period: 2026-10-01 09:00 to 2026-11-15 18:00",
    ]) {
      expect(screen.getByText(line)).toBeTruthy();
    }
  });

  it("links back to the coordinator's events", async () => {
    apiClient.get.mockResolvedValue({ data: OVERVIEW });
    renderPage();

    const back = await screen.findByRole("link", { name: "Back to registrations for my managed events" });
    expect(back.getAttribute("href")).toBe("/events/managed/registrations");
  });

  it("says there are no registrations, with what isn't recorded or set up", async () => {
    apiClient.get.mockResolvedValue({ data: NOTHING_YET });
    renderPage("/events/9/registration-overview");

    expect(await screen.findByText("No one has registered for this event yet.")).toBeTruthy();
    for (const line of [
      "Expected attendance: Not recorded",
      "Venue: No venue yet",
      "Registrations: 0",
      "Capacity: Not set up",
      "Registration period: Not set up",
    ]) {
      expect(screen.getByText(line)).toBeTruthy();
    }
  });

  it("shows access denied with no event data and no Retry", async () => {
    const denied = "You can only view registration information for events assigned to you.";
    apiClient.get.mockRejectedValue(failure(403, denied));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(denied);
    expect(screen.queryByRole("heading", { name: "Alumni Mixer" })).toBeNull();
    expect(screen.queryByText(/Registrations:/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("shows a retryable error with no data, and retrying loads it", async () => {
    apiClient.get
      .mockRejectedValueOnce(failure(503, UNAVAILABLE, { retryable: true }))
      .mockResolvedValueOnce({ data: OVERVIEW });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(UNAVAILABLE);
    expect(screen.queryByText(/Registrations:/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Alumni Mixer" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The registration information could not be loaded. Check your connection and try again.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("clears the previous event's figures when the next event fails to load", async () => {
    apiClient.get
      .mockResolvedValueOnce({ data: OVERVIEW })
      .mockRejectedValueOnce(failure(503, UNAVAILABLE, { retryable: true }));
    const user = renderPage();

    await screen.findByRole("heading", { name: "Alumni Mixer" });
    await user.click(screen.getByRole("link", { name: "Another event" }));

    expect((await screen.findByRole("alert")).textContent).toContain(UNAVAILABLE);
    expect(apiClient.get).toHaveBeenLastCalledWith("/events/9/registration-overview");
    expect(screen.queryByRole("heading", { name: "Alumni Mixer" })).toBeNull();
    expect(screen.queryByText("Registrations: 2")).toBeNull();
  });

  // Event 7's reply arrives after event 9's, so it is stale. (A late success after event 9
  // failed is not a case: the error is shown ahead of any data.)
  it.each(["success", "failure"])(
    "keeps the current event when the earlier event's %s arrives late", async (lateOutcome) => {
      const earlierEvent = deferred();
      const currentEvent = deferred();
      apiClient.get
        .mockReturnValueOnce(earlierEvent.promise)
        .mockReturnValueOnce(currentEvent.promise);
      const user = renderPage();
      await user.click(screen.getByRole("link", { name: "Another event" }));
      expect(apiClient.get).toHaveBeenLastCalledWith("/events/9/registration-overview");

      await act(async () => currentEvent.resolve({ data: NOTHING_YET }));
      await act(async () => {
        if (lateOutcome === "success") earlierEvent.resolve({ data: OVERVIEW });
        else earlierEvent.reject(failure(503, UNAVAILABLE, { retryable: true }));
      });

      expect(screen.getByRole("heading", { name: "Winter Networking Night" })).toBeTruthy();
      expect(screen.getByText("Registrations: 0")).toBeTruthy();
      expect(screen.queryByRole("heading", { name: "Alumni Mixer" })).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();
    },
  );
});
