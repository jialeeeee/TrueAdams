import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import NotificationsPage from "./NotificationsPage.jsx";

// Mirrors backend/tests/test_notifications.py: GET /api/notifications/ and
// POST /api/notifications/<id>/read.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

const UNREAD = {
  id: 2, kind: "venue_booking_approved", event_id: 7, read_at: null,
  message: "Your venue request for \"Harbour Lights Festival\" was approved.",
  created_at: "2026-10-02T01:00:00",
};
const READ = {
  id: 1, kind: "venue_hold_placed", event_id: 7, read_at: "2026-10-01T03:00:00",
  message: "gus placed a tentative hold on Aurora Ballroom.",
  created_at: "2026-10-01T01:00:00",
};

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <NotificationsPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("notifications", () => {
  it("lists the user's notifications, newest first, marking the unread ones", async () => {
    apiClient.get.mockResolvedValue({ data: { notifications: [UNREAD, READ], message: null } });
    renderPage();

    const items = await screen.findAllByRole("listitem");
    expect(apiClient.get).toHaveBeenCalledWith("/notifications/");
    expect(items[0].textContent).toContain(`New · Received ${localTime(UNREAD.created_at)}`);
    expect(items[0].textContent).toContain(UNREAD.message);
    expect(within(items[0]).getByRole("button", { name: "Mark as read" })).toBeTruthy();
    expect(items[1].textContent).not.toContain("New");
    expect(within(items[1]).queryByRole("button")).toBeNull();
  });

  it("says so when there are none", async () => {
    apiClient.get.mockResolvedValue({ data: { notifications: [], message: "You have no notifications." } });
    renderPage();

    expect(await screen.findByText("You have no notifications.")).toBeTruthy();
  });

  it("marks one notification read and leaves the others as they were", async () => {
    const other = { ...UNREAD, id: 3, message: "Another update." };
    apiClient.get.mockResolvedValue({ data: { notifications: [UNREAD, other], message: null } });
    apiClient.post.mockResolvedValue({ data: { notification: { ...UNREAD, read_at: "2026-10-02T02:00:00" } } });
    const user = renderPage();

    const [first] = await screen.findAllByRole("listitem");
    await user.click(within(first).getByRole("button", { name: "Mark as read" }));

    expect(apiClient.post).toHaveBeenCalledWith("/notifications/2/read");
    const [marked, untouched] = screen.getAllByRole("listitem");
    expect(within(marked).queryByRole("button")).toBeNull();
    expect(marked.textContent).not.toContain("New");
    expect(untouched.textContent).toContain("New");
    expect(within(untouched).getByRole("button", { name: "Mark as read" })).toBeTruthy();
  });

  it("shows why marking failed and lets the user try again when it can be retried", async () => {
    apiClient.get.mockResolvedValue({ data: { notifications: [UNREAD], message: null } });
    apiClient.post.mockRejectedValueOnce({
      response: { data: { error: "The notification could not be marked as read. Please try again.", retryable: true } },
    });
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Mark as read" }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "The notification could not be marked as read. Please try again. You can try again.",
    );
    expect(screen.getByRole("button", { name: "Mark as read" }).disabled).toBe(false);
  });

  it("shows a refusal as it is", async () => {
    apiClient.get.mockResolvedValue({ data: { notifications: [UNREAD], message: null } });
    apiClient.post.mockRejectedValueOnce({ response: { data: { error: "Notification not found." } } });
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Mark as read" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Notification not found.");
  });

  it("offers a retry when loading fails", async () => {
    apiClient.get
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce({ data: { notifications: [READ], message: null } });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Your notifications could not be loaded. Check your connection and try again.",
    );
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(READ.message)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
