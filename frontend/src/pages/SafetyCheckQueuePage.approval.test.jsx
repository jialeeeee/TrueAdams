// SCRUM-91 TC-91-01/05: docs/test-cases/SCRUM-91-safety-approval.md;
// backend/tests/test_safety_approval.py. A1/Q1 describes the proposed API contract.
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SafetyCheckQueuePage from "./SafetyCheckQueuePage.jsx";
import EventPlanningPage from "./EventPlanningPage.jsx";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const EVENT = {
  id: 1, title: "Safety review meeting", start_time: "2030-01-16T17:00:00",
  end_time: "2030-01-16T19:00:00", expected_attendance: 40,
  venues: [{ id: 10, name: "Meeting Room" }], equipment: [],
};
const COMMENT = "Exits and access routes checked.";
const FAILED = "The safety decision was not saved. Please try again.";
const SAFETY_CHECK = { decision: "approved", comment: COMMENT,
  officer: { id: 91, email: "officer@test.invalid" }, decided_at: "2026-10-28T08:00:00" };

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

describe("SCRUM-91 approval in the existing safety queue", () => {
  // TC-91-01/02 / AC1/2: optional comment paths and existing coordinator view.
  it("approves with or without a comment and shows success feedback", async () => {
    for (const comment of [COMMENT, ""]) {
      apiClient.post.mockReset();
      apiClient.post.mockResolvedValue({ data: {
        message: "Safety check approved.",
        safety_check: { ...SAFETY_CHECK, comment: comment || null },
        notification: { in_app: true, email_queued: true },
      } });
      const { user, row } = await openQueue();
      const input = row.getByRole("textbox", { name: /comment/i });
      if (comment) await user.type(input, comment);
      await user.click(row.getByRole("button", { name: /^approve(?: safety check)?$/i }));
      expect(apiClient.post).toHaveBeenCalledTimes(1);
      expect(apiClient.post.mock.calls[0][0]).toBe("/events/1/safety-checks/approve");
      expect(apiClient.post.mock.calls[0][1]?.comment ?? null).toBe(comment || null);
      expect(await screen.findByText("Safety check approved.")).toBeTruthy();
      cleanup();
    }
    apiClient.get.mockResolvedValue({ data: { ...EVENT, status: "approved",
      coordinator: { id: 92, email: "coordinator@test.invalid" }, safety_check: SAFETY_CHECK } });
    render(
      <MemoryRouter initialEntries={["/events/1/planning"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes><Route path="/events/:eventId/planning" element={<EventPlanningPage />} /></Routes>
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: EVENT.title });
    const summary = within(screen.getByRole("region", { name: "Safety check" }));
    expect(summary.getByText("Decision: Approved")).toBeTruthy();
    expect(summary.getByText("Safety Officer: officer@test.invalid")).toBeTruthy();
    expect(summary.getByText(`Comment: ${COMMENT}`)).toBeTruthy();
    expect(summary.getByText(`Decided: ${formatSavedAt(SAFETY_CHECK.decided_at)}`)).toBeTruthy();
  });

  // TC-91-05 / AC5: a backend save failure is shown without false approval.
  it("shows the save error and keeps the event unapproved with its comment", async () => {
    apiClient.post.mockRejectedValue({ response: {
      status: 503, data: { error: FAILED, retryable: true },
    } });
    const { user, row } = await openQueue();
    await user.type(row.getByRole("textbox", { name: /comment/i }), COMMENT);
    await user.click(row.getByRole("button", { name: /^approve(?: safety check)?$/i }));
    expect((await screen.findByRole("alert")).textContent).toBe(FAILED);
    expect(apiClient.post).toHaveBeenCalledWith("/events/1/safety-checks/approve", { comment: COMMENT });
    expect(screen.getByRole("heading", { name: EVENT.title })).toBeTruthy();
    expect(row.getByRole("textbox", { name: /comment/i }).value).toBe(COMMENT);
    expect(screen.queryByText("Safety check approved.")).toBeNull();
    expect(screen.queryByText(/^approved$/i)).toBeNull();
  });
});
