import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ReviewRequestPage from "./ReviewRequestPage.jsx";

// Frontend case TC-32-20 in docs/test-cases/SCRUM-32-approve-reject-event-request.md.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const REASON = "The proposed date clashes with the National Day Parade.";

function request(overrides = {}) {
  return {
    id: 7, title: "Harbour Lights Festival", status: "submitted",
    purpose: "Celebrate the harbour's reopening", description: "Lanterns and live music.",
    start_time: "2026-12-12T17:00:00", end_time: "2026-12-12T22:00:00",
    expected_attendance: 250, venue_requirements: "Open-air waterfront space",
    accessibility_needs: null, equipment_requirements: "PA system", registration_required: true,
    submitted_at: "2026-09-20T01:00:00", decided_at: null, decided_by: null, decision_note: null,
    ...overrides,
  };
}

function decided(status, note, emailQueued = true) {
  return {
    data: {
      message: `The request was ${status}. dana.organiser@connectsphere.test has been notified.`,
      request: request({ status, decision_note: note, decided_at: "2026-09-28T03:00:00",
        decided_by: { id: 2, email: "alice.coordinator@connectsphere.test" } }),
      notification: { in_app: true, email_queued: emailQueued },
    },
  };
}

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function words(count) {
  return Array.from({ length: count }, (_, i) => `w${i}`).join(" ");
}

async function renderPage(loaded = request()) {
  apiClient.get.mockResolvedValueOnce({ data: { request: loaded } });
  render(
    <MemoryRouter initialEntries={["/events/7/review"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="/events/:eventId/review" element={<ReviewRequestPage />} /></Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: /review/i });
  return userEvent.setup();
}

const box = () => screen.getByLabelText(/reason or note/i);
const button = (name) => screen.getByRole("button", { name });

async function enter(user, text) {
  await user.clear(box());
  if (text) {
    await user.click(box());
    await user.paste(text);
  }
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
  // SCRUM-55 adds a read-only history GET after the request loads. Keep the
  // existing decision/detail fixtures intact and supply that endpoint's shape.
  apiClient.get.mockImplementation(async (url) => {
    if (url.endsWith("/clarifications")) {
      return { data: { clarifications: [], message: "No questions have been sent for this event yet." } };
    }
    throw new Error(`Unexpected API read: ${url}`);
  });
});

