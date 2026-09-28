import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
  apiClient.get.mockResolvedValue({ data: { request: loaded } });
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
});

describe("SCRUM-32 review an event request", () => {
  it("shows the request's details and status", async () => {
    await renderPage();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/review");
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
    expect(screen.getByText("Celebrate the harbour's reopening")).toBeTruthy();
    expect(screen.getByText("Open-air waterfront space")).toBeTruthy();
  });

  it("allows approving without text, but needs a reason to reject", async () => {
    const user = await renderPage();
    expect(button("Approve").disabled).toBe(false);
    expect(button("Reject").disabled).toBe(true);
    await enter(user, "   ");
    expect(button("Reject").disabled).toBe(true);
    await enter(user, REASON);
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
