// SCRUM-55 TC-55-06..08: UNEXECUTED RED preparation.
// docs/test-cases/SCRUM-55-review-submitted-event-request.md and
// backend/tests/test_review_requests_unit.py. The list route/payload below are
// proposed additive contracts. Render the existing App so missing route wiring
// fails a visible-behavior assertion, not an import of a nonexistent component.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App.jsx";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const SUMMARY = {
  id: 8, title: "Accessibility workshop", status: "submitted",
  organiser: { id: 1, email: "owner@test.invalid" },
  start_time: "2026-12-12T17:00:00", submitted_at: "2026-10-14T01:00:00",
};
// User-confirmed SCRUM-55 eligibility: submitted and under_review only.
const UNDER_REVIEW = { ...SUMMARY, id: 11, title: "Access plan under review", status: "under_review" };
const LIST = { requests: [SUMMARY, UNDER_REVIEW], message: null };

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/review-requests"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("SCRUM-55 submitted requests list (UNEXECUTED)", () => {
  // TC-55-06: AC1, AC2, AC4. Eligibility is tested at the backend boundary.
  it("displays the summary fields and opens the selected request for review", async () => {
    apiClient.get.mockImplementation(async (url) => {
      if (url === "/events/review-requests") return { data: LIST };
      if (url === "/events/8/review") {
        return { data: { request: { ...SUMMARY, purpose: "Improve access" } } };
      }
      if (url === "/events/8/clarifications") {
        return { data: { event: SUMMARY, clarifications: [], can_send: true,
          message: "No questions have been sent for this event yet." } };
      }
      throw new Error(`Unexpected API read: ${url}`);
    });
    const user = renderPage();

    const link = await screen.findByRole("link", { name: SUMMARY.title });
    // Scope assertions to this request's visible row, not shared navigation.
    const row = within(link.closest("li, tr"));
    expect(row.getByText(/owner@test\.invalid/)).toBeTruthy();
    expect(row.getByText(/2026-12-12 17:00/)).toBeTruthy();
    // Reuse the established UTC audit-time formatter; do not dictate a new zone.
    expect(row.getByText((text) => text.includes(formatSavedAt(SUMMARY.submitted_at)))).toBeTruthy();
    expect(row.getByText("Status: Submitted")).toBeTruthy();
    expect(link.getAttribute("href")).toBe("/events/8/review");
    const reviewingLink = screen.getByRole("link", { name: UNDER_REVIEW.title });
    expect(within(reviewingLink.closest("li, tr")).getByText(/Under review/)).toBeTruthy();
    expect(reviewingLink.getAttribute("href")).toBe("/events/11/review");
    await user.click(link);
    expect(await screen.findByRole("heading", { name: `Review: ${SUMMARY.title}` })).toBeTruthy();
    expect(screen.getByText("Improve access")).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/8/review");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  // TC-55-07: AC3. Empty review queue, not the SCRUM-62 no-assignment state.
  it("shows the empty review-list message", async () => {
    apiClient.get.mockResolvedValue({ data: { requests: [],
      message: "You have no submitted event requests to review." } });
    renderPage();

    expect(await screen.findByText("You have no submitted event requests to review.")).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/review-requests");
    expect(screen.queryByRole("link", { name: SUMMARY.title })).toBeNull();
  });

  // TC-55-15: direct navigation must respect the API's session/role refusal.
  it.each([
    [401, "Your session is no longer valid. Please log in again."],
    [403, "Only event coordinators can view requests for review."],
  ])("shows a %s refusal without exposing request data", async (status, error) => {
    apiClient.get.mockRejectedValue({ response: { status, data: { error } } });
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toBe(error);
    expect(screen.queryByRole("link", { name: SUMMARY.title })).toBeNull();
    expect(screen.queryByText(/owner@test\.invalid/)).toBeNull();
    expect(apiClient.get).toHaveBeenCalledWith("/events/review-requests");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  // TC-55-08: AC7. Same user action for server and transport failures.
  it.each([
    ["server", Object.assign(new Error("Unavailable"), { response: { status: 503,
      data: { error: "Review requests could not be loaded. Please try again.", retryable: true } } }),
    "Review requests could not be loaded. Please try again."],
    ["network", new Error("Network Error"), /could not be loaded|check your connection/i],
  ])("explains a %s failure and recovers after Retry", async (_kind, failure, message) => {
    apiClient.get.mockRejectedValueOnce(failure).mockResolvedValueOnce({ data: LIST });
    const user = renderPage();

    const alert = await screen.findByRole("alert");
    if (typeof message === "string") expect(alert.textContent).toContain(message);
    else expect(alert.textContent).toMatch(message);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: SUMMARY.title })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(apiClient.get.mock.calls).toEqual([
      ["/events/review-requests"], ["/events/review-requests"],
    ]);
  });
});
