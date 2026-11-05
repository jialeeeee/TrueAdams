import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenueFormPage from "./VenueFormPage.jsx";
import VenuesPage from "./VenuesPage.jsx";

// CF08 frontend cases TC-CF08-09 to TC-CF08-11 in docs/test-cases/CF08-archive-venue.md.
// Responses mirror backend/tests/test_venue_archive.py:
//   POST /venues/<id>/archive and /restore -> { message, venue: details (+ archived_at) }
//   GET /venues/?archived=include lists archived venues too, each with archived_at.

vi.mock("../api/client.js", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();
const OPTIONS = { facilities: [], accessibility_features: [], room_layouts: ["theatre"] };
const HALL = {
  id: 1, name: "Orchard Hall", location: "12 Orchard Road", capacity: 120, facilities: [],
  accessibility_features: [], room_layouts: [], operating_hours: null, setup_minutes: 0,
  turnaround_minutes: 0,
};
const ARCHIVED_AT = "2027-05-01T01:00:00";
const STAFF = { id: 9, email: "gus@test.invalid" };
const entry = (action) => ({ action, changed_by: STAFF, changed_at: "2027-05-01T01:00:00", changes: {} });

function failure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

let venue;
let history;
let staff;
function serve() {
  apiClient.get.mockImplementation(async (url, config) => {
    if (url === "/venues/options") {
      if (!staff) throw failure(403, { error: "Only Venue Staff can add or edit venues." });
      return { data: OPTIONS };
    }
    if (url === "/venues/1") return { data: venue };
    if (url === "/venues/1/history") return { data: { history } };
    if (url === "/venues/") {
      const venues = [{ id: 1, name: "Orchard Hall" }];
      if (config?.params?.archived === "include") venues.push({ id: 2, name: "Old Annex", archived_at: ARCHIVED_AT });
      return { data: { venues, message: null } };
    }
    throw new Error(`unexpected GET ${url}`);
  });
}

function renderAt(path) {
  render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/venues" element={<VenuesPage />} />
        <Route path="/venues/:venueId/edit" element={<VenueFormPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  Object.values(apiClient).forEach((fn) => fn.mockReset());
  venue = HALL;
  history = [entry("added")];
  staff = true;
  serve();
});

describe("deleting a venue (CF08, SCRUM-101)", () => {
  // TC-CF08-09 · A1
  it("deletes the venue after a confirmation step", async () => {
    const message = "Orchard Hall was deleted. It is no longer offered for new bookings, and its records are kept.";
    apiClient.post.mockImplementation(async () => {
      history = [entry("added"), entry("archived")];
      return { data: { message, venue: { ...HALL, archived_at: ARCHIVED_AT } } };
    });
    const user = renderAt("/venues/1/edit");

    await user.click(await screen.findByRole("button", { name: "Delete venue" }));
    const step = screen.getByRole("region", { name: "Delete this venue" });
    expect(within(step).getByText(/it can be restored/)).toBeTruthy();
    await user.click(within(step).getByRole("button", { name: "Delete" }));

    expect(apiClient.post).toHaveBeenCalledWith("/venues/1/archive", {});
    expect((await screen.findByRole("status")).textContent).toBe(message);
    const archived = screen.getByRole("region", { name: "Deleted venue" });
    expect(archived.textContent).toContain(`Deleted on ${localTime(ARCHIVED_AT)}. It isn't offered for new bookings`);
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.getByText(`Deleted by ${STAFF.email} on ${localTime("2027-05-01T01:00:00")}`)).toBeTruthy();
  });

  // TC-CF08-09 · A1
  it("backing out deletes nothing", async () => {
    const user = renderAt("/venues/1/edit");

    await user.click(await screen.findByRole("button", { name: "Delete venue" }));
    await user.click(screen.getByRole("button", { name: "Back" }));

    expect(apiClient.post).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Delete venue" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
  });

  // TC-CF08-10 · A2, A5
  it("explains why a venue can't be deleted", async () => {
    const refusal = "Orchard Hall has 2 upcoming bookings, so it can't be deleted yet. Record it as unavailable so their coordinators find replacement venues, or delete it once they are over.";
    apiClient.post
      .mockRejectedValueOnce(failure(409, { error: refusal, reason: "upcoming_bookings", bookings: [5, 6] }))
      .mockRejectedValueOnce(new Error("Network Error"));
    const user = renderAt("/venues/1/edit");

    await user.click(await screen.findByRole("button", { name: "Delete venue" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect((await screen.findByRole("alert")).textContent).toBe(refusal);
    expect(screen.queryByRole("region", { name: "Deleted venue" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Delete venue" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect((await screen.findByRole("alert")).textContent)
      .toBe("The venue was not deleted. Check your connection and try again.");
  });

  // TC-CF08-11 · A3
  it("restores a deleted venue", async () => {
    venue = { ...HALL, archived_at: ARCHIVED_AT };
    history = [entry("added"), entry("archived")];
    apiClient.post.mockImplementation(async () => {
      history = [entry("added"), entry("archived"), entry("restored")];
      return { data: { message: "Orchard Hall is back in the catalogue.", venue: HALL } };
    });
    const user = renderAt("/venues/1/edit");

    await user.click(await screen.findByRole("button", { name: "Restore venue" }));

    expect(apiClient.post).toHaveBeenCalledWith("/venues/1/restore", {});
    expect((await screen.findByRole("status")).textContent).toBe("Orchard Hall is back in the catalogue.");
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Deleted venue" })).toBeNull();
    expect(screen.getByText(`Restored by ${STAFF.email} on ${localTime("2027-05-01T01:00:00")}`)).toBeTruthy();
  });

  // TC-CF08-11 · A3, A5
  it("explains a failed restore", async () => {
    venue = { ...HALL, archived_at: ARCHIVED_AT };
    apiClient.post.mockRejectedValue(failure(503, { error: " ", retryable: true }));
    const user = renderAt("/venues/1/edit");

    await user.click(await screen.findByRole("button", { name: "Restore venue" }));

    expect((await screen.findByRole("alert")).textContent)
      .toBe("The venue was not restored. Check your connection and try again.");
    expect(screen.getByRole("region", { name: "Deleted venue" })).toBeTruthy();
  });
});

describe("listing deleted venues (CF08, SCRUM-101)", () => {
  // TC-CF08-11 · A1, A3
  it("lets Venue Staff show deleted venues, marked as deleted", async () => {
    const user = renderAt("/venues");
    expect(await screen.findByText("Orchard Hall")).toBeTruthy();
    expect(screen.queryByText("Old Annex (deleted)")).toBeNull();

    await user.click(await screen.findByLabelText("Show deleted venues"));
    expect(await screen.findByText("Old Annex (deleted)")).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/venues/", { params: { archived: "include" } });

    await user.click(screen.getByLabelText("Show deleted venues"));
    expect(await screen.findByText("Orchard Hall")).toBeTruthy();
    expect(screen.queryByText("Old Annex (deleted)")).toBeNull();
  });

  // TC-CF08-11 · A1
  it("offers nobody else deleted venues", async () => {
    staff = false;
    renderAt("/venues");

    expect(await screen.findByText("Orchard Hall")).toBeTruthy();
    expect(screen.queryByLabelText("Show deleted venues")).toBeNull();
  });
});
