import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import DraftEventPage from "./DraftEventPage.jsx";

// Frontend cases TC-29-10, 15, 19, 23 and 29 in
// docs/test-cases/SCRUM-29-draft-event-request.md.
// SCRUM-28 TC-28-02/13/14 in SCRUM-28-Test-Coverage-Plan.xlsx;
// backend cases are in tests/test_event_submission.py. HTTP is mocked throughout.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));

const EMPTY = {
  purpose: null, description: null, start_time: null, end_time: null,
  expected_attendance: null, venue_requirements: null, accessibility_needs: null,
  equipment_requirements: null, registration_required: null,
};

function draft(overrides = {}) {
  return {
    id: 7, status: "draft", title: "Harbour Lights Festival", ...EMPTY,
    purpose: "Celebrate the harbour's reopening", start_time: "2026-12-12T17:00:00",
    expected_attendance: 250, created_at: "2026-09-20T02:00:00",
    last_saved_at: "2026-09-20T02:00:00", submitted_at: null,
    missing_for_submission: ["description", "end_time", "venue_requirements", "registration_required"],
    ...overrides,
  };
}

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true, response: { status, data },
  });
}

function Location() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

async function renderAt(path) {
  render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Location />
      <Routes>
        <Route path="/events/drafts/new" element={<DraftEventPage />} />
        <Route path="/events/drafts/:draftId" element={<DraftEventPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: /event request/i });
  return userEvent.setup();
}

const field = (label) => screen.getByLabelText(label);
const saveButton = () => screen.getByRole("button", { name: "Save draft" });
const submitButton = () => screen.getByRole("button", { name: "Submit for review" });

const COMPLETE_REQUEST = draft({
  description: "Lanterns", end_time: "2026-12-12T22:00:00", venue_requirements: "Waterfront",
  accessibility_needs: "Step-free access", equipment_requirements: "Projector",
  registration_required: true, missing_for_submission: [],
});
const FORM_LABELS = {
  title: "Event name", purpose: "Purpose", description: "Description", start_time: "Start",
  end_time: "End", expected_attendance: "Expected attendance", venue_requirements: "Venue requirements",
  accessibility_needs: "Accessibility needs", equipment_requirements: "Equipment requirements",
  registration_required: "Attendee registration needed",
};

function expectRequestValues(request) {
  for (const [name, label] of Object.entries(FORM_LABELS)) {
    const value = request[name];
    const displayed = name === "registration_required" ? (value ? "yes" : "no")
      : name.endsWith("_time") ? value.slice(0, 16) : String(value);
    expect(field(label).value).toBe(displayed);
  }
}

// The test router's <output> also has an implicit status role.
const confirmation = () => screen.getAllByRole("status").find((node) => /submitted/i.test(node.textContent));

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
  apiClient.put.mockReset();
});

