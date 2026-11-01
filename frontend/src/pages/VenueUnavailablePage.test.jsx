import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import VenueUnavailablePage from "./VenueUnavailablePage.jsx";

// Frontend cases for SCRUM-88 AC1 and AC6 (IS212-US88-TC1 to TC8 and TC27) in
// docs/test-cases/SCRUM-88-venue-becomes-unavailable.md. Responses mirror
// backend/tests/test_venue_unavailable.py.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const V101 = { id: 1, name: "Orchard Hall", location: "12 Orchard Road" };
const PERIOD = {
  id: 7, venue_id: 1, reason: "Floor renovation",
  start_time: "2027-11-20T09:00:00", end_time: "2027-11-20T18:00:00",
};

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function serve({ periods = [], denied = false } = {}) {
  apiClient.get.mockImplementation(async (url) => {
    if (url === "/venues/1") return { data: V101 };
    if (url === "/venues/1/unavailable") {
      if (denied) throw httpFailure(403, { error: "Only Venue Staff can record unavailable periods." });
      return { data: { periods, message: periods.length ? null : "No unavailable periods are recorded for this venue." } };
    }
    throw new Error(`unexpected GET ${url}`);
  });
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/venues/1/unavailable"]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes><Route path="/venues/:venueId/unavailable" element={<VenueUnavailablePage />} /></Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

async function fill(user, { reason = "Floor renovation", start = "2027-11-20T09:00", end = "2027-11-20T18:00" } = {}) {
  await screen.findByRole("heading", { name: /Orchard Hall/ });
  if (reason) await user.type(screen.getByLabelText("Reason"), reason);
  if (start) await user.type(screen.getByLabelText("Start"), start);
  if (end) await user.type(screen.getByLabelText("End"), end);
}

beforeEach(() => {
  Object.values(apiClient).forEach((fn) => fn.mockReset());
  serve();
});

describe("recording an unavailable period (AC1)", () => {
  it("TC1/TC2: sends the reason, start and end and shows the confirmation and the new period", async () => {
    apiClient.post.mockResolvedValue({ data: {
      message: "Orchard Hall is unavailable from 2027-11-20 09:00 to 2027-11-20 18:00. 1 booking was flagged.",
      period: PERIOD, flagged: [{ id: 5 }], notified: [2],
    } });
    const user = renderPage();
    await fill(user);
    serve({ periods: [PERIOD] });
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(apiClient.post).toHaveBeenCalledWith("/venues/1/unavailable", {
      reason: "Floor renovation", start_time: "2027-11-20T09:00", end_time: "2027-11-20T18:00",
    });
    expect((await screen.findByRole("status")).textContent).toContain("1 booking was flagged");
    const list = await screen.findByRole("list", { name: "Unavailable periods" });
    expect(list.textContent).toContain("Floor renovation");
    expect(list.textContent).toContain("2027-11-20 09:00 to 2027-11-20 18:00");
  });

  it("lists the periods already recorded, or says there are none", async () => {
    serve({ periods: [PERIOD] });
    renderPage();
    const list = await screen.findByRole("list", { name: "Unavailable periods" });
    expect(list.textContent).toContain("Floor renovation");
  });

  it("says when no period is recorded", async () => {
    renderPage();
    expect(await screen.findByText("No unavailable periods are recorded for this venue.")).toBeTruthy();
  });

  it("TC3/TC4/TC5: blocks the save and marks each missing field as required", async () => {
    const user = renderPage();
    await screen.findByRole("heading", { name: /Orchard Hall/ });
    await user.click(screen.getByRole("button", { name: "Save" }));

    const alerts = (await screen.findAllByRole("alert")).map((alert) => alert.textContent);
    expect(alerts).toEqual(expect.arrayContaining([
      "Enter the reason.", "Enter the start date and time.", "Enter the end date and time.",
    ]));
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("TC6/TC7: blocks an end that is not after the start", async () => {
    const user = renderPage();
    await fill(user, { start: "2027-11-20T18:00", end: "2027-11-20T09:00" });
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect((await screen.findByRole("alert")).textContent).toBe("The end must be after the start.");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("shows the server's field problems and keeps what was entered", async () => {
    apiClient.post.mockRejectedValue(httpFailure(400, {
      error: "Some details are missing or invalid.", fields: { reason: "The reason must be 500 characters or fewer." },
    }));
    const user = renderPage();
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect((await screen.findAllByRole("alert")).map((a) => a.textContent))
      .toContain("The reason must be 500 characters or fewer.");
    expect(screen.getByLabelText("Reason").value).toBe("Floor renovation");
  });

  it("a failed save says nothing was recorded and keeps the entries", async () => {
    apiClient.post.mockRejectedValue(httpFailure(503, {
      error: "The unavailable period was not saved. Please try again.", retryable: true,
    }));
    const user = renderPage();
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect((await screen.findByRole("alert")).textContent).toContain("was not saved");
    expect(screen.getByLabelText("Start").value).toBe("2027-11-20T09:00");
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("who can record (AC6)", () => {
  it("TC27: someone who is not Venue Staff gets the refusal and no form", async () => {
    serve({ denied: true });
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("Only Venue Staff");
    await waitFor(() => expect(screen.queryByLabelText("Reason")).toBeNull());
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});
