// SCRUM-75-test-cases.md TC-75-06..08; backend/tests/test_auth_unit.py verifies
// that protected API requests without the browser token are refused.
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
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

it.each(["/", "/events/75/planning", "/venues/bookings", "/resources", "/registrations"])(
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
  expect(apiClient.post).toHaveBeenCalledTimes(3);
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
