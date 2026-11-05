// SCRUM-75-test-cases.md TC-75-06..08; backend/tests/test_auth_unit.py verifies
// that protected API requests without the browser token are refused.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.jsx";
import apiClient from "./api/client.js";

vi.mock("./api/client.js", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

function BackButton() {
  const navigate = useNavigate();
  return <button onClick={() => navigate(-1)}>Browser back</button>;
}

function renderApp(path) {
  render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
      <BackButton />
    </MemoryRouter>,
  );
  return userEvent.setup();
}

function deferredLogin() {
  let resolve;
  const promise = new Promise((complete) => { resolve = complete; });
  return {
    promise,
    succeed: (token, role = "coordinator") => act(async () => {
      resolve({ data: { access_token: token, role } });
      await promise;
    }),
  };
}

async function enterCredentials(user) {
  await user.type(screen.getByPlaceholderText("Email"), "signin@test.invalid");
  await user.type(screen.getByPlaceholderText("Password"), "password");
}

beforeEach(() => {
  apiClient.get.mockResolvedValue({ data: { events: [], message: "No managed events." } });
  apiClient.post.mockResolvedValue({ data: { access_token: "new-token", role: "coordinator" } });
});

it.each(["/", "/events/75/planning", "/venues/bookings", "/notifications", "/registrations"])(
  "refuses signed-out direct navigation to %s before loading protected data", async (path) => {
    renderApp(path);
    expect(await screen.findByRole("heading", { name: "Login" })).toBeTruthy();
    expect(apiClient.get).not.toHaveBeenCalled();
  },
);

