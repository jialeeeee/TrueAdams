import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import MyRegistrationsPage from "./MyRegistrationsPage.jsx";

// Frontend cases for TC-68-01 to TC-68-16 in docs/test-cases/SCRUM-68-event-withdrawal.md.
// The API itself is covered by backend/tests/test_event_withdrawal.py; these check what
// the attendee sees. Responses mirror that API's contract:
//   GET  /registrations/              -> { active: [item], history: [item], message }
//   POST /registrations/<id>/withdraw -> { message, registration, event }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

function item(id, title, status, canWithdraw, start = "2026-11-20T10:00:00") {
  return {
    id,
    event: { id: id + 100, title, start_time: start, end_time: start.replace("10:00", "12:00"), status: "confirmed" },
    status,
    registered_at: "2026-10-01T08:00:00",
    can_withdraw: canWithdraw,
  };
}

const CHEM = item(31, "Chem Open House", "registered", true);
const WORKSHOP = item(32, "Ongoing Workshop", "registered", false, "2026-10-13T09:00:00");
const NIGHT = item(33, "Waitlist Night", "waitlisted", true, "2026-12-01T10:00:00");
const ROBOTICS = item(34, "Robotics Day", "withdrawn", false, "2026-12-05T10:00:00");

function list(active, history = [], message = null) {
  return { data: { active, history, message } };
}

