import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ManagedRegistrationsPage from "./ManagedRegistrationsPage.jsx";

// Frontend cases TC-72-15, TC-72-18 and TC-72-19 in
// docs/test-cases/SCRUM-72-coordinator-view-registration-information.md. The API itself is
// covered by backend/tests/test_coordinator_registrations.py; responses mirror its contract.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const summary = (capacity, registered_count, slots_remaining) => ({
  capacity, registered_count, slots_remaining,
});
const EVENTS = [
  { id: 3, title: "Winter Networking Night", start_time: "2026-11-01T09:00:00", status: "submitted",
    registration: summary(null, 0, null) },
  { id: 1, title: "Alumni Mixer", start_time: "2026-11-20T18:30:00", status: "approved",
    registration: summary(50, 2, 48) },
  { id: 2, title: "Harbour Lights Festival", start_time: "2026-12-12T17:00:00", status: "approved",
    registration: summary(2, 2, 0) },
];
const loaded = (events = EVENTS, message = null) => ({ data: { events, message } });
const NOT_LOADED = "The registration information for your events could not be loaded. Please try again.";

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ManagedRegistrationsPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const item = (name) => within(screen.getByRole("link", { name }).closest("li"));

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-72 registrations for my managed events", () => {
  it("lists each event with its registration summary", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Registrations for my managed events" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/managed/registrations");

    await screen.findByRole("link", { name: "Alumni Mixer" });
    const mixer = item("Alumni Mixer");
    expect(mixer.getByText("Proposed date: 2026-11-20 18:30")).toBeTruthy();
    expect(mixer.getByText("Status: Approved")).toBeTruthy();
    expect(mixer.getByText("Registrations: 2")).toBeTruthy();
    expect(mixer.getByText("Capacity: 50")).toBeTruthy();
    expect(mixer.getByText("Remaining places: 48")).toBeTruthy();
    const night = item("Winter Networking Night");
    expect(night.getByText("Capacity: Not set up")).toBeTruthy();
    expect(night.getByText("Remaining places: Not set up")).toBeTruthy();
  });

  it("keeps the order received and opens each event's registration overview", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    await screen.findByRole("link", { name: "Alumni Mixer" });
    expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual([
      "Winter Networking Night", "Alumni Mixer", "Harbour Lights Festival",
    ]);
    expect(screen.getByRole("link", { name: "Alumni Mixer" }).getAttribute("href"))
      .toBe("/events/1/registration-overview");
  });

  it("shows the empty state when no events are assigned", async () => {
    apiClient.get.mockResolvedValue(loaded([], "You have no events assigned to you yet."));
    renderPage();

    expect(await screen.findByText("You have no events assigned to you yet.")).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("shows a retryable error with no list, and retrying loads it", async () => {
    apiClient.get
      .mockRejectedValueOnce(Object.assign(new Error("fail"), {
        response: { status: 503, data: { error: NOT_LOADED, retryable: true } },
      }))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(NOT_LOADED);
    expect(screen.queryByRole("list")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Alumni Mixer" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The registration information for your events could not be loaded. Check your connection and try again.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
