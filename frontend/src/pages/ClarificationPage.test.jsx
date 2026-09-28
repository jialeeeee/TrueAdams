import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ClarificationPage from "./ClarificationPage.jsx";

// Frontend cases TC-31-14, 15, 18 and 21 in
// docs/test-cases/SCRUM-31-event-clarification.md.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const URL = "/events/7/clarifications";
const ORGANISER = "dana.organiser@connectsphere.test";
const QUESTION = "Do any guests need wheelchair access?";
const EARLIER = {
  id: 1, event_id: 7, message: "What is the expected attendance?",
  sender: { id: 2, email: "alice.coordinator@connectsphere.test" },
  created_at: "2026-09-28T02:00:00",
};

function thread(clarifications = [EARLIER]) {
  return {
    data: {
      event: { id: 7, title: "Charity Gala", status: "submitted", organiser: { id: 5, email: ORGANISER } },
      clarifications,
      message: clarifications.length ? null : "No questions have been sent for this event yet.",
    },
  };
}

function sent(message = QUESTION, emailQueued = true) {
  return {
    status: 201,
    data: {
      message: `Your question was sent to ${ORGANISER}.`,
      clarification: { ...EARLIER, id: 2, message, created_at: "2026-09-28T03:00:00" },
      notification: { in_app: true, email_queued: emailQueued },
    },
  };
}

function httpFailure(status, error) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true,
    response: { status, data: { error, ...(status === 503 ? { retryable: true } : {}) } },
  });
}

function words(count) {
  return Array.from({ length: count }, (_, i) => `w${i}`).join(" ");
}

async function renderPage() {
  render(
    <MemoryRouter initialEntries={[URL]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/clarifications" element={<ClarificationPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: /Charity Gala/ });
  return userEvent.setup();
}

const box = () => screen.getByLabelText(/your question/i);
const sendButton = () => screen.getByRole("button", { name: "Send question" });

// Pasting is much faster than typing 1,000 words key by key.
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
  apiClient.get.mockResolvedValue(thread());
});

describe("SCRUM-31 request clarification", () => {
  it("loads the event and its earlier questions", async () => {
    await renderPage();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/clarifications");
    expect(screen.getByText(new RegExp(ORGANISER))).toBeTruthy();
    expect(screen.getByText(EARLIER.message)).toBeTruthy();
  });

  it("shows an empty state when no questions have been sent", async () => {
    apiClient.get.mockResolvedValue(thread([]));
    await renderPage();
    expect(screen.getByText(/no questions have been sent/i)).toBeTruthy();
  });

  // TC-31-21 · AC5
  it("does not allow an empty or whitespace-only question to be sent", async () => {
    const user = await renderPage();
    expect(sendButton().disabled).toBe(true);
    await enter(user, "   \n  ");
    expect(sendButton().disabled).toBe(true);
    await user.click(sendButton());
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  // TC-31-14 · AC2, AC4
  it("counts words live and allows exactly 1,000", async () => {
    const user = await renderPage();
    await enter(user, words(1000));
    expect(screen.getByText("1000 / 1000 words")).toBeTruthy();
    expect(sendButton().disabled).toBe(false);
  });

  // TC-31-14 · AC2, AC4
  it("blocks 1,001 words and explains how many to remove", async () => {
    const user = await renderPage();
    await enter(user, words(1001));
    expect(screen.getByText("1001 / 1000 words")).toBeTruthy();
    expect(screen.getByText(/remove 1 word/i)).toBeTruthy();
    expect(sendButton().disabled).toBe(true);
    await user.click(sendButton());
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  // TC-31-15 · AC1, AC3
  it("sends the question, confirms it was sent, clears the box and lists it", async () => {
    apiClient.post.mockResolvedValue(sent());
    const user = await renderPage();
    await enter(user, `  ${QUESTION} `);
    await user.click(sendButton());

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/clarifications", { message: QUESTION });
    expect(await screen.findByText(`Your question was sent to ${ORGANISER}.`)).toBeTruthy();
    expect(box().value).toBe("");
    expect(screen.getByText(QUESTION)).toBeTruthy();
  });

  // TC-31-15 · AC3, AC6 (A6)
  it("says when the email could not be sent even though the question was", async () => {
    apiClient.post.mockResolvedValue(sent(QUESTION, false));
    const user = await renderPage();
    await enter(user, QUESTION);
    await user.click(sendButton());
    expect(await screen.findByText(/email could not be sent/i)).toBeTruthy();
  });

  // TC-31-18 · AC4
  it.each([
    [400, "Your question is 1,001 words long. The limit is 1,000 words."],
    [403, "Only the event's assigned coordinator can send clarification questions."],
    [409, "Questions cannot be sent for a cancelled event."],
    [503, "Your question was not sent. Please try again."],
  ])("shows the server's %s explanation and keeps the question for resending", async (status, error) => {
    apiClient.post.mockRejectedValue(httpFailure(status, error));
    const user = await renderPage();
    await enter(user, QUESTION);
    await user.click(sendButton());

    expect((await screen.findByRole("alert")).textContent).toContain(error);
    expect(box().value).toBe(QUESTION);
    expect(sendButton().disabled).toBe(false);
  });

  // TC-31-18 · AC4
  it("asks the user to check their connection when there is no response", async () => {
    apiClient.post.mockRejectedValue(new Error("Network Error"));
    const user = await renderPage();
    await enter(user, QUESTION);
    await user.click(sendButton());

    expect((await screen.findByRole("alert")).textContent).toMatch(/not sent.*connection.*try again/i);
    expect(box().value).toBe(QUESTION);
  });

  // TC-31-17 · AC4
  it("sends successfully on retry after a failure", async () => {
    apiClient.post
      .mockRejectedValueOnce(httpFailure(503, "Your question was not sent. Please try again."))
      .mockResolvedValueOnce(sent());
    const user = await renderPage();
    await enter(user, QUESTION);
    await user.click(sendButton());
    await screen.findByRole("alert");
    await user.click(sendButton());

    expect(await screen.findByText(`Your question was sent to ${ORGANISER}.`)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(apiClient.post).toHaveBeenCalledTimes(2);
  });

  it("shows a retryable error if the event cannot be loaded", async () => {
    apiClient.get
      .mockRejectedValueOnce(httpFailure(503, "The questions could not be loaded. Please try again."))
      .mockResolvedValueOnce(thread());
    render(
      <MemoryRouter initialEntries={[URL]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/events/:eventId/clarifications" element={<ClarificationPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    expect((await screen.findByRole("alert")).textContent).toMatch(/could not be loaded/i);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /Charity Gala/ })).toBeTruthy());
  });
});
