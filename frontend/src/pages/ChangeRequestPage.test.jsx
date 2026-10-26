import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ChangeRequestPage from "./ChangeRequestPage.jsx";

// Frontend cases TC-46-21 to TC-46-26 in docs/test-cases/SCRUM-46-change-request.md.
// The API is covered by backend/tests/test_change_requests.py; responses mirror its
// contract:
//   GET  /events/<id>/change-requests -> FORM = { event: { id, title, status, coordinator,
//     current: { FIELD: value } }, fields: [{ name, label }], can_request, blocked_reason,
//     message, pending_request: REQ | null }
//   POST /events/<id>/change-requests { FIELD: proposed value, ... }
//     -> 201 { message, request: REQ, notification }
//   REQ = { id, event_id, status, status_label, changes: [{ field, label, from, to }],
//     requested_by, requested_at }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const FIELDS = [
  { name: "start_time", label: "Start" },
  { name: "end_time", label: "End" },
  { name: "expected_attendance", label: "Expected attendance" },
  { name: "venue_requirements", label: "Venue requirements" },
  { name: "equipment_requirements", label: "Equipment requirements" },
];
const FORM = {
  event: {
    id: 7, title: "Charity Gala", status: "approved",
    coordinator: { id: 2, email: "alice@example.com" },
    current: {
      start_time: "2026-12-05T18:00:00", end_time: "2026-12-05T23:00:00", expected_attendance: 200,
      venue_requirements: "Ballroom for 200", equipment_requirements: "2 wireless microphones",
    },
  },
  fields: FIELDS, can_request: true, blocked_reason: null, message: null, pending_request: null,
};
const REQUEST = {
  id: 31, event_id: 7, status: "pending_review", status_label: "Pending Review",
  changes: [
    { field: "start_time", label: "Start", from: "2026-12-05T18:00:00", to: "2026-12-05T17:00:00" },
    { field: "expected_attendance", label: "Expected attendance", from: 200, to: 250 },
  ],
  requested_by: { id: 4, email: "dana@example.com" }, requested_at: "2026-10-26T02:00:00",
};
const CONFIRMATION = "Your change request for \"Charity Gala\" (Start and Expected attendance) is Pending Review. alice@example.com has been notified.";
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/change-request"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/change-request" element={<ChangeRequestPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const field = (label) => screen.getByLabelText(label);
const submitButton = () => screen.getByRole("button", { name: "Submit change request" });

async function replace(user, label, value) {
  await user.clear(field(label));
  await user.type(field(label), value);
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("SCRUM-46 an organiser requests a change to their approved event", () => {
  // TC-46-21 · AC1, AC2
  it("shows the event's current values in the form", async () => {
    apiClient.get.mockResolvedValue({ data: FORM });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Request a change" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/change-requests");
    expect(screen.getByRole("heading", { name: "Charity Gala" })).toBeTruthy();
    expect(screen.getByText("Coordinator: alice@example.com")).toBeTruthy();
    expect(field("Start").value).toBe("2026-12-05T18:00");
    expect(field("End").value).toBe("2026-12-05T23:00");
    expect(field("Expected attendance").value).toBe("200");
    expect(field("Venue requirements").value).toBe("Ballroom for 200");
    expect(field("Equipment requirements").value).toBe("2 wireless microphones");
  });

  // TC-46-22 · AC2, AC6
  it("sends only the changed fields and shows the confirmation", async () => {
    apiClient.get.mockResolvedValue({ data: FORM });
    apiClient.post.mockResolvedValue({ data: {
      message: CONFIRMATION, request: REQUEST, notification: { in_app: true, email_queued: true },
    } });
    const user = renderPage();

    await screen.findByRole("heading", { name: "Charity Gala" });
    await replace(user, "Start", "2026-12-05T17:00");
    await replace(user, "Expected attendance", "250");
    await user.click(submitButton());

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/change-requests", {
      start_time: "2026-12-05T17:00", expected_attendance: 250,
    });
    expect((await screen.findByRole("status")).textContent).toContain(CONFIRMATION);
    expect(screen.getByText("Status: Pending Review")).toBeTruthy();
    const changes = within(screen.getByRole("list", { name: "Requested changes" })).getAllByRole("listitem");
    expect(changes.map((item) => item.textContent)).toEqual([
      "Start: 2026-12-05 18:00 → 2026-12-05 17:00",
      "Expected attendance: 200 → 250",
    ]);
    expect(screen.queryByRole("button", { name: "Submit change request" })).toBeNull();
  });

  it("does not send a request that changes nothing", async () => {
    apiClient.get.mockResolvedValue({ data: FORM });
    const user = renderPage();

    await screen.findByRole("heading", { name: "Charity Gala" });
    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain("Change at least one value");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  // TC-46-23 · AC4
  it("shows why each field was refused and keeps the entries", async () => {
    apiClient.get.mockResolvedValue({ data: FORM });
    apiClient.post.mockRejectedValue(failed(422, {
      error: "Some changes can't be requested. Please correct them and try again.",
      fields: {
        end_time: "The end must be after the start.",
        expected_attendance: "Expected attendance must be a whole number of at least 1.",
      },
    }));
    const user = renderPage();

    await screen.findByRole("heading", { name: "Charity Gala" });
    await replace(user, "End", "2026-12-05T17:00");
    await replace(user, "Expected attendance", "-5");
    await user.click(submitButton());

    expect((await screen.findByText("The end must be after the start."))).toBeTruthy();
    expect(screen.getByText("Expected attendance must be a whole number of at least 1.")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Some changes can't be requested");
    expect(field("End").value).toBe("2026-12-05T17:00");
    expect(field("Expected attendance").value).toBe("-5");
    expect(screen.queryByRole("status")).toBeNull();
  });

  // TC-46-24 · AC1, AC5
  it("explains why no change can be requested", async () => {
    const message = "This event has no coordinator yet, so there is nobody to review a change request. Please try again once a coordinator is assigned.";
    apiClient.get.mockResolvedValue({ data: {
      ...FORM, event: { ...FORM.event, coordinator: null }, can_request: false,
      blocked_reason: "no_coordinator", message,
    } });
    renderPage();

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Submit change request" })).toBeNull();
    expect(screen.queryByLabelText("Start")).toBeNull();
  });

  // TC-46-25 · AC6
  it("shows the pending request instead of the form", async () => {
    const message = "A change request for this event is already pending review.";
    apiClient.get.mockResolvedValue({ data: {
      ...FORM, can_request: false, blocked_reason: "pending", message, pending_request: REQUEST,
    } });
    renderPage();

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.getByText("Status: Pending Review")).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "Requested changes" })).getAllByRole("listitem"))
      .toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Submit change request" })).toBeNull();
  });

  // TC-46-26 · AC8
  it("keeps the entries after a failed save so it can be tried again", async () => {
    const error = "Your change request was not submitted, and the event is unchanged. Please try again.";
    apiClient.get.mockResolvedValue({ data: FORM });
    apiClient.post
      .mockRejectedValueOnce(failed(503, { error, retryable: true }))
      .mockResolvedValueOnce({ data: { message: CONFIRMATION, request: REQUEST,
                                       notification: { in_app: true, email_queued: true } } });
    const user = renderPage();

    await screen.findByRole("heading", { name: "Charity Gala" });
    await replace(user, "Expected attendance", "250");
    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain(error);
    expect(field("Expected attendance").value).toBe("250");
    await user.click(submitButton());

    expect((await screen.findByRole("status")).textContent).toContain(CONFIRMATION);
    expect(apiClient.post.mock.calls[1]).toEqual(apiClient.post.mock.calls[0]);
  });

  it("explains a failed save without a server message", async () => {
    apiClient.get.mockResolvedValue({ data: FORM });
    apiClient.post.mockRejectedValue(new Error("Network Error"));
    const user = renderPage();

    await screen.findByRole("heading", { name: "Charity Gala" });
    await replace(user, "Expected attendance", "250");
    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain("was not submitted");
  });

  it("explains a failed load and offers Retry", async () => {
    apiClient.get
      .mockRejectedValueOnce(failed(503, { error: "The change request form could not be loaded. Please try again.", retryable: true }))
      .mockResolvedValueOnce({ data: FORM });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { name: "Charity Gala" })).toBeTruthy();
  });

  it("shows a refusal without Retry", async () => {
    const denied = "You can only request changes to events you organise.";
    apiClient.get.mockRejectedValue(failed(403, { error: denied }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(denied);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
