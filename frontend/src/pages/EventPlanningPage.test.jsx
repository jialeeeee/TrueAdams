import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EventPlanningPage from "./EventPlanningPage.jsx";

// Frontend cases TC-62-14 to TC-62-16 in
// docs/test-cases/SCRUM-62-managed-events-list.md. The API is SCRUM-34's, covered by
// backend/tests/test_event_planning_info.py; responses mirror its contract.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

const ALICE = { id: 2, email: "alice.coordinator@connectsphere.test" };
const DANA = { id: 5, email: "dana.organiser@connectsphere.test" };

// Every planning field recorded (EP-SEED E1).
const FESTIVAL = {
  id: 1,
  title: "Harbour Lights Festival",
  purpose: "Celebrate the harbour's reopening with the local community.",
  description: "Waterfront lantern festival with live music and food stalls.",
  status: "submitted",
  start_time: "2026-12-12T17:00:00",
  end_time: "2026-12-12T22:00:00",
  venue: { id: 9, name: "Aurora Ballroom", location: "Level 3, Marina Tower, 10 Bayfront Ave" },
  expected_attendance: 350,
  venue_requirements: "Waterfront access and space for 20 food stalls.",
  accessibility_needs: "Step-free routes and a quiet area.",
  equipment_requirements: "Stage lighting and a PA system.",
  registration_required: true,
  organiser: DANA,
  coordinator: ALICE,
  coordinator_assigned_at: "2026-09-10T09:30:00",
  created_at: "2026-09-05T14:00:00",
  not_recorded: [],
};

// Only the title, status, dates, organiser and coordinator recorded (EP-SEED E2),
// with registration recorded as not required.
const GALA = {
  ...FESTIVAL,
  id: 2,
  title: "Charity Gala",
  purpose: null,
  description: null,
  venue: null,
  expected_attendance: null,
  venue_requirements: null,
  accessibility_needs: null,
  equipment_requirements: null,
  registration_required: false,
  not_recorded: ["purpose", "description", "venue", "expected_attendance", "venue_requirements",
                 "accessibility_needs", "equipment_requirements"],
};

