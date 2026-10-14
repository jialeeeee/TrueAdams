import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import AppShell from "./AppShell.jsx";

// The page chrome: grouped navigation, active link, and the Login / Log out state.

function Location() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

function renderShell(path) {
  render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppShell>
        <Location />
        <Routes>
          <Route path="*" element={<p>Page content</p>} />
        </Routes>
      </AppShell>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

const main = () => within(screen.getByRole("navigation", { name: "Main" }));

afterEach(() => sessionStorage.clear());

describe("AppShell navigation", () => {
  it("shows the four groups and the page content", () => {
    renderShell("/events/managed");
    expect(main().getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Events", "Venues", "Resources", "Registrations",
    ]);
    expect(screen.getByText("Page content")).toBeTruthy();
  });

  it("marks the current group and lists that group's pages, with the current page marked", () => {
    renderShell("/events/managed");
    expect(main().getByRole("link", { name: "Events" }).getAttribute("aria-current")).toBe("true");
    expect(main().getByRole("link", { name: "Venues" }).getAttribute("aria-current")).toBeNull();

    const pages = within(screen.getByRole("navigation", { name: "Events pages" }));
    expect(pages.getAllByRole("link").map((link) => link.textContent)).toEqual([
      "All events", "My event requests", "My drafts", "My requests", "My managed events",
      "Requests for review",
    ]);
    expect(pages.getByRole("link", { name: "My managed events" }).getAttribute("aria-current")).toBe("page");
    expect(pages.getByRole("link", { name: "All events" }).getAttribute("aria-current")).toBeNull();
  });

  it("switches to the venue pages under /venues", () => {
    renderShell("/venues/search");
    const pages = within(screen.getByRole("navigation", { name: "Venues pages" }));
    expect(pages.getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Venues", "Venue availability", "Venue search",
    ]);
    expect(pages.getByRole("link", { name: "Venue search" }).getAttribute("aria-current")).toBe("page");
    expect(pages.getByRole("link", { name: "Venues" }).getAttribute("aria-current")).toBeNull();
  });

  it("has no second row for a group with a single page", () => {
    renderShell("/registrations");
    expect(main().getByRole("link", { name: "Registrations" }).getAttribute("aria-current")).toBe("true");
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
  });

  it("highlights no group on the login page", () => {
    renderShell("/login");
    expect(main().getAllByRole("link").some((link) => link.getAttribute("aria-current"))).toBe(false);
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
  });
});

describe("AppShell sign-in state", () => {
  it("offers Login when signed out and no Log out", () => {
    renderShell("/");
    expect(screen.getByRole("link", { name: "Login" }).getAttribute("href")).toBe("/login");
    expect(screen.queryByRole("button", { name: "Log out" })).toBeNull();
  });

  it("offers Log out when a token is stored, and logging out clears it and opens the login page", async () => {
    sessionStorage.setItem("access_token", "issued-token");
    const user = renderShell("/events/managed");
    expect(screen.queryByRole("link", { name: "Login" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Log out" }));

    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(screen.getByTestId("location").textContent).toBe("/login");
    expect(screen.getByRole("link", { name: "Login" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Log out" })).toBeNull();
  });
});
