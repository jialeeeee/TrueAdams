import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenueBookingRequestPage from "./VenueBookingRequestPage.jsx";

// Frontend cases TC-39-11, 15, 19 and 28 in
// docs/test-cases/SCRUM-39-venue-booking-request.md. The API contract mirrors
// backend/tests/test_venue_booking_request.py.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const URL = "/events/7/venue-request";
const REQUIREMENTS = "Open-air waterfront space for 250";

function planning(overrides = {}) {
  return {
    id: 7, title: "Harbour Lights Festival", status: "approved",
    start_time: "2027-03-12T17:00:00", end_time: "2027-03-12T22:00:00",
    expected_attendance: 250, venue_requirements: REQUIREMENTS, venue: null,
    ...overrides,
  };
}

const VENUES = {
  venues: [
    { id: 3, name: "Aurora Ballroom", location: "Level 3, Marina Tower", capacity: 400, is_available: true },
    { id: 4, name: "Civic Hall", location: "12 Civic Road", capacity: 80, is_available: true },
  ],
  message: null,
};

function created(body) {
  return {
    status: 201,
    data: {
      message: "Your request to book Aurora Ballroom for Harbour Lights Festival has been sent to Venue Staff. It stays pending until they decide.",
      booking: {
        id: 11, status: "pending",
        event: { id: 7, title: "Harbour Lights Festival", expected_attendance: 250 },
        venue: { id: 3, name: "Aurora Ballroom", location: "Level 3, Marina Tower" },
        start_time: `${body.start_time}:00`, end_time: `${body.end_time}:00`,
        venue_requirements: body.venue_requirements,
        requested_by: { id: 2, email: "alice.coordinator@connectsphere.test" },
        requested_at: "2026-10-14T03:00:00",
      },
    },
  };
}

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function mockLoad(event = planning()) {
  apiClient.get.mockImplementation((url) => {
    if (url === "/events/7/planning") return Promise.resolve({ data: event });
    if (url === "/venues/") return Promise.resolve({ data: VENUES });
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={[URL]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="/events/:eventId/venue-request" element={<VenueBookingRequestPage />} /></Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

async function renderLoaded(event) {
  mockLoad(event);
  const user = renderPage();
  await screen.findByRole("heading", { name: /request a venue/i });
  return user;
}

const field = (label) => screen.getByLabelText(label);
const submitButton = () => screen.getByRole("button", { name: "Submit request" });

async function fillValid(user) {
  await user.selectOptions(field("Venue"), "3");
  await user.clear(field("Start"));
  await user.type(field("Start"), "2027-03-12T16:00");
  await user.clear(field("End"));
  await user.type(field("End"), "2027-03-12T22:30");
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("SCRUM-39 submit a venue booking request", () => {
  // TC-39-11 · AC1, AC2
  it("prefills the times and requirements from the event and lists the venues", async () => {
    await renderLoaded();

    expect(apiClient.get).toHaveBeenCalledWith("/events/7/planning");
    expect(apiClient.get).toHaveBeenCalledWith("/venues/");
    expect(screen.getByRole("heading", { name: /Harbour Lights Festival/ })).toBeTruthy();
    expect(field("Start").value).toBe("2027-03-12T17:00");
    expect(field("End").value).toBe("2027-03-12T22:00");
    expect(field("Venue requirements").value).toBe(REQUIREMENTS);
    expect(field("Venue").value).toBe("");
    expect(screen.getByRole("option", { name: /Aurora Ballroom/ })).toBeTruthy();
    expect(screen.getByRole("option", { name: /Civic Hall/ })).toBeTruthy();
  });

  // TC-39-19 · AC1, AC2, AC4
  it("submits the edited request and confirms it with a Pending summary", async () => {
    const user = await renderLoaded();
    await fillValid(user);
    await user.clear(field("Venue requirements"));
    await user.type(field("Venue requirements"), "Waterfront space, stage power");
    const body = {
      event_id: 7, venue_id: 3, start_time: "2027-03-12T16:00", end_time: "2027-03-12T22:30",
      venue_requirements: "Waterfront space, stage power",
    };
    apiClient.post.mockResolvedValue(created(body));

    await user.click(submitButton());

    // SCRUM-84: setup and turnaround default to none.
    expect(apiClient.post).toHaveBeenCalledWith(
      "/venues/bookings", { ...body, setup_minutes: "0", turnaround_minutes: "0" });
    expect((await screen.findByRole("status")).textContent).toContain("sent to Venue Staff");
    expect(screen.getByText("Venue: Aurora Ballroom")).toBeTruthy();
    expect(screen.getByText("Requested: 2027-03-12 16:00 to 2027-03-12 22:30")).toBeTruthy();
    expect(screen.getByText("Status: Pending")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Submit request" })).toBeNull();
  });

  // TC-39-15 · AC3
  it("identifies missing information without sending the request", async () => {
    const user = await renderLoaded();
    await user.clear(field("Start"));
    await user.clear(field("Venue requirements"));
    await user.type(field("Venue requirements"), "   ");

    await user.click(submitButton());

    expect(apiClient.post).not.toHaveBeenCalled();
    expect(screen.getByText("Choose a venue.")).toBeTruthy();
    expect(screen.getByText("Enter the start date and time.")).toBeTruthy();
    expect(screen.getByText("Enter the venue requirements.")).toBeTruthy();
    expect(field("End").value).toBe("2027-03-12T22:00");
  });

  // TC-39-15 · AC3
  it("shows each problem the server identifies next to its field and keeps the inputs", async () => {
    apiClient.post.mockRejectedValue(httpFailure(400, {
      error: "Some details are missing or invalid. Please correct them and try again.",
      fields: { end_time: "The end must be after the start.", start_time: "The start must not be in the past." },
    }));
    const user = await renderLoaded();
    await fillValid(user);

    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain("missing or invalid");
    expect(screen.getByText("The end must be after the start.")).toBeTruthy();
    expect(screen.getByText("The start must not be in the past.")).toBeTruthy();
    expect(field("Start").value).toBe("2027-03-12T16:00");
    expect(field("Venue").value).toBe("3");
  });

  // TC-39-28 · AC6
  it.each([
    ["server error", httpFailure(503, { error: "Your venue request was not sent. Please try again.", retryable: true }), "not sent"],
    ["already pending", httpFailure(409, { error: "A venue request for this event is already pending." }), "already pending"],
    ["not allowed", httpFailure(403, { error: "Only the event's assigned coordinator can request a venue for it." }), "assigned coordinator"],
    ["no network", new Error("Network Error"), "Check your connection and try again"],
  ])("keeps the entered information when submission fails (%s), and the retry succeeds", async (_label, failure, message) => {
    const user = await renderLoaded();
    await fillValid(user);
    const body = {
      event_id: 7, venue_id: 3, start_time: "2027-03-12T16:00", end_time: "2027-03-12T22:30",
      venue_requirements: REQUIREMENTS,
    };
    apiClient.post.mockRejectedValueOnce(failure).mockResolvedValueOnce(created(body));

    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(screen.queryByRole("status")).toBeNull();
    expect(field("Venue").value).toBe("3");
    expect(field("Start").value).toBe("2027-03-12T16:00");
    expect(field("End").value).toBe("2027-03-12T22:30");
    expect(field("Venue requirements").value).toBe(REQUIREMENTS);
    expect(submitButton().disabled).toBe(false);

    await user.click(submitButton());
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("explains that only approved events can have a venue requested", async () => {
    await renderLoaded(planning({ status: "submitted" }));

    expect(screen.getByText(/only be requested for an approved event/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Submit request" })).toBeNull();
  });

  it("shows a retryable error when the event or venues cannot be loaded", async () => {
    apiClient.get.mockRejectedValueOnce(httpFailure(503, {
      error: "The event's information could not be loaded. Please try again.", retryable: true,
    }));
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    mockLoad();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: /request a venue/i })).toBeTruthy();
  });
});

// SCRUM-40: once Venue Staff approve a request, the event has a confirmed venue.
// Frontend case TC-40-24 in docs/test-cases/SCRUM-40-approve-venue-booking.md.
describe("SCRUM-40 the coordinator sees the confirmed venue", () => {
  it("shows the confirmed venue instead of offering a new request", async () => {
    await renderLoaded(planning({ venue: { id: 3, name: "Aurora Ballroom", location: "Level 3, Marina Tower" } }));

    expect(screen.getByText("Venue confirmed: Aurora Ballroom, Level 3, Marina Tower")).toBeTruthy();
    expect(screen.getByText(/change request/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Submit request" })).toBeNull();
    expect(screen.queryByLabelText("Venue")).toBeNull();
  });

  it("shows just the venue's name when its location is not recorded", async () => {
    await renderLoaded(planning({ venue: { id: 3, name: "Aurora Ballroom", location: null } }));

    expect(screen.getByText("Venue confirmed: Aurora Ballroom")).toBeTruthy();
  });
});
