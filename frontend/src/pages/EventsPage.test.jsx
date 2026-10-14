import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EventsPage from "./EventsPage.jsx";

// Frontend cases TC-74-01, TC-74-16 and TC-74-17 in
// docs/test-cases/SCRUM-74-view-event-details.md. The API itself is covered by
// backend/tests/test_event_details.py; these check what the user sees. Responses
// mirror that API's contract: GET /events/ -> { events: [item], message }.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const CHEM = {
  id: 7,
  title: "Chem Open House",
  start_time: "2026-11-20T10:00:00",
  end_time: "2026-11-20T12:00:00",
  registration_state: "open",
};
const FAIR = {
  id: 8,
  title: "Closed Fair",
  start_time: "2026-11-25T23:30:00",
  end_time: "2026-11-26T01:00:00",
  registration_state: "closed",
};

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true,
    response: { status, data },
  });
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/" element={<EventsPage />} />
        <Route path="/login" element={<p>Sign-in page</p>} />
        <Route path="/events/:eventId" element={<p>Event page</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-74 events list", () => {
  it("lists each published event as a link to its details", async () => {
    apiClient.get.mockResolvedValue({ data: { events: [CHEM, FAIR], message: null } });
    const user = renderPage();

    const link = await screen.findByRole("link", { name: "Chem Open House" });

    expect(apiClient.get).toHaveBeenCalledWith("/events/");
    expect(link.getAttribute("href")).toBe("/events/7");
    expect(screen.getByRole("link", { name: "Closed Fair" }).getAttribute("href")).toBe("/events/8");
    await user.click(link);
    expect(await screen.findByText("Event page")).toBeTruthy();
  });

  it("shows when each event starts and whether registration is open, in Singapore time", async () => {
    apiClient.get.mockResolvedValue({ data: { events: [CHEM, FAIR], message: null } });
    renderPage();

    await screen.findByRole("link", { name: "Chem Open House" });

    // dd/mm/yyyy and SGT, as recorded: the time is never shifted by the browser's zone,
    // so 23:30 stays on 25/11/2026.
    expect(screen.getByText("Starts: 20/11/2026 10:00 SGT")).toBeTruthy();
    expect(screen.getByText("Starts: 25/11/2026 23:30 SGT")).toBeTruthy();
    expect(screen.getByText("Registration: Open")).toBeTruthy();
    expect(screen.getByText("Registration: Closed")).toBeTruthy();
  });

  it("shows the server's message when there are no events", async () => {
    apiClient.get.mockResolvedValue({ data: { events: [], message: "There are no upcoming events." } });
    renderPage();

    expect(await screen.findByText("There are no upcoming events.")).toBeTruthy();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("shows why the list could not be loaded and lets the user try again", async () => {
    apiClient.get
      .mockRejectedValueOnce(httpFailure(503, { error: "Events could not be loaded. Please try again.", retryable: true }))
      .mockResolvedValueOnce({ data: { events: [CHEM], message: null } });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("Events could not be loaded. Please try again.");
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("link", { name: "Chem Open House" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Events could not be loaded. Check your connection and try again.",
    );
  });

  it("sends a signed-out user to the sign-in page and shows no events", async () => {
    apiClient.get.mockRejectedValue(httpFailure(401, { msg: "Missing Authorization Header" }));
    renderPage();

    expect(await screen.findByText("Sign-in page")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Events" })).toBeNull();
  });
});
