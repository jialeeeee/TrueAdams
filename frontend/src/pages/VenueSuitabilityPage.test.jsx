import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenueSuitabilityPage from "./VenueSuitabilityPage.jsx";

// Screen cases IS212-US38-TC1, TC2, TC9, TC10, TC12, TC13 and TC14 in the "Sprint 3 test
// cases" sheet. Responses mirror backend/tests/test_venue_suitability.py.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const VENUES = { venues: [{ id: 1, name: "Orchard Hall" }, { id: 2, name: "Marina Room" }], message: null };

const check = (requirement, item, label, status, detail) =>
  ({ requirement, item, label, status, detail });

const MEETS = {
  event: { id: 7, title: "E-401" }, venue: { id: 1, name: "Orchard Hall" },
  checks: [
    check("attendance", null, "Attendance", "match", "80 expected, within the capacity of 120."),
    check("facility", "Projector", "Facility: Projector", "match", "Orchard Hall has Projector."),
    check("accessibility", "Wheelchair ramp", "Accessibility: Wheelchair ramp", "match", "Orchard Hall has Wheelchair ramp."),
    check("layout", "theatre", "Layout: theatre", "match", "Orchard Hall has theatre."),
  ],
  overall: "meets", summary: "Orchard Hall meets the checked requirements.",
};
const MIXED = {
  ...MEETS,
  checks: [
    check("attendance", null, "Attendance", "match", "80 expected, within the capacity of 120."),
    check("facility", "Video conferencing", "Facility: Video conferencing", "mismatch", "Orchard Hall does not have Video conferencing."),
    check("layout", "theatre", "Layout: theatre", "unable_to_assess", "Orchard Hall's layouts are not recorded."),
  ],
  overall: "does_not_meet", summary: "Orchard Hall does not meet all the checked requirements.",
};
const UNABLE = {
  ...MEETS,
  checks: [check("attendance", null, "Attendance", "unable_to_assess", "The event's expected attendance is not recorded.")],
  overall: "unable_to_assess",
  summary: "Some requirements could not be assessed for Orchard Hall, so it can't be said to meet them.",
};

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

async function renderPage() {
  apiClient.get.mockImplementation(async (url) => {
    if (url === "/venues/") return { data: VENUES };
    throw new Error(`unexpected GET ${url}`);
  });
  render(
    <MemoryRouter initialEntries={["/events/7/venue-suitability"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="/events/:eventId/venue-suitability" element={<VenueSuitabilityPage />} /></Routes>
    </MemoryRouter>,
  );
  const user = userEvent.setup();
  await screen.findByRole("heading", { name: "Check venue suitability" });
  await screen.findByLabelText("Venue");
  return user;
}

const run = (user) => user.click(screen.getByRole("button", { name: "Run check" }));

beforeEach(() => apiClient.get.mockReset());

describe("venue suitability screen", () => {
  it("TC1/TC13: runs the check for the chosen venue and shows a line per requirement", async () => {
    const user = await renderPage();
    apiClient.get.mockResolvedValue({ data: MEETS });
    await user.selectOptions(screen.getByLabelText("Venue"), "1");
    await run(user);
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/venue-suitability", { params: { venue_id: "1" } });
    const lines = await screen.findByRole("list", { name: "Checked requirements" });
    expect(lines.querySelectorAll("li")).toHaveLength(4);
    expect(lines.textContent).toContain("Attendance: Match");
    expect(screen.getByRole("heading", { name: "Meets the checked requirements" })).toBeTruthy();
  });

  it("TC2: asks for a venue and runs no check without one", async () => {
    const user = await renderPage();
    await run(user);
    expect((await screen.findByRole("alert")).textContent).toBe("Select a venue to check.");
    expect(apiClient.get).toHaveBeenCalledTimes(1); // only the venue list
  });

  it("TC9: labels matches, mismatches and what could not be assessed", async () => {
    const user = await renderPage();
    apiClient.get.mockResolvedValue({ data: MIXED });
    await user.selectOptions(screen.getByLabelText("Venue"), "1");
    await run(user);
    const lines = await screen.findByRole("list", { name: "Checked requirements" });
    expect(lines.textContent).toContain("Attendance: Match");
    expect(lines.textContent).toContain("Facility: Video conferencing: Mismatch");
    expect(lines.textContent).toContain("Layout: theatre: Unable to assess");
    expect(screen.getByRole("heading", { name: "Does not meet all the checked requirements" })).toBeTruthy();
  });

  it("TC10/TC12: unrecorded information is Unable to assess and is not a pass", async () => {
    const user = await renderPage();
    apiClient.get.mockResolvedValue({ data: UNABLE });
    await user.selectOptions(screen.getByLabelText("Venue"), "1");
    await run(user);
    expect((await screen.findByRole("list", { name: "Checked requirements" })).textContent)
      .toContain("Attendance: Unable to assess");
    expect(screen.getByRole("heading", { name: "Could not be fully assessed" })).toBeTruthy();
    expect(screen.queryByText(/meets the checked requirements/i)).toBeNull();
  });

  it("TC14: the passing result does not claim a booking", async () => {
    const user = await renderPage();
    apiClient.get.mockResolvedValue({ data: MEETS });
    await user.selectOptions(screen.getByLabelText("Venue"), "1");
    await run(user);
    await screen.findByRole("list", { name: "Checked requirements" });
    const text = document.body.textContent.toLowerCase();
    for (const word of ["booked", "confirmed", "approved", "reserved"]) expect(text).not.toContain(word);
    expect(screen.getByText("This check does not book the venue or send a venue request.")).toBeTruthy();
  });

  it("a failed check shows the error and no stale result, and can be run again", async () => {
    const user = await renderPage();
    apiClient.get.mockResolvedValueOnce({ data: MEETS });
    await user.selectOptions(screen.getByLabelText("Venue"), "1");
    await run(user);
    await screen.findByRole("list", { name: "Checked requirements" });

    apiClient.get.mockRejectedValueOnce(httpFailure(503, {
      error: "The venue check could not be completed. Please try again.", retryable: true }));
    await run(user);
    expect((await screen.findByRole("alert")).textContent).toContain("could not be completed");
    expect(screen.queryByRole("list", { name: "Checked requirements" })).toBeNull();

    apiClient.get.mockResolvedValueOnce({ data: MEETS });
    await run(user);
    expect(await screen.findByRole("list", { name: "Checked requirements" })).toBeTruthy();
  });

  it("offers a retry when the venues cannot be loaded", async () => {
    apiClient.get.mockRejectedValueOnce(new Error("Network Error"));
    render(
      <MemoryRouter initialEntries={["/events/7/venue-suitability"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes><Route path="/events/:eventId/venue-suitability" element={<VenueSuitabilityPage />} /></Routes>
      </MemoryRouter>,
    );
    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    apiClient.get.mockResolvedValueOnce({ data: VENUES });
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("Venue")).toBeTruthy();
  });
});
