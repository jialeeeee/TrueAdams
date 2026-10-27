import { render, screen, waitFor, within } from "@testing-library/react";
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
    if (url === "/venues/bookings") return Promise.resolve({ data: { bookings: [], message: null } });
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

// SCRUM-69: TC-69-14/15/26, AC4; see
// docs/test-cases/SCRUM-69-reject-venue-booking.md and
// backend/tests/test_venue_booking_rejection.py. GREEN requires recovery from
// request rows; notification storage must not be the only saved-decision source.
describe("SCRUM-69 coordinator sees the saved venue rejection", () => {
  const REASON = "The required stage power cannot be provided for this arrangement.";
  const SAVED = {
    id: 11, status: "rejected", rejection_reason: REASON,
    event: { id: 7, title: "Harbour Lights Festival" },
    venue: { id: 3, name: "Aurora Ballroom" },
    start_time: "2027-03-12T16:00:00", end_time: "2027-03-12T22:30:00",
    decided_at: "2026-10-21T03:00:00", decided_by: { id: 9, email: "gus.venue@connectsphere.test" },
  };

  function mockSaved(bookings = [SAVED], failure = null, event = planning()) {
    apiClient.get.mockImplementation((url) => {
      if (url === "/events/7/planning") return Promise.resolve({ data: event });
      if (url === "/venues/") return Promise.resolve({ data: VENUES });
      if (url === "/venues/bookings") {
        return failure ? Promise.reject(failure) : Promise.resolve({ data: { bookings, message: null } });
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
  }

  it("shows the persisted rejection and reason when reopening the coordinator page", async () => {
    mockSaved();
    renderPage();

    expect(await screen.findByText(`Reason: ${REASON}`)).toBeTruthy();
    expect(screen.getByText("Status: Rejected")).toBeTruthy();
    expect(screen.getByText("Requested: 2027-03-12 16:00 to 2027-03-12 22:30")).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/venues/bookings", { params: { event_id: "7" } });
    expect(apiClient.get).not.toHaveBeenCalledWith("/notifications/");
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: /Harbour Lights Festival/ })).toBeTruthy();
    // Rejected venue request does not change the event to rejected or confirm a venue.
    expect(screen.queryByText(/Venue confirmed:/)).toBeNull();
  });

  it("keeps the saved rejection visible alongside a later confirmed venue", async () => {
    mockSaved([SAVED], null, planning({ venue: { id: 4, name: "Civic Hall", location: "12 Civic Road" } }));
    renderPage();

    expect(await screen.findByText(`Reason: ${REASON}`)).toBeTruthy();
    expect(screen.getByRole("region", { name: "Previous venue decisions" })).toBeTruthy();
    expect(screen.getByText("Venue confirmed: Civic Hall, 12 Civic Road")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Submit request" })).toBeNull();
  });

  it("reports saved rejection load failure and retries without losing request details", async () => {
    const message = "Saved venue outcomes could not be loaded. Please try again.";
    mockSaved([], httpFailure(503, { error: message, retryable: true }));
    const user = renderPage();
    await screen.findByRole("heading", { name: /request a venue/i });
    await user.clear(field("Venue requirements"));
    await user.type(field("Venue requirements"), "Keep my unsent requirements.");

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    mockSaved();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(`Reason: ${REASON}`)).toBeTruthy();
    expect(field("Venue requirements").value).toBe("Keep my unsent requirements.");
    await waitFor(() => expect(screen.queryByText(message)).toBeNull());
  });
});

