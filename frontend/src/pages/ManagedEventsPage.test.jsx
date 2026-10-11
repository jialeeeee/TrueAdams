import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ManagedEventsPage from "./ManagedEventsPage.jsx";

// Frontend cases TC-62-11 to TC-62-13 and TC-62-15 in
// docs/test-cases/SCRUM-62-managed-events-list.md. The API itself is covered by
// backend/tests/test_managed_events.py; responses mirror its contract.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const EVENTS = [
  { id: 3, title: "Winter Networking Night", start_time: "2026-10-01T09:00:00", status: "cancelled" },
  { id: 2, title: "Alumni Mixer", start_time: "2026-11-20T18:30:00", status: "approved" },
  { id: 1, title: "Harbour Lights Festival", start_time: "2026-12-12T17:00:00", status: "submitted" },
  { id: 4, title: null, start_time: null, status: "under_review" },
];
const loaded = (events = EVENTS, message = null) => ({ data: { events, message } });

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ManagedEventsPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const item = (name) => within(screen.getByRole("link", { name }).closest("li"));

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-62 my managed events", () => {
  it("lists each event with its name, proposed date and status", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    expect(await screen.findByRole("heading", { name: "My managed events" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/managed");

    await screen.findByRole("link", { name: "Harbour Lights Festival" });
    // Singapore time, shown as recorded rather than converted.
    expect(item("Harbour Lights Festival").getByText("Proposed date: 2026-12-12 17:00")).toBeTruthy();
    expect(item("Harbour Lights Festival").getByText("Status: Submitted")).toBeTruthy();
    expect(item("Alumni Mixer").getByText("Status: Approved")).toBeTruthy();
    expect(item("Winter Networking Night").getByText("Status: Cancelled")).toBeTruthy();
  });

  it("keeps the order received", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    await screen.findByRole("link", { name: "Alumni Mixer" });
    expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual([
      "Winter Networking Night", "Alumni Mixer", "Harbour Lights Festival", "Not recorded",
    ]);
  });

  it("opens each event's planning page", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    const link = await screen.findByRole("link", { name: "Alumni Mixer" });
    expect(link.getAttribute("href")).toBe("/events/2/planning");
  });

  it("shows a missing name and proposed date as Not recorded, still linked", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    const link = await screen.findByRole("link", { name: "Not recorded" });
    expect(link.getAttribute("href")).toBe("/events/4/planning");
    expect(item("Not recorded").getByText("Proposed date: Not recorded")).toBeTruthy();
    expect(item("Not recorded").getByText("Status: Under review")).toBeTruthy();
  });

  it("shows the empty state when no events are assigned", async () => {
    apiClient.get.mockResolvedValue(loaded([], "You have no events assigned to you yet."));
    renderPage();

    expect(await screen.findByText("You have no events assigned to you yet.")).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("shows a retryable error when the list cannot be loaded", async () => {
    apiClient.get
      .mockRejectedValueOnce(Object.assign(new Error("fail"), {
        response: { status: 503, data: { error: "Your managed events could not be loaded. Please try again.", retryable: true } },
      }))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Your managed events could not be loaded. Please try again.",
    );
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Alumni Mixer" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Your managed events could not be loaded. Check your connection and try again.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