function renderPage(eventId = 1) {
  render(
    <MemoryRouter
      initialEntries={[`/events/${eventId}/planning`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/events/:eventId/planning" element={<EventPlanningPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

// The value shown for a labelled field.
const field = (label) => {
  const term = screen.getAllByRole("term").find((dt) => dt.textContent === label);
  return term.nextElementSibling.textContent;
};

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-62 event planning page", () => {
  it("shows the event's status and assigned coordinator", async () => {
    apiClient.get.mockResolvedValue({ data: FESTIVAL });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Harbour Lights Festival" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/1/planning");
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
    expect(screen.getByText("Coordinator: alice.coordinator@connectsphere.test")).toBeTruthy();
  });

  it("shows every planning field with its recorded value", async () => {
    apiClient.get.mockResolvedValue({ data: FESTIVAL });
    renderPage();
    await screen.findByRole("heading", { name: "Harbour Lights Festival" });

    expect(screen.getAllByRole("term")).toHaveLength(16);
    expect(field("Purpose")).toBe(FESTIVAL.purpose);
    expect(field("Status")).toBe("Submitted");
    // Singapore time, shown as recorded rather than converted.
    expect(field("Start")).toBe("2026-12-12 17:00");
    expect(field("End")).toBe("2026-12-12 22:00");
    expect(field("Venue")).toBe("Aurora Ballroom, Level 3, Marina Tower, 10 Bayfront Ave");
    expect(field("Expected attendance")).toBe("350");
    expect(field("Attendee registration required")).toBe("Yes");
    expect(field("Organiser")).toBe(DANA.email);
    expect(field("Coordinator")).toBe(ALICE.email);
    expect(field("Coordinator assigned")).toBe(localTime("2026-09-10T09:30:00"));
    expect(field("Request created")).toBe(localTime("2026-09-05T14:00:00"));
    expect(screen.queryByText("Not recorded")).toBeNull();
  });

  it("shows unrecorded fields as Not recorded, never blank", async () => {
    apiClient.get.mockResolvedValue({ data: GALA });
    renderPage(2);
    await screen.findByRole("heading", { name: "Charity Gala" });

    for (const label of ["Purpose", "Description", "Venue", "Expected attendance",
      "Venue requirements", "Accessibility needs", "Equipment requirements"]) {
      expect(field(label)).toBe("Not recorded");
    }
    // "No" is a recorded answer, not a missing one.
    expect(field("Attendee registration required")).toBe("No");
    for (const dd of screen.getAllByRole("definition")) {
      expect(dd.textContent.trim()).not.toBe("");
    }
  });

  it("shows a retryable error and loads the event on retry", async () => {
    apiClient.get
      .mockRejectedValueOnce(Object.assign(new Error("fail"), {
        response: { status: 503, data: { error: "The event's information could not be loaded. Please try again.", retryable: true } },
      }))
      .mockResolvedValueOnce({ data: FESTIVAL });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The event's information could not be loaded. Please try again.",
    );
    expect(screen.queryByText("Harbour Lights Festival")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Harbour Lights Festival" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a refusal without a Retry button or any event information", async () => {
    apiClient.get.mockRejectedValue(Object.assign(new Error("fail"), {
      response: { status: 403, data: { error: "You are not allowed to view this event's planning information." } },
    }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "You are not allowed to view this event's planning information.",
    );
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.queryByRole("term")).toBeNull();
    expect(screen.getByRole("link", { name: "Back to my managed events" }).getAttribute("href"))
      .toBe("/events/managed");
  });
});

// SCRUM-39: an approved event offers its coordinator a way to request a venue
// (TC-39-11 in docs/test-cases/SCRUM-39-venue-booking-request.md).
describe("SCRUM-39 request a venue from the planning view", () => {
  it("links an approved event to its venue request page", async () => {
    apiClient.get.mockResolvedValue({ data: { ...FESTIVAL, status: "approved" } });
    renderPage();

    const link = await screen.findByRole("link", { name: "Request a venue" });
    expect(link.getAttribute("href")).toBe("/events/1/venue-request");
  });

  it.each(["draft", "submitted", "under_review", "rejected", "cancelled"])(
    "offers no venue request for a %s event",
    async (status) => {
      apiClient.get.mockResolvedValue({ data: { ...FESTIVAL, status } });
      renderPage();

      await screen.findByRole("heading", { name: "Harbour Lights Festival" });
      expect(screen.queryByRole("link", { name: "Request a venue" })).toBeNull();
    },
  );
});

// SCRUM-45 AC7 (TC-45-35): the event's coordinator sets up registration from here.
describe("SCRUM-45 set up registration from the planning view", () => {
  it("links an approved event that needs registration to its settings", async () => {
    apiClient.get.mockResolvedValue({ data: { ...FESTIVAL, status: "approved" } });
    renderPage();

    const link = await screen.findByRole("link", { name: "Set up registration" });
    expect(link.getAttribute("href")).toBe("/events/1/registration-settings");
  });

  it.each([
    ["a submitted event", { status: "submitted" }],
    ["an event that needs no registration", { status: "approved", registration_required: false }],
  ])("offers no registration set-up for %s", async (_, changes) => {
    apiClient.get.mockResolvedValue({ data: { ...FESTIVAL, ...changes } });
    renderPage();

    await screen.findByRole("heading", { name: "Harbour Lights Festival" });
    expect(screen.queryByRole("link", { name: "Set up registration" })).toBeNull();
  });
});

// SCRUM-38: the venue suitability check is reached from the planning view.
describe("SCRUM-38 check venue suitability from the planning view", () => {
  it("links the event to its venue suitability check", async () => {
    apiClient.get.mockResolvedValue({ data: FESTIVAL });
    renderPage();

    const link = await screen.findByRole("link", { name: "Check venue suitability" });
    expect(link.getAttribute("href")).toBe("/events/1/venue-suitability");
  });
});

// SCRUM-42 (TC-42-39): the coordinator records equipment requirements from the planning view.
describe("SCRUM-42 record equipment requirements from the planning view", () => {
  it("links to the equipment requirements", async () => {
    apiClient.get.mockResolvedValue({ data: FESTIVAL });
    renderPage();

    const link = await screen.findByRole("link", { name: "Equipment requirements" });
    expect(link.getAttribute("href")).toBe("/events/1/equipment");
  });
});

// SCRUM-85: TC-85-24 and 25 in docs/test-cases/SCRUM-85-several-venues-for-one-event.md.
// The API is backend/tests/test_several_venues.py's `venue_bookings`.
describe("SCRUM-85 venue bookings in the planning view", () => {
  const AURORA = { id: 9, name: "Aurora Ballroom", location: "Level 3, Marina Tower" };
  const CIVIC = { id: 4, name: "Civic Hall", location: null };
  const booking = (id, venue, start, end, status, extra = {}) => ({
    id, venue, start_time: start, end_time: end, setup_minutes: 0, turnaround_minutes: 0,
    status, hold_expires_at: null, hold_expired: null, ...extra,
  });
  const BOOKINGS = [
    booking(21, CIVIC, "2026-12-11T10:00:00", "2026-12-11T12:00:00", "rejected"),
    booking(22, AURORA, "2026-12-12T17:00:00", "2026-12-12T22:00:00", "confirmed",
      { setup_minutes: 30, turnaround_minutes: 45 }),
    booking(23, CIVIC, "2026-12-12T17:00:00", "2026-12-12T19:00:00", "pending"),
    booking(24, CIVIC, "2026-12-13T09:00:00", "2026-12-13T12:00:00", "tentative",
      { hold_expires_at: "2026-12-01T12:00:00", hold_expired: false }),
    booking(25, AURORA, "2026-12-14T09:00:00", "2026-12-14T12:00:00", "tentative",
      { hold_expires_at: "2026-10-01T12:00:00", hold_expired: true }),
  ];

  // TC-85-24 · AC4
  it("lists every venue booking with its status", async () => {
    apiClient.get.mockResolvedValue({ data: { ...FESTIVAL, venue_bookings: BOOKINGS } });
    renderPage();

    const region = await screen.findByRole("region", { name: "Venue bookings" });
    const items = within(region).getAllByRole("listitem").map((item) => item.textContent);
    expect(items).toEqual([
      "Civic Hall2026-12-11 10:00 to 2026-12-11 12:00Status: Rejected",
      "Aurora Ballroom, Level 3, Marina Tower2026-12-12 17:00 to 2026-12-12 22:00"
        + "Setup 30 min before, turnaround 45 min afterStatus: Confirmed",
      "Civic Hall2026-12-12 17:00 to 2026-12-12 19:00Status: Pending",
      "Civic Hall2026-12-13 09:00 to 2026-12-13 12:00Status: Tentative, held until 2026-12-01 12:00",
      "Aurora Ballroom, Level 3, Marina Tower2026-12-14 09:00 to 2026-12-14 12:00"
        + "Status: Hold expired on 2026-10-01 12:00",
    ]);
  });

  // TC-85-25 · AC4
  it("says when the event has no venue bookings", async () => {
    apiClient.get.mockResolvedValue({ data: { ...FESTIVAL, venue_bookings: [] } });
    renderPage();

    const region = await screen.findByRole("region", { name: "Venue bookings" });
    expect(region.textContent).toContain("No venue bookings yet.");
    expect(within(region).queryAllByRole("listitem")).toEqual([]);
  });
});
