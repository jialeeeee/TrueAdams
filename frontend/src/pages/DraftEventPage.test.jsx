import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import DraftEventPage from "./DraftEventPage.jsx";

// Frontend cases TC-29-10, 15, 19, 23 and 29 in
// docs/test-cases/SCRUM-29-draft-event-request.md.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));

const EMPTY = {
  purpose: null, description: null, start_time: null, end_time: null,
  expected_attendance: null, venue_requirements: null, accessibility_needs: null,
  equipment_requirements: null, registration_required: null,
};

function draft(overrides = {}) {
  return {
    id: 7, status: "draft", title: "Harbour Lights Festival", ...EMPTY,
    purpose: "Celebrate the harbour's reopening", start_time: "2026-12-12T17:00:00",
    expected_attendance: 250, created_at: "2026-09-20T02:00:00",
    last_saved_at: "2026-09-20T02:00:00", submitted_at: null,
    missing_for_submission: ["description", "end_time", "venue_requirements", "registration_required"],
    ...overrides,
  };
}

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function Location() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

async function renderAt(path) {
  render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Location />
      <Routes>
        <Route path="/events/drafts/new" element={<DraftEventPage />} />
        <Route path="/events/drafts/:draftId" element={<DraftEventPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: /event request/i });
  return userEvent.setup();
}

const field = (label) => screen.getByLabelText(label);
const saveButton = () => screen.getByRole("button", { name: "Save draft" });
const submitButton = () => screen.getByRole("button", { name: "Submit for review" });

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
  apiClient.put.mockReset();
});

