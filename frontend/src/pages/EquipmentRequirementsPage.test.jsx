import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EquipmentRequirementsPage from "./EquipmentRequirementsPage.jsx";

// Frontend cases TC-42-30 to TC-42-37, 41 and 42 in docs/test-cases/SCRUM-42-equipment-requirements.md.
// The API is covered by backend/tests/test_equipment_requirements.py; responses mirror its
// contract:
//   GET    /events/<id>/equipment-requirements -> PAGE
//   POST   /events/<id>/equipment-requirements -> { confirmation, requirement, ...PAGE }
//   PUT    /events/<id>/equipment-requirements/<rid> -> { confirmation, requirement, ...PAGE }
//   DELETE /events/<id>/equipment-requirements/<rid> -> { confirmation, ...PAGE }
//   PATCH  /events/<id>/equipment-requirements/<rid>/arrangement -> { confirmation, requirement, ...PAGE }
//   PAGE = { event, organiser_note, requirements, can_edit, can_update_arrangements, notice, message }

vi.mock("../api/client.js", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

const EVENT = {
  id: 7,
  title: "Charity Gala",
  status: "approved",
  start_time: "2026-12-05T18:00:00",
  end_time: "2026-12-05T23:00:00",
  coordinator: { id: 2, email: "alice.coordinator@connectsphere.test" },
};
const MIC = {
  id: 11,
  equipment_type: "Wireless microphone",
  quantity: 2,
  technical_requirements: "Lapel, with spare batteries",
  status: "requested",
  status_label: "Requested",
  arrangement_note: null,
  recorded_at: "2026-10-21T02:00:00",
  last_saved_at: "2026-10-21T02:00:00",
  arrangement_updated_at: null,
  arrangement_updated_by: null,
};
const PROJECTOR = {
  ...MIC,
  id: 12,
  equipment_type: "Projector",
  quantity: 1,
  technical_requirements: null,
  status: "being_arranged",
  status_label: "Being arranged",
  arrangement_note: "Held at the AV store",
};
const PAGE = {
  event: EVENT,
  organiser_note: "Two wireless microphones and a projector",
  requirements: [MIC],
  can_edit: true,
  can_update_arrangements: false,
  notice: null,
  message: null,
};
const EMPTY = { ...PAGE, requirements: [], message: "No equipment requirements have been recorded for this event." };
const TECH_PAGE = { ...PAGE, requirements: [MIC, PROJECTOR], can_edit: false, can_update_arrangements: true };

const loaded = (overrides = {}) => ({ data: { ...PAGE, ...overrides } });
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/equipment"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/equipment" element={<EquipmentRequirementsPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const typeInput = () => screen.getByLabelText("Equipment type");
const quantityInput = () => screen.getByLabelText("Quantity");
const technicalInput = () => screen.getByLabelText("Technical requirements (optional)");
const recordButton = () => screen.getByRole("button", { name: "Record requirement" });
const list = () => screen.getByRole("list", { name: "Recorded equipment requirements" });

async function enter(user, { type, quantity, technical }) {
  await user.clear(typeInput());
  await user.type(typeInput(), type);
  await user.clear(quantityInput());
  await user.type(quantityInput(), quantity);
  await user.clear(technicalInput());
  if (technical) await user.type(technicalInput(), technical);
}

beforeEach(() => {
  for (const method of ["get", "post", "put", "delete", "patch"]) apiClient[method].mockReset();
});

describe("SCRUM-42 AC1/AC3 the coordinator records equipment requirements", () => {
  // TC-42-30
  it("shows the event, the organiser's note and the recorded requirements", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Equipment requirements" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/equipment-requirements");
    expect(screen.getByRole("heading", { name: "Charity Gala" })).toBeTruthy();
    expect(screen.getByText("When: 05/12/2026 18:00 SGT to 05/12/2026 23:00 SGT")).toBeTruthy();
    expect(screen.getByText("From the organiser's request: Two wireless microphones and a projector")).toBeTruthy();
    const item = within(list()).getByRole("listitem");
    expect(item.textContent).toContain("2 × Wireless microphone");
    expect(item.textContent).toContain("Technical requirements: Lapel, with spare batteries");
    expect(item.textContent).toContain("Status: Requested");
    expect(screen.getByRole("link", { name: "Back to the event" }).getAttribute("href")).toBe("/events/7/planning");
  });

  it("says when nothing has been recorded yet", async () => {
    apiClient.get.mockResolvedValue({ data: EMPTY });
    renderPage();

    expect(await screen.findByText("No equipment requirements have been recorded for this event.")).toBeTruthy();
    expect(recordButton()).toBeTruthy();
  });

  // TC-42-31
  it("records a requirement and shows the confirmation", async () => {
    const message = "Recorded 2 × Wireless microphone for Charity Gala. Recording a requirement does not reserve any equipment.";
    apiClient.get.mockResolvedValue({ data: EMPTY });
    apiClient.post.mockResolvedValue({ data: { ...PAGE, confirmation: message, requirement: MIC } });
    const user = renderPage();
    await screen.findByLabelText("Equipment type");

    await enter(user, { type: "Wireless microphone", quantity: "2", technical: "Lapel, with spare batteries" });
    await user.click(recordButton());

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/equipment-requirements", {
      equipment_type: "Wireless microphone", quantity: 2, technical_requirements: "Lapel, with spare batteries",
    });
    expect((await screen.findByRole("status")).textContent).toContain(message);
    expect(within(list()).getByRole("listitem").textContent).toContain("2 × Wireless microphone");
    expect(typeInput().value).toBe("");
    expect(quantityInput().value).toBe("");
  });

  // TC-42-32
  it("shows each invalid field and keeps what was entered", async () => {
    apiClient.get.mockResolvedValue({ data: EMPTY });
    apiClient.post.mockRejectedValue(failed(422, {
      error: "Some details are not valid. Please correct them and try again.",
      fields: { equipment_type: "Enter the equipment type.", quantity: "Quantity must be a whole number from 1 to 1000." },
    }));
    const user = renderPage();
    await screen.findByLabelText("Equipment type");

    await enter(user, { type: " ", quantity: "0" });
    await user.click(recordButton());

    expect((await screen.findByRole("alert")).textContent).toContain("Please correct them");
    expect(screen.getByText("Enter the equipment type.")).toBeTruthy();
    expect(screen.getByText("Quantity must be a whole number from 1 to 1000.")).toBeTruthy();
    expect(typeInput().value).toBe(" ");
    expect(quantityInput().value).toBe("0");
  });

  // TC-42-33
  it("keeps the entry when saving fails so it can be saved again", async () => {
    const refusal = "The equipment requirement was not saved, and the recorded requirements are unchanged. Please try again.";
    apiClient.get.mockResolvedValue(loaded());
    apiClient.post
      .mockRejectedValueOnce(failed(503, { error: refusal, retryable: true }))
      .mockResolvedValueOnce({ data: { ...PAGE, requirements: [MIC, PROJECTOR], confirmation: "Recorded.", requirement: PROJECTOR } });
    const user = renderPage();
    await screen.findByLabelText("Equipment type");

    await enter(user, { type: "Projector", quantity: "1" });
    await user.click(recordButton());

    expect((await screen.findByRole("alert")).textContent).toContain(refusal);
    expect(typeInput().value).toBe("Projector");
    expect(quantityInput().value).toBe("1");
    expect(within(list()).getAllByRole("listitem")).toHaveLength(1);

    await user.click(recordButton());
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(apiClient.post).toHaveBeenCalledTimes(2);
    expect(within(list()).getAllByRole("listitem")).toHaveLength(2);
  });

  it("explains a failed save without a server message", async () => {
    apiClient.get.mockResolvedValue(loaded());
    apiClient.post.mockRejectedValue(new Error("Network Error"));
    const user = renderPage();
    await screen.findByLabelText("Equipment type");

    await enter(user, { type: "Projector", quantity: "1" });
    await user.click(recordButton());

    expect((await screen.findByRole("alert")).textContent).toContain("recorded requirements are unchanged");
  });

  // TC-42-34
  it("edits a requirement", async () => {
    const edited = { ...MIC, quantity: 3, technical_requirements: "Handheld" };
    apiClient.get.mockResolvedValue(loaded());
    apiClient.put.mockResolvedValue({ data: { ...PAGE, requirements: [edited], requirement: edited, confirmation: "Updated 3 × Wireless microphone." } });
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Edit 2 × Wireless microphone" }));
    expect(typeInput().value).toBe("Wireless microphone");
    expect(quantityInput().value).toBe("2");
    expect(technicalInput().value).toBe("Lapel, with spare batteries");
    await user.clear(quantityInput());
    await user.type(quantityInput(), "3");
    await user.clear(technicalInput());
    await user.type(technicalInput(), "Handheld");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(apiClient.put).toHaveBeenCalledWith("/events/7/equipment-requirements/11", {
      equipment_type: "Wireless microphone", quantity: 3, technical_requirements: "Handheld",
    });
    expect((await screen.findByRole("status")).textContent).toContain("Updated 3 × Wireless microphone.");
    expect(within(list()).getByRole("listitem").textContent).toContain("3 × Wireless microphone");
    expect(screen.getByRole("button", { name: "Record requirement" })).toBeTruthy();
  });

  it("cancels an edit without saving", async () => {
    apiClient.get.mockResolvedValue(loaded());
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Edit 2 × Wireless microphone" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(apiClient.put).not.toHaveBeenCalled();
    expect(typeInput().value).toBe("");
    expect(recordButton()).toBeTruthy();
  });

  it("removes a requirement", async () => {
    apiClient.get.mockResolvedValue(loaded());
    apiClient.delete.mockResolvedValue({ data: { ...EMPTY, confirmation: "Removed 2 × Wireless microphone." } });
    const user = renderPage();

    await user.click(await screen.findByRole("button", { name: "Remove 2 × Wireless microphone" }));

    expect(apiClient.delete).toHaveBeenCalledWith("/events/7/equipment-requirements/11");
    expect((await screen.findByRole("status")).textContent).toContain("Removed 2 × Wireless microphone.");
    expect(screen.getByText("No equipment requirements have been recorded for this event.")).toBeTruthy();
  });
});

