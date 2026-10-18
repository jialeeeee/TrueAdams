import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EventDetailsPage from "./EventDetailsPage.jsx";

// Frontend cases TC-74-02 to TC-74-17 in docs/test-cases/SCRUM-74-view-event-details.md,
// and the "Request reassignment" entry point of TC-61-01 to TC-61-03 in
// docs/test-cases/SCRUM-61-reassignment-request.md. The API itself is covered by
// backend/tests/test_event_details.py; these check what the user sees. Responses
// mirror that API's contract: GET /events/<id> -> { event }.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const EVENT = {
  id: 7,
  title: "Chem Open House",
  description: "Open house for O-Level chemistry",
  status: "approved",
  start_time: "2026-11-20T10:00:00",
  end_time: "2026-11-20T12:00:00",
  venue: { name: "Seminar Room 2", location: "SMU Library, 70 Stamford Rd" },
  registration: {
    state: "open",
    opens_at: "2026-11-01T00:00:00",
    closes_at: "2026-11-15T00:00:00",
    capacity: 5,
    registered_count: 2,
    slots_remaining: 3,
  },
  my_registration: null,
  can_register: true,
  register_blocked_reason: null,
  can_request_reassignment: false,
};

function withEvent(changes = {}, registration = {}) {
  return {
    data: { event: { ...EVENT, ...changes, registration: { ...EVENT.registration, ...registration } } },
  };
}

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true,
    response: { status, data },
  });
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId" element={<EventDetailsPage />} />
        <Route path="/events/:eventId/register" element={<p>Register page</p>} />
        <Route path="/events/:eventId/reassign" element={<p>Reassign page</p>} />
        <Route path="/login" element={<p>Sign-in page</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-74 event details", () => {
  it("shows every required field", async () => {
    apiClient.get.mockResolvedValue(withEvent());
    renderPage();

    expect(await screen.findByRole("heading", { level: 1, name: "Chem Open House" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7");
    for (const text of [
      "Description: Open house for O-Level chemistry",
      "Starts: 20/11/2026 10:00 SGT",
      "Ends: 20/11/2026 12:00 SGT",
      "Venue: Seminar Room 2",
      "Location: SMU Library, 70 Stamford Rd",
      "Registration opens: 01/11/2026 00:00 SGT",
      "Registration closes: 15/11/2026 00:00 SGT",
      "Capacity: 5",
      "Slots remaining: 3",
      "Registration: Open",
    ]) {
      expect(screen.getByText(text)).toBeTruthy();
    }
  });

  it("shows times as recorded in Singapore time, whatever the browser's time zone", async () => {
    apiClient.get.mockResolvedValue(withEvent({
      start_time: "2026-11-20T23:30:00",
      end_time: "2026-11-21T01:00:00",
    }));
    renderPage();

    expect(await screen.findByText("Starts: 20/11/2026 23:30 SGT")).toBeTruthy();
    expect(screen.getByText("Ends: 21/11/2026 01:00 SGT")).toBeTruthy();
  });

  it("shows 'Not provided' for empty optional fields, never blank or null", async () => {
    apiClient.get.mockResolvedValue(withEvent(
      { description: null, venue: null },
      { capacity: null, slots_remaining: null },
    ));
    renderPage();

    await screen.findByRole("heading", { level: 1, name: "Chem Open House" });

    for (const label of ["Description", "Venue", "Location", "Capacity", "Slots remaining"]) {
      expect(screen.getByText(`${label}: Not provided`)).toBeTruthy();
    }
    expect(document.body.textContent).not.toMatch(/null|undefined/);
  });

  it("shows 'Not provided' for a venue without a recorded location", async () => {
    apiClient.get.mockResolvedValue(withEvent({ venue: { name: "Pop-up Tent", location: null } }));
    renderPage();

    expect(await screen.findByText("Venue: Pop-up Tent")).toBeTruthy();
    expect(screen.getByText("Location: Not provided")).toBeTruthy();
  });

  it.each([
    ["open", "Registration: Open"],
    ["closed", "Registration: Closed"],
    ["full", "Registration: Full"],
  ])("shows whether registration is %s", async (state, text) => {
    apiClient.get.mockResolvedValue(withEvent({}, { state }));
    renderPage();

    expect(await screen.findByText(text)).toBeTruthy();
  });

  it("shows the event's status to someone viewing an unpublished event, and not otherwise", async () => {
    apiClient.get.mockResolvedValueOnce(withEvent({ status: "draft", can_register: false, register_blocked_reason: "not_attendee" }));
    renderPage();
    expect(await screen.findByText("Status: Draft")).toBeTruthy();
  });

  it("does not show a status line for a published event", async () => {
    apiClient.get.mockResolvedValue(withEvent());
    renderPage();

    await screen.findByRole("heading", { level: 1, name: "Chem Open House" });
    expect(screen.queryByText(/^Status:/)).toBeNull();
  });

  it("shows the attendee's own registration status", async () => {
    apiClient.get.mockResolvedValue(withEvent({
      my_registration: { id: 31, status: "registered" },
      can_register: false,
      register_blocked_reason: "already_registered",
    }));
    renderPage();

    expect(await screen.findByText("Your registration: Registered")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Register" })).toBeNull();
  });

  it("shows no registration status to someone who is not registered", async () => {
    apiClient.get.mockResolvedValue(withEvent());
    renderPage();

    await screen.findByRole("heading", { level: 1, name: "Chem Open House" });
    expect(screen.queryByText(/^Your registration:/)).toBeNull();
  });

  it("offers Register only when registration is possible", async () => {
    apiClient.get.mockResolvedValue(withEvent());
    const user = renderPage();

    const register = await screen.findByRole("link", { name: "Register" });
    expect(register.getAttribute("href")).toBe("/events/7/register");
    await user.click(register);
    expect(await screen.findByText("Register page")).toBeTruthy();
  });

  it.each([
    ["already_registered", { my_registration: { id: 31, status: "registered" } }, {}, "Your registration: Registered"],
    ["full", {}, { state: "full", slots_remaining: 0 }, "Registration: Full"],
    ["closed", {}, { state: "closed" }, "Registration: Closed"],
  ])("replaces Register with the reason (%s)", async (reason, event, registration, text) => {
    apiClient.get.mockResolvedValue(withEvent(
      { ...event, can_register: false, register_blocked_reason: reason },
      registration,
    ));
    renderPage();

    expect(await screen.findByText(text)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Register" })).toBeNull();
    expect(screen.queryByRole("button", { name: /register/i })).toBeNull();
  });
});

describe("SCRUM-61 entry point on the event page", () => {
  it("offers Request reassignment to the event's main coordinator", async () => {
    apiClient.get.mockResolvedValue(withEvent({ can_request_reassignment: true, can_register: false, register_blocked_reason: "not_attendee" }));
    const user = renderPage();

    const link = await screen.findByRole("link", { name: "Request reassignment" });
    expect(link.getAttribute("href")).toBe("/events/7/reassign");
    await user.click(link);
    expect(await screen.findByText("Reassign page")).toBeTruthy();
  });

  it("does not offer Request reassignment to anyone else", async () => {
    apiClient.get.mockResolvedValue(withEvent({ can_request_reassignment: false }));
    renderPage();

    await screen.findByRole("heading", { level: 1, name: "Chem Open House" });
    expect(screen.queryByRole("link", { name: /request reassignment/i })).toBeNull();
  });
});

describe("SCRUM-74 when the event cannot be shown", () => {
  it("shows a friendly page for an event that is not found, with no details", async () => {
    apiClient.get.mockRejectedValue(httpFailure(404, { error: "Event not found." }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("Event not found.");
    expect(screen.queryByText(/^Starts:/)).toBeNull();
    expect(screen.queryByRole("link", { name: "Register" })).toBeNull();
    expect(screen.getByRole("link", { name: "Back to events" }).getAttribute("href")).toBe("/");
  });

  it("shows the same page when the server sends no message", async () => {
    apiClient.get.mockRejectedValue(httpFailure(404, "<html>Not Found</html>"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("Event not found.");
    expect(document.body.textContent).not.toContain("<html>");
  });

  it("shows why the event could not be loaded and lets the user try again", async () => {
    apiClient.get
      .mockRejectedValueOnce(httpFailure(503, { error: "The event could not be loaded. Please try again.", retryable: true }))
      .mockResolvedValueOnce(withEvent());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("The event could not be loaded. Please try again.");
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Chem Open House" })).toBeTruthy();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The event could not be loaded. Check your connection and try again.",
    );
  });

  it("sends a signed-out user to the sign-in page and shows no details", async () => {
    apiClient.get.mockRejectedValue(httpFailure(401, { msg: "Missing Authorization Header" }));
    renderPage();

    expect(await screen.findByText("Sign-in page")).toBeTruthy();
    expect(screen.queryByText("Chem Open House")).toBeNull();
  });
});
