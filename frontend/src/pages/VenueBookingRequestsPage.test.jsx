import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenueBookingRequestsPage from "./VenueBookingRequestsPage.jsx";

// Frontend case TC-39-20 in docs/test-cases/SCRUM-39-venue-booking-request.md:
// Venue Staff's list of pending requests (GET /api/venues/bookings).

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

const BOOKING = {
  id: 11, status: "pending",
  event: { id: 7, title: "Harbour Lights Festival", expected_attendance: 250 },
  venue: { id: 3, name: "Aurora Ballroom", location: "Level 3, Marina Tower" },
  start_time: "2027-03-12T16:00:00", end_time: "2027-03-12T22:30:00",
  venue_requirements: "Open-air waterfront space for 250, stage power",
  requested_by: { id: 2, email: "alice.coordinator@connectsphere.test" },
  requested_at: "2026-10-14T03:00:00",
  // SCRUM-41: the pending list also gives each request's conflicts.
  conflicts: [],
};

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <VenueBookingRequestsPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("SCRUM-39 venue booking requests for Venue Staff", () => {
  it("lists each pending request with what Venue Staff need to assess it", async () => {
    apiClient.get.mockResolvedValue({ data: { bookings: [BOOKING], message: null } });
    renderPage();

    const item = await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    expect(apiClient.get).toHaveBeenCalledWith("/venues/bookings");
    const text = item.textContent;
    expect(text).toContain("Venue: Aurora Ballroom, Level 3, Marina Tower");
    expect(text).toContain("Requested: 2027-03-12 16:00 to 2027-03-12 22:30");
    expect(text).toContain("Expected attendance: 250");
    expect(text).toContain("Requirements: Open-air waterfront space for 250, stage power");
    expect(text).toContain(`Requested by alice.coordinator@connectsphere.test on ${localTime("2026-10-14T03:00:00")}`);
    expect(text).toContain("Status: Pending");
  });

  it("shows the empty state", async () => {
    apiClient.get.mockResolvedValue({ data: { bookings: [], message: "There are no pending venue requests." } });
    renderPage();
    expect(await screen.findByText("There are no pending venue requests.")).toBeTruthy();
  });

  it("shows a retryable error when the requests cannot be loaded", async () => {
    apiClient.get
      .mockRejectedValueOnce(Object.assign(new Error("fail"), {
        response: { status: 503, data: { error: "Venue requests could not be loaded. Please try again.", retryable: true } },
      }))
      .mockResolvedValueOnce({ data: { bookings: [BOOKING], message: null } });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("listitem", { name: "Harbour Lights Festival" })).toBeTruthy();
  });
});

