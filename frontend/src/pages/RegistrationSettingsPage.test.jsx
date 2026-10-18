import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import RegistrationSettingsPage from "./RegistrationSettingsPage.jsx";

// Frontend case TC-45-35 in docs/test-cases/SCRUM-45-register-for-event.md (AC7: the
// event's coordinator sets up registration). The API itself is covered by
// backend/tests/test_registration_settings.py; responses mirror its contract:
//   GET/PUT /events/<id>/registration-settings -> { event_id, capacity, opens_at, closes_at,
//     registered_count, venue_capacity, can_edit, message } (+ PUT's confirmation message)

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), put: vi.fn() } }));

const SETTINGS = {
  event_id: 7, capacity: 30, opens_at: "2026-10-01T09:00:00", closes_at: "2026-11-30T00:00:00",
  registered_count: 2, venue_capacity: 40, can_edit: true, message: null,
};
const loaded = (overrides = {}) => ({ data: { ...SETTINGS, ...overrides } });
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/registration-settings"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/registration-settings" element={<RegistrationSettingsPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const places = () => screen.getByLabelText("Number of places");
const opens = () => screen.getByLabelText("Registration opens");
const closes = () => screen.getByLabelText("Registration closes");
const saveButton = () => screen.getByRole("button", { name: "Save registration settings" });

async function enter(user, { capacity, opensAt, closesAt }) {
  await user.clear(places());
  await user.type(places(), capacity);
  await user.clear(opens());
  await user.type(opens(), opensAt);
  await user.clear(closes());
  await user.type(closes(), closesAt);
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.put.mockReset();
});

describe("SCRUM-45 AC7 the coordinator sets up registration", () => {
  it("shows the current settings, the registered count and the venue's capacity", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Set up registration" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/registration-settings");
    expect(places().value).toBe("30");
    expect(opens().value).toBe("2026-10-01T09:00");
    expect(closes().value).toBe("2026-11-30T00:00");
    expect(screen.getByText("Registered so far: 2")).toBeTruthy();
    expect(screen.getByText("The venue holds 40 people.")).toBeTruthy();
  });

  it("saves the settings entered and shows the confirmation", async () => {
    const message = "Registration for Winter Networking Night is set up: 35 places, open from 2026-10-15 09:00 to 2026-12-01 00:00.";
    apiClient.get.mockResolvedValue(loaded());
    apiClient.put.mockResolvedValue({ data: { ...SETTINGS, capacity: 35, message } });
    const user = renderPage();
    await screen.findByLabelText("Number of places");

    await enter(user, { capacity: "35", opensAt: "2026-10-15T09:00", closesAt: "2026-12-01T00:00" });
    await user.click(saveButton());

    expect(apiClient.put).toHaveBeenCalledWith("/events/7/registration-settings", {
      capacity: 35, opens_at: "2026-10-15T09:00", closes_at: "2026-12-01T00:00",
    });
    expect((await screen.findByRole("status")).textContent).toContain(message);
  });

  it("shows why a save was refused and keeps what was entered", async () => {
    const refusal = "2 people are already registered, so there must be at least 2 places.";
    apiClient.get.mockResolvedValue(loaded());
    apiClient.put.mockRejectedValue(failed(409, { error: refusal, reason: "below_registered" }));
    const user = renderPage();
    await screen.findByLabelText("Number of places");

    await enter(user, { capacity: "1", opensAt: "2026-10-01T09:00", closesAt: "2026-11-30T00:00" });
    await user.click(saveButton());

    expect((await screen.findByRole("alert")).textContent).toContain(refusal);
    expect(places().value).toBe("1");
    expect(saveButton().disabled).toBe(false);
  });

  it("explains when registration can't be set up, with no form", async () => {
    const message = "The organiser said this event doesn't need attendee registration.";
    apiClient.get.mockResolvedValue(loaded({ can_edit: false, message, capacity: null,
                                             opens_at: null, closes_at: null }));
    renderPage();

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByLabelText("Number of places")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save registration settings" })).toBeNull();
  });

  it("denies anyone but the event's coordinator, with no form or retry", async () => {
    const denied = "Only the event's coordinator can set up registration.";
    apiClient.get.mockRejectedValue(failed(403, { error: denied }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(denied);
    expect(screen.queryByLabelText("Number of places")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("shows a load failure with a Retry button", async () => {
    apiClient.get
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The registration settings could not be loaded. Check your connection and try again.",
    );
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("Number of places")).toBeTruthy();
  });
});
