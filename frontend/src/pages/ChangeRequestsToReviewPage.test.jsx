import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ChangeRequestsToReviewPage from "./ChangeRequestsToReviewPage.jsx";

// Frontend case TC-70-31 in docs/test-cases/SCRUM-70-review-change-request.md. The API is
// covered by backend/tests/test_change_request_review.py (TC-70-04); responses mirror it:
//   GET /events/change-requests -> { requests: [REQ + event: { id, title, status }], message }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const DANA = { id: 4, email: "dana@example.com" };
const REQUESTS = [
  {
    id: 31, event_id: 7, status: "pending_review", status_label: "Pending Review",
    event: { id: 7, title: "Charity Gala", status: "approved" },
    changes: [
      { field: "start_time", label: "Start", from: "2026-12-05T18:00:00", to: "2026-12-06T18:00:00" },
      { field: "end_time", label: "End", from: "2026-12-05T23:00:00", to: "2026-12-06T23:30:00" },
    ],
    requested_by: DANA, requested_at: "2026-10-26T02:00:00",
    decided_at: null, decided_by: null, decision_reason: null,
  },
  {
    id: 32, event_id: 9, status: "pending_review", status_label: "Pending Review",
    event: { id: 9, title: "Winter Concert", status: "cancelled" },
    changes: [{ field: "expected_attendance", label: "Expected attendance", from: 300, to: 320 }],
    requested_by: DANA, requested_at: "2026-10-27T02:00:00",
    decided_at: null, decided_by: null, decision_reason: null,
  },
];
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });
const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ChangeRequestsToReviewPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-70 change requests to review", () => {
  // TC-70-31 · AC1
  it("lists the pending change requests with links to review them", async () => {
    apiClient.get.mockResolvedValue({ data: { requests: REQUESTS, message: null } });
    renderPage();

    const links = await screen.findAllByRole("link");
    expect(apiClient.get).toHaveBeenCalledWith("/events/change-requests");
    expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
      ["Charity Gala", "/events/7/change-requests/31"],
      ["Winter Concert", "/events/9/change-requests/32"],
    ]);
    const first = within(screen.getAllByRole("listitem")[0]);
    expect(first.getByText(`Requested by ${DANA.email} on ${localTime("2026-10-26T02:00:00")}`)).toBeTruthy();
    expect(first.getByText("Changes: Start and End")).toBeTruthy();
    expect(within(screen.getAllByRole("listitem")[1]).getByText("Event status: Cancelled")).toBeTruthy();
  });

  it("says when there is nothing to review", async () => {
    apiClient.get.mockResolvedValue({ data: { requests: [],
      message: "You have no change requests to review." } });
    renderPage();

    expect(await screen.findByText("You have no change requests to review.")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("explains a failed load and offers Retry", async () => {
    apiClient.get.mockRejectedValueOnce(new Error("Network Error"));
    apiClient.get.mockResolvedValueOnce({ data: { requests: REQUESTS, message: null } });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Change requests could not be loaded. Check your connection and try again.");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Charity Gala" })).toBeTruthy();
  });

  it("shows a refusal without Retry", async () => {
    apiClient.get.mockRejectedValue(failed(403, {
      error: "Only event coordinators can review change requests." }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Only event coordinators can review change requests.");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