// SCRUM-43 (TC-43-21): Technical Support reach the availability check from here.
describe("SCRUM-43 check availability from the equipment requirements", () => {
  it("links Technical Support Staff to the availability check", async () => {
    apiClient.get.mockResolvedValue({ data: TECH_PAGE });
    renderPage();

    const link = await screen.findByRole("link", { name: "Check availability" });
    expect(link.getAttribute("href")).toBe("/events/7/equipment-availability");
  });

  it("does not offer the check to the coordinator", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    await screen.findByRole("heading", { name: "Charity Gala" });
    expect(screen.queryByRole("link", { name: "Check availability" })).toBeNull();
  });
});

// SCRUM-44 (TC-44-47): reserving starts from here; the coordinator can see what is reserved.
describe("SCRUM-44 reserve equipment from the equipment requirements", () => {
  it("links Technical Support Staff to reserving equipment", async () => {
    apiClient.get.mockResolvedValue({ data: TECH_PAGE });
    renderPage();

    const link = await screen.findByRole("link", { name: "Reserve equipment" });
    expect(link.getAttribute("href")).toBe("/events/7/equipment-reservations");
    expect(screen.queryByRole("link", { name: "Reserved equipment" })).toBeNull();
  });

  it("links the coordinator to the reserved equipment", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    const link = await screen.findByRole("link", { name: "Reserved equipment" });
    expect(link.getAttribute("href")).toBe("/events/7/equipment-reservations");
    expect(screen.queryByRole("link", { name: "Reserve equipment" })).toBeNull();
  });
});

