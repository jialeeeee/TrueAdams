import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import MyEventRequestsPage from "./MyEventRequestsPage.jsx";

// Frontend cases TC-59-11 to TC-59-15 in
// docs/test-cases/SCRUM-59-drafts-separate-from-submitted.md. The API itself is
// covered by backend/tests/test_my_event_requests.py; responses mirror its contract.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

const DRAFTS = [
  { id: 2, title: "Winter Networking Night", status: "draft", last_saved_at: "2026-09-27T08:30:00" },
  { id: 3, title: null, status: "draft", last_saved_at: "2026-09-26T09:00:00" },
  { id: 1, title: "Harbour Lights Festival", status: "draft", last_saved_at: "2026-09-25T10:00:00" },
];
const SUBMITTED = [
  { id: 13, title: "Alumni Mixer", status: "approved", submitted_at: "2026-09-22T09:00:00", decided_at: "2026-09-23T09:00:00", decision_note: "Venue confirmed" },
  { id: 12, title: "Spring Garden Party", status: "under_review", submitted_at: "2026-09-21T09:00:00", decided_at: null, decision_note: null },
  { id: 11, title: "Product Launch", status: "submitted", submitted_at: "2026-09-20T09:00:00", decided_at: null, decision_note: null },
  { id: 14, title: "Rooftop Cinema", status: "rejected", submitted_at: "2026-09-06T09:00:00", decided_at: "2026-09-12T09:00:00", decision_note: "No licensed venue is available" },
];
const loaded = (drafts = DRAFTS, submitted = SUBMITTED, message = null) => ({ data: { drafts, submitted, message } });
const EMPTY = loaded([], [], "You have no event requests yet.");

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <MyEventRequestsPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const section = (name) => screen.getByRole("region", { name });

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-59 my event requests", () => {
  it("shows drafts and submitted requests in two labelled sections", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    expect(await screen.findByRole("heading", { name: "My event requests" })).toBeTruthy();
    expect(apiClient.get).toHaveBeenCalledWith("/events/mine");

    const drafts = within(section("Drafts"));
    expect(drafts.getByText("Harbour Lights Festival")).toBeTruthy();
    expect(drafts.getByText(`Draft · last saved ${localTime("2026-09-25T10:00:00")}`)).toBeTruthy();
    expect(drafts.queryByText("Product Launch")).toBeNull();

    const submitted = within(section("Submitted requests"));
    expect(submitted.getByText("Product Launch")).toBeTruthy();
    expect(submitted.getByText("Status: Submitted")).toBeTruthy();
    expect(submitted.getByText("Status: Under review")).toBeTruthy();
    expect(submitted.getByText(`Status: Approved · decided ${localTime("2026-09-23T09:00:00")}`)).toBeTruthy();
    expect(submitted.getByText("Note: Venue confirmed")).toBeTruthy();
    expect(submitted.getByText("Reason: No licensed venue is available")).toBeTruthy();
    expect(submitted.queryByText("Harbour Lights Festival")).toBeNull();
    expect(submitted.queryByText(/^Draft/)).toBeNull();
  });

  it("lists drafts in the order received", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    const items = within(await screen.findByRole("region", { name: "Drafts" })).getAllByRole("listitem");
    expect(items.map((item) => item.querySelector("a").textContent)).toEqual([
      "Winter Networking Night", "Untitled draft", "Harbour Lights Festival",
    ]);
  });

  it("opens drafts in the editor but never links submitted requests to it", async () => {
    apiClient.get.mockResolvedValue(loaded());
    renderPage();

    const link = await screen.findByRole("link", { name: "Harbour Lights Festival" });
    expect(link.getAttribute("href")).toBe("/events/drafts/1");

    const submitted = section("Submitted requests");
    expect(within(submitted).queryAllByRole("link")).toEqual([]);
    const editorLinks = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    for (const request of SUBMITTED) {
      expect(editorLinks).not.toContain(`/events/drafts/${request.id}`);
    }
  });

  it.each([
    ["missing", null],
    ["empty", ""],
    ["only spaces", "   "],
  ])("shows a draft whose name is %s as Untitled draft, still linked", async (_label, title) => {
    apiClient.get.mockResolvedValue(loaded([{ id: 3, title, status: "draft", last_saved_at: "2026-09-26T09:00:00" }], []));
    renderPage();

    const link = await screen.findByRole("link", { name: "Untitled draft" });
    expect(link.getAttribute("href")).toBe("/events/drafts/3");
  });

  it("shows the empty state when there are no requests", async () => {
    apiClient.get.mockResolvedValue(EMPTY);
    renderPage();

    expect(await screen.findByText("You have no event requests yet.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Drafts" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Submitted requests" })).toBeNull();
    expect(screen.getByRole("link", { name: "New event request" }).getAttribute("href")).toBe("/events/drafts/new");
  });

  it("says when one section is empty", async () => {
    apiClient.get.mockResolvedValueOnce(loaded(DRAFTS, []));
    renderPage();
    expect(await within(await screen.findByRole("region", { name: "Submitted requests" })).findByText("No submitted requests.")).toBeTruthy();
  });

  it("says when there are no drafts", async () => {
    apiClient.get.mockResolvedValueOnce(loaded([], SUBMITTED));
    renderPage();
    expect(await within(await screen.findByRole("region", { name: "Drafts" })).findByText("No drafts.")).toBeTruthy();
  });

  it("shows a retryable error when the list cannot be loaded", async () => {
    apiClient.get
      .mockRejectedValueOnce(Object.assign(new Error("fail"), {
        response: { status: 503, data: { error: "Your event requests could not be loaded. Please try again.", retryable: true } },
      }))
      .mockResolvedValueOnce(loaded());
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("Your event requests could not be loaded. Please try again.");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("region", { name: "Drafts" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a fallback message when the server cannot be reached", async () => {
    apiClient.get.mockRejectedValue(new Error("Network Error"));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Your event requests could not be loaded. Check your connection and try again.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
