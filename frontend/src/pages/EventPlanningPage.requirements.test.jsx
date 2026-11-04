// CF11 (G4 clarification #8): the coordinator records what the event needs of a venue on
// its planning page, so the venue suitability check can show a mismatch. Cases TC15 to
// TC20 in docs/test-cases/SCRUM-38-assess-venue-against-event.md; the API is covered by
// backend/tests/test_venue_suitability.py (PlanningRequirementsTests).
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EventPlanningPage from "./EventPlanningPage.jsx";

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), patch: vi.fn() } }));

const EVENT = {
  id: 1,
  title: "Inclusive Tech Talk",
  status: "approved",
  start_time: "2030-03-04T18:00:00",
  end_time: "2030-03-04T21:00:00",
  coordinator: { id: 2, email: "alice@test.invalid" },
  organiser: { id: 4, email: "dana@test.invalid" },
  not_recorded: [],
  venue_bookings: [],
  requirements: { facilities: null, accessibility_features: [], layouts: ["theatre", "Stage"] },
};
const SAVED = { ...EVENT, message: "Changes saved." };

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function renderPage(event = EVENT) {
  apiClient.get.mockResolvedValue({ data: event });
  render(
    <MemoryRouter initialEntries={["/events/1/planning"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Link to="/events/2/planning">Open second event</Link>
      <Routes>
        <Route path="/events/:eventId/planning" element={<EventPlanningPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const group = (name) => screen.getByRole("group", { name });
const box = (groupName, name) => within(group(groupName)).getByRole("checkbox", { name });
const saved = (groupName) => within(group(groupName)).getByText(/^Saved: /).textContent;
const saveButton = () => screen.getByRole("button", { name: "Save requirements" });

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.patch.mockReset();
});

describe("CF11 the event's requirements on its planning page", () => {
  // TC17: not recorded, none needed and recorded lists are told apart; a name saved
  // outside the venue lists is kept as its own box.
  it("shows what the event needs, telling not recorded from none needed", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Event requirements" });

    expect(saved("Required facilities")).toBe("Saved: Not recorded");
    expect(saved("Required accessibility features")).toBe("Saved: None needed");
    expect(saved("Required layouts")).toBe("Saved: Theatre, Stage");
    expect(within(group("Required facilities")).getAllByRole("checkbox").map((b) => b.checked))
      .toEqual([false, false, false, false]);
    expect(box("Required accessibility features", "None needed").checked).toBe(true);
    expect(box("Required layouts", "Theatre").checked).toBe(true);
    expect(box("Required layouts", "Classroom").checked).toBe(false);
    expect(box("Required layouts", "Stage").checked).toBe(true);
  });

  // TC18: ticked names are sent in the list's order; None needed sends []; nothing
  // ticked sends null (not recorded). The page then shows what was saved.
  it("saves the ticked requirements and shows them as saved", async () => {
    let finish;
    apiClient.patch.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const user = renderPage();
    await screen.findByRole("heading", { name: "Event requirements" });

    await user.click(box("Required facilities", "Microphone"));
    await user.click(box("Required facilities", "Projector"));
    await user.click(box("Required accessibility features", "Wheelchair ramp"));
    await user.click(box("Required layouts", "Theatre"));
    await user.click(box("Required layouts", "Stage"));
    await user.click(saveButton());

    expect(saveButton().disabled).toBe(true);
    expect(box("Required facilities", "Projector").disabled).toBe(true);
    expect(apiClient.patch).toHaveBeenCalledWith("/events/1", {
      required_facilities: ["Projector", "Microphone"],
      required_accessibility_features: ["Wheelchair ramp"],
      required_layouts: null,
    });
    await act(async () => finish({ data: { ...SAVED, requirements: {
      facilities: ["Projector", "Microphone"], accessibility_features: ["Wheelchair ramp"],
      layouts: null } } }));

    expect(screen.getByRole("status").textContent).toBe("Changes saved.");
    expect(saved("Required facilities")).toBe("Saved: Projector, Microphone");
    expect(saved("Required accessibility features")).toBe("Saved: Wheelchair ramp");
    expect(saved("Required layouts")).toBe("Saved: Not recorded");
    expect(saveButton().disabled).toBe(false);
  });

  // TC19: None needed and the names are each other's opposite.
  it("clears the names when None needed is ticked, and None needed when a name is", async () => {
    const user = renderPage();
    await screen.findByRole("heading", { name: "Event requirements" });

    await user.click(box("Required accessibility features", "Hearing loop"));
    expect(box("Required accessibility features", "None needed").checked).toBe(false);
    await user.click(box("Required layouts", "None needed"));
    expect(box("Required layouts", "Theatre").checked).toBe(false);
    expect(box("Required layouts", "Stage").checked).toBe(false);
    await user.click(box("Required accessibility features", "Hearing loop"));
    await user.click(box("Required facilities", "None needed"));
    await user.click(box("Required facilities", "None needed"));
    apiClient.patch.mockResolvedValue({ data: SAVED });
    await user.click(saveButton());

    expect(apiClient.patch).toHaveBeenCalledWith("/events/1", {
      required_facilities: null, required_accessibility_features: null, required_layouts: [],
    });
  });

  // TC20: a refused or failed save says why, keeps the ticks, and can be retried.
  it.each([
    ["a refused save", httpFailure(422, {
      error: "Some changes could not be saved. Please correct them and try again.",
      fields: { required_layouts: "Required layouts can have at most 20 names." },
    }), "Some changes could not be saved. Please correct them and try again. Required layouts can have at most 20 names."],
    // e.g. cancelled by someone else since the page opened (SCRUM-53 AC3).
    ["a refusal without field problems", httpFailure(409, {
      error: "This event is cancelled and can no longer be edited.",
    }), "This event is cancelled and can no longer be edited."],
    ["a failure without a message", httpFailure(503, { retryable: true }),
      "Your changes could not be saved. Check your connection and try again."],
    ["no network", new Error("Network Error"),
      "Your changes could not be saved. Check your connection and try again."],
  ])("explains %s and keeps the ticks for a retry", async (_case, failure, message) => {
    apiClient.patch.mockRejectedValueOnce(failure).mockResolvedValueOnce({ data: SAVED });
    const user = renderPage();
    await screen.findByRole("heading", { name: "Event requirements" });

    await user.click(box("Required facilities", "Projector"));
    await user.click(saveButton());

    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(box("Required facilities", "Projector").checked).toBe(true);
    expect(saved("Required facilities")).toBe("Saved: Not recorded");
    await user.click(saveButton());
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // Must match NON_EDITABLE_STATUSES in backend/app/events/routes.py (SCRUM-53).
  it("shows a cancelled event's requirements without letting them be changed", async () => {
    renderPage({ ...EVENT, status: "cancelled" });
    await screen.findByRole("heading", { name: "Event requirements" });

    expect(saved("Required layouts")).toBe("Saved: Theatre, Stage");
    expect(screen.queryAllByRole("checkbox")).toEqual([]);
    expect(screen.queryByRole("button", { name: "Save requirements" })).toBeNull();
    expect(screen.getByText("A cancelled event can't be edited.")).toBeTruthy();
  });

  // A reply that arrives after another event was opened belongs to the old event.
  it("ignores a save that finishes after another event was opened", async () => {
    let finish;
    apiClient.patch.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const user = renderPage();
    await screen.findByRole("heading", { name: "Event requirements" });
    await user.click(box("Required facilities", "Projector"));
    await user.click(saveButton());

    apiClient.get.mockResolvedValue({ data: { ...EVENT, id: 2, title: "Second Event" } });
    await user.click(screen.getByRole("link", { name: "Open second event" }));
    await screen.findByRole("heading", { name: "Second Event" });
    await act(async () => finish({ data: { ...SAVED, requirements: {
      facilities: ["Projector"], accessibility_features: [], layouts: null } } }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "Second Event" })).toBeTruthy());
    expect(saved("Required facilities")).toBe("Saved: Not recorded");
    expect(box("Required facilities", "Projector").checked).toBe(false);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