function withdrawn(message = "You've withdrawn from Chem Open House.") {
  return {
    data: {
      message,
      registration: { id: 31, event_id: 131, status: "withdrawn", registered_at: "2026-10-01T08:00:00" },
      event: { id: 131, registered_count: 1, slots_remaining: 4 },
    },
  };
}

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true,
    response: { status, data },
  });
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/my-registrations"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/my-registrations" element={<MyRegistrationsPage />} />
        <Route path="/login" element={<p>Sign-in page</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const withdrawButton = (title) => screen.getByRole("button", { name: `Withdraw from ${title}` });

async function openConfirmation(user, title = "Chem Open House") {
  await screen.findByRole("heading", { name: "My registrations" });
  await user.click(withdrawButton(title));
  return screen.getByRole("dialog");
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("SCRUM-68 my registrations", () => {
  it("lists the attendee's active registrations with their event, start time and status", async () => {
    apiClient.get.mockResolvedValue(list([CHEM, NIGHT]));
    renderPage();

    expect(await screen.findByRole("heading", { name: "My registrations" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/registrations/");
    expect(screen.getByText("Chem Open House")).toBeTruthy();
    expect(screen.getByText("Starts: 20/11/2026 10:00 SGT")).toBeTruthy();
    expect(screen.getByText("Status: Registered")).toBeTruthy();
    expect(screen.getByText("Status: Waitlisted")).toBeTruthy();
  });

  it("offers Withdraw only where the server says withdrawing is possible", async () => {
    apiClient.get.mockResolvedValue(list([CHEM, WORKSHOP]));
    renderPage();

    expect(await screen.findByRole("button", { name: "Withdraw from Chem Open House" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Withdraw from Ongoing Workshop" })).toBeNull();
    expect(screen.getByText("Ongoing Workshop")).toBeTruthy();
  });

  it("shows withdrawn registrations in the history, with no Withdraw button", async () => {
    apiClient.get.mockResolvedValue(list([CHEM], [ROBOTICS]));
    renderPage();

    await screen.findByRole("heading", { name: "My registrations" });
    const history = screen.getByRole("region", { name: "History" });

    expect(within(history).getByText("Robotics Day")).toBeTruthy();
    expect(within(history).getByText("Status: Withdrawn")).toBeTruthy();
    expect(within(history).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("button", { name: "Withdraw from Robotics Day" })).toBeNull();
  });

  it("shows the server's message when there are no registrations", async () => {
    apiClient.get.mockResolvedValue(list([], [], "You have no registrations."));
    renderPage();

    expect(await screen.findByText("You have no registrations.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^withdraw/i })).toBeNull();
  });

  it("shows why the list could not be loaded and lets the attendee try again", async () => {
    apiClient.get
      .mockRejectedValueOnce(httpFailure(503, { error: "Your registrations could not be loaded. Please try again.", retryable: true }))
      .mockResolvedValueOnce(list([CHEM]));
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("Your registrations could not be loaded. Please try again.");
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Chem Open House")).toBeTruthy();
  });

  it("sends a signed-out user to the sign-in page and shows no registrations", async () => {
    apiClient.get.mockRejectedValue(httpFailure(401, { msg: "Missing Authorization Header" }));
    renderPage();

    expect(await screen.findByText("Sign-in page")).toBeTruthy();
    expect(screen.queryByText("Chem Open House")).toBeNull();
  });
});

describe("SCRUM-68 withdrawing", () => {
  it("asks for confirmation first, and cancelling leaves the registration unchanged", async () => {
    apiClient.get.mockResolvedValue(list([CHEM]));
    const user = renderPage();

    const dialog = await openConfirmation(user);

    expect(within(dialog).getByRole("heading", { name: /withdraw from chem open house/i })).toBeTruthy();
    expect(apiClient.post).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(screen.getByText("Status: Registered")).toBeTruthy();
    expect(withdrawButton("Chem Open House")).toBeTruthy();
  });

  it("withdraws on confirmation, shows the success message and moves the registration to the history", async () => {
    apiClient.get.mockResolvedValue(list([CHEM, NIGHT]));
    apiClient.post.mockResolvedValue(withdrawn());
    const user = renderPage();
    const dialog = await openConfirmation(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));

    expect(apiClient.post).toHaveBeenCalledWith("/registrations/31/withdraw");
    expect((await screen.findByRole("status")).textContent).toContain("You've withdrawn from Chem Open House.");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("button", { name: "Withdraw from Chem Open House" })).toBeNull();
    const history = screen.getByRole("region", { name: "History" });
    expect(within(history).getByText("Chem Open House")).toBeTruthy();
    expect(within(history).getByText("Status: Withdrawn")).toBeTruthy();
    // The other registration is untouched.
    expect(withdrawButton("Waitlist Night")).toBeTruthy();
  });

  it("sends one request when Confirm is clicked twice", async () => {
    apiClient.get.mockResolvedValue(list([CHEM]));
    apiClient.post.mockReturnValue(new Promise(() => {}));
    const user = renderPage();
    const dialog = await openConfirmation(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));
    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));

    expect(apiClient.post).toHaveBeenCalledTimes(1);
  });

  it.each([
    [409, { error: "You have already withdrawn from this event.", reason: "already_withdrawn" }],
    [409, { error: "This event has already started, so you can no longer withdraw.", reason: "event_started" }],
    [409, { error: "This event has been cancelled, so there is nothing to withdraw from.", reason: "event_cancelled" }],
    [403, { error: "You can only withdraw your own registration." }],
  ])("shows the server's message for a %i and leaves the registration as it was", async (status, data) => {
    apiClient.get.mockResolvedValue(list([CHEM]));
    apiClient.post.mockRejectedValue(httpFailure(status, data));
    const user = renderPage();
    const dialog = await openConfirmation(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));

    expect((await screen.findByRole("alert")).textContent).toContain(data.error);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText("Status: Registered")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "History" })).toBeNull();
  });

  it("shows an error when saving fails, keeps the registration and lets the attendee try again", async () => {
    apiClient.get.mockResolvedValue(list([CHEM]));
    apiClient.post
      .mockRejectedValueOnce(httpFailure(503, { error: "Your withdrawal was not saved. Please try again.", retryable: true }))
      .mockResolvedValueOnce(withdrawn());
    const user = renderPage();
    const dialog = await openConfirmation(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Your withdrawal was not saved. Please try again.");
    expect(screen.getByText("Status: Registered")).toBeTruthy();
    expect(withdrawButton("Chem Open House").disabled).toBe(false);

    await user.click(withdrawButton("Chem Open House"));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirm" }));
    expect((await screen.findByRole("status")).textContent).toContain("You've withdrawn from Chem Open House.");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockResolvedValue(list([CHEM]));
    apiClient.post.mockRejectedValue(new Error("Network Error"));
    const user = renderPage();
    const dialog = await openConfirmation(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Your withdrawal was not saved. Check your connection and try again.",
    );
    expect(screen.getByText("Status: Registered")).toBeTruthy();
  });
});