it("signs out, refuses navigation and browser back, then allows sign-in again", async () => {
  sessionStorage.setItem("access_token", "old-token");
  sessionStorage.setItem("unrelated-preference", "keep");
  const user = renderApp("/events/managed");
  expect(await screen.findByText("No managed events.")).toBeTruthy();
  // Leave a protected page earlier in history before signing out.
  await user.click(screen.getByRole("link", { name: "Events", exact: true }));
  expect(await screen.findByRole("heading", { name: "Events" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Sign out" }));
  expect(sessionStorage.getItem("access_token")).toBeNull();
  expect(sessionStorage.getItem("unrelated-preference")).toBe("keep");
  expect(screen.getByRole("heading", { name: "Login" })).toBeTruthy();
  apiClient.get.mockClear();
  await user.click(screen.getByRole("button", { name: "Browser back" }));
  expect(screen.getByRole("heading", { name: "Login" })).toBeTruthy();
  await user.click(screen.getByRole("link", { name: "My managed events" }));
  expect(screen.getByRole("heading", { name: "Login" })).toBeTruthy();
  expect(apiClient.get).not.toHaveBeenCalled();
  await enterCredentials(user);
  await user.click(screen.getByRole("button", { name: "Login" }));
  expect(await screen.findByText("No managed events.")).toBeTruthy();
  await waitFor(() => expect(sessionStorage.getItem("access_token")).toBe("new-token"));
  expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
});

const loginCalls = () => apiClient.post.mock.calls.filter(([url]) => url === "/auth/login").length;

// TC-75-07: logging out on /login must invalidate even the latest pending request.
it("ignores overlapping login responses after sign-out and allows deliberate sign-in again", async () => {
  sessionStorage.setItem("access_token", "existing-token");
  const first = deferredLogin();
  const second = deferredLogin();
  apiClient.post.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const user = renderApp("/login");
  await enterCredentials(user);
  await user.click(screen.getByRole("button", { name: "Login" }));
  await user.click(screen.getByRole("button", { name: "Login" }));
  expect(apiClient.post).toHaveBeenCalledTimes(2);
  await user.click(screen.getByRole("button", { name: "Sign out" }));

  await first.succeed("older-token");
  await second.succeed("late-token");
  expect(sessionStorage.getItem("access_token")).toBeNull();
  expect(screen.getByRole("heading", { name: "Login" })).toBeTruthy();
  expect(apiClient.get).not.toHaveBeenCalled();

  await user.click(screen.getByRole("button", { name: "Login" }));
  expect(await screen.findByRole("heading", { name: "My managed events" })).toBeTruthy();
  expect(sessionStorage.getItem("access_token")).toBe("new-token");
  // Three login submissions; signing out also told the server (SCRUM-75 AC6, TC-75-13).
  expect(loginCalls()).toBe(3);
  expect(apiClient.post).toHaveBeenCalledWith("/auth/logout", {}, { signingOutToken: "existing-token" });
});

// TC-75-08: latest submission wins regardless of response order.
it.each(["before", "after"])("ignores a superseded login response arriving %s the latest response", async (order) => {
  const first = deferredLogin();
  const second = deferredLogin();
  apiClient.post.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const user = renderApp("/login");
  await enterCredentials(user);
  await user.click(screen.getByRole("button", { name: "Login" }));
  await user.click(screen.getByRole("button", { name: "Login" }));

  if (order === "before") {
    await first.succeed("superseded-token", "attendee");
    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(screen.getByRole("heading", { name: "Login" })).toBeTruthy();
    expect(apiClient.get).not.toHaveBeenCalled();
  }
  await second.succeed("current-token");
  expect(await screen.findByRole("heading", { name: "My managed events" })).toBeTruthy();
  apiClient.get.mockClear();
  if (order === "after") await first.succeed("superseded-token", "attendee");
  expect(sessionStorage.getItem("access_token")).toBe("current-token");
  expect(screen.getByRole("heading", { name: "My managed events" })).toBeTruthy();
  expect(apiClient.get).not.toHaveBeenCalled();

  await user.click(screen.getByRole("button", { name: "Sign out" }));
  expect(sessionStorage.getItem("access_token")).toBeNull();
  expect(screen.getByRole("heading", { name: "Login" })).toBeTruthy();
});

// The nav shows each role its own pages. The backend still refuses everyone else.
it.each([
  ["attendee", ["Events", "Notifications", "My registrations"]],
  // CF09 added "Events calendar" for Venue Staff, coordinators and Technical Support Staff.
  ["venue_staff", ["Events", "Notifications", "Venues", "Venue availability", "Events calendar",
    "Venue booking requests", "Tentative holds", "Setup or turnaround conflicts", "Replacement venues needed"]],
  ["tech_staff", ["Events", "Notifications", "Events calendar", "Equipment requests"]],
  ["safety_officer", ["Events", "Notifications", "Safety checks"]],
])("shows a signed-in %s only their own links", async (role, links) => {
  apiClient.post.mockResolvedValue({ data: { access_token: "role-token", role } });
  apiClient.get.mockResolvedValue({
    data: { events: [], notifications: [], requests: [], bookings: [], message: "Nothing." },
  });
  const user = renderApp("/login");
  await enterCredentials(user);
  await user.click(screen.getByRole("button", { name: "Login" }));
  await waitFor(() => expect(sessionStorage.getItem("user_role")).toBe(role));

  const shown = within(screen.getByRole("navigation")).getAllByRole("link").map((link) => link.textContent);
  expect(shown).toEqual(links);

  await user.click(screen.getByRole("button", { name: "Sign out" }));
  expect(sessionStorage.getItem("user_role")).toBeNull();
});

// TC-76-09 (CF01): a user with several roles sees the links of each, in the menu's order,
// and signing out forgets them all.
it("shows a user with several roles the links of each", async () => {
  apiClient.post.mockResolvedValue({
    data: { access_token: "roles-token", role: "organiser", roles: ["organiser", "attendee"] },
  });
  apiClient.get.mockResolvedValue({ data: { drafts: [], submitted: [], message: "Nothing." } });
  const user = renderApp("/login");
  await enterCredentials(user);
  await user.click(screen.getByRole("button", { name: "Login" }));

  const shown = () => within(screen.getByRole("navigation")).getAllByRole("link").map((link) => link.textContent);
  await waitFor(() => expect(shown()).toEqual(["Events", "Notifications", "My event requests", "My drafts",
    "My requests", "Registrations for my events", "My registrations"]));

  await user.click(screen.getByRole("button", { name: "Sign out" }));
  expect(sessionStorage.getItem("user_roles")).toBeNull();
});

// A session whose role list can't be read falls back to its main role.
it.each([
  ["not JSON", "{not json"],
  ["not a list", JSON.stringify({ role: "attendee" })],
])("uses the main role when the stored role list is %s", async (_case, stored) => {
  sessionStorage.setItem("access_token", "old-session");
  sessionStorage.setItem("user_role", "safety_officer");
  sessionStorage.setItem("user_roles", stored);
  apiClient.get.mockResolvedValue({ data: { notifications: [], message: "You have no notifications." } });
  renderApp("/notifications");
  expect(await screen.findByText("You have no notifications.")).toBeTruthy();

  const nav = screen.getByRole("navigation");
  expect(within(nav).getAllByRole("link").map((link) => link.textContent))
    .toEqual(["Events", "Notifications", "Safety checks"]);
  sessionStorage.clear();
});

it("shows an administrator, or a session without a role, every link", async () => {
  sessionStorage.setItem("access_token", "admin-token");
  sessionStorage.setItem("user_role", "admin");
  apiClient.get.mockResolvedValue({ data: { notifications: [], message: "You have no notifications." } });
  renderApp("/notifications");
  expect(await screen.findByText("You have no notifications.")).toBeTruthy();

  const nav = screen.getByRole("navigation");
  expect(within(nav).getByRole("link", { name: "Safety checks" })).toBeTruthy();
  expect(within(nav).getByRole("link", { name: "My registrations" })).toBeTruthy();
  expect(within(nav).queryByRole("link", { name: "Resources" })).toBeNull();
  sessionStorage.clear();
});

// TC-75-13 · SCRUM-75 AC6: signing out tells the server, which refuses the token from then
// on. The browser forgets it first, so a failed call never keeps anyone signed in.
describe("SCRUM-75 signing out on the server", () => {
  it("sends the token it signs out of", async () => {
    sessionStorage.setItem("access_token", "existing-token");
    const user = renderApp("/events/managed");
    await screen.findByRole("heading", { name: "My managed events" });

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(apiClient.post).toHaveBeenCalledWith("/auth/logout", {}, { signingOutToken: "existing-token" });
    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(screen.getByRole("heading", { name: "Login" })).toBeTruthy();
  });

  it("is signed out in the browser even when the server call fails", async () => {
    sessionStorage.setItem("access_token", "existing-token");
    apiClient.post.mockRejectedValueOnce(new Error("Network Error"));
    const user = renderApp("/events/managed");
    await screen.findByRole("heading", { name: "My managed events" });

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(await screen.findByRole("heading", { name: "Login" })).toBeTruthy();
  });
});
