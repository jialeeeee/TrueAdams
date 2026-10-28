import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ChangeRequestReviewPage from "./ChangeRequestReviewPage.jsx";

// Frontend cases TC-70-26 to TC-70-30 in docs/test-cases/SCRUM-70-review-change-request.md.
// The API is covered by backend/tests/test_change_request_review.py; responses mirror its
// contract:
//   GET  /events/<id>/change-requests/<rid> -> { event: { id, title, status, organiser },
//     request: REQ, impact: IMPACT, can_decide, blocked_reason, message }
//   POST /events/<id>/change-requests/<rid>/decision { decision, reason? }
//     -> { message, request: REQ, notification: { in_app, email_queued, attendees_notified } }
//   REQ = { id, event_id, status, status_label, changes: [{ field, label, from, to }],
//     requested_by, requested_at, decided_at, decided_by, decision_reason }
//   IMPACT = { venue_bookings: [{ id, venue, start_time, end_time, status, reasons }],
//     equipment: [{ id, equipment_type, quantity, reserved, reasons }],
//     registrations: { registered, capacity, reasons }, affected, message }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const ALICE = { id: 2, email: "alice@example.com" };
const DANA = { id: 4, email: "dana@example.com" };
const REQUEST = {
  id: 31, event_id: 7, status: "pending_review", status_label: "Pending Review",
  changes: [
    { field: "start_time", label: "Start", from: "2026-12-05T18:00:00", to: "2026-12-06T18:00:00" },
    { field: "expected_attendance", label: "Expected attendance", from: 200, to: 250 },
  ],
  requested_by: DANA, requested_at: "2026-10-26T02:00:00",
  decided_at: null, decided_by: null, decision_reason: null,
};
const IMPACT = {
  venue_bookings: [{
    id: 51, venue: { id: 3, name: "Grand Ballroom" }, start_time: "2026-12-05T18:00:00",
    end_time: "2026-12-05T23:00:00", status: "confirmed",
    reasons: ["Booked for the current date and time; it isn't moved automatically.",
      "Grand Ballroom holds 220 people, fewer than the new expected attendance of 250."],
  }],
  equipment: [{
    id: 61, equipment_type: "Wireless microphone", quantity: 2, reserved: 2,
    reasons: ["2 reserved for the current date and time; they are released if the change is accepted."],
  }],
  registrations: {
    registered: 2, capacity: 210,
    reasons: ["2 registered attendees will be told the new date and time."],
  },
  affected: true, message: null,
};
const REVIEW = {
  event: { id: 7, title: "Charity Gala", status: "approved", organiser: DANA },
  request: REQUEST, impact: IMPACT, can_decide: true, blocked_reason: null, message: null,
};
const NOTHING = {
  venue_bookings: [], equipment: [], registrations: { registered: 0, capacity: null, reasons: [] },
  affected: false, message: "Nothing recorded for this event is affected by these changes.",
};
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });
const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/change-requests/31"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/change-requests/:requestId" element={<ChangeRequestReviewPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const reasonBox = () => screen.getByLabelText(/Reason for rejecting/);
const button = (name) => screen.getByRole("button", { name });

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("SCRUM-70 the coordinator reviews a change request", () => {
  // TC-70-26 · AC2
  it("shows the requested changes and what they affect", async () => {
    apiClient.get.mockResolvedValue({ data: REVIEW });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Review change request: Charity Gala" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/change-requests/31");
    const changes = within(screen.getByRole("list", { name: "Requested changes" })).getAllByRole("listitem");
    expect(changes.map((item) => item.textContent)).toEqual([
      "Start: 2026-12-05 18:00 → 2026-12-06 18:00", "Expected attendance: 200 → 250",
    ]);
    expect(screen.getByText(`Requested by ${DANA.email} on ${localTime("2026-10-26T02:00:00")}`)).toBeTruthy();

    const venues = screen.getByRole("region", { name: "Venue bookings affected" });
    expect(within(venues).getByText("Grand Ballroom, 2026-12-05 18:00 to 2026-12-05 23:00 (Confirmed)")).toBeTruthy();
    expect(within(venues).getByText(IMPACT.venue_bookings[0].reasons[1])).toBeTruthy();
    const equipment = screen.getByRole("region", { name: "Equipment affected" });
    expect(within(equipment).getByText("Wireless microphone × 2 (2 reserved)")).toBeTruthy();
    expect(within(equipment).getByText(IMPACT.equipment[0].reasons[0])).toBeTruthy();
    const registrations = screen.getByRole("region", { name: "Registrations affected" });
    expect(within(registrations).getByText(IMPACT.registrations.reasons[0])).toBeTruthy();
    expect(button("Accept")).toBeTruthy();
    expect(button("Reject")).toBeTruthy();
  });

  // TC-70-26 · AC2
  it("says when nothing recorded is affected", async () => {
    apiClient.get.mockResolvedValue({ data: { ...REVIEW, impact: NOTHING } });
    renderPage();

    expect(await screen.findByText(NOTHING.message)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Venue bookings affected" })).toBeNull();
  });

  // TC-70-27 · AC3, AC8
  it("accepts the request and shows the decision", async () => {
    apiClient.get.mockResolvedValue({ data: REVIEW });
    const decided = { ...REQUEST, status: "accepted", status_label: "Accepted",
      decided_at: "2026-10-28T03:00:00", decided_by: ALICE };
    const message = "You accepted the change request for \"Charity Gala\". The event now shows the new values.";
    apiClient.post.mockResolvedValue({ data: { message, request: decided,
      notification: { in_app: true, email_queued: true, attendees_notified: 2 } } });
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Accept" }));

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/change-requests/31/decision", { decision: "accept" });
    expect((await screen.findByRole("status")).textContent).toContain(message);
    expect(screen.getByText("Status: Accepted")).toBeTruthy();
    expect(screen.getByText(`Decided by ${ALICE.email} · ${localTime("2026-10-28T03:00:00")}`)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  // TC-70-28 · AC4
  it("requires a reason of at most 500 characters to reject", async () => {
    apiClient.get.mockResolvedValue({ data: REVIEW });
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    expect(screen.getByRole("alert").textContent).toBe("A reason is required to reject this change request.");
    expect(reasonBox().getAttribute("aria-invalid")).toBe("true");
    expect(apiClient.post).not.toHaveBeenCalled();

    await user.click(reasonBox());
    await user.paste("x".repeat(501));
    expect(screen.getByText("501 / 500 characters")).toBeTruthy();
    expect(screen.getByText("That is over the 500-character limit. Remove 1 character to continue.")).toBeTruthy();
    expect(button("Reject").disabled).toBe(true);

    await user.type(reasonBox(), "{Backspace}");
    expect(screen.getByText("500 / 500 characters")).toBeTruthy();
    const decided = { ...REQUEST, status: "rejected", status_label: "Rejected",
      decided_at: "2026-10-28T03:00:00", decided_by: ALICE, decision_reason: "x".repeat(500) };
    apiClient.post.mockResolvedValue({ data: { message: "You rejected the change request.", request: decided,
      notification: { in_app: true, email_queued: true, attendees_notified: 0 } } });
    await user.click(button("Reject"));

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/change-requests/31/decision",
      { decision: "reject", reason: "x".repeat(500) });
    expect(await screen.findByText("Status: Rejected")).toBeTruthy();
    expect(screen.getByText(`Reason: ${"x".repeat(500)}`)).toBeTruthy();
  });

  // TC-70-29 · AC6
  it("keeps the reason after a failed decision so it can be tried again", async () => {
    apiClient.get.mockResolvedValue({ data: REVIEW });
    apiClient.post.mockRejectedValueOnce(failed(503, {
      error: "The decision was not saved, so the change request and the event are unchanged. Please try again.",
      retryable: true,
    }));
    const user = renderPage();

    await user.type(await screen.findByLabelText(/Reason for rejecting/), "The ballroom is too small.");
    await user.click(button("Reject"));

    expect((await screen.findByRole("alert")).textContent).toContain("was not saved");
    expect(reasonBox().value).toBe("The ballroom is too small.");
    expect(screen.getByText("Status: Pending Review")).toBeTruthy();

    apiClient.post.mockRejectedValueOnce(new Error("Network Error"));
    await user.click(button("Reject"));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "The decision was not saved. Check your connection and try again.");
    expect(button("Reject").disabled).toBe(false);
  });

  // TC-70-30 · AC1, AC3
  it("explains why a request can't be decided", async () => {
    const decided = { ...REQUEST, status: "rejected", status_label: "Rejected",
      decided_at: "2026-10-27T03:00:00", decided_by: ALICE, decision_reason: "Too big." };
    apiClient.get.mockResolvedValueOnce({ data: { ...REVIEW, request: decided, can_decide: false,
      blocked_reason: "decided", message: "This change request was already rejected." } });
    renderPage();

    expect(await screen.findByText("This change request was already rejected.")).toBeTruthy();
    expect(screen.getByText("Status: Rejected")).toBeTruthy();
    expect(screen.getByText("Reason: Too big.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
    expect(screen.queryByLabelText(/Reason for rejecting/)).toBeNull();
  });

  it("explains a failed load and offers Retry", async () => {
    apiClient.get.mockRejectedValueOnce(failed(503, {
      error: "The change request could not be loaded. Please try again.", retryable: true }));
    apiClient.get.mockResolvedValueOnce({ data: REVIEW });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toBe("The change request could not be loaded. Please try again.");
    await user.click(button("Retry"));
    expect(await screen.findByRole("heading", { name: "Review change request: Charity Gala" })).toBeTruthy();
  });

  it("offers no Retry for a refusal", async () => {
    apiClient.get.mockRejectedValue(failed(403, {
      error: "Only the event's coordinator can review its change requests." }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toBe("Only the event's coordinator can review its change requests.");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
