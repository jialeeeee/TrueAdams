import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ReassignCoordinatorPage from "./ReassignCoordinatorPage.jsx";

// Frontend cases TC-82-14 to TC-82-16 in
// docs/test-cases/SCRUM-82-lead-reassigns-coordinator.md. The API itself is covered by
// backend/tests/test_lead_reassign_coordinator.py; responses mirror its contract:
//   GET /events/<id>/eligible-coordinators -> { event_id, event, current_coordinator,
//                                               coordinators, message }
//   PUT /events/<id>/coordinator -> { message, event_id, coordinator, previous_coordinator,
//                                     assigned_by, assigned_at, notification }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), put: vi.fn() } }));

const ALICE = { id: 11, email: "alice.coordinator@connectsphere.test" };
const BEN = { id: 12, email: "ben.coordinator@connectsphere.test" };
const CHLOE = { id: 13, email: "chloe.coordinator@connectsphere.test" };
const LENA = { id: 21, email: "lena.lead@connectsphere.test" };
const EVENT = {
  id: 7, title: "Harbour Lights Festival", start_time: "2026-12-12T17:00:00", status: "submitted",
};

const loaded = (coordinators = [BEN, CHLOE], message = null) => ({
  data: { event_id: 7, event: EVENT, current_coordinator: ALICE, coordinators, message },
});
const CONFIRMATION = `${CHLOE.email} is now the coordinator for Harbour Lights Festival.`;
const reassigned = (emailQueued = true) => ({
  data: {
    message: CONFIRMATION, event_id: 7, coordinator: CHLOE, previous_coordinator: ALICE,
    assigned_by: LENA, assigned_at: "2026-10-17T05:00:00",
    notification: { in_app: true, email_queued: emailQueued },
  },
});
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

const SAVE_FAILED = "The coordinator assignment could not be saved. Please try again.";

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/change-coordinator"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/change-coordinator" element={<ReassignCoordinatorPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const coordinatorBox = () => screen.getByRole("combobox", { name: "New coordinator" });
const reassignButton = () => screen.getByRole("button", { name: "Reassign coordinator" });

async function chooseAndReassign(user, email = CHLOE.email) {
  await screen.findByRole("combobox", { name: "New coordinator" });
  await user.selectOptions(coordinatorBox(), email);
  await user.click(reassignButton());
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.put.mockReset();
});

describe("SCRUM-82 a Lead reassigns an event to a different coordinator", () => {
  it("shows the event, its current coordinator and the coordinators to choose from", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Harbour Lights Festival" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/eligible-coordinators");
    expect(screen.getByRole("heading", { level: 1, name: "Reassign coordinator" })).toBeTruthy();
    // Singapore time, shown as recorded rather than converted.
    expect(screen.getByText("Proposed date: 2026-12-12 17:00")).toBeTruthy();
    expect(screen.getByText("Status: Submitted")).toBeTruthy();
    expect(screen.getByText(`Current coordinator: ${ALICE.email}`)).toBeTruthy();
    expect(within(coordinatorBox()).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Choose a coordinator", BEN.email, CHLOE.email,
    ]);
  });

  it("reassigns to the chosen coordinator and says both were notified", async () => {
    apiClient.get.mockResolvedValue(loaded());
    apiClient.put.mockResolvedValue(reassigned());
    const user = renderPage();

    await chooseAndReassign(user);

    expect(apiClient.put).toHaveBeenCalledWith("/events/7/coordinator", { coordinator_id: CHLOE.id });
    expect(await screen.findByText(CONFIRMATION)).toBeTruthy();
    expect(screen.getByText(`Current coordinator: ${CHLOE.email}`)).toBeTruthy();
    expect(screen.getByText("Both coordinators have been notified.")).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reassign coordinator" })).toBeNull();
  });

  it("says when an email could not be sent", async () => {
    apiClient.get.mockResolvedValue(loaded());
    apiClient.put.mockResolvedValue(reassigned(false));
    const user = renderPage();

    await chooseAndReassign(user);

    expect(await screen.findByText(CONFIRMATION)).toBeTruthy();
    expect(screen.getByText(
      "Both coordinators were notified in ConnectSphere, but an email could not be sent.",
    )).toBeTruthy();
  });

  it("asks for a coordinator before sending anything", async () => {
    apiClient.get.mockResolvedValue(loaded());
    const user = renderPage();

    await screen.findByRole("combobox", { name: "New coordinator" });
    await user.click(reassignButton());

    expect(screen.getByRole("alert").textContent).toContain("Choose a coordinator.");
    expect(apiClient.put).not.toHaveBeenCalled();
  });

  it("shows a refusal such as the same coordinator, without confirming", async () => {
    const same = "This user is already the event's coordinator.";
    apiClient.get.mockResolvedValue(loaded());
    apiClient.put.mockRejectedValue(failed(409, { error: same }));
    const user = renderPage();

    await chooseAndReassign(user);

    expect((await screen.findByRole("alert")).textContent).toContain(same);
    expect(screen.queryByText(CONFIRMATION)).toBeNull();
    expect(screen.getByText(`Current coordinator: ${ALICE.email}`)).toBeTruthy();
  });

  it("denies anyone else without showing the event, a form or a retry", async () => {
    const denied = "Only Event Coordinator Leads can reassign coordinators.";
    apiClient.get.mockRejectedValue(failed(403, { error: denied }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(denied);
    expect(screen.queryByRole("heading", { name: "Harbour Lights Festival" })).toBeNull();
    expect(screen.queryByText(/Current coordinator/)).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("tells the Lead when no other eligible coordinator exists, with no form", async () => {
    const message = "No eligible coordinators are available for this event.";
    apiClient.get.mockResolvedValue(loaded([], message));
    renderPage();

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.getByText(`Current coordinator: ${ALICE.email}`)).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reassign coordinator" })).toBeNull();
  });

  it("keeps the choice when the save fails, so the Lead can try again", async () => {
    apiClient.get.mockResolvedValue(loaded());
    apiClient.put
      .mockRejectedValueOnce(failed(503, { error: SAVE_FAILED, retryable: true }))
      .mockResolvedValueOnce(reassigned());
    const user = renderPage();

    await chooseAndReassign(user);

    expect((await screen.findByRole("alert")).textContent).toContain(SAVE_FAILED);
    expect(coordinatorBox().value).toBe(String(CHLOE.id));
    await user.click(reassignButton());
    expect(await screen.findByText(CONFIRMATION)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a load failure with a Retry button that loads the event", async () => {
    const loadFailed = "Eligible coordinators could not be loaded. Please try again.";
    apiClient.get
      .mockRejectedValueOnce(failed(503, { error: loadFailed, retryable: true }))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(loadFailed);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Harbour Lights Festival" })).toBeTruthy();
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
