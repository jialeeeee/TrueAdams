import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import EquipmentRequestsPage from "./EquipmentRequestsPage.jsx";

// Frontend case TC-42-38 in docs/test-cases/SCRUM-42-equipment-requirements.md (AC4:
// Technical Support Staff find the events whose equipment needs arranging). The API is
// covered by backend/tests/test_equipment_requirements.py (TC-42-20, 23, 29); responses
// mirror its contract:
//   GET /events/equipment-requests -> { events: [{ id, title, status, start_time, end_time,
//     coordinator, requirement_count, status_counts }], message }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const LAUNCH = {
  id: 8,
  title: "Product Launch",
  status: "submitted",
  start_time: "2026-11-20T14:00:00",
  end_time: "2026-11-20T16:00:00",
  coordinator: { id: 3, email: "ben.coordinator@connectsphere.test" },
  requirement_count: 1,
  status_counts: { requested: 1, being_arranged: 0, unavailable: 0 },
};
const GALA = {
  ...LAUNCH,
  id: 7,
  title: "Charity Gala",
  status: "approved",
  start_time: "2026-12-05T18:00:00",
  end_time: "2026-12-05T23:00:00",
  coordinator: { id: 2, email: "alice.coordinator@connectsphere.test" },
  requirement_count: 2,
  status_counts: { requested: 1, being_arranged: 1, unavailable: 0 },
};
const failed = (status, data) =>
  Object.assign(new Error("Request failed"), { response: { status, data } });

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/equipment-requests"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/equipment-requests" element={<EquipmentRequestsPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-42 AC4 Technical Support Staff see which events need equipment", () => {
  it("lists each event with its coordinator and arrangement progress, linking to its requirements", async () => {
    apiClient.get.mockResolvedValue({ data: { events: [LAUNCH, GALA], message: null } });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Equipment requests" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/equipment-requests");
    const items = screen.getAllByRole("listitem");
    expect(items.map((item) => within(item).getByRole("link").textContent)).toEqual(["Product Launch", "Charity Gala"]);
    const gala = items[1];
    expect(within(gala).getByRole("link").getAttribute("href")).toBe("/events/7/equipment");
    expect(gala.textContent).toContain("05/12/2026 18:00 SGT");
    expect(gala.textContent).toContain("Coordinator: alice.coordinator@connectsphere.test");
    expect(gala.textContent).toContain("2 requirements");
    expect(gala.textContent).toContain("Requested: 1");
    expect(gala.textContent).toContain("Being arranged: 1");
    expect(gala.textContent).toContain("Suitable equipment unavailable: 0");
    expect(items[0].textContent).toContain("1 requirement");
  });

  it("says when no event needs equipment arranged", async () => {
    const message = "No events have equipment requirements to arrange.";
    apiClient.get.mockResolvedValue({ data: { events: [], message } });
    renderPage();

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("shows a refusal without Retry", async () => {
    const denied = "Only Technical Support Staff can view equipment requests.";
    apiClient.get.mockRejectedValue(failed(403, { error: denied }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(denied);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("offers Retry after a load failure, never an empty list", async () => {
    apiClient.get
      .mockRejectedValueOnce(failed(503, { error: "The equipment requests could not be loaded. Please try again.", retryable: true }))
      .mockResolvedValueOnce({ data: { events: [GALA], message: null } });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    expect(screen.queryByText("No events have equipment requirements to arrange.")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("link", { name: "Charity Gala" })).toBeTruthy();
  });
});