// SCRUM-94: TC-94-07, 08, 09 and 21 in docs/test-cases/SCRUM-94-cancel-venue-booking.md.
// The API contract mirrors backend/tests/test_venue_booking_cancellation.py.
describe("SCRUM-94 the coordinator cancels a venue booking", () => {
  const CIVIC = { id: 4, name: "Civic Hall", location: "12 Civic Road" };
  const AURORA = { id: 3, name: "Aurora Ballroom", location: "Level 3, Marina Tower" };
  const booking = (id, status, venue, start, end, extra = {}) => ({
    id, status, venue, event: { id: 7, title: "Harbour Lights Festival" },
    start_time: start, end_time: end, rejection_reason: null, decided_at: null, decided_by: null,
    ...extra,
  });
  const P1 = booking(11, "pending", AURORA, "2027-03-12T16:00:00", "2027-03-12T22:30:00");
  const T1 = booking(12, "tentative", AURORA, "2027-03-13T09:00:00", "2027-03-13T12:00:00");
  const C1 = booking(13, "confirmed", CIVIC, "2027-03-12T16:00:00", "2027-03-12T22:30:00");
  const R1 = booking(14, "rejected", CIVIC, "2027-03-11T10:00:00", "2027-03-11T12:00:00",
    { rejection_reason: "No stage power." });
  const X1 = booking(15, "cancelled", { id: 5, name: "Bayfront Pavilion", location: null },
    "2027-03-11T13:00:00", "2027-03-11T15:00:00");
  const CANCELLED_MESSAGE =
    "You cancelled the booking of Civic Hall for Harbour Lights Festival. The venue is free again for that time, and Venue Staff have been notified.";

  function mockBookings(bookings, event = planning({ venue: CIVIC })) {
    apiClient.get.mockImplementation((url) => {
      if (url === "/events/7/planning") return Promise.resolve({ data: event });
      if (url === "/venues/") return Promise.resolve({ data: VENUES });
      if (url === "/venues/bookings") return Promise.resolve({ data: { bookings, message: null } });
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
  }

  async function renderBookings(bookings = [P1, T1, C1, R1, X1]) {
    mockBookings(bookings);
    const user = renderPage();
    await screen.findByRole("region", { name: "Venue bookings" });
    return user;
  }

  const bookingItem = (text) =>
    within(screen.getByRole("region", { name: "Venue bookings" }))
      .getAllByRole("listitem").find((item) => item.textContent.includes(text));
  const civicItem = () => bookingItem("Civic Hall, 2027-03-12 16:00 to 2027-03-12 22:30");

  // TC-94-07 · AC2
  it("lists the event's bookings and offers to cancel only the live ones", async () => {
    await renderBookings();

    const list = within(screen.getByRole("region", { name: "Venue bookings" }));
    expect(list.getAllByRole("listitem")).toHaveLength(4);
    for (const [text, status] of [
      ["Aurora Ballroom, 2027-03-12 16:00 to 2027-03-12 22:30", "Pending"],
      ["Aurora Ballroom, 2027-03-13 09:00 to 2027-03-13 12:00", "Tentative"],
      ["Civic Hall, 2027-03-12 16:00 to 2027-03-12 22:30", "Confirmed"],
    ]) {
      const item = bookingItem(text);
      expect(item.textContent).toContain(`Status: ${status}`);
      expect(within(item).getByRole("button", { name: "Cancel booking" })).toBeTruthy();
    }
    const cancelled = bookingItem("Bayfront Pavilion");
    expect(cancelled.textContent).toContain("Status: Cancelled");
    expect(within(cancelled).queryByRole("button", { name: "Cancel booking" })).toBeNull();
    // The rejection stays with its reason under the previous decisions only (SCRUM-69).
    expect(list.queryByText(/No stage power/)).toBeNull();
    expect(screen.getByText("Reason: No stage power.")).toBeTruthy();
  });

  // TC-94-08 · AC2
  it("asks for confirmation and sends nothing when the coordinator keeps the booking", async () => {
    const user = await renderBookings();

    await user.click(within(civicItem()).getByRole("button", { name: "Cancel booking" }));
    const confirmation = screen.getByRole("group", { name: "Confirm cancellation" });
    expect(confirmation.textContent).toContain("Civic Hall");
    expect(confirmation.textContent).toContain("2027-03-12 16:00 to 2027-03-12 22:30");
    expect(confirmation.textContent).toContain("released");
    await user.click(within(confirmation).getByRole("button", { name: "Keep booking" }));

    expect(screen.queryByRole("group", { name: "Confirm cancellation" })).toBeNull();
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(civicItem().textContent).toContain("Status: Confirmed");
  });

  // TC-94-09 · AC2, AC3
  it("cancels the booking on confirmation and shows it as cancelled", async () => {
    const user = await renderBookings();
    const cancelledC1 = { ...C1, status: "cancelled" };
    apiClient.post.mockResolvedValue({
      data: { message: CANCELLED_MESSAGE, booking: cancelledC1,
        notification: { in_app: true, email_queued: true } },
    });

    await user.click(within(civicItem()).getByRole("button", { name: "Cancel booking" }));
    // The server has cancelled it: the page reloads the event (no venue now) and its bookings.
    mockBookings([P1, T1, cancelledC1, R1, X1], planning());
    await user.click(screen.getByRole("button", { name: "Yes, cancel booking" }));

    expect((await screen.findByRole("status")).textContent).toBe(CANCELLED_MESSAGE);
    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(apiClient.post).toHaveBeenCalledWith("/venues/bookings/13/cancel");
    await waitFor(() => expect(civicItem().textContent).toContain("Status: Cancelled"));
    expect(within(civicItem()).queryByRole("button", { name: "Cancel booking" })).toBeNull();
    expect(screen.queryByText(/Venue confirmed:/)).toBeNull();
    expect(screen.queryByRole("group", { name: "Confirm cancellation" })).toBeNull();
  });

  // TC-94-21 · AC6
  it("shows the error and keeps the booking when cancelling fails", async () => {
    const message = "The cancellation was not saved, so the booking is unchanged. Please try again.";
    const user = await renderBookings();
    apiClient.post.mockRejectedValue(httpFailure(503, { error: message, retryable: true }));

    await user.click(within(civicItem()).getByRole("button", { name: "Cancel booking" }));
    await user.click(screen.getByRole("button", { name: "Yes, cancel booking" }));

    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(civicItem().textContent).toContain("Status: Confirmed");
    expect(within(civicItem()).getByRole("button", { name: "Cancel booking" })).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
