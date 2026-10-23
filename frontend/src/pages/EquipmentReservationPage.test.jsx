import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EquipmentReservationPage from "./EquipmentReservationPage.jsx";

// Frontend cases TC-44-38 to TC-44-46 in docs/test-cases/SCRUM-44-reserve-equipment.md.
// The API is covered by backend/tests/test_equipment_reservation.py; responses mirror
// its contract:
//   GET  /events/<id>/equipment-reservations -> PAGE = { event, reservation_period,
//     can_reserve, notice, message, requirements: [REQ], released: [RES] }
//   POST /events/<id>/equipment-reservations { requirement_id, items: [{ resource_id, quantity }] }
//     -> 201 { confirmation, saved, reservations, notification, ...PAGE }
//   REQ = { id, equipment_type, quantity, technical_requirements, technical_note,
//     reserved_quantity, remaining_quantity, available_to_reserve, state, state_label,
//     options: [{ id, name, category, quantity_available, reserved_for_other_events,
//     reserved_for_this_event, available_to_reserve }], excluded, reservations: [RES] }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const EVENT = {
  id: 7, title: "Charity Gala", status: "approved",
  start_time: "2026-12-05T18:00:00", end_time: "2026-12-05T23:00:00",
  coordinator: { id: 2, email: "alice@example.com" },
};
const PERIOD = { start_time: "2026-12-05T18:00:00", end_time: "2026-12-05T23:00:00" };
const option = (id, name, available, extra = {}) => ({
  id, name, category: "Wireless microphone", quantity_available: available,
  reserved_for_other_events: 0, reserved_for_this_event: 0, available_to_reserve: available, ...extra,
});
const MICS = {
  id: 11, equipment_type: "Wireless microphone", quantity: 3, technical_requirements: "Lapel",
  technical_note: "Technical Support must confirm the technical requirements: Lapel",
  reserved_quantity: 0, remaining_quantity: 3, available_to_reserve: 4,
  state: "can_reserve", state_label: "Equipment can be reserved",
  options: [option(1, "Shure SLX-D", 2), option(2, "Sennheiser EW-D", 2)],
  excluded: [], reservations: [],
};
const PROJECTOR = {
  id: 12, equipment_type: "Projector", quantity: 1, technical_requirements: null, technical_note: null,
  reserved_quantity: 0, remaining_quantity: 1, available_to_reserve: 2,
  state: "can_reserve", state_label: "Equipment can be reserved",
  options: [{ ...option(4, "BenQ LU935", 2), category: "Projector" }],
  excluded: [{ id: 3, name: "Epson EB-L", reason: "unavailable",
               detail: "Unavailable 2026-12-05 17:00 to 2026-12-05 19:00: Lamp replacement" }],
  reservations: [],
};
const HOLOGRAM = {
  id: 13, equipment_type: "Hologram projector", quantity: 1, technical_requirements: null, technical_note: null,
  reserved_quantity: 0, remaining_quantity: 1, available_to_reserve: 0,
  state: "none_available", state_label: "No suitable equipment is available to reserve",
  options: [], excluded: [], reservations: [],
};
const PAGE = {
  event: EVENT, reservation_period: PERIOD, can_reserve: true, notice: null, message: null,
  requirements: [MICS, PROJECTOR, HOLOGRAM], released: [],
};
const reservation = (id, name, quantity, extra = {}) => ({
  id, requirement_id: 11, resource: { id, name }, quantity,
  start_time: PERIOD.start_time, end_time: PERIOD.end_time, status: "reserved",
  reserved_by: { id: 9, email: "hana@example.com" }, reserved_at: "2026-10-23T02:00:00",
  released_at: null, release_reason: null, ...extra,
});
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/equipment-reservations"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/equipment-reservations" element={<EquipmentReservationPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const items = () =>
  within(screen.getByRole("list", { name: "Equipment requirements" })).getAllByRole("listitem")
    .filter((item) => item.parentElement.getAttribute("aria-label") === "Equipment requirements");
const quantity = (name) => screen.getByLabelText(`Quantity of ${name}`);
const reserveButton = (requirement) => screen.getByRole("button", { name: `Reserve for ${requirement}` });

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("SCRUM-44 Technical Support reserve equipment for an event", () => {
  // TC-44-38 · AC1
  it("shows the reservation period and what can be reserved for each requirement", async () => {
    apiClient.get.mockResolvedValue({ data: PAGE });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Equipment reservations" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/equipment-reservations");
    expect(screen.getByRole("heading", { name: "Charity Gala" })).toBeTruthy();
    expect(screen.getByText("Reservation period: 05/12/2026 18:00 SGT to 05/12/2026 23:00 SGT")).toBeTruthy();
    const [mics, projector] = items();
    expect(mics.textContent).toContain("3 × Wireless microphone");
    expect(mics.textContent).toContain("Technical Support must confirm the technical requirements: Lapel");
    expect(mics.textContent).toContain("Reserved: 0 of 3");
    expect(mics.textContent).toContain("Shure SLX-D: 2 available to reserve");
    expect(mics.textContent).toContain("Sennheiser EW-D: 2 available to reserve");
    expect(projector.textContent).toContain(
      "Not available: Epson EB-L (Unavailable 2026-12-05 17:00 to 2026-12-05 19:00: Lamp replacement)");
    expect(quantity("Shure SLX-D")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to the equipment requirements" }).getAttribute("href"))
      .toBe("/events/7/equipment");
  });

  it("says how much of an item other events and this event have reserved", async () => {
    const shared = {
      ...MICS,
      options: [option(1, "Shure SLX-D", 2, { reserved_for_other_events: 1, reserved_for_this_event: 1, available_to_reserve: 0 }),
                option(2, "Sennheiser EW-D", 2)],
    };
    apiClient.get.mockResolvedValue({ data: { ...PAGE, requirements: [shared] } });
    renderPage();

    await screen.findByRole("heading", { name: "Charity Gala" });
    expect(items()[0].textContent).toContain(
      "Shure SLX-D: 0 available to reserve (2 recorded, 1 reserved for other events at this time, 1 already reserved for this event)");
  });

  // TC-44-39 · AC2, AC3
  it("reserves the chosen quantities and shows the confirmation", async () => {
    const confirmation = "Reserved 2 × Shure SLX-D and 1 × Sennheiser EW-D for 3 × Wireless microphone at Charity Gala, 2026-12-05 18:00 to 2026-12-05 23:00. The event's coordinator has been notified.";
    const reserved = {
      ...MICS, reserved_quantity: 3, remaining_quantity: 0, state: "fully_reserved", state_label: "Fully reserved",
      reservations: [reservation(1, "Shure SLX-D", 2), reservation(2, "Sennheiser EW-D", 1)],
    };
    apiClient.get.mockResolvedValue({ data: PAGE });
    apiClient.post.mockResolvedValue({ data: {
      ...PAGE, requirements: [reserved, PROJECTOR, HOLOGRAM], confirmation, saved: true,
      reservations: reserved.reservations, notification: { in_app: true, email_queued: true },
    } });
    const user = renderPage();

    await user.type(await screen.findByLabelText("Quantity of Shure SLX-D"), "2");
    await user.type(quantity("Sennheiser EW-D"), "1");
    await user.click(reserveButton("3 × Wireless microphone"));

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/equipment-reservations", {
      requirement_id: 11, items: [{ resource_id: 1, quantity: 2 }, { resource_id: 2, quantity: 1 }],
    });
    expect((await screen.findByRole("status")).textContent).toContain(confirmation);
    const mics = items()[0];
    expect(mics.textContent).toContain("Reserved: 3 of 3");
    expect(mics.textContent).toContain("Fully reserved");
    expect(mics.textContent).toContain("2 × Shure SLX-D reserved by hana@example.com");
    expect(mics.textContent).toContain("1 × Sennheiser EW-D reserved by hana@example.com");
    expect(screen.queryByRole("button", { name: "Reserve for 3 × Wireless microphone" })).toBeNull();
  });

  it("sends only the items given a quantity", async () => {
    apiClient.get.mockResolvedValue({ data: PAGE });
    apiClient.post.mockResolvedValue({ data: { ...PAGE, confirmation: "Reserved 1 × BenQ LU935.", saved: true } });
    const user = renderPage();

    await user.type(await screen.findByLabelText("Quantity of BenQ LU935"), "1");
    await user.click(reserveButton("1 × Projector"));

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/equipment-reservations", {
      requirement_id: 12, items: [{ resource_id: 4, quantity: 1 }],
    });
  });

  // TC-44-40 · AC5
  it("shows the available quantity when more is chosen than is available", async () => {
    const error = "Only 1 × Shure SLX-D is available for this event's period, not 2. Nothing was reserved.";
    apiClient.get.mockResolvedValue({ data: PAGE });
    apiClient.post.mockRejectedValue(failed(409, {
      error, available_quantity: 3,
      shortfalls: [{ resource_id: 1, name: "Shure SLX-D", requested_quantity: 2, available_quantity: 1 }],
    }));
    const user = renderPage();

    await user.type(await screen.findByLabelText("Quantity of Shure SLX-D"), "2");
    await user.click(reserveButton("3 × Wireless microphone"));

    expect((await within(items()[0]).findByRole("alert")).textContent).toContain(error);
    expect(screen.queryByRole("status")).toBeNull();
    expect(quantity("Shure SLX-D").value).toBe("2");
  });

  // TC-44-41 · AC6
  it("says when no suitable equipment is available and offers nothing to reserve", async () => {
    apiClient.get.mockResolvedValue({ data: PAGE });
    renderPage();

    await screen.findByRole("heading", { name: "Charity Gala" });
    const hologram = items()[2];
    expect(hologram.textContent).toContain("No suitable equipment is available to reserve");
    expect(within(hologram).queryByRole("button")).toBeNull();
    expect(within(hologram).queryByRole("spinbutton")).toBeNull();
  });

  // TC-44-42 · AC7
  it("keeps the selection after a failed save so it can be tried again", async () => {
    const error = "The equipment was not reserved, and the existing reservations are unchanged. Please try again.";
    apiClient.get.mockResolvedValue({ data: PAGE });
    apiClient.post
      .mockRejectedValueOnce(failed(503, { error, retryable: true }))
      .mockResolvedValueOnce({ data: { ...PAGE, confirmation: "Reserved 1 × BenQ LU935.", saved: true } });
    const user = renderPage();

    await user.type(await screen.findByLabelText("Quantity of BenQ LU935"), "1");
    await user.click(reserveButton("1 × Projector"));

    expect((await within(items()[1]).findByRole("alert")).textContent).toContain(error);
    expect(quantity("BenQ LU935").value).toBe("1");
    await user.click(reserveButton("1 × Projector"));

    expect((await screen.findByRole("status")).textContent).toContain("Reserved 1 × BenQ LU935.");
    expect(apiClient.post).toHaveBeenCalledTimes(2);
    expect(apiClient.post.mock.calls[1]).toEqual(apiClient.post.mock.calls[0]);
  });

  it("explains a failed save without a server message", async () => {
    apiClient.get.mockResolvedValue({ data: PAGE });
    apiClient.post.mockRejectedValue(new Error("Network Error"));
    const user = renderPage();

    await user.type(await screen.findByLabelText("Quantity of BenQ LU935"), "1");
    await user.click(reserveButton("1 × Projector"));

    expect((await screen.findByRole("alert")).textContent).toContain("The equipment was not reserved");
  });

  it("loads the page again when the reservation was saved but the page could not be sent back", async () => {
    const confirmation = "Reserved 1 × BenQ LU935 for 1 × Projector at Charity Gala.";
    const reserved = { ...PROJECTOR, reserved_quantity: 1, remaining_quantity: 0, state: "fully_reserved",
                       state_label: "Fully reserved", reservations: [reservation(5, "BenQ LU935", 1)] };
    apiClient.get
      .mockResolvedValueOnce({ data: PAGE })
      .mockResolvedValueOnce({ data: { ...PAGE, requirements: [MICS, reserved, HOLOGRAM] } });
    apiClient.post.mockResolvedValue({ data: {
      confirmation, saved: true,
      refresh_error: "The equipment was reserved, but the updated page could not be loaded. Reload the page to see it.",
    } });
    const user = renderPage();

    await user.type(await screen.findByLabelText("Quantity of BenQ LU935"), "1");
    await user.click(reserveButton("1 × Projector"));

    expect((await screen.findByRole("status")).textContent).toContain(confirmation);
    expect(await screen.findByText("1 × BenQ LU935 reserved by hana@example.com")).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledTimes(2);
  });

  // TC-44-43 · AC1, AC8
  it("shows the coordinator the reservations without a way to reserve", async () => {
    const reserved = { ...MICS, reserved_quantity: 2, remaining_quantity: 1,
                       reservations: [reservation(1, "Shure SLX-D", 2)] };
    apiClient.get.mockResolvedValue({ data: { ...PAGE, can_reserve: false, requirements: [reserved, PROJECTOR] } });
    renderPage();

    await screen.findByRole("heading", { name: "Charity Gala" });
    expect(items()[0].textContent).toContain("Reserved: 2 of 3");
    expect(items()[0].textContent).toContain("2 × Shure SLX-D reserved by hana@example.com");
    expect(screen.queryByRole("button", { name: /^Reserve for/ })).toBeNull();
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  // TC-44-44 · AC9
  it("lists released reservations with the reason", async () => {
    const released = [reservation(1, "Shure SLX-D", 2, {
      status: "released", released_at: "2026-10-24T01:00:00", release_reason: "The event was cancelled.",
    })];
    apiClient.get.mockResolvedValue({ data: {
      ...PAGE, event: { ...EVENT, status: "cancelled" }, can_reserve: false,
      notice: "This event is cancelled, so equipment can't be reserved for it.", released,
    } });
    renderPage();

    const list = await screen.findByRole("list", { name: "Released reservations" });
    expect(within(list).getByRole("listitem").textContent).toContain("2 × Shure SLX-D released: The event was cancelled.");
  });

  // TC-44-45 · AC1
  it("explains why an event that is not approved cannot be reserved for", async () => {
    const notice = "Equipment can only be reserved for approved events. This event is submitted.";
    apiClient.get.mockResolvedValue({ data: { ...PAGE, event: { ...EVENT, status: "submitted" }, can_reserve: false, notice } });
    renderPage();

    expect(await screen.findByText(notice)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Reserve for/ })).toBeNull();
  });

  it("says when the event has no requirements", async () => {
    const message = "No equipment requirements have been recorded for this event.";
    apiClient.get.mockResolvedValue({ data: { ...PAGE, requirements: [], message } });
    renderPage();

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Equipment requirements" })).toBeNull();
  });

  it("explains a failed load and offers Retry", async () => {
    apiClient.get
      .mockRejectedValueOnce(failed(503, { error: "The equipment reservations could not be loaded. Please try again.", retryable: true }))
      .mockResolvedValueOnce({ data: PAGE });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { name: "Charity Gala" })).toBeTruthy();
  });

  it("shows a refusal without Retry", async () => {
    const denied = "You are not allowed to view this event's equipment reservations.";
    apiClient.get.mockRejectedValue(failed(403, { error: denied }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(denied);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});

function later() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

describe("SCRUM-44 pages for another event or out of order", () => {
  // TC-44-46 · AC1
  it("shows only the event in the address, even when the previous event's page arrives last", async () => {
    const gala = later();
    const workshop = { ...PAGE, event: { ...EVENT, id: 8, title: "Workshop" },
                       requirements: [{ ...HOLOGRAM, id: 21, equipment_type: "Lectern" }] };
    apiClient.get.mockImplementation(async (url) => {
      if (url === "/events/7/equipment-reservations") return gala.promise;
      if (url === "/events/8/equipment-reservations") return { data: workshop };
      throw new Error(`Unexpected API read: ${url}`);
    });
    render(
      <MemoryRouter initialEntries={["/events/7/equipment-reservations"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Link to="/events/8/equipment-reservations">Open the workshop</Link>
        <Routes>
          <Route path="/events/:eventId/equipment-reservations" element={<EquipmentReservationPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole("link", { name: "Open the workshop" }));
    expect(await screen.findByRole("heading", { name: "Workshop" })).toBeTruthy();
    await act(async () => gala.resolve({ data: PAGE }));

    expect(screen.queryByRole("heading", { name: "Charity Gala" })).toBeNull();
    expect(screen.queryByText(/Wireless microphone/)).toBeNull();
    expect(items()[0].textContent).toContain("1 × Lectern");
  });
});