describe("SCRUM-42 AC4/AC6 Technical Support Staff update the arrangements", () => {
  // TC-42-35
  it("lets Technical Support Staff update the arrangement status", async () => {
    const updated = { ...MIC, status: "being_arranged", status_label: "Being arranged", arrangement_note: "Two lapel mics held" };
    apiClient.get.mockResolvedValue({ data: TECH_PAGE });
    apiClient.patch.mockResolvedValue({
      data: { ...TECH_PAGE, requirements: [updated, PROJECTOR], requirement: updated, confirmation: "Arrangement status updated to Being arranged." },
    });
    const user = renderPage();

    const status = await screen.findByLabelText("Arrangement status for 2 × Wireless microphone");
    expect(screen.queryByLabelText("Equipment type")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Edit / })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Remove / })).toBeNull();
    expect(screen.getByRole("link", { name: "Back to equipment requests" }).getAttribute("href")).toBe("/equipment-requests");
    // Reserving is SCRUM-44: these are the only statuses offered (AC6).
    expect(within(status).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Requested", "Being arranged", "Suitable equipment unavailable",
    ]);
    expect(screen.getByText("Note from Technical Support: Held at the AV store")).toBeTruthy();

    await user.selectOptions(status, "being_arranged");
    await user.type(screen.getByLabelText("Note for 2 × Wireless microphone"), "Two lapel mics held");
    await user.click(screen.getByRole("button", { name: "Update 2 × Wireless microphone" }));

    expect(apiClient.patch).toHaveBeenCalledWith("/events/7/equipment-requirements/11/arrangement", {
      status: "being_arranged", note: "Two lapel mics held",
    });
    expect((await screen.findByRole("status")).textContent).toContain("Arrangement status updated to Being arranged.");
    expect(within(list()).getAllByRole("listitem")[0].textContent).toContain("Status: Being arranged");
  });

  it("shows why an arrangement update failed", async () => {
    const refusal = "The arrangement status was not saved. Please try again.";
    apiClient.get.mockResolvedValue({ data: TECH_PAGE });
    apiClient.patch.mockRejectedValue(failed(503, { error: refusal, retryable: true }));
    const user = renderPage();

    await user.selectOptions(await screen.findByLabelText("Arrangement status for 1 × Projector"), "unavailable");
    await user.click(screen.getByRole("button", { name: "Update 1 × Projector" }));

    expect((await screen.findByRole("alert")).textContent).toContain(refusal);
    expect(screen.getByLabelText("Arrangement status for 1 × Projector").value).toBe("unavailable");
  });
});