// SCRUM-55 TC-55-09..10: UNEXECUTED. See
// docs/test-cases/SCRUM-55-review-submitted-event-request.md and
// backend/tests/test_review_requests_unit.py. Existing SCRUM-32 tests only check
// a subset of the fields on this screen; SCRUM-34 tests a different screen.
describe("SCRUM-55 read submitted details and history (UNEXECUTED)", () => {
  // TC-55-09: AC4. NULL and false must remain visibly different answers.
  it.each([
    ["recorded", "Step-free access", true, "Step-free access", "Yes"],
    ["unrecorded accessibility and no registration", null, false, "Not provided", "No"],
  ])("shows all submitted fields with %s values", async (_case, accessibility, registration, shownAccess, shownRegistration) => {
    await renderPage(request({ accessibility_needs: accessibility, registration_required: registration }));
    expect(screen.getByRole("heading", { name: "Review: Harbour Lights Festival" })).toBeTruthy();
    const expected = {
      Purpose: "Celebrate the harbour's reopening",
      Description: "Lanterns and live music.",
      Start: "2026-12-12 17:00", End: "2026-12-12 22:00",
      "Expected attendance": "250", "Venue requirements": "Open-air waterfront space",
      "Accessibility needs": shownAccess, "Equipment requirements": "PA system",
      "Attendee registration needed": shownRegistration,
    };
    for (const [label, value] of Object.entries(expected)) {
      const term = screen.getAllByRole("term").find((node) => node.textContent === label);
      expect(term).toBeTruthy();
      expect(within(term.parentElement).getByRole("definition").textContent).toBe(value);
    }
  });

  // TC-55-10: AC5, AC4. Reuse one mounted route to catch a stale other-event thread.
  it("shows the selected request's existing messages and replaces them when another request opens", async () => {
    const questions = { 7: "Do guests need wheelchair access?", 8: "Is a projector required?" };
    apiClient.get.mockImplementation(async (url) => {
      const match = /^\/events\/(7|8)\/(review|clarifications)$/.exec(url);
      if (!match) throw new Error(`Unexpected API read: ${url}`);
      const id = Number(match[1]);
      const event = request({ id, title: id === 7 ? "Harbour Lights Festival" : "Workshop" });
      if (match[2] === "review") return { data: { request: event } };
      return { data: { event: { id, title: event.title, status: "submitted",
        organiser: { id: 1, email: "owner@test.invalid" } },
      clarifications: [{ id: id + 20, event_id: id, message: questions[id],
        sender: { id: 2, email: "current@test.invalid" }, created_at: "2026-10-14T02:00:00" }],
      can_send: true, message: null } };
    });
    render(
      <MemoryRouter initialEntries={["/events/7/review"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Link to="/events/8/review">Open workshop</Link>
        <Routes><Route path="/events/:eventId/review" element={<ReviewRequestPage />} /></Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    expect(await screen.findByText(questions[7])).toBeTruthy();
    await user.click(screen.getByRole("link", { name: "Open workshop" }));
    expect(await screen.findByRole("heading", { name: "Review: Workshop" })).toBeTruthy();
    expect(await screen.findByText(questions[8])).toBeTruthy();
    expect(screen.queryByText(questions[7])).toBeNull();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/clarifications");
    expect(apiClient.get).toHaveBeenCalledWith("/events/8/clarifications");
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});

// TC-55-13..14: focused post-GREEN regressions for the additional history GET.
describe("SCRUM-55 post-GREEN history regressions", () => {
  it("retries failed history without reloading details or losing a typed decision reason", async () => {
    const history = vi.fn()
      .mockRejectedValueOnce(httpFailure(503, { error: "Questions are temporarily unavailable.", retryable: true }))
      .mockResolvedValueOnce({ data: { clarifications: [{ id: 21, event_id: 7,
        message: "Is a projector required?", sender: { id: 2, email: "current@test.invalid" },
        created_at: "2026-10-14T02:00:00" }], message: null } });
    apiClient.get.mockImplementation((url) => {
      if (url === "/events/7/clarifications") return history();
      throw new Error(`Unexpected API read: ${url}`);
    });
    const user = await renderPage();
    const thread = within(screen.getByRole("region", { name: "Clarification history" }));
    expect((await thread.findByRole("alert")).textContent).toBe("Questions are temporarily unavailable.");
    expect(screen.getByRole("heading", { name: "Review: Harbour Lights Festival" })).toBeTruthy();
    await enter(user, REASON);

    await user.click(thread.getByRole("button", { name: "Retry questions" }));

    expect(await thread.findByText("Is a projector required?")).toBeTruthy();
    expect(thread.queryByRole("alert")).toBeNull();
    expect(box().value).toBe(REASON);
    expect(apiClient.get.mock.calls.filter(([url]) => url === "/events/7/review")).toHaveLength(1);
    expect(history).toHaveBeenCalledTimes(2);
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("ignores a late history response after a different request is selected", async () => {
    let finishPrevious;
    const previous = new Promise((resolve) => { finishPrevious = resolve; });
    apiClient.get.mockImplementation(async (url) => {
      if (url === "/events/7/review") return { data: { request: request() } };
      if (url === "/events/7/clarifications") return previous;
      if (url === "/events/8/review") return { data: { request: request({ id: 8, title: "Workshop" }) } };
      if (url === "/events/8/clarifications") {
        return { data: { clarifications: [], message: "No workshop questions yet." } };
      }
      throw new Error(`Unexpected API read: ${url}`);
    });
    render(
      <MemoryRouter initialEntries={["/events/7/review"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Link to="/events/8/review">Open workshop</Link>
        <Routes><Route path="/events/:eventId/review" element={<ReviewRequestPage />} /></Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    expect(await screen.findByText("Loading questions…")).toBeTruthy();
    await user.click(screen.getByRole("link", { name: "Open workshop" }));
    expect(await screen.findByText("No workshop questions yet.")).toBeTruthy();

    await act(async () => {
      finishPrevious({ data: { clarifications: [{ id: 20, event_id: 7,
        message: "Private previous-event question", sender: { id: 2, email: "current@test.invalid" },
        created_at: "2026-10-14T02:00:00" }], message: null } });
    });

    expect(screen.getByRole("heading", { name: "Review: Workshop" })).toBeTruthy();
    expect(screen.getByText("No workshop questions yet.")).toBeTruthy();
    expect(screen.queryByText("Private previous-event question")).toBeNull();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});

describe("SCRUM-32 review an event request", () => {
  it("shows the request's details and status", async () => {
    await renderPage();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/review");
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
    expect(screen.getByText("Celebrate the harbour's reopening")).toBeTruthy();
    expect(screen.getByText("Open-air waterfront space")).toBeTruthy();
  });

  // SCRUM-60 changed this: Reject stays enabled and says a reason is required (TC-60-12).
  it("allows approving without text", async () => {
    await renderPage();
    expect(button("Approve").disabled).toBe(false);
    expect(button("Reject").disabled).toBe(false);
  });

  it("approves, shows Approved, and removes the buttons", async () => {
    apiClient.post.mockResolvedValue(decided("approved", null));
    const user = await renderPage();

    await user.click(button("Approve"));

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/decision", { decision: "approve" });
    expect(await screen.findByText("Status: Approved")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("approved");
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("rejects with the trimmed reason and shows it", async () => {
    apiClient.post.mockResolvedValue(decided("rejected", REASON));
    const user = await renderPage();

    await enter(user, `  ${REASON}  `);
    await user.click(button("Reject"));

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/decision", { decision: "reject", reason: REASON });
    expect(await screen.findByText("Status: Rejected")).toBeTruthy();
    expect(screen.getByText(`Reason: ${REASON}`)).toBeTruthy();
  });

  it("sends an approval note when one is typed", async () => {
    apiClient.post.mockResolvedValue(decided("approved", "Book the venue by 1 Nov."));
    const user = await renderPage();

    await enter(user, "Book the venue by 1 Nov.");
    await user.click(button("Approve"));

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/decision", { decision: "approve", reason: "Book the venue by 1 Nov." });
    expect(await screen.findByText("Note: Book the venue by 1 Nov.")).toBeTruthy();
  });

  it("counts words and blocks more than 1,000", async () => {
    const user = await renderPage();
    await enter(user, words(1000));
    expect(screen.getByText("1000 / 1000 words")).toBeTruthy();
    expect(button("Reject").disabled).toBe(false);
    await enter(user, words(1001));
    expect(screen.getByText(/remove 1 word/i)).toBeTruthy();
    expect(button("Reject").disabled).toBe(true);
    expect(button("Approve").disabled).toBe(true);
  });

  it.each([
    ["server error", httpFailure(503, { error: "The decision was not saved. Please try again.", retryable: true }), "The decision was not saved. Please try again."],
    ["already decided", httpFailure(409, { error: "This request is approved; only submitted requests can be approved or rejected." }), "only submitted requests"],
    ["no network", new Error("Network Error"), "The decision was not saved. Check your connection and try again."],
  ])("shows why the decision failed (%s) and keeps the reason", async (_label, failure, message) => {
    apiClient.post.mockRejectedValue(failure);
    const user = await renderPage();

    await enter(user, REASON);
    await user.click(button("Reject"));

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(box().value).toBe(REASON);
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
    expect(button("Reject").disabled).toBe(false);
  });

  it("says when the email could not be sent", async () => {
    apiClient.post.mockResolvedValue(decided("approved", null, false));
    const user = await renderPage();
    await user.click(button("Approve"));
    expect(await screen.findByText(/email could not be sent/i)).toBeTruthy();
  });

  it("shows the outcome without buttons for a request that is already decided", async () => {
    await renderPage(request({ status: "rejected", decision_note: "No licensed venue is available", decided_at: "2026-09-12T01:00:00" }));
    expect(screen.getByText("Status: Rejected")).toBeTruthy();
    expect(screen.getByText("Reason: No licensed venue is available")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByLabelText(/reason or note/i)).toBeNull();
  });

  it("shows a retryable error when the request cannot be loaded", async () => {
    apiClient.get
      .mockRejectedValueOnce(httpFailure(403, { error: "Only the event's assigned coordinator can review this request." }))
      .mockResolvedValueOnce({ data: { request: request() } });
    render(
      <MemoryRouter initialEntries={["/events/7/review"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes><Route path="/events/:eventId/review" element={<ReviewRequestPage />} /></Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    expect((await screen.findByRole("alert")).textContent).toContain("assigned coordinator");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Status: Submitted")).toBeTruthy();
  });
});

// Frontend cases TC-60-11 to TC-60-14 in docs/test-cases/SCRUM-60-accountable-decisions.md.
// The API side is backend/tests/test_decision_accountability.py.
describe("SCRUM-60 who decided and when, blank reasons and failed saves", () => {
  const ALICE = { id: 2, email: "alice.coordinator@connectsphere.test" };
  // Must match REASON_REQUIRED in backend/tests/test_decision_accountability.py.
  const REASON_REQUIRED = "A reason is required to reject this request.";
  const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

  it("confirms the outcome with who decided and when", async () => {
    apiClient.post.mockResolvedValue(decided("rejected", REASON));
    const user = await renderPage();

    await enter(user, REASON);
    await user.click(button("Reject"));

    const confirmation = within(await screen.findByRole("status"));
    expect(confirmation.getByText("The request was rejected. dana.organiser@connectsphere.test has been notified.")).toBeTruthy();
    expect(confirmation.getByText(`Decided by ${ALICE.email} · ${localTime("2026-09-28T03:00:00")}`)).toBeTruthy();
    expect(screen.getByText("Status: Rejected")).toBeTruthy();
    expect(screen.getByText(`Reason: ${REASON}`)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("shows who decided an already decided request", async () => {
    await renderPage(request({ status: "rejected", decision_note: "No licensed venue is available",
      decided_at: "2026-09-12T01:00:00", decided_by: ALICE }));
    expect(screen.getByText(`Decided ${localTime("2026-09-12T01:00:00")}`)).toBeTruthy();
    expect(screen.getByText(`Decided by ${ALICE.email}`)).toBeTruthy();
  });

  it("says when the decider was not recorded", async () => {
    await renderPage(request({ status: "approved", decided_at: "2026-09-10T01:00:00", decided_by: null }));
    expect(screen.getByText("Decided by: not recorded")).toBeTruthy();
  });

  it.each([
    ["no text", ""],
    ["spaces", "   "],
    ["a non-breaking space and a tab", "\u00a0\t"],
    ["a zero-width space", "\u200b"],
  ])("says a reason is required when rejecting with only spaces (%s)", async (_label, typed) => {
    const user = await renderPage();

    await enter(user, typed);
    await user.click(button("Reject"));

    expect((await screen.findByRole("alert")).textContent).toBe(REASON_REQUIRED);
    expect(box().getAttribute("aria-invalid")).toBe("true");
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
  });

  it("clears the message once a reason is typed", async () => {
    apiClient.post.mockResolvedValue(decided("rejected", REASON));
    const user = await renderPage();
    await user.click(button("Reject"));
    expect(await screen.findByRole("alert")).toBeTruthy();

    await enter(user, REASON);

    expect(screen.queryByRole("alert")).toBeNull();
    expect(box().getAttribute("aria-invalid")).not.toBe("true");
    await user.click(button("Reject"));
    expect(apiClient.post).toHaveBeenCalledWith("/events/7/decision", { decision: "reject", reason: REASON });
  });

  it("shows the server's refusal of the reason and keeps the text", async () => {
    apiClient.post.mockRejectedValue(httpFailure(400, { error: REASON_REQUIRED, field: "reason" }));
    const user = await renderPage();

    await enter(user, REASON);
    await user.click(button("Reject"));

    expect((await screen.findByRole("alert")).textContent).toBe(REASON_REQUIRED);
    expect(box().value).toBe(REASON);
    expect(box().getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
  });

  it("keeps the reason exactly as typed after a failed save and resends it on retry", async () => {
    const typed = "  The venue is double-booked.\nPlease pick another date.  ";
    const trimmed = "The venue is double-booked.\nPlease pick another date.";
    apiClient.post
      .mockRejectedValueOnce(httpFailure(503, { error: "The decision was not saved, so the request is still submitted. Please try again.", retryable: true }))
      .mockResolvedValueOnce(decided("rejected", trimmed));
    const user = await renderPage();

    await enter(user, typed);
    await user.click(button("Reject"));

    expect((await screen.findByRole("alert")).textContent).toContain("not saved");
    expect(box().value).toBe(typed);
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();

    await user.click(button("Reject"));

    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(apiClient.post).toHaveBeenCalledTimes(2);
    expect(apiClient.post.mock.calls[0][1]).toEqual({ decision: "reject", reason: trimmed });
    expect(apiClient.post.mock.calls[1][1]).toEqual({ decision: "reject", reason: trimmed });
  });
});

// Frontend cases TC-77-07 and TC-77-08 in docs/test-cases/SCRUM-77-approve-event-request.md.
// The API side is backend/tests/test_approve_event_request.py.
describe("SCRUM-77 only a submitted request can be approved", () => {
  // A request under review now offers the decision too (SCRUM-31 A13, TC-31-42).
  it.each([
    ["approved", "Approved"],
    ["draft", "Draft"],
    ["cancelled", "Cancelled"],
  ])("offers no Approve button for a %s request", async (status, label) => {
    await renderPage(request({ status }));
    expect(screen.getByText(`Status: ${label}`)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("shows the server's refusal when the request is no longer submitted", async () => {
    const refusal = "This request is approved; only submitted requests can be approved or rejected.";
    apiClient.post.mockRejectedValue(httpFailure(409, { error: refusal }));
    const user = await renderPage();

    await user.click(button("Approve"));

    expect((await screen.findByRole("alert")).textContent).toContain(refusal);
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
  });
});

// SCRUM-31 (reopened): the assigned coordinator starts reviewing a submitted request.
// Frontend cases TC-31-40 to 42 in docs/test-cases/SCRUM-31-event-clarification.md;
// the API contract mirrors backend/tests/test_event_review_start.py.
describe("SCRUM-31 start reviewing a request", () => {
  const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();
  const ALICE = { id: 2, email: "alice.coordinator@connectsphere.test" };
  const UNDER_REVIEW = request({
    status: "under_review", review_started_at: "2026-10-26T02:00:00", review_started_by: ALICE,
  });

  // TC-31-40 · AC8
  it("starts the review and keeps the decision available", async () => {
    apiClient.post.mockResolvedValue({
      data: { message: 'You started reviewing "Harbour Lights Festival".', request: UNDER_REVIEW },
    });
    const user = await renderPage();

    await user.click(button("Start review"));

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/review");
    expect(await screen.findByText("Status: Under review")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain('You started reviewing "Harbour Lights Festival".');
    expect(screen.getByText(`Review started by ${ALICE.email} on ${localTime("2026-10-26T02:00:00")}`)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start review" })).toBeNull();
    expect(button("Approve")).toBeTruthy();
    expect(button("Reject")).toBeTruthy();
  });

  // TC-31-41 · AC7, AC9, AC10
  it.each([
    ["not submitted", httpFailure(409, { error: "This request is approved; only a submitted request can be put under review." }), "only a submitted request"],
    ["not the coordinator", httpFailure(403, { error: "Only the event's assigned coordinator can start reviewing this request." }), "assigned coordinator"],
    ["a save failure", httpFailure(503, { error: "The review was not started, so the request is still submitted. Please try again.", retryable: true }), "not started"],
    ["no network", new Error("Network Error"), "Check your connection and try again"],
  ])("explains why the review could not be started (%s)", async (_label, failure, message) => {
    apiClient.post.mockRejectedValue(failure);
    const user = await renderPage();

    await user.click(button("Start review"));

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
    expect(button("Start review")).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });

  // TC-31-42 · AC8, AC9 (Q7)
  it("shows who started the review and offers the decision", async () => {
    await renderPage(UNDER_REVIEW);

    expect(screen.getByText("Status: Under review")).toBeTruthy();
    expect(screen.getByText(`Review started by ${ALICE.email} on ${localTime("2026-10-26T02:00:00")}`)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start review" })).toBeNull();
    expect(button("Approve")).toBeTruthy();
    expect(button("Reject")).toBeTruthy();
  });
});
