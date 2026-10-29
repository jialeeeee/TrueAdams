// SCRUM-92 TC-92-01/02/03/06: docs/test-cases/SCRUM-92-safety-rejection-changes.md;
// backend/tests/test_safety_rejection_changes.py. A1 documents proposed action URLs.
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SafetyCheckQueuePage from "./SafetyCheckQueuePage.jsx";
import EventPlanningPage from "./EventPlanningPage.jsx";
import apiClient from "../api/client.js";

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const EVENT = {
  id: 1, title: "Safety corrections workshop", start_time: "2030-01-16T17:00:00",
  end_time: "2030-01-16T19:00:00", expected_attendance: 40,
  venues: [{ id: 10, name: "Meeting Room" }], equipment: [],
};
const COMMENT = "Keep the emergency exit clear and describe the revised access route.";
const FAILED = "The safety decision was not saved. Please try again.";
const ACTIONS = [
  { path: "reject", decision: "rejected", button: /^reject(?: safety check)?$/i,
    message: "Safety check rejected.", label: "Rejected" },
  { path: "request-changes", decision: "changes_requested", button: /^request changes$/i,
    message: "Safety changes requested.", label: "Changes requested" },
];

async function openQueue() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <SafetyCheckQueuePage />
    </MemoryRouter>,
  );
  const title = await screen.findByRole("heading", { name: EVENT.title });
  return { user: userEvent.setup(), row: within(title.closest("li, tr")) };
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
  apiClient.get.mockResolvedValue({ data: { events: [EVENT], message: null } });
});

describe("SCRUM-92 rejection and changes in the existing safety queue", () => {
  // TC-92-01/02/03 / AC1/2/3: both actions, required comment, success and reuse
  // of the existing coordinator view. No separate page or corrective workflow.
  it("requires a comment for both actions, shows success and exposes the coordinator outcome", async () => {
    for (const action of ACTIONS) {
      apiClient.get.mockResolvedValue({ data: { events: [EVENT], message: null } });
      apiClient.post.mockReset();
      const summary = { decision: action.decision, comment: COMMENT,
        officer: { id: 92, email: "officer@test.invalid" }, decided_at: "2026-10-29T08:00:00" };
      apiClient.post.mockResolvedValue({ data: { message: action.message,
        safety_check: summary, notification: { in_app: true, email_queued: true } } });
      const { user, row } = await openQueue();
      const input = row.getByRole("textbox", { name: /comment/i });
      const button = row.getByRole("button", { name: action.button });
      await user.click(button);
      expect(apiClient.post).not.toHaveBeenCalled();
      await user.type(input, "   ");
      await user.click(button);
      expect(apiClient.post).not.toHaveBeenCalled();
      expect(screen.queryByText(action.message)).toBeNull();
      await user.clear(input);
      await user.type(input, COMMENT);
      await user.click(button);
      expect(apiClient.post).toHaveBeenCalledTimes(1);
      expect(apiClient.post).toHaveBeenCalledWith(`/events/1/safety-checks/${action.path}`, { comment: COMMENT });
      expect(await screen.findByText(action.message)).toBeTruthy();
      cleanup();

      apiClient.get.mockResolvedValue({ data: { ...EVENT, status: "approved",
        coordinator: { id: 2, email: "current@test.invalid" }, safety_check: summary } });
      render(
        <MemoryRouter initialEntries={["/events/1/planning"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes><Route path="/events/:eventId/planning" element={<EventPlanningPage />} /></Routes>
        </MemoryRouter>,
      );
      await screen.findByRole("heading", { name: EVENT.title });
      const outcome = within(screen.getByRole("region", { name: "Safety check" }));
      expect(outcome.getByText(`Decision: ${action.label}`)).toBeTruthy();
      expect(outcome.getByText(`Comment: ${COMMENT}`)).toBeTruthy();
      cleanup();
    }
  });

  // TC-92-06 / AC6: the backend error is visible and the comment survives retry.
  it("shows a failed save for either action without success or losing the comment", async () => {
    for (const action of ACTIONS) {
      apiClient.post.mockReset();
      apiClient.post.mockRejectedValue({ response: {
        status: 503, data: { error: FAILED, retryable: true },
      } });
      const { user, row } = await openQueue();
      await user.type(row.getByRole("textbox", { name: /comment/i }), COMMENT);
      await user.click(row.getByRole("button", { name: action.button }));
      expect((await screen.findByRole("alert")).textContent).toBe(FAILED);
      expect(apiClient.post).toHaveBeenCalledWith(`/events/1/safety-checks/${action.path}`, { comment: COMMENT });
      expect(row.getByRole("textbox", { name: /comment/i }).value).toBe(COMMENT);
      expect(screen.getByRole("heading", { name: EVENT.title })).toBeTruthy();
      expect(screen.queryByText(action.message)).toBeNull();
      // Submit again to verify retry is available with the same retained input.
      await user.click(row.getByRole("button", { name: action.button }));
      expect(apiClient.post).toHaveBeenCalledTimes(2);
      cleanup();
    }
  });
});
