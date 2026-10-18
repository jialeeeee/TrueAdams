import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EventRegistrationPage from "./EventRegistrationPage.jsx";

// Frontend case TC-45-23 in docs/test-cases/SCRUM-45-register-for-event.md (reopened
// 18 Oct 2026: no waiting list, and a full event says "This event is full.").
// The API itself is covered by backend/tests/test_event_registration.py;
// these check what the attendee sees. Responses mirror that API's contract.

vi.mock("../api/client.js", () => ({ default: { post: vi.fn() } }));

function registered(status, message, extra = {}) {
  return {
    data: {
      message,
      registration: { id: 31, event_id: 7, status, registered_at: "2026-11-01T04:00:00" },
      ...extra,
    },
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
    <MemoryRouter initialEntries={["/events/7/register"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="/events/:eventId/register" element={<EventRegistrationPage />} /></Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const registerButton = () => screen.getByRole("button", { name: /^register/i });

beforeEach(() => {
  apiClient.post.mockReset();
});

describe("SCRUM-45 register for an event", () => {
  it("offers to register for the event", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /register/i })).toBeTruthy();
    expect(registerButton().disabled).toBe(false);
  });

  it("registers and shows the confirmation and status", async () => {
    apiClient.post.mockResolvedValue(registered("registered", "You're registered for Harbour Lights Festival."));
    const user = renderPage();

    await user.click(registerButton());

    expect(apiClient.post).toHaveBeenCalledWith("/registrations/", { event_id: 7 });
    expect((await screen.findByRole("status")).textContent).toContain("You're registered for Harbour Lights Festival.");
    expect(screen.getByText("Status: Registered")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^register/i })).toBeNull();
  });

  it("shows the existing status when already registered", async () => {
    apiClient.post.mockResolvedValue(registered(
      "registered",
      "You're already registered for Harbour Lights Festival. Your status is Registered.",
      { already_registered: true },
    ));
    const user = renderPage();

    await user.click(registerButton());

    expect((await screen.findByRole("status")).textContent).toContain("already registered");
    expect(screen.getByText("Status: Registered")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^register/i })).toBeNull();
  });

  // Must match BLOCKED_MESSAGES in backend/app/registrations/routes.py.
  it.each([
    ["closed", "Registration for this event is closed."],
    ["full", "This event is full."],
    ["disabled", "Registration has not been enabled for this event."],
  ])("explains why registration is blocked (%s)", async (reason, error) => {
    apiClient.post.mockRejectedValue(httpFailure(409, { error, reason }));
    const user = renderPage();

    await user.click(registerButton());

    expect((await screen.findByRole("alert")).textContent).toContain(error);
    expect(screen.queryByText(/^Status:/)).toBeNull();
  });

  it("shows why saving failed and lets the attendee try again", async () => {
    apiClient.post
      .mockRejectedValueOnce(httpFailure(503, { error: "Your registration was not saved. Please try again.", retryable: true }))
      .mockResolvedValueOnce(registered("registered", "You're registered for Harbour Lights Festival."));
    const user = renderPage();

    await user.click(registerButton());

    expect((await screen.findByRole("alert")).textContent).toContain("Your registration was not saved. Please try again.");
    expect(screen.queryByText(/^Status:/)).toBeNull();
    expect(registerButton().disabled).toBe(false);

    await user.click(registerButton());
    expect(await screen.findByText("Status: Registered")).toBeTruthy();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.post.mockRejectedValue(new Error("Network Error"));
    const user = renderPage();

    await user.click(registerButton());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Your registration was not saved. Check your connection and try again.",
    );
  });

  it("sends one request when Register is clicked twice", async () => {
    apiClient.post.mockReturnValue(new Promise(() => {}));
    const user = renderPage();

    await user.click(registerButton());
    await user.click(registerButton());

    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(registerButton().disabled).toBe(true);
  });
});
