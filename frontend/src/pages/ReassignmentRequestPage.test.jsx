import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import ReassignmentRequestPage from "./ReassignmentRequestPage.jsx";

// Frontend cases for TC-61-01 to TC-61-17 in docs/test-cases/SCRUM-61-reassignment-request.md.
// The API itself is covered by backend/tests/test_reassignment_request.py; these check
// what the coordinator sees. Responses mirror that API's contract:
//   GET  /events/<id>/reassignment -> { event, coordinators, pending_request, can_request,
//                                       blocked_reason, message }
//   POST /events/<id>/reassignment -> { message, request, notification }

vi.mock("../api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

// Must match MAX_REASON_LENGTH in backend/app/events/routes.py.
const MAX_REASON_LENGTH = 500;

const OPEN_FORM = {
  data: {
    event: { id: 7, title: "Chem Open House", status: "confirmed" },
    coordinators: [
      { id: 2, email: "ben.coordinator@connectsphere.test" },
      { id: 3, email: "chloe.coordinator@connectsphere.test" },
    ],
    pending_request: null,
    can_request: true,
    blocked_reason: null,
    message: null,
  },
};

function blocked(blockedReason, message, extra = {}) {
  return {
    data: {
      ...OPEN_FORM.data,
      can_request: false,
      blocked_reason: blockedReason,
      message,
      ...extra,
    },
  };
}

function submitted(message = "Your request was sent to ben.coordinator@connectsphere.test.") {
  return {
    data: {
      message,
      request: {
        id: 12,
        event_id: 7,
        requester_id: 1,
        coordinator_id: 2,
        reason: "Overseas on 20/11/2026",
        status: "pending",
        requested_at: "2026-10-13T04:00:00",
      },
      notification: { in_app: true, email_queued: true },
    },
  };
}

function httpFailure(status, data) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true,
    response: { status, data },
  });
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/events/7/reassign"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/events/:eventId/reassign" element={<ReassignmentRequestPage />} />
        <Route path="/login" element={<p>Sign-in page</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const submitButton = () => screen.getByRole("button", { name: /^submit/i });
const coordinatorBox = () => screen.getByLabelText("New coordinator");
const reasonBox = () => screen.getByLabelText("Reason");

async function fillIn(user, { coordinator = "ben.coordinator@connectsphere.test", reason = "Overseas on 20/11/2026" } = {}) {
  if (coordinator) await user.selectOptions(coordinatorBox(), coordinator);
  if (reason) {
    await user.click(reasonBox());
    await user.paste(reason);
  }
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
});

describe("SCRUM-61 the request form", () => {
  it("opens the form for the event's main coordinator", async () => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    renderPage();

    expect(await screen.findByRole("heading", { name: "Request reassignment" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/7/reassignment");
    expect(screen.getByText("Chem Open House")).toBeTruthy();
    expect(submitButton().disabled).toBe(false);
  });

  it("lists the eligible coordinators and not the requester", async () => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    renderPage();

    await screen.findByRole("heading", { name: "Request reassignment" });

    const options = Array.from(coordinatorBox().querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toContain("ben.coordinator@connectsphere.test");
    expect(options).toContain("chloe.coordinator@connectsphere.test");
    expect(options).not.toContain("alice.coordinator@connectsphere.test");
    // Nothing is chosen until the coordinator chooses.
    expect(coordinatorBox().value).toBe("");
  });

  it("sends the selected coordinator and the reason, then confirms and shows the request as pending", async () => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    apiClient.post.mockResolvedValue(submitted());
    const user = renderPage();
    await screen.findByRole("heading", { name: "Request reassignment" });
    await fillIn(user);

    await user.click(submitButton());

    expect(apiClient.post).toHaveBeenCalledWith("/events/7/reassignment", {
      coordinator_id: 2,
      reason: "Overseas on 20/11/2026",
    });
    expect((await screen.findByRole("status")).textContent).toContain("Your request was sent to ben.coordinator@connectsphere.test.");
    expect(screen.getByText("Status: Pending")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^submit/i })).toBeNull();
  });

  it("accepts a reason of exactly the maximum length", async () => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    apiClient.post.mockResolvedValue(submitted());
    const user = renderPage();
    await screen.findByRole("heading", { name: "Request reassignment" });
    // The box has no maxLength attribute, so an over-length reason is caught and explained below.
    expect(reasonBox().getAttribute("maxlength")).toBeNull();
    await fillIn(user, { reason: "A".repeat(MAX_REASON_LENGTH) });

    await user.click(submitButton());

    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(apiClient.post.mock.calls[0][1].reason).toHaveLength(MAX_REASON_LENGTH);
    expect(await screen.findByRole("status")).toBeTruthy();
  });

  it("blocks a reason over the maximum length and says so", async () => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    const user = renderPage();
    await screen.findByRole("heading", { name: "Request reassignment" });
    await fillIn(user, { reason: "A".repeat(MAX_REASON_LENGTH + 1) });

    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain(`${MAX_REASON_LENGTH} characters or fewer`);
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(reasonBox().value).toHaveLength(MAX_REASON_LENGTH + 1);
  });

  it.each([
    ["nothing", ""],
    ["only spaces", "   "],
  ])("blocks an empty reason (%s) and says a reason is required", async (_label, reason) => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    const user = renderPage();
    await screen.findByRole("heading", { name: "Request reassignment" });
    await user.selectOptions(coordinatorBox(), "ben.coordinator@connectsphere.test");
    if (reason) {
      await user.click(reasonBox());
      await user.paste(reason);
    }

    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain("Enter a reason for the reassignment.");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("blocks a request with no coordinator selected", async () => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    const user = renderPage();
    await screen.findByRole("heading", { name: "Request reassignment" });
    await fillIn(user, { coordinator: "" });

    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain("Choose a coordinator.");
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("sends one request when Submit is clicked twice", async () => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    apiClient.post.mockReturnValue(new Promise(() => {}));
    const user = renderPage();
    await screen.findByRole("heading", { name: "Request reassignment" });
    await fillIn(user);

    await user.click(submitButton());
    await user.click(submitButton());

    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(submitButton().disabled).toBe(true);
  });
});

