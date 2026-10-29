import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import EquipmentRequirementsPage from "./EquipmentRequirementsPage.jsx";

// Frontend cases TC-42-30 to TC-42-37, 41 and 42 in docs/test-cases/SCRUM-42-equipment-requirements.md.
// The API is covered by backend/tests/test_equipment_requirements.py; responses mirror its
// contract:
//   GET    /events/<id>/equipment-requirements -> PAGE
//   POST   /events/<id>/equipment-requirements -> { confirmation, requirement, ...PAGE }
//   PUT    /events/<id>/equipment-requirements/<rid> -> { confirmation, requirement, ...PAGE }
//   DELETE /events/<id>/equipment-requirements/<rid> -> { confirmation, ...PAGE }
//   PATCH  /events/<id>/equipment-requirements/<rid>/arrangement -> { confirmation, requirement, ...PAGE }
//   PAGE = { event, organiser_note, requirements, can_edit, can_update_arrangements, can_reserve,
//     notice, message }

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
  can_reserve: false,
  notice: null,
  message: null,
};
const EMPTY = { ...PAGE, requirements: [], message: "No equipment requirements have been recorded for this event." };
const TECH_PAGE = { ...PAGE, requirements: [MIC, PROJECTOR], can_edit: false, can_update_arrangements: true,
                    can_reserve: true };

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

  // TC-44-53: e.g. a submitted event, or one without times (SCRUM-44 review).
  it("offers Technical Support Staff a view link when the event can't be reserved for", async () => {
    apiClient.get.mockResolvedValue({ data: { ...TECH_PAGE, can_reserve: false } });
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

    // With the details it showed, so a change by the coordinator is noticed (SCRUM-97 A5).
    expect(apiClient.patch).toHaveBeenCalledWith("/events/7/equipment-requirements/11/arrangement", {
      status: "being_arranged", note: "Two lapel mics held", last_saved_at: MIC.last_saved_at,
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

// SCRUM-96: Technical Support view an event's equipment requirements. Frontend cases
// TC-96-13 to 16 in docs/test-cases/SCRUM-96-tech-views-equipment-requirements.md; the API
// side is backend/tests/test_tech_views_equipment.py.
describe("SCRUM-96 Technical Support view an event's equipment requirements", () => {
  const items = () => within(list()).getAllByRole("listitem");

  // TC-96-13 · AC1
  it("shows Technical Support each requirement's type, quantity and technical requirements", async () => {
    apiClient.get.mockResolvedValue({ data: TECH_PAGE });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Charity Gala" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/equipment-requirements");
    expect(items()).toHaveLength(2);
    expect(within(items()[0]).getByText("2 × Wireless microphone")).toBeTruthy();
    expect(within(items()[0]).getByText("Technical requirements: Lapel, with spare batteries")).toBeTruthy();
    expect(within(items()[0]).getByText("Status: Requested")).toBeTruthy();
    expect(within(items()[1]).getByText("1 × Projector")).toBeTruthy();
    expect(within(items()[1]).getByText("Technical requirements: None recorded")).toBeTruthy();
    expect(within(items()[1]).getByText("Status: Being arranged")).toBeTruthy();
    expect(screen.getByText("From the organiser's request: Two wireless microphones and a projector")).toBeTruthy();
    // They view and arrange; recording and editing are the coordinator's (SCRUM-42).
    expect(screen.queryByLabelText("Equipment type")).toBeNull();
    expect(screen.queryByRole("button", { name: /^(Edit|Remove) / })).toBeNull();
    expect(screen.getByLabelText("Arrangement status for 2 × Wireless microphone")).toBeTruthy();
  });

  // TC-96-14 · AC2
  it("shows a refusal or a missing event without Retry", async () => {
    for (const [status, message] of [
      [403, "You are not allowed to view this event's equipment requirements."],
      [404, "Event not found."],
    ]) {
      apiClient.get.mockReset();
      apiClient.get.mockRejectedValue(failed(status, { error: message }));
      const { unmount } = render(
        <MemoryRouter initialEntries={["/events/7/equipment"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes>
            <Route path="/events/:eventId/equipment" element={<EquipmentRequirementsPage />} />
          </Routes>
        </MemoryRouter>,
      );

      expect((await screen.findByRole("alert")).textContent).toBe(message);
      expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
      expect(screen.queryByRole("list", { name: "Recorded equipment requirements" })).toBeNull();
      expect(screen.queryByRole("heading", { name: "Charity Gala" })).toBeNull();
      unmount();
    }
  });

  // TC-96-15 · AC3
  it("explains a failed load and loads the requirements on Retry", async () => {
    const outage = "The equipment requirements could not be loaded. Please try again.";
    apiClient.get
      .mockRejectedValueOnce(failed(503, { error: outage, retryable: true }))
      .mockResolvedValueOnce({ data: TECH_PAGE });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toBe(outage);
    expect(screen.queryByRole("list", { name: "Recorded equipment requirements" })).toBeNull();
    // A failed load is never shown as "nothing recorded".
    expect(screen.queryByText("No equipment requirements have been recorded for this event.")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("2 × Wireless microphone")).toBeTruthy();
    expect(screen.getByText("1 × Projector")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(apiClient.get).toHaveBeenCalledTimes(2);
    expect(apiClient.get).toHaveBeenLastCalledWith("/events/7/equipment-requirements");
  });

  // TC-96-16 · AC3
  it("asks to check the connection when there is no reply, and keeps Retry until a load works", async () => {
    const noReply = Object.assign(new Error("Network Error"), { request: {} });
    apiClient.get
      .mockRejectedValueOnce(noReply)
      .mockRejectedValueOnce(noReply)
      .mockResolvedValueOnce({ data: TECH_PAGE });
    const user = renderPage();

    const connection = "The equipment requirements could not be loaded. Check your connection and try again.";
    expect((await screen.findByRole("alert")).textContent).toBe(connection);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await vi.waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(2));
    expect((await screen.findByRole("alert")).textContent).toBe(connection);

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("2 × Wireless microphone")).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledTimes(3);
  });
});

// SCRUM-97: Technical Support update an event's equipment requirements. Frontend cases
// TC-97-14 to 19 in docs/test-cases/SCRUM-97-tech-updates-equipment-requirements.md; the API
// side is backend/tests/test_tech_updates_equipment.py.
describe("SCRUM-97 Technical Support update an event's equipment requirements", () => {
  const HANA = { id: 9, email: "hana.tech@connectsphere.test" };
  const TOM = { id: 10, email: "tom.tech@connectsphere.test" };
  const ARRANGED = { ...PROJECTOR, arrangement_updated_by: HANA, arrangement_updated_at: "2026-10-29T06:30:00.123456" };
  const PAGE_97 = { ...TECH_PAGE, requirements: [MIC, ARRANGED] };
  const NOT_SAVED = "The arrangement was not saved, and the recorded requirements are unchanged. Please try again.";
  const items = () => within(list()).getAllByRole("listitem");
  const updatedBy = (who, at) => `Arrangement updated by ${who.email} on ${formatSavedAt(at)}`;
  const micStatus = () => screen.getByLabelText("Arrangement status for 2 × Wireless microphone");
  const micNote = () => screen.getByLabelText("Note for 2 × Wireless microphone");
  const updateMic = () => screen.getByRole("button", { name: "Update 2 × Wireless microphone" });

  async function enterMic(user) {
    await user.selectOptions(await screen.findByLabelText("Arrangement status for 2 × Wireless microphone"), "being_arranged");
    await user.type(micNote(), "Two lapel mics held");
  }

  // TC-97-14 · AC1
  it("shows who updated each arrangement and when, and sends the details it showed", async () => {
    apiClient.get.mockResolvedValue({ data: PAGE_97 });
    apiClient.patch.mockReturnValue(new Promise(() => {}));
    const user = renderPage();

    expect(await screen.findByText(updatedBy(HANA, ARRANGED.arrangement_updated_at))).toBeTruthy();
    expect(within(items()[1]).getByText(updatedBy(HANA, ARRANGED.arrangement_updated_at))).toBeTruthy();
    // Never updated: nobody is named.
    expect(within(items()[0]).queryByText(/Arrangement updated by/)).toBeNull();

    await enterMic(user);
    await user.click(updateMic());

    expect(apiClient.patch).toHaveBeenCalledWith("/events/7/equipment-requirements/11/arrangement", {
      status: "being_arranged", note: "Two lapel mics held", last_saved_at: MIC.last_saved_at,
    });
  });

  // TC-97-15 · AC1
  it("shows the update, who made it and when once it is saved", async () => {
    const at = "2026-10-30T03:15:00.000001";
    const updated = {
      ...MIC, status: "being_arranged", status_label: "Being arranged", arrangement_note: "Two lapel mics held",
      arrangement_updated_by: TOM, arrangement_updated_at: at,
    };
    apiClient.get.mockResolvedValue({ data: PAGE_97 });
    apiClient.patch.mockResolvedValue({
      data: { ...PAGE_97, requirements: [updated, ARRANGED], requirement: updated, saved: true,
              confirmation: "Arrangement status updated to Being arranged." },
    });
    const user = renderPage();

    await enterMic(user);
    await user.click(updateMic());

    expect((await screen.findByRole("status")).textContent).toBe("Arrangement status updated to Being arranged.");
    const mic = items()[0];
    expect(within(mic).getByText("Status: Being arranged")).toBeTruthy();
    expect(within(mic).getByText("Note from Technical Support: Two lapel mics held")).toBeTruthy();
    expect(within(mic).getByText(updatedBy(TOM, at))).toBeTruthy();
    expect(within(items()[1]).getByText(updatedBy(HANA, ARRANGED.arrangement_updated_at))).toBeTruthy();
  });

  // TC-97-16 · AC2
  it("shows a refusal and leaves the requirements as they were", async () => {
    const refusal = "Only Technical Support Staff can update equipment arrangements.";
    apiClient.get.mockResolvedValue({ data: PAGE_97 });
    apiClient.patch.mockRejectedValue(failed(403, { error: refusal }));
    const user = renderPage();

    await enterMic(user);
    await user.click(updateMic());

    expect((await screen.findByRole("alert")).textContent).toBe(refusal);
    expect(screen.queryByRole("status")).toBeNull();
    expect(within(items()[0]).getByText("Status: Requested")).toBeTruthy();
    expect(within(items()[0]).queryByText(/Note from Technical Support/)).toBeNull();
    expect(within(items()[0]).queryByText(/Arrangement updated by/)).toBeNull();
    expect(within(items()[1]).getByText(updatedBy(HANA, ARRANGED.arrangement_updated_at))).toBeTruthy();
  });

  // TC-97-17 · AC3
  it("keeps the requirements and the entry when a save fails, and saves on trying again", async () => {
    const updated = { ...MIC, status: "being_arranged", status_label: "Being arranged", arrangement_note: "Two lapel mics held",
                      arrangement_updated_by: HANA, arrangement_updated_at: "2026-10-30T03:15:00" };
    apiClient.get.mockResolvedValue({ data: PAGE_97 });
    apiClient.patch
      .mockRejectedValueOnce(failed(503, { error: NOT_SAVED, retryable: true }))
      .mockResolvedValueOnce({
        data: { ...PAGE_97, requirements: [updated, ARRANGED], requirement: updated, saved: true,
                confirmation: "Arrangement status updated to Being arranged." },
      });
    const user = renderPage();

    await enterMic(user);
    await user.click(updateMic());

    expect((await screen.findByRole("alert")).textContent).toBe(NOT_SAVED);
    expect(within(items()[0]).getByText("Status: Requested")).toBeTruthy();
    expect(within(items()[1]).getByText("Status: Being arranged")).toBeTruthy();
    expect(within(items()[1]).getByText("Note from Technical Support: Held at the AV store")).toBeTruthy();
    // What was chosen and typed stays, so pressing Update again tries again.
    expect(micStatus().value).toBe("being_arranged");
    expect(micNote().value).toBe("Two lapel mics held");

    await user.click(updateMic());

    expect((await screen.findByRole("status")).textContent).toBe("Arrangement status updated to Being arranged.");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(within(items()[0]).getByText("Status: Being arranged")).toBeTruthy();
    expect(apiClient.patch).toHaveBeenCalledTimes(2);
    expect(apiClient.patch.mock.calls[1]).toEqual(apiClient.patch.mock.calls[0]);
  });

  // TC-97-18 · AC3
  it("says the requirements are unchanged when there is no reply", async () => {
    apiClient.get.mockResolvedValue({ data: PAGE_97 });
    apiClient.patch.mockRejectedValue(Object.assign(new Error("Network Error"), { request: {} }));
    const user = renderPage();

    await enterMic(user);
    await user.click(updateMic());

    expect((await screen.findByRole("alert")).textContent).toBe(
      "The arrangement was not saved, and the recorded requirements are unchanged. Check your connection and try again.",
    );
    expect(within(items()[0]).getByText("Status: Requested")).toBeTruthy();
    expect(micNote().value).toBe("Two lapel mics held");
  });

  // TC-97-19 · AC1 (A5)
  it("reloads the new details when the coordinator changed the requirement", async () => {
    const changedMessage = "The coordinator has changed this requirement since you opened it, so your update was not saved. "
      + "It is now 5 × Wireless microphone: check the new details and update it again.";
    const changed = { ...MIC, quantity: 5, last_saved_at: "2026-10-30T02:00:00" };
    apiClient.get
      .mockResolvedValueOnce({ data: PAGE_97 })
      .mockResolvedValueOnce({ data: { ...PAGE_97, requirements: [changed, ARRANGED] } });
    apiClient.patch.mockRejectedValue(failed(409, { error: changedMessage, reload: true }));
    const user = renderPage();

    await enterMic(user);
    await user.click(updateMic());

    expect((await screen.findByRole("alert")).textContent).toBe(changedMessage);
    expect(await screen.findByText("5 × Wireless microphone")).toBeTruthy();
    expect(screen.queryByText("2 × Wireless microphone")).toBeNull();
    expect(apiClient.get).toHaveBeenCalledTimes(2);
    expect(within(items()[0]).getByText("Status: Requested")).toBeTruthy();
  });
});