describe("SCRUM-29 draft event request", () => {
  // TC-29-10 · AC2
  it("shows a new request as not saved yet, and needs an event name to save", async () => {
    const user = await renderAt("/events/drafts/new");
    expect(screen.getByText(/not saved yet/i)).toBeTruthy();
    expect(saveButton().disabled).toBe(true);
    await user.type(field("Event name"), "   ");
    expect(saveButton().disabled).toBe(true);
  });

  // TC-29-01, TC-29-10, TC-29-19 · AC1, AC2, AC4
  it("saves a new draft with only a name, shows Draft and the last-saved time, then updates the same draft", async () => {
    apiClient.post.mockResolvedValue({ status: 201, data: draft({ ...EMPTY, id: 9, title: "Spring Garden Party", last_saved_at: "2026-09-28T03:00:00" }) });
    apiClient.put.mockResolvedValue({ data: draft({ ...EMPTY, id: 9, title: "Spring Garden Party", purpose: "Staff social", last_saved_at: "2026-09-28T03:05:00" }) });
    const user = await renderAt("/events/drafts/new");

    await user.type(field("Event name"), "Spring Garden Party");
    await user.click(saveButton());

    expect(apiClient.post).toHaveBeenCalledWith("/events/drafts", expect.objectContaining({
      title: "Spring Garden Party", purpose: null, expected_attendance: null, registration_required: null,
    }));
    expect(await screen.findByText(`Last saved: ${localTime("2026-09-28T03:00:00")}`)).toBeTruthy();
    expect(screen.getByText("Status: Draft")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/events/drafts/9"));

    await user.type(field("Purpose"), "Staff social");
    await user.click(saveButton());

    expect(apiClient.put).toHaveBeenCalledWith("/events/drafts/9", expect.objectContaining({ purpose: "Staff social" }));
    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(apiClient.get).not.toHaveBeenCalled();
    expect(await screen.findByText(`Last saved: ${localTime("2026-09-28T03:05:00")}`)).toBeTruthy();
  });

  // TC-29-15 · AC3
  it("reopens a draft with its saved information, ready to edit", async () => {
    apiClient.get.mockResolvedValue({ data: draft() });
    await renderAt("/events/drafts/7");

    expect(apiClient.get).toHaveBeenCalledWith("/events/drafts/7");
    expect(field("Event name").value).toBe("Harbour Lights Festival");
    expect(field("Purpose").value).toBe("Celebrate the harbour's reopening");
    expect(field("Start").value).toBe("2026-12-12T17:00");
    expect(field("Expected attendance").value).toBe("250");
    expect(field("Description").value).toBe("");
    expect(field("Event name").disabled).toBe(false);
    expect(screen.getByText(`Last saved: ${localTime("2026-09-20T02:00:00")}`)).toBeTruthy();
  });

  // TC-29-23 · AC5
  it.each([
    ["server error", httpFailure(503, { error: "Your draft was not saved. Please try again.", retryable: true }), "Your draft was not saved. Please try again."],
    ["invalid value", httpFailure(400, { error: "Expected attendance must be a whole number of at least 1.", field: "expected_attendance" }), "Expected attendance must be a whole number of at least 1."],
    ["no network", new Error("Network Error"), "Your draft was not saved. Check your connection and try again."],
  ])("keeps the edits and the last-saved time when saving fails (%s), and saves on retry", async (_label, failure, message) => {
    apiClient.get.mockResolvedValue({ data: draft() });
    apiClient.put
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce({ data: draft({ description: "Lanterns and live music", last_saved_at: "2026-09-28T04:00:00" }) });
    const user = await renderAt("/events/drafts/7");

    await user.type(field("Description"), "Lanterns and live music");
    await user.click(saveButton());

    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(field("Description").value).toBe("Lanterns and live music");
    expect(screen.getByText(`Last saved: ${localTime("2026-09-20T02:00:00")}`)).toBeTruthy();
    expect(saveButton().disabled).toBe(false);

    await user.click(saveButton());
    expect(await screen.findByText(`Last saved: ${localTime("2026-09-28T04:00:00")}`)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // TC-29-29 · AC6
  it("saves the current edits, then submits, and shows the request as Submitted", async () => {
    const complete = draft({
      description: "Lanterns", end_time: "2026-12-12T22:00:00", venue_requirements: "Waterfront",
      registration_required: true, missing_for_submission: [],
    });
    // SCRUM-28 TC-28-02: additive all-field/receipt and in-flight preservation checks.
    Object.assign(complete, {
      accessibility_needs: "Step-free access", equipment_requirements: "Projector",
    });
    apiClient.get.mockResolvedValue({ data: draft() });
    let finishSave;
    apiClient.put.mockReturnValue(new Promise((resolve) => { finishSave = resolve; }));
    apiClient.post.mockResolvedValue({ data: { ...complete, status: "submitted", submitted_at: "2026-09-28T05:00:00" } });
    const user = await renderAt("/events/drafts/7");

    await user.type(field("Description"), "Lanterns");
    await user.type(field("End"), "2026-12-12T22:00");
    await user.type(field("Venue requirements"), "Waterfront");
    await user.type(field("Accessibility needs"), "Step-free access");
    await user.type(field("Equipment requirements"), "Projector");
    await user.selectOptions(field("Attendee registration needed"), "yes");
    await user.click(submitButton());

    // Soft assertion lets all original success assertions still run during RED.
    expect.soft(Object.values(FORM_LABELS).every((label) => field(label).disabled)).toBe(true);
    finishSave({ data: complete });

    await screen.findByText("Status: Submitted");
    expect(apiClient.put).toHaveBeenCalledWith("/events/drafts/7", expect.objectContaining({ description: "Lanterns" }));
    expect(apiClient.post).toHaveBeenCalledWith("/events/drafts/7/submit");
    expect(apiClient.put.mock.invocationCallOrder[0]).toBeLessThan(apiClient.post.mock.invocationCallOrder[0]);
    expect(field("Event name").disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Save draft" })).toBeNull();
    expect(apiClient.put).toHaveBeenCalledWith("/events/drafts/7", {
      title: complete.title, purpose: complete.purpose, description: complete.description,
      start_time: "2026-12-12T17:00", end_time: "2026-12-12T22:00",
      expected_attendance: 250, venue_requirements: "Waterfront",
      accessibility_needs: "Step-free access", equipment_requirements: "Projector",
      registration_required: true,
    });
    expectRequestValues(complete);
    expect(confirmation().textContent).toMatch(/submitted.*review/i);
    expect(screen.getByText(/(?:request|reference).*#?7\b/i)).toBeTruthy();
  });

  // TC-29-29, TC-29-26 · AC6
  it("lists the missing fields when submission is refused, and stays a Draft with the edits kept", async () => {
    apiClient.get.mockResolvedValue({ data: draft() });
    apiClient.put.mockResolvedValue({ data: draft({ purpose: "Harbour party" }) });
    apiClient.post.mockRejectedValue(httpFailure(400, {
      error: "Complete these fields before submitting.",
      missing: ["description", "end_time", "venue_requirements", "registration_required"],
    }));
    const user = await renderAt("/events/drafts/7");

    await user.clear(field("Purpose"));
    await user.type(field("Purpose"), "Harbour party");
    await user.click(submitButton());

    const alert = await screen.findByRole("alert");
    for (const label of ["Description", "End", "Venue requirements", "Attendee registration needed"]) {
      expect(alert.textContent).toContain(label);
    }
    expect(screen.getByText("Status: Draft")).toBeTruthy();
    expect(field("Purpose").value).toBe("Harbour party");
    expect(field("Event name").disabled).toBe(false);
  });

  it("does not submit when saving the edits first fails", async () => {
    apiClient.get.mockResolvedValue({ data: draft() });
    apiClient.put.mockRejectedValue(httpFailure(503, { error: "Your draft was not saved. Please try again.", retryable: true }));
    const user = await renderAt("/events/drafts/7");

    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain("not saved");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("explains when a request has already been submitted and cannot be edited as a draft", async () => {
    apiClient.get.mockRejectedValue(httpFailure(409, { error: "This request has already been submitted and can no longer be edited as a draft." }));
    render(
      <MemoryRouter initialEntries={["/events/drafts/7"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes><Route path="/events/drafts/:draftId" element={<DraftEventPage />} /></Routes>
      </MemoryRouter>,
    );
    expect((await screen.findByRole("alert")).textContent).toContain("already been submitted");
  });
});

describe("SCRUM-28 submission failure and known-ID recovery", () => {
  // TC-28-13: AC3/6. Two meaningful submit-stage failures, one test definition.
  it.each([
    ["invalid end", httpFailure(400, { error: "The end must be after the start.", field: "end_time" }), "The end must be after the start."],
    ["commit refusal", httpFailure(503, { error: "The submission could not be saved. Please try again.", retryable: true }), "The submission could not be saved. Please try again."],
  ])("retains request details after submit rejection and retries the same request (%s)", async (_label, failure, message) => {
    const entered = { ...COMPLETE_REQUEST, description: "Lanterns and live music" };
    apiClient.get.mockResolvedValue({ data: COMPLETE_REQUEST });
    apiClient.put.mockResolvedValue({ data: entered });
    apiClient.post.mockRejectedValueOnce(failure).mockResolvedValueOnce({
      data: { ...entered, status: "submitted", submitted_at: "2026-10-14T02:00:00" },
    });
    const user = await renderAt("/events/drafts/7");
    await user.clear(field("Description"));
    await user.type(field("Description"), entered.description);
    // First variant saves a temporarily invalid end (allowed for a draft).
    if (_label === "invalid end") {
      entered.end_time = entered.start_time;
      await user.clear(field("End"));
      await user.type(field("End"), entered.start_time.slice(0, 16));
    }
    await user.click(submitButton());
    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expectRequestValues(entered);
    expect(screen.getByText("Status: Draft")).toBeTruthy();
    expect(submitButton().disabled).toBe(false);
    if (_label === "invalid end") {
      entered.end_time = COMPLETE_REQUEST.end_time;
      await user.clear(field("End"));
      await user.type(field("End"), entered.end_time.slice(0, 16));
      apiClient.post.mockResolvedValueOnce({ data: { ...entered, status: "submitted" } });
    }
    await user.click(submitButton());
    await screen.findByText("Status: Submitted");
    expect(apiClient.post).toHaveBeenNthCalledWith(1, "/events/drafts/7/submit");
    expect(apiClient.post).toHaveBeenNthCalledWith(2, "/events/drafts/7/submit");
    expect(apiClient.post.mock.calls.every(([url]) => url === "/events/drafts/7/submit")).toBe(true);
    expectRequestValues(entered);
  });

  // TC-28-14: AC4/5/6. Existing owner endpoints; no new reconciliation API.
  it.each(["submitted", "draft", "unavailable"])(
    "reconciles uncertain submission outcomes without creating another request (%s)",
    async (outcome) => {
      const saved = { ...COMPLETE_REQUEST, description: "Lanterns and live music" };
      const retained = { ...saved };
      let lost = false;
      let statusChecks = 0;
      apiClient.get.mockImplementation((url) => {
        if (!lost && url === "/events/drafts/7") return Promise.resolve({ data: COMPLETE_REQUEST });
        // Submitted variant: a second outage permits newer unsaved edits before
        // a later successful receipt check. Reconciliation must retain them.
        if (outcome === "submitted" && statusChecks++ === 0) return Promise.reject(new Error("Network Error"));
        if (outcome === "unavailable") return Promise.reject(new Error("Network Error"));
        const receipt = { id: 7, title: saved.title, status: "submitted", submitted_at: "2026-10-14T02:00:00", decided_at: null, decision_note: null, decided_by: null };
        if (url === "/events/mine") return Promise.resolve({
          data: { drafts: outcome === "draft" ? [{ id: 7, title: saved.title, status: "draft", last_saved_at: saved.last_saved_at }] : [],
            submitted: outcome === "submitted" ? [receipt] : [], message: null },
        });
        if (url === "/events/requests") return Promise.resolve({
          data: { requests: outcome === "submitted" ? [receipt] : [], message: null },
        });
        if (url === "/events/drafts/7" && outcome === "draft") return Promise.resolve({ data: saved });
        if (url === "/events/drafts/7") return Promise.reject(httpFailure(409, {
          error: "This request has already been submitted and can no longer be edited as a draft.",
        }));
        throw new Error(`Unexpected API endpoint: ${url}`);
      });
      apiClient.put.mockImplementation(() => outcome === "submitted" && lost
        ? Promise.reject(httpFailure(409, { error: "This request has already been submitted and can no longer be edited as a draft." }))
        : Promise.resolve({ data: saved }));
      apiClient.post.mockImplementationOnce(() => {
        lost = true;
        return Promise.reject(new Error("Network Error"));
      }).mockResolvedValue({ data: { ...saved, status: "submitted", submitted_at: "2026-10-14T02:00:00" } });
      const user = await renderAt("/events/drafts/7");
      await user.clear(field("Description"));
      await user.type(field("Description"), saved.description);
      await user.click(submitButton());
      await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1));
      await waitFor(() => expect(screen.queryByText("Status: Submitted") || screen.queryByRole("alert")).toBeTruthy());

      // Accept an immediate status check or a simple user-triggered retry/check.
      if (screen.queryByText("Status: Submitted")) {
        expect(outcome).toBe("submitted");
      } else {
        await screen.findByRole("alert");
        expectRequestValues(saved);
        if (outcome === "submitted") {
          retained.description += " plus unsaved edits";
          await user.type(field("Description"), " plus unsaved edits");
        }
        const retry = screen.queryByRole("button", { name: /retry|check.*status/i }) ?? submitButton();
        await user.click(retry);
      }
      if (outcome === "submitted") {
        await screen.findByText("Status: Submitted");
        expect(confirmation().textContent).toMatch(/submitted/i);
        expect(screen.getByText(/(?:request|reference).*#?7\b/i)).toBeTruthy();
        expect(apiClient.post).toHaveBeenCalledTimes(1);
        expect(field("Event name").disabled).toBe(true);
        expectRequestValues(retained);
      } else if (outcome === "draft") {
        // Reconciliation may just restore Draft; a second explicit click may retry it.
        if (!screen.queryByText("Status: Submitted")) await user.click(submitButton());
        await screen.findByText("Status: Submitted");
        expect(apiClient.post).toHaveBeenCalledTimes(2);
        expectRequestValues(saved);
      } else {
        expect(apiClient.post).toHaveBeenCalledTimes(1);
        const alert = await screen.findByRole("alert");
        expect(alert.textContent).toMatch(/uncertain|could not confirm|cannot confirm|could not determine|unable to confirm|may have been submitted/i);
        expectRequestValues(saved);
        expect(apiClient.post).toHaveBeenCalledTimes(1);
      }
      const reconciliationCalls = apiClient.get.mock.calls.slice(1);
      expect(reconciliationCalls.length).toBeGreaterThan(0);
      expect(reconciliationCalls.every(([url]) => ["/events/mine", "/events/requests", "/events/drafts/7"].includes(url))).toBe(true);
      expect(apiClient.post.mock.calls.every(([url]) => url === "/events/drafts/7/submit")).toBe(true);
    },
  );
});
