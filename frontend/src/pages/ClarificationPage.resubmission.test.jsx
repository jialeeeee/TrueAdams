// SCRUM-95 TC-95-01..05: docs/test-cases/SCRUM-95-clarification-resubmission.md
// Backend counterpart: backend/tests/test_clarification_resubmission.py.
// Proposed organiser additions to the existing clarification page/API (A1, A3).
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ClarificationPage from "./ClarificationPage.jsx";

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const QUESTION = "Who will staff the accessible entrance?";
const REPLY = "The accessible entrance will be staffed throughout the event.";
const DESCRIPTION = "An updated description with the accessible entrance arrangements.";
const SAVE_ERROR = "Your reply and changes were not saved. Please try again.";
// Must match MAX_CLARIFICATION_WORDS in backend/app/events/routes.py (AC2).
const MAX_WORDS = 1000;

function thread() {
  return {
    event: {
      id: 7, title: "Charity Gala", status: "under_review",
      organiser: { id: 1, email: "owner@test.invalid" },
    },
    editable_fields: {
      title: "Charity Gala",
      description: "Original description", purpose: "Fundraising", accessibility_needs: null,
    },
    clarifications: [{
      id: 20, event_id: 7, message: QUESTION,
      sender: { id: 2, email: "coordinator@test.invalid" },
      created_at: "2026-10-29T03:00:00",
    }],
    can_send: false, can_resubmit: true, message: null,
  };
}

async function openPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/clarifications"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/clarifications" element={<ClarificationPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByText(QUESTION);
  return userEvent.setup();
}

async function replace(user, field, text) {
  await user.clear(field);
  if (text) {
    await user.click(field);
    await user.paste(text);
  }
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
  apiClient.get.mockImplementation(async (url) => {
    if (url === "/events/7/clarifications") return { data: thread() };
    throw new Error(`Unexpected SCRUM-95 read: ${url}`);
  });
});

describe("SCRUM-95 organiser clarification resubmission", () => {
  // TC-95-01..04 / AC1..4: existing history plus reply, normal edit, resubmit.
  it("shows the question and resubmits a reply with a permitted description edit", async () => {
    apiClient.post.mockResolvedValue({ data: {
      message: "Your request has been resubmitted for review.",
      request: { id: 7, status: "submitted", description: DESCRIPTION },
      notification: { in_app: true, email_queued: true },
    } });
    const user = await openPage();
    const reply = screen.getByRole("textbox", { name: /your reply/i });
    const description = screen.getByRole("textbox", { name: /^description$/i });
    expect(description.value).toBe("Original description");
    await replace(user, reply, REPLY);
    await replace(user, description, DESCRIPTION);
    await user.click(screen.getByRole("button", { name: /resubmit/i }));

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/events/7/resubmit", {
      message: REPLY, changes: { description: DESCRIPTION },
    }));
    expect((await screen.findByRole("status")).textContent).toMatch(/resubmitted.*review/i);
    expect(screen.getByText(/status: submitted/i)).toBeTruthy();
  });

  // TC-95-02, TC-95-05 / AC2, AC5: validation and retained entries in one flow.
  it("blocks blank and over-limit replies and retains both entries after a save error", async () => {
    apiClient.post.mockRejectedValue({ response: {
      status: 503, data: { error: SAVE_ERROR, retryable: true },
    } });
    const user = await openPage();
    const reply = screen.getByRole("textbox", { name: /your reply/i });
    const description = screen.getByRole("textbox", { name: /^description$/i });
    const resubmit = screen.getByRole("button", { name: /resubmit/i });
    expect(resubmit.disabled).toBe(true);
    await replace(user, reply, "  \n\t ");
    expect(resubmit.disabled).toBe(true);
    await replace(user, reply, "word ".repeat(MAX_WORDS + 1));
    expect(resubmit.disabled).toBe(true);
    await user.click(resubmit);
    expect(apiClient.post).not.toHaveBeenCalled();

    // Exactly 1,000 words and more than 1,000 characters must remain valid.
    const limitReply = Array(MAX_WORDS).fill("reply").join(" ");
    await replace(user, reply, limitReply);
    await replace(user, description, DESCRIPTION);
    expect(resubmit.disabled).toBe(false);
    await user.click(resubmit);
    expect((await screen.findByRole("alert")).textContent).toContain(SAVE_ERROR);
    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(reply.value).toBe(limitReply);
    expect(description.value).toBe(DESCRIPTION);
    expect(resubmit.disabled).toBe(false);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText(/status: under[ _]review/i)).toBeTruthy();
  });

  // TC-95-03/05: a coordinator decision closes eligibility while composing.
  it("refreshes eligibility after a stale 409 and keeps the entries without offering resubmission", async () => {
    const decided = { ...thread(), can_resubmit: false, editable_fields: {},
      event: { ...thread().event, status: "approved" } };
    apiClient.get.mockResolvedValueOnce({ data: thread() }).mockResolvedValueOnce({ data: decided });
    const error = "This request is not awaiting a clarification reply. Reload its questions.";
    apiClient.post.mockRejectedValue({ response: { status: 409, data: { error } } });
    const user = await openPage();
    await replace(user, screen.getByRole("textbox", { name: /your reply/i }), REPLY);
    await replace(user, screen.getByRole("textbox", { name: /^description$/i }), DESCRIPTION);
    await user.click(screen.getByRole("button", { name: /resubmit/i }));

    expect((await screen.findByRole("alert")).textContent).toContain(error);
    await screen.findByText(/status: approved/i);
    expect(apiClient.get).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("textbox", { name: /your reply/i }).value).toBe(REPLY);
    expect(screen.getByRole("textbox", { name: /^description$/i }).value).toBe(DESCRIPTION);
    const resubmit = screen.getByRole("button", { name: /resubmit/i });
    expect(resubmit.disabled).toBe(true);
    await user.click(resubmit);
    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
