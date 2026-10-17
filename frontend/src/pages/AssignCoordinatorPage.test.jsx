import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import AssignCoordinatorPage from "./AssignCoordinatorPage.jsx";

// Frontend cases TC-81-18 to TC-81-22 in
// docs/test-cases/SCRUM-81-lead-assigns-coordinator.md. The API itself is covered by
// backend/tests/test_lead_assign_coordinator.py; responses mirror its contract:
//   GET  /events/<id>/assignment -> { event, coordinators, message }
//   POST /events/<id>/assignment -> { message, assignment, notification }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const ALICE = { id: 11, email: "alice.coordinator@connectsphere.test" };
const BEN = { id: 12, email: "ben.coordinator@connectsphere.test" };
const LENA = { id: 21, email: "lena.lead@connectsphere.test" };
const EVENT = {
  id: 7, title: "Harbour Lights Festival", start_time: "2026-12-12T17:00:00", status: "submitted",
};

const loaded = (coordinators = [ALICE, BEN], message = null) => ({
  data: { event: EVENT, coordinators, message },
});
const CONFIRMATION = `${ALICE.email} is now the coordinator for Harbour Lights Festival.`;
const assigned = (emailQueued = true) => ({
  data: {
    message: CONFIRMATION,
    assignment: {
      event_id: 7, coordinator: ALICE, assigned_by: LENA, assigned_at: "2026-10-17T05:00:00",
    },
    notification: { in_app: true, email_queued: emailQueued },
  },
});
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

const ALREADY_ASSIGNED = "This event already has a coordinator. Use the reassign function to change it.";
const SAVE_FAILED = "The assignment was not saved. Please try again.";
const NO_ELIGIBLE = "No eligible coordinator is available for this event.";

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/assign"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/assign" element={<AssignCoordinatorPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const coordinatorBox = () => screen.getByRole("combobox", { name: "Coordinator" });
const assignButton = () => screen.getByRole("button", { name: "Assign coordinator" });

async function chooseAndAssign(user, email = ALICE.email) {
  await screen.findByRole("combobox", { name: "Coordinator" });
  await user.selectOptions(coordinatorBox(), email);
  await user.click(assignButton());
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("SCRUM-81 a Lead assigns a coordinator to a waiting event", () => {
  it("shows the waiting event and its eligible coordinators", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Harbour Lights Festival" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/assignment");
    expect(screen.getByRole("heading", { name: "Assign a coordinator" })).toBeTruthy();
    // Singapore time, shown as recorded rather than converted.
    expect(screen.getByText("Proposed date: 2026-12-12 17:00")).toBeTruthy();
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
    expect(within(coordinatorBox()).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Choose a coordinator", ALICE.email, BEN.email,
    ]);
  });

  it("assigns the chosen coordinator and says they were notified", async () => {
    apiClient.get.mockResolvedValue(loaded());
    apiClient.post.mockResolvedValue(assigned());
    const user = renderPage();

    await chooseAndAssign(user);

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/assignment", { coordinator_id: ALICE.id });
    expect(await screen.findByText(CONFIRMATION)).toBeTruthy();
    expect(screen.getByText("They have been notified.")).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Assign coordinator" })).toBeNull();
  });

  it("says when the email could not be sent", async () => {
    apiClient.get.mockResolvedValue(loaded());
    apiClient.post.mockResolvedValue(assigned(false));
    const user = renderPage();

    await chooseAndAssign(user);

    expect(await screen.findByText(CONFIRMATION)).toBeTruthy();
    expect(screen.getByText(
      "They were notified in ConnectSphere, but the email could not be sent.",
    )).toBeTruthy();
  });

  it("asks for a coordinator before sending anything", async () => {
    apiClient.get.mockResolvedValue(loaded());
    const user = renderPage();

    await screen.findByRole("combobox", { name: "Coordinator" });
    await user.click(assignButton());

    expect(screen.getByRole("alert").textContent).toContain("Choose a coordinator.");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("tells the Lead when no eligible coordinator exists, with no form", async () => {
    apiClient.get.mockResolvedValue(loaded([], NO_ELIGIBLE));
    renderPage();

    expect(await screen.findByText(NO_ELIGIBLE)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Harbour Lights Festival" })).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Assign coordinator" })).toBeNull();
  });

  it("points to the reassign function when the event already has a coordinator", async () => {
    apiClient.get.mockRejectedValue(failed(409, { error: ALREADY_ASSIGNED, reason: "already_assigned" }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(ALREADY_ASSIGNED);
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("refuses when another Lead assigned the event first, without confirming", async () => {
    apiClient.get.mockResolvedValue(loaded());
    apiClient.post.mockRejectedValue(failed(409, { error: ALREADY_ASSIGNED, reason: "already_assigned" }));
    const user = renderPage();

    await chooseAndAssign(user);

    expect((await screen.findByRole("alert")).textContent).toContain(ALREADY_ASSIGNED);
    expect(screen.queryByText(CONFIRMATION)).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Assign coordinator" })).toBeNull();
  });

  it("denies anyone else without showing the event, a form or a retry", async () => {
    const denied = "Only Event Coordinator Leads can assign coordinators.";
    apiClient.get.mockRejectedValue(failed(403, { error: denied }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(denied);
    expect(screen.queryByRole("heading", { name: "Harbour Lights Festival" })).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("keeps the choice when the save fails, so the Lead can try again", async () => {
    apiClient.get.mockResolvedValue(loaded());
    apiClient.post
      .mockRejectedValueOnce(failed(503, { error: SAVE_FAILED, retryable: true }))
      .mockResolvedValueOnce(assigned());
    const user = renderPage();

    await chooseAndAssign(user);

    expect((await screen.findByRole("alert")).textContent).toContain(SAVE_FAILED);
    expect(screen.queryByText(CONFIRMATION)).toBeNull();
    expect(coordinatorBox().value).toBe(String(ALICE.id));

    await user.click(assignButton());
    expect(await screen.findByText(CONFIRMATION)).toBeTruthy();
    expect(apiClient.post).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a load failure with a Retry button that loads the event", async () => {
    const loadFailed = "The event could not be loaded. Please try again.";
    apiClient.get
      .mockRejectedValueOnce(failed(503, { error: loadFailed, retryable: true }))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(loadFailed);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Harbour Lights Festival" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The event could not be loaded. Check your connection and try again.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
