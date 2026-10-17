import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import TentativeHoldsPage from "./TentativeHoldsPage.jsx";

// Frontend cases TC-87-36 and TC-87-37 in docs/test-cases/SCRUM-87-tentative-venue-hold.md:
// Venue Staff's unexpired holds (GET /api/venues/holds) and changing an expiry
// (PATCH /api/venues/bookings/<id>/hold). Responses mirror backend/tests/test_venue_holds.py.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), patch: vi.fn() } }));

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

const HOLD = {
  id: 11, status: "tentative",
  event: { id: 7, title: "Harbour Lights Festival", expected_attendance: 250 },
  venue: { id: 3, name: "Aurora Ballroom", location: "Level 3, Marina Tower" },
  start_time: "2027-03-12T16:00:00", end_time: "2027-03-12T22:30:00",
  venue_requirements: "Open-air waterfront space for 250, stage power",
  requested_by: { id: 2, email: "alice.coordinator@connectsphere.test" },
  requested_at: "2026-10-14T03:00:00",
  hold: { held_at: "2027-02-20T01:00:00", held_by: { id: 9, email: "gus.venue@connectsphere.test" }, expires_at: "2027-03-01T17:00:00" },
};
const LISTED = { data: { holds: [HOLD], message: null } };

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <TentativeHoldsPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const expiryField = () => screen.getByLabelText("New expiry for Harbour Lights Festival");
const changeButton = () => screen.getByRole("button", { name: "Change expiry for Harbour Lights Festival" });

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.patch.mockReset();
});

describe("SCRUM-87 tentative holds for Venue Staff", () => {
  // TC-87-36 · AC3
  it("lists each unexpired hold with its period, expiry and who held it", async () => {
    apiClient.get.mockResolvedValue(LISTED);
    renderPage();

    const item = await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    expect(apiClient.get).toHaveBeenCalledWith("/venues/holds");
    const text = item.textContent;
    expect(text).toContain("Venue: Aurora Ballroom, Level 3, Marina Tower");
    expect(text).toContain("Held: 2027-03-12 16:00 to 2027-03-12 22:30");
    expect(text).toContain("Expires: 2027-03-01 17:00");
    expect(text).toContain(`Held by gus.venue@connectsphere.test on ${localTime("2027-02-20T01:00:00")}`);
    expect(expiryField().value).toBe("2027-03-01T17:00");
  });

  // TC-87-36 · AC3 — a venue whose location is not recorded shows only its name.
  it("shows only the venue's name when its location is not recorded", async () => {
    apiClient.get.mockResolvedValue({
      data: { holds: [{ ...HOLD, venue: { ...HOLD.venue, location: null } }], message: null },
    });
    renderPage();

    const item = await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    expect(within(item).getByText("Venue: Aurora Ballroom")).toBeTruthy();
  });

  // TC-87-36 · AC3
  it("shows the empty state", async () => {
    apiClient.get.mockResolvedValue({ data: { holds: [], message: "There are no tentative holds." } });
    renderPage();

    expect(await screen.findByText("There are no tentative holds.")).toBeTruthy();
    expect(screen.queryByRole("listitem")).toBeNull();
  });

  // TC-87-36 · AC7
  it("shows a load failure with Retry, and the retry loads the holds", async () => {
    apiClient.get
      .mockRejectedValueOnce(httpFailure(503, { error: "Tentative holds could not be loaded. Please try again.", retryable: true }))
      .mockResolvedValueOnce(LISTED);
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("listitem", { name: "Harbour Lights Festival" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // TC-87-36 · AC6
  it("shows a refusal without Retry or holds", async () => {
    apiClient.get.mockRejectedValue(httpFailure(403, { error: "Only Venue Staff can view tentative holds." }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("Only Venue Staff");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.queryByRole("listitem")).toBeNull();
  });

  // TC-87-37 · AC3
  it("changes a hold's expiry and reloads the holds", async () => {
    apiClient.get.mockResolvedValueOnce(LISTED).mockResolvedValueOnce({
      data: { holds: [{ ...HOLD, hold: { ...HOLD.hold, expires_at: "2027-03-05T12:00:00" } }], message: null },
    });
    apiClient.patch.mockResolvedValue({
      data: {
        message: "The hold on Aurora Ballroom for Harbour Lights Festival now expires on 2027-03-05 12:00. alice.coordinator@connectsphere.test has been notified.",
        booking: { ...HOLD, hold: { ...HOLD.hold, expires_at: "2027-03-05T12:00:00" } },
        notification: { in_app: true, email_queued: true },
      },
    });
    const user = renderPage();
    await screen.findByRole("listitem", { name: "Harbour Lights Festival" });

    await user.clear(expiryField());
    await user.type(expiryField(), "2027-03-05T12:00");
    await user.click(changeButton());

    expect(apiClient.patch).toHaveBeenCalledWith("/venues/bookings/11/hold", { expires_at: "2027-03-05T12:00" });
    expect((await screen.findByRole("status")).textContent).toContain("now expires on 2027-03-05 12:00");
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(2));
    const item = await screen.findByRole("listitem", { name: "Harbour Lights Festival" });
    expect(await within(item).findByText("Expires: 2027-03-05 12:00")).toBeTruthy();
  });

  // TC-87-37 · AC3, AC7
  it.each([
    ["an invalid expiry", httpFailure(400, { error: "The expiry must be in the future.", field: "expires_at" }), "must be in the future"],
    ["an expired hold", httpFailure(409, { error: "This hold expired on 2027-03-01 17:00, so its expiry can no longer be changed.", reason: "expired" }), "can no longer be changed"],
    ["a save failure", httpFailure(503, { error: "The new expiry was not saved, so the hold still expires on 2027-03-01 17:00. Please try again.", retryable: true }), "was not saved"],
    ["no network", new Error("Network Error"), "Check your connection and try again"],
  ])("explains a refused change (%s) and keeps the hold and the new expiry", async (_label, failure, message) => {
    apiClient.get.mockResolvedValue(LISTED);
    apiClient.patch.mockRejectedValue(failure);
    const user = renderPage();
    await screen.findByRole("listitem", { name: "Harbour Lights Festival" });

    await user.clear(expiryField());
    await user.type(expiryField(), "2027-03-05T12:00");
    await user.click(changeButton());

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(screen.getByRole("listitem", { name: "Harbour Lights Festival" }).textContent).toContain("Expires: 2027-03-01 17:00");
    expect(expiryField().value).toBe("2027-03-05T12:00");
    expect(screen.queryByRole("status")).toBeNull();
  });
});
