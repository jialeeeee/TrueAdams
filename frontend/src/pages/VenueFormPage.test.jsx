import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenueFormPage from "./VenueFormPage.jsx";
import VenuesPage from "./VenuesPage.jsx";

// Screen cases IS212-US63-TC1, TC2-TC4, TC6, TC8, TC11, TC12, TC13, TC15 and TC16 in the
// "Sprint 3 test cases" sheet. Responses mirror backend/tests/test_venue_catalogue.py.

vi.mock("../api/client.js", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

const OPTIONS = {
  facilities: ["Projector", "Microphone", "Video conferencing"],
  accessibility_features: ["Wheelchair ramp", "Hearing loop"],
  room_layouts: ["theatre", "classroom", "boardroom", "banquet"],
};
const V101 = {
  id: 1, name: "Orchard Hall", location: "12 Orchard Road", capacity: 120,
  facilities: ["Projector"], accessibility_features: [], room_layouts: ["theatre"],
  operating_hours: "Mon-Fri 08:00-22:00",
};
const HISTORY = { history: [{ action: "added", changed_by: { id: 1, email: "venue_staff1@test.example" }, changed_at: "2026-10-20T01:00:00", changes: {} }] };

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function serve({ options = OPTIONS } = {}) {
  apiClient.get.mockImplementation(async (url) => {
    if (url === "/venues/options") {
      if (!options) throw httpFailure(403, { error: "Only Venue Staff can add or edit venues." });
      return { data: options };
    }
    if (url === "/venues/1") return { data: V101 };
    if (url === "/venues/1/history") return { data: HISTORY };
    if (url === "/venues/") return { data: { venues: [{ id: 1, name: "Orchard Hall" }], message: null } };
    throw new Error(`unexpected GET ${url}`);
  });
}

function renderAt(path) {
  render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/venues" element={<VenuesPage />} />
        <Route path="/venues/new" element={<VenueFormPage />} />
        <Route path="/venues/:venueId/edit" element={<VenueFormPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  Object.values(apiClient).forEach((fn) => fn.mockReset());
  serve();
});

describe("add venue", () => {
  it("TC1: sends every detail entered", async () => {
    apiClient.post.mockResolvedValue({ data: { message: "Orchard Hall was added to the catalogue.", venue: { id: 2 } } });
    const user = renderAt("/venues/new");
    await user.type(await screen.findByLabelText("Name"), "Orchard Hall");
    await user.type(screen.getByLabelText("Location"), "12 Orchard Road, Singapore 238888");
    await user.type(screen.getByLabelText("Capacity"), "120");
    await user.click(screen.getByLabelText("Projector"));
    await user.click(screen.getByLabelText("Microphone"));
    await user.click(screen.getByLabelText("Wheelchair ramp"));
    await user.click(screen.getByLabelText("Theatre"));
    await user.click(screen.getByLabelText("Classroom"));
    await user.type(screen.getByLabelText("Operating hours"), "Mon-Fri 08:00-22:00");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(apiClient.post).toHaveBeenCalledWith("/venues/", {
      name: "Orchard Hall", location: "12 Orchard Road, Singapore 238888", capacity: "120",
      facilities: ["Projector", "Microphone"], accessibility_features: ["Wheelchair ramp"],
      room_layouts: ["theatre", "classroom"], operating_hours: "Mon-Fri 08:00-22:00",
    });
  });

  it("TC8: offers only the defined options, with no free-text entry", async () => {
    renderAt("/venues/new");
    await screen.findByLabelText("Projector");
    expect(screen.getAllByRole("checkbox")).toHaveLength(9);
    expect(screen.queryByText("Jacuzzi")).toBeNull();
    for (const group of ["Facilities", "Accessibility features", "Layouts"]) {
      expect(screen.getByRole("group", { name: group })).toBeTruthy();
    }
  });

  it("TC2-TC4, TC6, TC12: marks every field the server names and keeps the entries", async () => {
    apiClient.post.mockRejectedValue(httpFailure(400, {
      error: "Name is required.",
      fields: { name: "Name is required.", capacity: "Capacity must be a whole number of at least 1." },
    }));
    const user = renderAt("/venues/new");
    await user.type(await screen.findByLabelText("Location"), "12 Orchard Road");
    await user.type(screen.getByLabelText("Capacity"), "0");
    await user.click(screen.getByLabelText("Projector"));
    await user.click(screen.getByLabelText("Theatre"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Name is required.")).toBeTruthy();
    expect(screen.getByText("Capacity must be a whole number of at least 1.")).toBeTruthy();
    expect(screen.getByLabelText("Name").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByLabelText("Capacity").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByLabelText("Location").getAttribute("aria-invalid")).toBeNull();
    expect(screen.getByLabelText("Location").value).toBe("12 Orchard Road");
    expect(screen.getByLabelText("Capacity").value).toBe("0");
    expect(screen.getByLabelText("Projector").checked).toBe(true);
    expect(screen.getByLabelText("Theatre").checked).toBe(true);
  });
});

describe("edit venue", () => {
  it("TC11: loads the venue, saves a change and lists the history", async () => {
    apiClient.put.mockResolvedValue({ data: { message: "Orchard Hall was updated.", venue: V101 } });
    const user = renderAt("/venues/1/edit");
    const capacity = await screen.findByLabelText("Capacity");
    await waitFor(() => expect(capacity.value).toBe("120"));
    expect(screen.getByLabelText("Name").value).toBe("Orchard Hall");
    await user.clear(capacity);
    await user.type(capacity, "150");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Orchard Hall was updated.")).toBeTruthy();
    expect(apiClient.put).toHaveBeenCalledWith("/venues/1", expect.objectContaining({ capacity: "150" }));
    expect(await screen.findByText(/Added by venue_staff1@test.example/)).toBeTruthy();
  });

  it("TC13: a failed save shows the error, keeps the edit, and a second Save retries", async () => {
    apiClient.put
      .mockRejectedValueOnce(httpFailure(503, { error: "The venue could not be saved. Try again.", retryable: true }))
      .mockResolvedValueOnce({ data: { message: "Orchard Hall was updated.", venue: V101 } });
    const user = renderAt("/venues/1/edit");
    const capacity = await screen.findByLabelText("Capacity");
    await waitFor(() => expect(capacity.value).toBe("120"));
    await user.clear(capacity);
    await user.type(capacity, "150");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("The venue could not be saved. Try again.")).toBeTruthy();
    expect(screen.getByLabelText("Capacity").value).toBe("150");

    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Orchard Hall was updated.")).toBeTruthy();
    expect(apiClient.put).toHaveBeenCalledTimes(2);
    expect(apiClient.put.mock.calls[1][1].capacity).toBe("150");
  });

  it("a network failure also keeps the entries and offers another try", async () => {
    apiClient.put.mockRejectedValue(new Error("Network Error"));
    const user = renderAt("/venues/1/edit");
    await waitFor(() => expect(screen.getByLabelText("Capacity").value).toBe("120"));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/could not be saved/)).toBeTruthy();
    expect(screen.getByLabelText("Name").value).toBe("Orchard Hall");
  });
});

describe("who can see add and edit", () => {
  it("TC15/TC16: no form and no Add or Edit action for someone who is not Venue Staff", async () => {
    serve({ options: null });
    const user = renderAt("/venues");
    expect(await screen.findByText("Orchard Hall")).toBeTruthy();
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith("/venues/options"));
    expect(screen.queryByRole("link", { name: "Add venue" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Edit Orchard Hall" })).toBeNull();
    expect(user).toBeTruthy();
  });

  it("TC15: a direct visit to the edit page shows the refusal, not the form", async () => {
    serve({ options: null });
    renderAt("/venues/1/edit");
    expect(await screen.findByText("Only Venue Staff can add or edit venues.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("Venue Staff see Add venue and Edit", async () => {
    renderAt("/venues");
    expect(await screen.findByRole("link", { name: "Add venue" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Edit Orchard Hall" })).toBeTruthy();
  });
});
