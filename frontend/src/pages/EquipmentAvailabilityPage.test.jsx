import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EquipmentAvailabilityPage from "./EquipmentAvailabilityPage.jsx";

// Frontend cases TC-43-16 to TC-43-20 in docs/test-cases/SCRUM-43-equipment-availability.md.
// The API is covered by backend/tests/test_equipment_availability.py; responses mirror
// its contract:
//   GET /events/<id>/equipment-availability -> { event, checks: [LINE], summary,
//     can_all_be_met, notice, message }
//   LINE = { requirement_id, equipment_type, requested_quantity, technical_requirements,
//     technical_note, available_quantity, result, result_label, suitable, excluded }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const EVENT = {
  id: 7, title: "Charity Gala", status: "approved",
  start_time: "2026-12-05T18:00:00", end_time: "2026-12-05T23:00:00",
};
const MICS = {
  requirement_id: 11, equipment_type: "Wireless microphone", requested_quantity: 3,
  technical_requirements: "Lapel",
  technical_note: "Technical Support must confirm the technical requirements: Lapel",
  available_quantity: 4, result: "enough", result_label: "Enough available",
  suitable: [
    { id: 1, name: "Shure SLX-D", category: "Wireless microphone", quantity_available: 2 },
    { id: 2, name: "Sennheiser EW-D", category: "wireless  MICROPHONE", quantity_available: 2 },
  ],
  excluded: [],
};
const PROJECTOR = {
  requirement_id: 12, equipment_type: "Projector", requested_quantity: 1,
  technical_requirements: null, technical_note: null,
  available_quantity: 2, result: "enough", result_label: "Enough available",
  suitable: [{ id: 4, name: "BenQ LU935", category: "Projector", quantity_available: 2 }],
  excluded: [{ id: 3, name: "Epson EB-L", reason: "unavailable",
               detail: "Unavailable 2026-12-05 17:00 to 2026-12-05 19:00: Lamp replacement" }],
};
const HOLOGRAM = {
  requirement_id: 13, equipment_type: "Hologram projector", requested_quantity: 1,
  technical_requirements: null, technical_note: null,
  available_quantity: 0, result: "none_suitable", result_label: "No suitable equipment available",
  suitable: [], excluded: [],
};
const RESULT = {
  event: EVENT,
  checks: [MICS, PROJECTOR, HOLOGRAM],
  summary: "2 of 3 equipment requirements can be met from available equipment.",
  can_all_be_met: false,
  notice: "Checking availability does not reserve any equipment.",
  message: null,
};
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/equipment-availability"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/equipment-availability" element={<EquipmentAvailabilityPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const lines = () =>
  within(screen.getByRole("list", { name: "Availability by requirement" })).getAllByRole("listitem");

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-43 Technical Support check equipment availability", () => {
  // TC-43-16
  it("shows each requirement with its requested and available quantity", async () => {
    apiClient.get.mockResolvedValue({ data: RESULT });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Equipment availability" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/equipment-availability");
    expect(screen.getByRole("heading", { name: "Charity Gala" })).toBeTruthy();
    expect(screen.getByText("For: 05/12/2026 18:00 SGT to 05/12/2026 23:00 SGT")).toBeTruthy();
    expect(screen.getByText("2 of 3 equipment requirements can be met from available equipment.")).toBeTruthy();
    const [mics, , hologram] = lines();
    expect(mics.textContent).toContain("3 × Wireless microphone");
    expect(mics.textContent).toContain("Requested: 3 · Available: 4");
    expect(mics.textContent).toContain("Enough available");
    expect(mics.textContent).toContain("Counted: Shure SLX-D (2), Sennheiser EW-D (2)");
    expect(mics.textContent).toContain("Technical Support must confirm the technical requirements: Lapel");
    expect(hologram.textContent).toContain("Requested: 1 · Available: 0");
    expect(hologram.textContent).toContain("No suitable equipment available");
    expect(screen.getByRole("link", { name: "Back to the equipment requirements" }).getAttribute("href"))
      .toBe("/events/7/equipment");
  });

  // TC-43-17
  it("lists the equipment excluded and why", async () => {
    apiClient.get.mockResolvedValue({ data: RESULT });
    renderPage();

    await screen.findByRole("heading", { name: "Equipment availability" });
    const projector = lines()[1];
    expect(projector.textContent).toContain("Counted: BenQ LU935 (2)");
    expect(projector.textContent).toContain(
      "Not counted: Epson EB-L (Unavailable 2026-12-05 17:00 to 2026-12-05 19:00: Lamp replacement)");
  });

  // TC-43-18
  it("says that checking does not reserve any equipment", async () => {
    apiClient.get.mockResolvedValue({ data: RESULT });
    renderPage();

    expect(await screen.findByText("Checking availability does not reserve any equipment.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /reserve/i })).toBeNull();
  });

  it("says when the event has no requirements to check", async () => {
    const message = "No equipment requirements have been recorded for this event.";
    apiClient.get.mockResolvedValue({ data: { ...RESULT, checks: [], summary: null, message } });
    renderPage();

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Availability by requirement" })).toBeNull();
  });

  // TC-43-19
  it("explains missing times without showing a result", async () => {
    const error = "The event's start time and end time are not recorded, so equipment availability can't be checked. Ask the event's coordinator to record them.";
    apiClient.get.mockRejectedValue(failed(422, { error, missing: ["start_time", "end_time"] }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(error);
    expect(screen.queryByRole("list", { name: "Availability by requirement" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  // TC-43-20
  it("offers Retry after a failed check", async () => {
    apiClient.get
      .mockRejectedValueOnce(failed(503, { error: "The equipment availability check could not be completed. Please try again.", retryable: true }))
      .mockResolvedValueOnce({ data: RESULT });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be completed");
    expect(screen.queryByText(RESULT.summary)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(RESULT.summary)).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledTimes(2);
  });

  it("explains a failed check without a server message", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be completed");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("shows a refusal without Retry", async () => {
    const denied = "Only Technical Support Staff can check equipment availability.";
    apiClient.get.mockRejectedValue(failed(403, { error: denied }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(denied);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
