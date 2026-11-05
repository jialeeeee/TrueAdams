// The app shell: header, grouped menu and the small-screen Menu button. App.test.jsx covers
// which links each role sees and signing in and out; these cover how the shell shows them.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.jsx";
import apiClient from "./api/client.js";

vi.mock("./api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

function renderSignedIn(path, roles) {
  sessionStorage.setItem("access_token", "shell-token");
  if (roles) {
    sessionStorage.setItem("user_role", roles[0]);
    sessionStorage.setItem("user_roles", JSON.stringify(roles));
  }
  render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const menu = () => screen.getByRole("navigation", { name: "Main" });
const menuButton = () => screen.getByRole("button", { name: "Menu" });

beforeEach(() => {
  sessionStorage.clear();
  apiClient.get.mockResolvedValue({ data: { events: [], notifications: [], message: "Nothing yet." } });
  // Signing out tells the server (SCRUM-75 AC6).
  apiClient.post.mockResolvedValue({ data: {} });
});

describe("the app shell", () => {
  it("groups the menu by area, in menu order, and marks the page being shown", async () => {
    renderSignedIn("/notifications", ["organiser", "attendee"]);
    await screen.findByText("Nothing yet.");

    const groups = within(menu()).getAllByRole("group").map((group) => [
      document.getElementById(group.getAttribute("aria-labelledby")).textContent,
      within(group).getAllByRole("link").map((link) => link.textContent),
    ]);
    expect(groups).toEqual([
      ["Overview", ["Events", "Notifications"]],
      ["My events", ["My event requests", "My drafts", "My requests", "Registrations for my events"]],
      ["Attending", ["My registrations"]],
    ]);
    expect(within(menu()).getByRole("link", { name: "Notifications" }).getAttribute("aria-current")).toBe("page");
    expect(within(menu()).getByRole("link", { name: "Events" }).getAttribute("aria-current")).toBeNull();
  });

  it("names each role the user holds in the header, and a role it doesn't know as stored", async () => {
    renderSignedIn("/notifications", ["coordinator_lead", "venue_staff", "guest"]);
    await screen.findByText("Nothing yet.");

    expect([...screen.getByRole("group", { name: "Your roles" }).children]
      .map((badge) => badge.textContent)).toEqual(["Coordinator Lead", "Venue Staff", "guest"]);
  });

  it("shows no roles for a session that names none, and offers Login when signed out", async () => {
    renderSignedIn("/notifications");
    await screen.findByText("Nothing yet.");
    expect(screen.queryByRole("group", { name: "Your roles" })).toBeNull();

    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));
    expect(screen.getByRole("banner").querySelector('a[href="/login"]').textContent).toBe("Login");
  });

  it("opens and closes the menu with the Menu button, and closes it on opening a page", async () => {
    const user = renderSignedIn("/notifications", ["attendee"]);
    await screen.findByText("Nothing yet.");
    expect(menuButton().getAttribute("aria-controls")).toBe(menu().id);
    expect(menuButton().getAttribute("aria-expanded")).toBe("false");
    expect(menu().className).toBe("side-nav");

    await user.click(menuButton());
    expect(menuButton().getAttribute("aria-expanded")).toBe("true");
    expect(menu().className).toBe("side-nav open");
    await user.click(menuButton());
    expect(menuButton().getAttribute("aria-expanded")).toBe("false");

    await user.click(menuButton());
    await user.click(within(menu()).getByRole("link", { name: "Events" }));
    expect(menuButton().getAttribute("aria-expanded")).toBe("false");
    expect(menu().className).toBe("side-nav");
  });

  it("lets keyboard users skip to the page's content", async () => {
    renderSignedIn("/notifications", ["attendee"]);
    await screen.findByText("Nothing yet.");

    const skip = screen.getByRole("link", { name: "Skip to main content" });
    expect(skip.getAttribute("href")).toBe("#main");
    expect(screen.getByRole("main").id).toBe("main");
  });
});