describe("SCRUM-61 when no request can be made", () => {
  it("says no eligible coordinator is available and offers no way to submit", async () => {
    apiClient.get.mockResolvedValue(blocked(
      "no_eligible_coordinators",
      "No eligible coordinator is available for this event.",
      { coordinators: [] },
    ));
    renderPage();

    expect(await screen.findByText("No eligible coordinator is available for this event.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^submit/i })).toBeNull();
    expect(screen.queryByLabelText("New coordinator")).toBeNull();
  });

  it("shows an existing request as pending and offers no second request", async () => {
    apiClient.get.mockResolvedValue(blocked(
      "pending",
      "A reassignment request is already pending for this event.",
      { pending_request: { id: 12, event_id: 7, requester_id: 1, coordinator_id: 2, reason: "Overseas", status: "pending", requested_at: "2026-10-13T04:00:00" } },
    ));
    renderPage();

    expect(await screen.findByText("A reassignment request is already pending for this event.")).toBeTruthy();
    expect(screen.getByText("Status: Pending")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^submit/i })).toBeNull();
  });

  it.each([
    ["cancelled", "A reassignment cannot be requested for a cancelled event."],
    ["past", "A reassignment cannot be requested for an event that has ended."],
  ])("explains why a %s event cannot be reassigned", async (reason, message) => {
    apiClient.get.mockResolvedValue(blocked(reason, message));
    renderPage();

    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^submit/i })).toBeNull();
  });

  it("shows the server's refusal when someone else is not allowed to open the form", async () => {
    apiClient.get.mockRejectedValue(httpFailure(403, { error: "Only the event's main coordinator can request a reassignment." }));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("Only the event's main coordinator can request a reassignment.");
    expect(screen.queryByLabelText("New coordinator")).toBeNull();
    expect(screen.queryByRole("button", { name: /^submit/i })).toBeNull();
  });

  it("sends a signed-out user to the sign-in page and shows no event or form", async () => {
    apiClient.get.mockRejectedValue(httpFailure(401, { msg: "Missing Authorization Header" }));
    renderPage();

    expect(await screen.findByText("Sign-in page")).toBeTruthy();
    expect(screen.queryByText("Chem Open House")).toBeNull();
    expect(screen.queryByLabelText("Reason")).toBeNull();
  });

  it("shows why the form could not be loaded and lets the coordinator try again", async () => {
    apiClient.get
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce(OPEN_FORM);
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The reassignment form could not be loaded. Check your connection and try again.",
    );
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { name: "Request reassignment" })).toBeTruthy();
  });
});

describe("SCRUM-61 when the server refuses or fails", () => {
  it.each([
    [409, { error: "A reassignment request is already pending for this event.", reason: "pending" }],
    [422, { error: "The selected user is not an eligible coordinator." }],
    [400, { error: "The reason must be 500 characters or fewer.", field: "reason" }],
  ])("shows the server's message for a %i and keeps what was typed", async (status, data) => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    apiClient.post.mockRejectedValue(httpFailure(status, data));
    const user = renderPage();
    await screen.findByRole("heading", { name: "Request reassignment" });
    await fillIn(user);

    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain(data.error);
    expect(screen.queryByRole("status")).toBeNull();
    expect(reasonBox().value).toBe("Overseas on 20/11/2026");
    expect(coordinatorBox().value).toBe("2");
  });

  it("shows an error when saving fails and lets the coordinator try again without retyping", async () => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    apiClient.post
      .mockRejectedValueOnce(httpFailure(503, { error: "Your request was not saved. Please try again.", retryable: true }))
      .mockResolvedValueOnce(submitted());
    const user = renderPage();
    await screen.findByRole("heading", { name: "Request reassignment" });
    await fillIn(user);

    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain("Your request was not saved. Please try again.");
    expect(screen.queryByText("Status: Pending")).toBeNull();
    expect(reasonBox().value).toBe("Overseas on 20/11/2026");
    expect(submitButton().disabled).toBe(false);

    await user.click(submitButton());
    expect(await screen.findByText("Status: Pending")).toBeTruthy();
    expect(apiClient.post).toHaveBeenCalledTimes(2);
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockResolvedValue(OPEN_FORM);
    apiClient.post.mockRejectedValue(new Error("Network Error"));
    const user = renderPage();
    await screen.findByRole("heading", { name: "Request reassignment" });
    await fillIn(user);

    await user.click(submitButton());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Your request was not saved. Check your connection and try again.",
    );
  });
});
