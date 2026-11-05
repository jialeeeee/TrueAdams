// SCRUM-98 TC-98-11 to TC-98-13; docs/test-cases/SCRUM-98-cancel-event.md and
// backend/tests/test_cancel_event.py. Responses mirror its contract:
//   POST /events/<id>/cancel { reason } -> { message, event: { id, status, cancellation:
//     { cancelled_by, cancelled_at, reason } }, released, notification }
//   GET /events/<id>/planning adds cancellation once the event is cancelled.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EventPlanningPage from "./EventPlanningPage.jsx";

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();
const ALICE = { id: 2, email: "alice@test.invalid" };
const EVENT = {
  id: 7, title: "Harbour Talk", status: "approved", start_time: "2027-06-10T10:00:00",
  end_time: "2027-06-10T12:00:00", coordinator: ALICE,
  organiser: { id: 4, email: "dana@test.invalid" }, not_recorded: [], venue_bookings: [],
};
const REASON = "The organiser asked to cancel: the speaker withdrew.";
const CANCELLATION = { cancelled_by: ALICE, cancelled_at: "2027-05-01T01:00:00", reason: REASON };
const DONE = {
  message: "You cancelled \"Harbour Talk\". Its venue bookings, equipment reservations and registrations were released, and everyone affected has been told.",
  event: { id: 7, status: "cancelled", cancellation: CANCELLATION },
  released: { venue_bookings: 1, equipment_reservations: 0, registrations: 2 },
  notification: { in_app: true, email_queued: true },
};
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/planning"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/planning" element={<EventPlanningPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const eventStatus = () => screen.getAllByText(/^Status: /)[0].textContent;

describe("EventPlanningPage cancelling the event (SCRUM-98)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiClient.get.mockResolvedValue({ data: EVENT });
  });

  // TC-98-11 · AC2
  it("offers cancelling only for events that can be cancelled", async () => {
    for (const status of ["submitted", "under_review", "approved", "confirmed"]) {
      apiClient.get.mockResolvedValueOnce({ data: { ...EVENT, status } });
      const { unmount } = render(
        <MemoryRouter initialEntries={["/events/7/planning"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes><Route path="/events/:eventId/planning" element={<EventPlanningPage />} /></Routes>
        </MemoryRouter>,
      );
      expect(await screen.findByRole("button", { name: "Cancel event" })).toBeTruthy();
      unmount();
    }
    for (const status of ["draft", "rejected", "cancelled"]) {
      apiClient.get.mockResolvedValueOnce({ data: { ...EVENT, status } });
      const { unmount } = render(
        <MemoryRouter initialEntries={["/events/7/planning"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes><Route path="/events/:eventId/planning" element={<EventPlanningPage />} /></Routes>
        </MemoryRouter>,
      );
      await screen.findByRole("heading", { name: "Harbour Talk" });
      expect(screen.queryByRole("button", { name: "Cancel event" })).toBeNull();
      unmount();
    }
  });

  // TC-98-12 · AC3, AC4
  it("asks for a reason, then cancels and shows the record", async () => {
    apiClient.post.mockResolvedValue({ data: DONE });
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Cancel event" }));
    const form = screen.getByRole("form", { name: "Cancel this event" });
    expect(within(form).getByText(/can't be reinstated/)).toBeTruthy();
    await user.click(within(form).getByRole("button", { name: "Confirm cancellation" }));
    expect(within(form).getByRole("alert").textContent).toBe("Give a reason for cancelling the event.");
    expect(apiClient.post).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Reason for cancelling"), REASON);
    expect(within(form).getByText(`${REASON.length} / 500 characters`)).toBeTruthy();
    await user.click(within(form).getByRole("button", { name: "Confirm cancellation" }));

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/cancel", { reason: REASON });
    expect((await screen.findByRole("status")).textContent).toBe(DONE.message);
    expect(eventStatus()).toBe("Status: Cancelled");
    const record = screen.getByRole("region", { name: "Cancellation" });
    expect(within(record).getByText(`Cancelled by ${ALICE.email} · ${localTime("2027-05-01T01:00:00")}`)).toBeTruthy();
    expect(within(record).getByText(`Reason: ${REASON}`)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel event" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Mark event Confirmed" })).toBeNull();
  });

  // TC-98-12 · AC3
  it("backing out changes nothing", async () => {
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Cancel event" }));
    await user.type(screen.getByLabelText("Reason for cancelling"), REASON);
    await user.click(screen.getByRole("button", { name: "Back" }));

    expect(screen.queryByRole("form", { name: "Cancel this event" })).toBeNull();
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(eventStatus()).toBe("Status: Approved");
    await user.click(screen.getByRole("button", { name: "Cancel event" }));
    expect(screen.getByLabelText("Reason for cancelling").value).toBe("");
  });

  // TC-98-12 · AC3
  it("refuses a reason over 500 characters", async () => {
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Cancel event" }));
    const box = screen.getByLabelText("Reason for cancelling");
    await user.click(box);
    await user.paste("x".repeat(501));
    await user.click(screen.getByRole("button", { name: "Confirm cancellation" }));

    expect(screen.getByRole("alert").textContent).toBe("The reason can be at most 500 characters.");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  // TC-98-13 · AC1, AC9
  it("explains a refusal or failure and keeps the reason", async () => {
    apiClient.post
      .mockRejectedValueOnce(failed(409, { error: "This event has already started, so it can no longer be cancelled.", reason: "started" }))
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockRejectedValueOnce(failed(503, { error: " " }));
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Cancel event" }));
    await user.type(screen.getByLabelText("Reason for cancelling"), REASON);
    const confirm = screen.getByRole("button", { name: "Confirm cancellation" });
    await user.click(confirm);
    expect((await screen.findByRole("alert")).textContent)
      .toBe("This event has already started, so it can no longer be cancelled.");
    await user.click(confirm);
    expect((await screen.findByRole("alert")).textContent)
      .toBe("The event was not cancelled. Check your connection and try again.");
    await user.click(confirm);
    expect((await screen.findByRole("alert")).textContent)
      .toBe("The event was not cancelled. Check your connection and try again.");
    expect(screen.getByLabelText("Reason for cancelling").value).toBe(REASON);
    expect(eventStatus()).toBe("Status: Approved");
  });

  // TC-98-12 · AC4
  it("shows the cancellation of an event loaded as cancelled, even without who", async () => {
    apiClient.get.mockResolvedValue({ data: { ...EVENT, status: "cancelled",
      cancellation: { ...CANCELLATION, cancelled_by: null } } });
    renderPage();

    const record = await screen.findByRole("region", { name: "Cancellation" });
    expect(within(record).getByText(`Cancelled by Not recorded · ${localTime("2027-05-01T01:00:00")}`)).toBeTruthy();
  });
});
