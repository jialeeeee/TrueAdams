import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import MyDraftsPage from "./MyDraftsPage.jsx";

// Frontend part of TC-29-09 (drafts list) in docs/test-cases/SCRUM-29-draft-event-request.md.

vi.mock("../api/client.js", () => ({ default: { get: vi.fn() } }));

const localTime = (iso) => new Date(`${iso}Z`).toLocaleString();

function renderPage() {
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <MyDraftsPage />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  apiClient.get.mockReset();
});

describe("SCRUM-29 my drafts", () => {
  it("lists drafts with their last-saved time and a link to continue editing", async () => {
    apiClient.get.mockResolvedValue({
      data: {
        drafts: [
          { id: 8, title: "Winter Networking Night", status: "draft", last_saved_at: "2026-09-25T08:30:00" },
          { id: 7, title: "Harbour Lights Festival", status: "draft", last_saved_at: "2026-09-20T02:00:00" },
        ],
        message: null,
      },
    });
    renderPage();

    const link = await screen.findByRole("link", { name: "Harbour Lights Festival" });
    expect(apiClient.get).toHaveBeenCalledWith("/events/drafts");
    expect(link.getAttribute("href")).toBe("/events/drafts/7");
    expect(screen.getByText(`Draft · last saved ${localTime("2026-09-20T02:00:00")}`)).toBeTruthy();
    expect(screen.getByRole("link", { name: "New event request" }).getAttribute("href")).toBe("/events/drafts/new");
  });

  it("shows the empty state", async () => {
    apiClient.get.mockResolvedValue({ data: { drafts: [], message: "You have no draft event requests." } });
    renderPage();
    expect(await screen.findByText("You have no draft event requests.")).toBeTruthy();
  });

  it("shows a retryable error when drafts cannot be loaded", async () => {
    apiClient.get
      .mockRejectedValueOnce(Object.assign(new Error("fail"), {
        response: { status: 503, data: { error: "Your drafts could not be loaded. Please try again.", retryable: true } },
      }))
      .mockResolvedValueOnce({ data: { drafts: [], message: "You have no draft event requests." } });
    const user = renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("could not be loaded");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("You have no draft event requests.")).toBeTruthy();
  });
});
