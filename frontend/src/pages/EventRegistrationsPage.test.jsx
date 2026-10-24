import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EventRegistrationsPage from "./EventRegistrationsPage.jsx";

// Frontend cases TC-54-17 to TC-54-20 in
// docs/test-cases/SCRUM-54-view-registration-information.md. The API itself is covered by
// backend/tests/test_organiser_registrations.py; responses mirror its contract.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

// Registration times are naive UTC audit timestamps, shown in local time (A6).
const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

const EVENT = {
  id: 7, title: "Alumni Mixer", start_time: "2026-11-20T18:30:00", status: "approved",
  registration: { capacity: 50, registered_count: 2, slots_remaining: 48 },
};
const REGISTRATIONS = [
  { id: 11, attendee: { id: 21, email: "att1@test.invalid" },
    registered_at: "2026-10-01T03:00:00", status: "registered" },
  { id: 12, attendee: { id: 22, email: "farah@test.invalid" },
    registered_at: "2026-10-02T01:00:00", status: "registered" },
  { id: 13, attendee: { id: 23, email: "att2@test.invalid" },
    registered_at: "2026-10-03T05:30:00", status: "withdrawn" },
];
const loaded = (registrations = REGISTRATIONS, message = null, event = EVENT) => ({
  data: { event, registrations, message },
});
const failure = (status, error, extra = {}) => Object.assign(new Error("fail"), {
  response: { status, data: { error, ...extra } },
});
const UNAVAILABLE = "The registration information for this event could not be loaded. Please try again.";

function renderPage(path = "/events/7/registrations") {
  render(
    <MemoryRouter initialEntries={[path]}
                  future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Link to="/events/9/registrations">Another event</Link>
      <Routes>
        <Route path="/events/:eventId/registrations" element={<EventRegistrationsPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-54 an event's registrations", () => {
  it("shows the event's summary and each registration", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Alumni Mixer" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/registrations");
    expect(screen.getByText("Proposed date: 2026-11-20 18:30")).toBeTruthy();
    expect(screen.getByText("Status: Approved")).toBeTruthy();
    expect(screen.getByText("Registrations: 2")).toBeTruthy();
    expect(screen.getByText("Capacity: 50")).toBeTruthy();
    expect(screen.getByText("Remaining places: 48")).toBeTruthy();

    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent))
      .toEqual(["Attendee", "Registered on", "Status"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell").map((td) => td.textContent)))
      .toEqual([
        ["att1@test.invalid", localTime("2026-10-01T03:00:00"), "Registered"],
        ["farah@test.invalid", localTime("2026-10-02T01:00:00"), "Registered"],
        ["att2@test.invalid", localTime("2026-10-03T05:30:00"), "Withdrawn"],
      ]);
  });

  it("links back to the organiser's events", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    const back = await screen.findByRole("link", { name: "Back to registrations for my events" });
    expect(back.getAttribute("href")).toBe("/events/organised");
  });

  it("says there are no registrations instead of an empty table", async () => {
    apiClient.get.mockResolvedValue(loaded([], "No one has registered for this event yet.", {
      ...EVENT, registration: { capacity: 50, registered_count: 0, slots_remaining: 50 },
    }));
    renderPage();

    expect(await screen.findByText("No one has registered for this event yet.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Alumni Mixer" })).toBeTruthy();
    expect(screen.getByText("Registrations: 0")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows access denied with no event data and no Retry", async () => {
    apiClient.get.mockRejectedValue(failure(
      403, "You can only view registration information for events you organise.",
    ));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "You can only view registration information for events you organise.",
    );
    expect(screen.queryByRole("heading", { name: "Alumni Mixer" })).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("shows a retryable error with no data, and retrying loads it", async () => {
    apiClient.get
      .mockRejectedValueOnce(failure(503, UNAVAILABLE, { retryable: true }))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(UNAVAILABLE);
    expect(screen.queryByRole("table")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Alumni Mixer" })).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
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

  it("clears the previous event's data when the next event fails to load", async () => {
    apiClient.get
      .mockResolvedValueOnce(loaded())
      .mockRejectedValueOnce(failure(503, UNAVAILABLE, { retryable: true }));
    const user = renderPage();

    await screen.findByRole("heading", { name: "Alumni Mixer" });
    await user.click(screen.getByRole("link", { name: "Another event" }));

    expect((await screen.findByRole("alert")).textContent).toContain(UNAVAILABLE);
    expect(apiClient.get).toHaveBeenLastCalledWith("/events/9/registrations");
    expect(screen.queryByRole("heading", { name: "Alumni Mixer" })).toBeNull();
    expect(screen.queryByText("att1@test.invalid")).toBeNull();
  });
});