// SCRUM-40: Venue Staff approve a pending request. Frontend cases TC-40-02, 23, 26
// and 29 in docs/test-cases/SCRUM-40-approve-venue-booking.md; the API contract
// mirrors backend/tests/test_venue_booking_approval.py.
describe("SCRUM-40 approve a venue booking request", () => {
  const OTHER = {
    ...BOOKING, id: 12,
    event: { id: 8, title: "Winter Networking Night", expected_attendance: 80 },
  };
  const approveButton = (title) => screen.getByRole("button", { name: `Approve booking for ${title}` });

  function httpFailure(status, data) {
    return Object.assign(new Error(`Request failed with status ${status}`), {
      isAxiosError: true, response: { status, data },
    });
  }

  async function renderList() {
    apiClient.get.mockResolvedValue({ data: { bookings: [BOOKING, OTHER], message: null } });
    const user = renderPage();
    await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    return user;
  }

  // TC-40-02 · AC1, AC2
  it("offers Approve for each pending request", async () => {
    await renderList();
    expect(approveButton("Harbour Lights Festival")).toBeTruthy();
    expect(approveButton("Winter Networking Night")).toBeTruthy();
  });

  // TC-40-23 · AC4
  it("approves a request, shows the confirmation and removes it from the pending list", async () => {
    apiClient.post.mockResolvedValue({
      data: {
        message: "You approved Aurora Ballroom for Harbour Lights Festival. alice.coordinator@connectsphere.test has been notified.",
        booking: { ...BOOKING, status: "confirmed", decided_at: "2026-10-15T02:00:00",
          decided_by: { id: 9, email: "gus.venue@connectsphere.test" } },
        notification: { in_app: true, email_queued: true },
      },
    });
    const user = await renderList();
    // SCRUM-41: the list is reloaded after an approval, without the approved request.
    apiClient.get.mockResolvedValue({ data: { bookings: [OTHER], message: null } });

    await user.click(approveButton("Harbour Lights Festival"));

    expect(apiClient.post).toHaveBeenCalledWith("/venues/bookings/11/approve");
    expect((await screen.findByRole("status")).textContent).toContain("You approved Aurora Ballroom");
    expect(screen.queryByRole("listitem", { name: "Harbour Lights Festival" })).toBeNull();
    expect(screen.getByRole("listitem", { name: "Winter Networking Night" })).toBeTruthy();
  });

  // TC-40-26 · AC5
  it("explains each conflict and keeps the request pending", async () => {
    apiClient.post.mockRejectedValue(httpFailure(409, {
      error: "This booking can't be approved because it clashes with other arrangements.",
      reason: "conflict",
      conflicts: [
        { type: "block", id: 4, start: "2027-03-12T15:00:00", end: "2027-03-12T17:00:00", reason: "Electrical works" },
        { type: "block", id: 5, start: "2027-03-12T17:30:00", end: "2027-03-12T17:45:00", reason: null },
        { type: "booking", id: 6, start: "2027-03-12T18:00:00", end: "2027-03-12T20:00:00", event: { id: 9, title: "Product Launch" } },
        { type: "booking", id: 7, start: "2027-03-12T20:00:00", end: "2027-03-12T21:00:00", event: null },
        { type: "event_booking", id: 8, start: "2027-03-12T16:00:00", end: "2027-03-12T22:30:00", venue: { id: 4, name: "Civic Hall" } },
      ],
    }));
    const user = await renderList();

    await user.click(approveButton("Harbour Lights Festival"));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("clashes with other arrangements");
    const lines = Array.from(alert.querySelectorAll("li")).map((li) => li.textContent);
    expect(lines).toEqual([
      "Blocked (Electrical works), 2027-03-12 15:00 to 2027-03-12 17:00",
      "Blocked, 2027-03-12 17:30 to 2027-03-12 17:45",
      "Confirmed booking for Product Launch, 2027-03-12 18:00 to 2027-03-12 20:00",
      "Confirmed booking, 2027-03-12 20:00 to 2027-03-12 21:00",
      "This event's confirmed booking at Civic Hall, 2027-03-12 16:00 to 2027-03-12 22:30",
    ]);
    expect(screen.getByRole("listitem", { name: "Harbour Lights Festival" })).toBeTruthy();
    expect(approveButton("Harbour Lights Festival").disabled).toBe(false);
    expect(screen.queryByRole("status")).toBeNull();
  });

  // TC-40-29 · AC6
  it.each([
    ["save failure", httpFailure(503, { error: "The approval was not saved, so the request is still pending. Please try again.", retryable: true }), "still pending"],
    ["no longer pending", httpFailure(409, { error: "This request is confirmed, so it can no longer be approved.", reason: "not_pending" }), "can no longer be approved"],
    ["no network", new Error("Network Error"), "Check your connection and try again"],
  ])("shows why approval failed (%s), keeps the request, and the retry succeeds", async (_label, failure, message) => {
    apiClient.post.mockRejectedValueOnce(failure).mockResolvedValueOnce({
      data: { message: "You approved Aurora Ballroom for Harbour Lights Festival.", booking: { ...BOOKING, status: "confirmed" },
        notification: { in_app: true, email_queued: true } },
    });
    const user = await renderList();

    await user.click(approveButton("Harbour Lights Festival"));

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(screen.getByRole("listitem", { name: "Harbour Lights Festival" })).toBeTruthy();
    expect(approveButton("Harbour Lights Festival").disabled).toBe(false);

    await user.click(approveButton("Harbour Lights Festival"));
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

// SCRUM-41: conflicts are shown before approval. Frontend cases TC-41-06 and 07 in
// docs/test-cases/SCRUM-41-prevent-venue-booking-conflicts.md; the API contract
// mirrors backend/tests/test_venue_booking_conflicts.py.
describe("SCRUM-41 conflicts are shown before approval", () => {
  const OTHER = {
    ...BOOKING, id: 12,
    event: { id: 8, title: "Winter Networking Night", expected_attendance: 80 },
  };
  const APPROVED = {
    data: {
      message: "You approved Aurora Ballroom for Harbour Lights Festival. alice.coordinator@connectsphere.test has been notified.",
      booking: { ...BOOKING, status: "confirmed" },
      notification: { in_app: true, email_queued: true },
    },
  };

  // TC-41-06 · AC2
  it("shows each request's conflicts with their periods", async () => {
    const clashing = {
      ...BOOKING,
      conflicts: [
        { type: "block", id: 4, start: "2027-03-12T15:00:00", end: "2027-03-12T17:00:00", reason: "Electrical works" },
        { type: "booking", id: 6, start: "2027-03-12T18:00:00", end: "2027-03-12T20:00:00", event: { id: 9, title: "Product Launch" } },
      ],
    };
    apiClient.get.mockResolvedValue({ data: { bookings: [clashing, OTHER], message: null } });
    renderPage();

    const item = await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    const conflicts = within(item).getByRole("list", { name: "Conflicts for Harbour Lights Festival" });
    expect(within(conflicts).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Blocked (Electrical works), 2027-03-12 15:00 to 2027-03-12 17:00",
      "Confirmed booking for Product Launch, 2027-03-12 18:00 to 2027-03-12 20:00",
    ]);
    const other = screen.getByRole("listitem", { name: "Winter Networking Night" });
    expect(other.textContent).toContain("No conflicts found.");
    expect(within(other).queryByRole("list")).toBeNull();
    for (const title of ["Harbour Lights Festival", "Winter Networking Night"]) {
      expect(screen.getByRole("button", { name: `Approve booking for ${title}` }).disabled).toBe(false);
    }
  });

  // TC-41-07 · AC2 (Q2)
  it("reloads the list after an approval so new clashes show", async () => {
    const nowClashing = {
      ...OTHER,
      conflicts: [
        { type: "booking", id: 11, start: "2027-03-12T16:00:00", end: "2027-03-12T22:30:00", event: { id: 7, title: "Harbour Lights Festival" } },
      ],
    };
    apiClient.get
      .mockResolvedValueOnce({ data: { bookings: [BOOKING, OTHER], message: null } })
      .mockResolvedValueOnce({ data: { bookings: [nowClashing], message: null } });
    apiClient.post.mockResolvedValue(APPROVED);
    const user = renderPage();
    await screen.findByRole("listitem", { name: "Harbour Lights Festival" });

    await user.click(screen.getByRole("button", { name: "Approve booking for Harbour Lights Festival" }));

    await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(2));
    expect(apiClient.get).toHaveBeenLastCalledWith("/venues/bookings");
    const other = screen.getByRole("listitem", { name: "Winter Networking Night" });
    expect(await within(other).findByText(
      "Confirmed booking for Harbour Lights Festival, 2027-03-12 16:00 to 2027-03-12 22:30",
    )).toBeTruthy();
    expect(screen.queryByRole("listitem", { name: "Harbour Lights Festival" })).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("You approved Aurora Ballroom");
  });
});

// SCRUM-87: Venue Staff place a tentative hold. Frontend cases TC-87-34 and 35 in
// docs/test-cases/SCRUM-87-tentative-venue-hold.md; the API contract mirrors
// backend/tests/test_venue_holds.py.
describe("SCRUM-87 place a tentative hold", () => {
  const HELD = {
    data: {
      message: "You placed a tentative hold on Aurora Ballroom for Harbour Lights Festival until 2027-03-01 17:00. alice.coordinator@connectsphere.test has been notified.",
      booking: {
        ...BOOKING, status: "tentative",
        hold: { held_at: "2027-02-20T01:00:00", held_by: { id: 9, email: "gus.venue@connectsphere.test" }, expires_at: "2027-03-01T17:00:00" },
      },
      notification: { in_app: true, email_queued: true },
    },
  };
  const expiryField = () => screen.getByLabelText("Hold expiry for Harbour Lights Festival");
  const holdButton = () => screen.getByRole("button", { name: "Place tentative hold for Harbour Lights Festival" });

  function httpFailure(status, data) {
    return Object.assign(new Error(`Request failed with status ${status}`), {
      isAxiosError: true, response: { status, data },
    });
  }

  async function renderList() {
    apiClient.get.mockResolvedValue({ data: { bookings: [BOOKING], message: null } });
    const user = renderPage();
    await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    return user;
  }

  // TC-87-34 · AC1, AC2
  it("places a tentative hold with the expiry entered", async () => {
    apiClient.post.mockResolvedValue(HELD);
    const user = await renderList();
    apiClient.get.mockResolvedValue({ data: { bookings: [], message: "There are no pending venue requests." } });

    await user.type(expiryField(), "2027-03-01T17:00");
    await user.click(holdButton());

    expect(apiClient.post).toHaveBeenCalledWith("/venues/bookings/11/hold", { expires_at: "2027-03-01T17:00" });
    expect((await screen.findByRole("status")).textContent).toContain(
      "You placed a tentative hold on Aurora Ballroom for Harbour Lights Festival until 2027-03-01 17:00.",
    );
    expect(await screen.findByText("There are no pending venue requests.")).toBeTruthy();
    expect(screen.queryByRole("listitem", { name: "Harbour Lights Festival" })).toBeNull();
    expect(apiClient.get).toHaveBeenCalledTimes(2);
  });

  // TC-87-35 · AC2, AC4, AC7
  it.each([
    ["an invalid expiry", httpFailure(400, { error: "The hold must expire no later than the booking's start (2027-03-12 16:00).", field: "expires_at" }),
      "no later than the booking's start", null],
    ["a clash with a hold", httpFailure(409, {
      error: "This booking can't be placed on hold because it clashes with other arrangements at Aurora Ballroom.",
      reason: "conflict",
      conflicts: [{ type: "hold", id: 31, start: "2027-03-12T18:00:00", end: "2027-03-12T20:00:00", event: { id: 9, title: "Product Launch" }, expires_at: "2027-03-01T17:00:00" }],
    }), "clashes with other arrangements", "Tentative hold for Product Launch until 2027-03-01 17:00, 2027-03-12 18:00 to 2027-03-12 20:00"],
    ["a save failure", httpFailure(503, { error: "The hold was not saved, so the request is still pending. Please try again.", retryable: true }),
      "still pending", null],
    ["no network", new Error("Network Error"), "Check your connection and try again", null],
  ])("explains a refused hold (%s) and keeps the request and expiry", async (_label, failure, message, conflictLine) => {
    apiClient.post.mockRejectedValue(failure);
    const user = await renderList();

    await user.type(expiryField(), "2027-03-01T17:00");
    await user.click(holdButton());

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(message);
    if (conflictLine) {
      expect(Array.from(alert.querySelectorAll("li")).map((li) => li.textContent)).toEqual([conflictLine]);
    }
    expect(screen.getByRole("listitem", { name: "Harbour Lights Festival" })).toBeTruthy();
    expect(expiryField().value).toBe("2027-03-01T17:00");
    expect(screen.queryByRole("status")).toBeNull();
  });
});

// SCRUM-69 RED: TC-69-24/25 (AC2/AC3/AC4/AC6). Contract and assumptions:
// docs/test-cases/SCRUM-69-reject-venue-booking.md; backend counterpart:
// backend/tests/test_venue_booking_rejection.py. AC1 reuses SCRUM-39 above.
describe("SCRUM-69 reject a pending venue booking request", () => {
  const REASON = "The required stage power cannot be provided for this arrangement.";
  const OTHER = {
    ...BOOKING, id: 12,
    event: { id: 8, title: "Winter Networking Night", expected_attendance: 80 },
  };
  // Must match SCRUM-69 AC3 and backend test MAX_REASON_LENGTH (500 characters).
  const MAX_REASON_LENGTH = 500;
  const reasonField = (title = BOOKING.event.title) =>
    screen.getByRole("textbox", { name: `Rejection reason for ${title}` });
  const rejectButton = () =>
    screen.getByRole("button", { name: `Reject booking for ${BOOKING.event.title}` });

  function rejected(reason = REASON, emailQueued = true) {
    return {
      data: {
        message: "The venue request for Harbour Lights Festival at Aurora Ballroom was rejected.",
        booking: { ...BOOKING, status: "rejected", rejection_reason: reason,
          decided_at: "2026-10-21T03:00:00", decided_by: { id: 9, email: "gus.venue@connectsphere.test" } },
        notification: { in_app: true, email_queued: emailQueued },
      },
    };
  }

  function httpFailure(status, data) {
    return Object.assign(new Error(`Request failed with status ${status}`), {
      isAxiosError: true, response: { status, data },
    });
  }

  async function renderList() {
    apiClient.get.mockResolvedValue({ data: { bookings: [BOOKING, OTHER], message: null } });
    const user = renderPage();
    await screen.findByRole("listitem", { name: BOOKING.event.title });
    return user;
  }

  it.each([true, false])("rejects the selected request with its reason (email queued: %s)", async (emailQueued) => {
    const user = await renderList();
    await user.type(reasonField(), REASON);
    apiClient.post.mockResolvedValue(rejected(REASON, emailQueued));
    apiClient.get.mockResolvedValue({ data: { bookings: [OTHER], message: null } });

    await user.click(rejectButton());

    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(apiClient.post).toHaveBeenCalledWith("/venues/bookings/11/reject", { reason: REASON });
    expect((await screen.findByRole("status")).textContent).toContain("was rejected");
    expect(screen.queryByRole("listitem", { name: BOOKING.event.title })).toBeNull();
    expect(screen.getByRole("listitem", { name: OTHER.event.title })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledTimes(2);
  });

  it.each(["", "   ", "\n\t"])("requires a nonblank rejection reason (%j)", async (reason) => {
    const user = await renderList();
    if (reason) await user.type(reasonField(), reason);

    await user.click(rejectButton());

    expect(apiClient.post).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toMatch(/reason.*required|enter.*reason/i);
    expect(screen.getByRole("listitem", { name: BOOKING.event.title })).toBeTruthy();
  });

  it("accepts exactly 500 characters without truncating the reason", async () => {
    const user = await renderList();
    const reason = "x".repeat(MAX_REASON_LENGTH);
    await user.click(reasonField());
    await user.paste(reason);
    apiClient.post.mockResolvedValue(rejected(reason));
    apiClient.get.mockResolvedValue({ data: { bookings: [OTHER], message: null } });

    await user.click(rejectButton());

    expect(apiClient.post).toHaveBeenCalledWith("/venues/bookings/11/reject", { reason });
    expect(await screen.findByRole("status")).toBeTruthy();
  });

  it("refuses a 501-character reason before sending a rejection", async () => {
    const user = await renderList();
    await user.click(reasonField());
    await user.paste("x".repeat(MAX_REASON_LENGTH + 1));

    await user.click(rejectButton());

    expect(apiClient.post).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toContain("500");
    expect(reasonField().value).toHaveLength(MAX_REASON_LENGTH + 1);
  });

  it.each([
    ["validation", httpFailure(400, { error: "Enter a rejection reason.", field: "reason" }), "Enter a rejection reason."],
    ["stale request", httpFailure(409, { error: "This request is confirmed, so it can no longer be rejected.", reason: "not_pending" }), "can no longer be rejected"],
    ["save failure", httpFailure(503, { error: "The rejection was not saved. Please try again.", retryable: true }), "rejection was not saved"],
    ["network", new Error("Network Error"), "try again"],
  ])("keeps each request's reason after a rejection failure (%s)", async (_label, failure, message) => {
    const user = await renderList();
    await user.type(reasonField(), REASON);
    await user.type(reasonField(OTHER.event.title), "Keep this other reason.");
    apiClient.post.mockRejectedValueOnce(failure).mockResolvedValueOnce(rejected());

    await user.click(rejectButton());

    expect((await screen.findByRole("alert")).textContent.toLowerCase()).toContain(message.toLowerCase());
    expect(reasonField().value).toBe(REASON);
    expect(reasonField(OTHER.event.title).value).toBe("Keep this other reason.");
    expect(screen.queryByRole("status")).toBeNull();
    if (!failure.response || failure.response.data.retryable) {
      apiClient.get.mockResolvedValue({ data: { bookings: [OTHER], message: null } });
      await user.click(rejectButton());
      expect(await screen.findByRole("status")).toBeTruthy();
      expect(apiClient.post).toHaveBeenLastCalledWith("/venues/bookings/11/reject", { reason: REASON });
    }
  });
});