// Review of PR #47: replies for another event, or older replies, must never show.
const WORKSHOP = {
  ...PAGE,
  event: { ...EVENT, id: 8, title: "Workshop" },
  organiser_note: null,
  requirements: [{ ...MIC, id: 21, equipment_type: "Lectern", quantity: 1, technical_requirements: null }],
};

function later() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

// One mounted route, as when the address changes from event 7's page to event 8's.
function renderMovingToWorkshop() {
  render(
    <MemoryRouter initialEntries={["/events/7/equipment"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Link to="/events/8/equipment">Open the workshop</Link>
      <Routes>
        <Route path="/events/:eventId/equipment" element={<EquipmentRequirementsPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const pageFor = (gala) => async (url) => {
  if (url === "/events/7/equipment-requirements") return gala;
  if (url === "/events/8/equipment-requirements") return { data: WORKSHOP };
  throw new Error(`Unexpected API read: ${url}`);
};

describe("SCRUM-42 replies for another event or out of order", () => {
  // TC-42-41
  it("shows only the event in the address, even when the previous event's reply arrives last", async () => {
    const gala = later();
    apiClient.get.mockImplementation(pageFor(gala.promise));
    const user = renderMovingToWorkshop();

    await user.click(screen.getByRole("link", { name: "Open the workshop" }));
    expect(await screen.findByRole("heading", { name: "Workshop" })).toBeTruthy();
    await act(async () => gala.resolve({ data: PAGE }));

    expect(screen.getByRole("heading", { name: "Workshop" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Charity Gala" })).toBeNull();
    expect(screen.queryByText(/Wireless microphone/)).toBeNull();
    expect(within(list()).getByRole("listitem").textContent).toContain("1 × Lectern");
  });

  it("starts the next event with an empty form, not the previous event's edit", async () => {
    apiClient.get.mockImplementation(pageFor(Promise.resolve({ data: PAGE })));
    const user = renderMovingToWorkshop();
    await user.click(await screen.findByRole("button", { name: "Edit 2 × Wireless microphone" }));
    expect(typeInput().value).toBe("Wireless microphone");

    await user.click(screen.getByRole("link", { name: "Open the workshop" }));

    expect(await screen.findByRole("heading", { name: "Workshop" })).toBeTruthy();
    expect(typeInput().value).toBe("");
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
  });

  it("ignores a save for the previous event that finishes after moving on", async () => {
    const saved = later();
    apiClient.get.mockImplementation(pageFor(Promise.resolve({ data: PAGE })));
    apiClient.post.mockReturnValue(saved.promise);
    const user = renderMovingToWorkshop();
    await screen.findByLabelText("Equipment type");
    await enter(user, { type: "Projector", quantity: "1" });
    await user.click(recordButton());

    await user.click(screen.getByRole("link", { name: "Open the workshop" }));
    await screen.findByRole("heading", { name: "Workshop" });
    await act(async () => saved.resolve({
      data: { ...PAGE, requirements: [MIC, PROJECTOR], requirement: PROJECTOR, confirmation: "Recorded 1 × Projector for Charity Gala." },
    }));

    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByText(/Projector/)).toBeNull();
    expect(within(list()).getByRole("listitem").textContent).toContain("1 × Lectern");
  });

  // TC-42-42
  it("loads the list again when the change was saved but the list could not be sent back", async () => {
    const confirmation = "Recorded 1 × Projector for Charity Gala. Recording a requirement does not reserve any equipment.";
    apiClient.get
      .mockResolvedValueOnce(loaded())
      .mockResolvedValueOnce(loaded({ requirements: [MIC, PROJECTOR] }));
    apiClient.post.mockResolvedValue({ data: {
      confirmation, saved: true,
      refresh_error: "The change was saved, but the updated requirements could not be loaded. Reload the page to see them.",
    } });
    const user = renderPage();
    await screen.findByLabelText("Equipment type");

    await enter(user, { type: "Projector", quantity: "1" });
    await user.click(recordButton());

    expect((await screen.findByRole("status")).textContent).toContain(confirmation);
    expect(await within(list()).findByText("1 × Projector")).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(typeInput().value).toBe("");
  });

  it("says the change was saved when the list can't be loaded afterwards either", async () => {
    apiClient.get
      .mockResolvedValueOnce(loaded())
      .mockRejectedValueOnce(failed(503, { error: "The equipment requirements could not be loaded. Please try again.", retryable: true }));
    apiClient.post.mockResolvedValue({ data: {
      confirmation: "Recorded 1 × Projector for Charity Gala.", saved: true,
      refresh_error: "The change was saved, but the updated requirements could not be loaded. Reload the page to see them.",
    } });
    const user = renderPage();
    await screen.findByLabelText("Equipment type");

    await enter(user, { type: "Projector", quantity: "1" });
    await user.click(recordButton());

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    expect(screen.getByRole("status").textContent).toContain("Recorded 1 × Projector");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("keeps the newest list when an older load arrives after a save", async () => {
    const reload = later();
    apiClient.get
      .mockResolvedValueOnce(loaded())
      .mockReturnValueOnce(reload.promise);
    apiClient.post
      .mockResolvedValueOnce({ data: { confirmation: "Recorded 1 × Projector.", saved: true, refresh_error: "Reload the page." } })
      .mockResolvedValueOnce({ data: { ...PAGE, requirements: [MIC, PROJECTOR, { ...PROJECTOR, id: 13, equipment_type: "Screen" }], confirmation: "Recorded 1 × Screen." } });
    const user = renderPage();
    await screen.findByLabelText("Equipment type");

    await enter(user, { type: "Projector", quantity: "1" });
    await user.click(recordButton());
    await enter(user, { type: "Screen", quantity: "1" });
    await user.click(recordButton());
    expect(await within(list()).findByText("1 × Screen")).toBeTruthy();
    await act(async () => reload.resolve(loaded()));

    expect(within(list()).getAllByRole("listitem")).toHaveLength(3);
  });
});

describe("SCRUM-42 read-only and failures", () => {
  // TC-42-36
  it("shows a cancelled event's requirements read-only", async () => {
    const notice = "This event is cancelled, so its equipment requirements can no longer be changed.";
    apiClient.get.mockResolvedValue(loaded({ event: { ...EVENT, status: "cancelled" }, can_edit: false, notice }));
    renderPage();

    expect(await screen.findByText(notice)).toBeTruthy();
    expect(within(list()).getByRole("listitem").textContent).toContain("2 × Wireless microphone");
    expect(screen.queryByLabelText("Equipment type")).toBeNull();
    expect(screen.queryByRole("button", { name: /^(Edit|Remove|Update) / })).toBeNull();
  });

  // TC-42-37
  it("offers Retry after a load failure", async () => {
    apiClient.get
      .mockRejectedValueOnce(failed(503, { error: "The equipment requirements could not be loaded. Please try again.", retryable: true }))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    expect(screen.queryByRole("list", { name: "Recorded equipment requirements" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { name: "Charity Gala" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledTimes(2);
  });

  it("shows a refusal without Retry", async () => {
    const denied = "You are not allowed to view this event's equipment requirements.";
    apiClient.get.mockRejectedValue(failed(403, { error: denied }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(denied);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.queryByLabelText("Equipment type")).toBeNull();
  });
});