describe("SCRUM-29 draft event request", () => {
  // TC-29-10 · AC2
  it("shows a new request as not saved yet, and needs an event name to save", async () => {
    const user = await renderAt("/events/drafts/new");
    expect(screen.getByText(/not saved yet/i)).toBeTruthy();
    expect(saveButton().disabled).toBe(true);
    await user.type(field("Event name"), "   ");
    expect(saveButton().disabled).toBe(true);
  });

  // TC-29-01, TC-29-10, TC-29-19 · AC1, AC2, AC4
  it("saves a new draft with only a name, shows Draft and the last-saved time, then updates the same draft", async () => {
    apiClient.post.mockResolvedValue({ status: 201, data: draft({ ...EMPTY, id: 9, title: "Spring Garden Party", last_saved_at: "2026-09-28T03:00:00" }) });
    apiClient.put.mockResolvedValue({ data: draft({ ...EMPTY, id: 9, title: "Spring Garden Party", purpose: "Staff social", last_saved_at: "2026-09-28T03:05:00" }) });
    const user = await renderAt("/events/drafts/new");

    await user.type(field("Event name"), "Spring Garden Party");
    await user.click(saveButton());

    expect(apiClient.post).toHaveBeenCalledWith("/events/drafts", expect.objectContaining({
      title: "Spring Garden Party", purpose: null, expected_attendance: null, registration_required: null,
    }));
    expect(await screen.findByText(`Last saved: ${localTime("2026-09-28T03:00:00")}`)).toBeTruthy();
    expect(screen.getByText("Status: Draft")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/events/drafts/9"));

    await user.type(field("Purpose"), "Staff social");
    await user.click(saveButton());

    expect(apiClient.put).toHaveBeenCalledWith("/events/drafts/9", expect.objectContaining({ purpose: "Staff social" }));
    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(apiClient.get).not.toHaveBeenCalled();
    expect(await screen.findByText(`Last saved: ${localTime("2026-09-28T03:05:00")}`)).toBeTruthy();
  });

  // TC-29-15 · AC3
  it("reopens a draft with its saved information, ready to edit", async () => {
    apiClient.get.mockResolvedValue({ data: draft() });
    await renderAt("/events/drafts/7");

    expect(apiClient.get).toHaveBeenCalledWith("/events/drafts/7");
    expect(field("Event name").value).toBe("Harbour Lights Festival");
    expect(field("Purpose").value).toBe("Celebrate the harbour's reopening");
    expect(field("Start").value).toBe("2026-12-12T17:00");
    expect(field("Expected attendance").value).toBe("250");
    expect(field("Description").value).toBe("");
    expect(field("Event name").disabled).toBe(false);
    expect(screen.getByText(`Last saved: ${localTime("2026-09-20T02:00:00")}`)).toBeTruthy();
  });

  // TC-29-23 · AC5
  it.each([
    ["server error", httpFailure(503, { error: "Your draft was not saved. Please try again.", retryable: true }), "Your draft was not saved. Please try again."],
    ["invalid value", httpFailure(400, { error: "Expected attendance must be a whole number of at least 1.", field: "expected_attendance" }), "Expected attendance must be a whole number of at least 1."],
    ["no network", new Error("Network Error"), "Your draft was not saved. Check your connection and try again."],
  ])("keeps the edits and the last-saved time when saving fails (%s), and saves on retry", async (_label, failure, message) => {
    apiClient.get.mockResolvedValue({ data: draft() });
    apiClient.put
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce({ data: draft({ description: "Lanterns and live music", last_saved_at: "2026-09-28T04:00:00" }) });
    const user = await renderAt("/events/drafts/7");

    await user.type(field("Description"), "Lanterns and live music");
    await user.click(saveButton());

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(field("Description").value).toBe("Lanterns and live music");
    expect(screen.getByText(`Last saved: ${localTime("2026-09-20T02:00:00")}`)).toBeTruthy();
    expect(saveButton().disabled).toBe(false);

    await user.click(saveButton());
    expect(await screen.findByText(`Last saved: ${localTime("2026-09-28T04:00:00")}`)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // TC-29-29 · AC6
  it("saves the current edits, then submits, and shows the request as Submitted", async () => {
    const complete = draft({
      description: "Lanterns", end_time: "2026-12-12T22:00:00", venue_requirements: "Waterfront",
      registration_required: true, missing_for_submission: [],
    });
    apiClient.get.mockResolvedValue({ data: draft() });
    apiClient.put.mockResolvedValue({ data: complete });
    apiClient.post.mockResolvedValue({ data: { ...complete, status: "submitted", submitted_at: "2026-09-28T05:00:00" } });
    const user = await renderAt("/events/drafts/7");

    await user.type(field("Description"), "Lanterns");
    await user.click(submitButton());

    await screen.findByText("Status: Submitted");
    expect(apiClient.put).toHaveBeenCalledWith("/events/drafts/7", expect.objectContaining({ description: "Lanterns" }));
    expect(apiClient.post).toHaveBeenCalledWith("/events/drafts/7/submit");
    expect(apiClient.put.mock.invocationCallOrder[0]).toBeLessThan(apiClient.post.mock.invocationCallOrder[0]);
    expect(field("Event name").disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Save draft" })).toBeNull();
  });

  // TC-29-29, TC-29-26 · AC6
  it("lists the missing fields when submission is refused, and stays a Draft with the edits kept", async () => {
    apiClient.get.mockResolvedValue({ data: draft() });
    apiClient.put.mockResolvedValue({ data: draft({ purpose: "Harbour party" }) });
    apiClient.post.mockRejectedValue(httpFailure(400, {
      error: "Complete these fields before submitting.",
      missing: ["description", "end_time", "venue_requirements", "registration_required"],
    }));
    const user = await renderAt("/events/drafts/7");

    await user.clear(field("Purpose"));
    await user.type(field("Purpose"), "Harbour party");
    await user.click(submitButton());

    const alert = await screen.findByRole("alert");
    for (const label of ["Description", "End", "Venue requirements", "Attendee registration needed"]) {
      expect(alert.textContent).toContain(label);
    }
    expect(screen.getByText("Status: Draft")).toBeTruthy();
    expect(field("Purpose").value).toBe("Harbour party");
    expect(field("Event name").disabled).toBe(false);
  });

  it("does not submit when saving the edits first fails", async () => {
    apiClient.get.mockResolvedValue({ data: draft() });
    apiClient.put.mockRejectedValue(httpFailure(503, { error: "Your draft was not saved. Please try again.", retryable: true }));
    const user = await renderAt("/events/drafts/7");

    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain("not saved");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("explains when a request has already been submitted and cannot be edited as a draft", async () => {
    apiClient.get.mockRejectedValue(httpFailure(409, { error: "This request has already been submitted and can no longer be edited as a draft." }));
    render(
      <MemoryRouter initialEntries={["/events/drafts/7"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes><Route path="/events/drafts/:draftId" element={<DraftEventPage />} /></Routes>
      </MemoryRouter>,
    );
    expect((await screen.findByRole("alert")).textContent).toContain("already been submitted");
  });
});
