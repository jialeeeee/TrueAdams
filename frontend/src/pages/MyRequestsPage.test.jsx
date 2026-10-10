import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import MyRequestsPage from "./MyRequestsPage.jsx";

// Frontend case TC-32-21 in docs/test-cases/SCRUM-32-approve-reject-event-request.md.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <MyRequestsPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-32 my event requests", () => {
  it("shows each request's status, decision time, and the reason or note", async () => {
    apiClient.get.mockResolvedValue({
      data: {
        requests: [
          { id: 1, title: "Harbour Lights Festival", status: "submitted", submitted_at: "2026-09-20T01:00:00", decided_at: null, decision_note: null },
          { id: 6, title: "Rooftop Cinema", status: "rejected", submitted_at: "2026-09-06T01:00:00", decided_at: "2026-09-12T01:00:00", decision_note: "No licensed venue is available" },
          { id: 5, title: "Product Launch", status: "approved", submitted_at: "2026-09-05T01:00:00", decided_at: "2026-09-10T01:00:00", decision_note: "Venue confirmed" },
        ],
        message: null,
      },
    });
    renderPage();

    expect(await screen.findByText("Rooftop Cinema")).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/requests");
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
    expect(screen.getByText(`Status: Rejected · decided ${localTime("2026-09-12T01:00:00")}`)).toBeTruthy();
    expect(screen.getByText("Reason: No licensed venue is available")).toBeTruthy();
    expect(screen.getByText(`Status: Approved · decided ${localTime("2026-09-10T01:00:00")}`)).toBeTruthy();
    expect(screen.getByText("Note: Venue confirmed")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    apiClient.get.mockResolvedValue({ data: { requests: [], message: "You have not submitted any event requests yet." } });
    renderPage();
    expect(await screen.findByText("You have not submitted any event requests yet.")).toBeTruthy();
  });

  it("shows a retryable error when requests cannot be loaded", async () => {
    apiClient.get
      .mockRejectedValueOnce(Object.assign(new Error("fail"), {
        response: { status: 503, data: { error: "Your event requests could not be loaded. Please try again.", retryable: true } },
      }))
      .mockResolvedValueOnce({ data: { requests: [], message: "You have not submitted any event requests yet." } });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("You have not submitted any event requests yet.")).toBeTruthy();
  });
});

// Frontend case TC-60-15 in docs/test-cases/SCRUM-60-accountable-decisions.md; the
// API side is backend/tests/test_decision_accountability.py (TC-60-03).
describe("SCRUM-60 who decided", () => {
  it("SCRUM-60 shows who decided each request", async () => {
    apiClient.get.mockResolvedValue({
      data: {
        requests: [
          { id: 1, title: "Harbour Lights Festival", status: "submitted", submitted_at: "2026-09-20T01:00:00", decided_at: null, decided_by: null, decision_note: null },
          { id: 6, title: "Rooftop Cinema", status: "rejected", submitted_at: "2026-09-06T01:00:00", decided_at: "2026-09-12T01:00:00", decided_by: { id: 2, email: "alice.coordinator@connectsphere.test" }, decision_note: "No licensed venue is available" },
          { id: 5, title: "Product Launch", status: "approved", submitted_at: "2026-09-05T01:00:00", decided_at: "2026-09-10T01:00:00", decided_by: null, decision_note: "Venue confirmed" },
        ],
        message: null,
      },
    });
    renderPage();

    const item = async (title) => within((await screen.findByText(title)).closest("li"));
    expect((await item("Rooftop Cinema")).getByText("Decided by alice.coordinator@connectsphere.test")).toBeTruthy();
    expect((await item("Product Launch")).getByText("Decided by: not recorded")).toBeTruthy();
    expect((await item("Harbour Lights Festival")).queryByText(/Decided by/)).toBeNull();
  });
});
