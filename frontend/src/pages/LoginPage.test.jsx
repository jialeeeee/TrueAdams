import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "../api/client.js";
import LoginPage from "./LoginPage.jsx";

vi.mock("../api/client.js", () => ({ default: { post: vi.fn() } }));

const EMAIL = "signin@test.invalid";
const PASSWORD = "Test-signin-password!";
const INVALID = "Invalid email or password.";
const REQUIRED = "Email and password are required.";
const UNAVAILABLE = "Sign-in is temporarily unavailable. Please try again.";

function httpFailure(status, error) {
  return Object.assign(new Error(`Request failed with status ${status}`), {
    isAxiosError: true,
    response: { status, data: { error, ...(status === 503 ? { retryable: true } : {}) } },
  });
}

function Location() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

function renderLogin() {
  render(
    <MemoryRouter initialEntries={["/login"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Location />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<h1>Events</h1>} />
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

async function submit(user, { email = EMAIL, password = PASSWORD } = {}) {
  if (email) await user.type(screen.getByPlaceholderText("Email"), email);
  if (password) await user.type(screen.getByPlaceholderText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Login" }));
}

function expectNoSessionOrNavigation() {
  expect(sessionStorage.getItem("access_token")).toBeNull();
  expect(screen.getByTestId("location").textContent).toBe("/login");
}

beforeEach(() => {
  apiClient.post.mockReset();
});

describe("SCRUM-27 sign-in", () => {
  it("submits entered credentials to POST /auth/login", async () => {
    apiClient.post.mockResolvedValue({ data: { access_token: "issued-token" } });
    await submit(renderLogin());
    expect(apiClient.post).toHaveBeenCalledTimes(1);
    expect(apiClient.post).toHaveBeenCalledWith("/auth/login", {
      email: EMAIL, password: PASSWORD,
    });
  });

  it("stores the returned token in sessionStorage and navigates to Events", async () => {
    apiClient.post.mockResolvedValue({ data: { access_token: "issued-token" } });
    await submit(renderLogin());
    await waitFor(() => expect(sessionStorage.getItem("access_token")).toBe("issued-token"));
    expect(await screen.findByRole("heading", { name: "Events" })).toBeTruthy();
    expect(screen.getByTestId("location").textContent).toBe("/");
  });

  it("displays the backend 401 explanation without authenticating or navigating", async () => {
    apiClient.post.mockRejectedValue(httpFailure(401, INVALID));
    await submit(renderLogin());
    expect(await screen.findByText(INVALID)).toBeTruthy();
    expectNoSessionOrNavigation();
  });

  it.each(["email", "password"])("gives visible feedback for an empty %s", async (field) => {
    // Either native form validation or a displayed application/API error is
    // acceptable. No particular validation component or hook is prescribed.
    apiClient.post.mockRejectedValue(httpFailure(400, REQUIRED));
    await submit(renderLogin(), { [field]: "" });
    await waitFor(() => {
      const inputs = [screen.getByPlaceholderText("Email"), screen.getByPlaceholderText("Password")];
      const nativeFeedback = inputs.some((input) => !input.validity.valid && Boolean(input.validationMessage));
      expect(nativeFeedback || Boolean(screen.queryByText(/required|enter.*email|enter.*password/i))).toBe(true);
    });
    expectNoSessionOrNavigation();
  });

  it("displays a backend 400 validation error", async () => {
    apiClient.post.mockRejectedValue(httpFailure(400, REQUIRED));
    await submit(renderLogin());
    expect(await screen.findByText(REQUIRED)).toBeTruthy();
    expectNoSessionOrNavigation();
  });

  it("displays retry guidance for an authentication service outage", async () => {
    apiClient.post.mockRejectedValue(httpFailure(503, UNAVAILABLE));
    await submit(renderLogin());
    expect(await screen.findByText(/try again|retry/i)).toBeTruthy();
    expectNoSessionOrNavigation();
  });

  it("displays retry guidance for a network failure without an HTTP response", async () => {
    apiClient.post.mockRejectedValue(new Error("Network Error"));
    await submit(renderLogin());
    expect(await screen.findByText(/try again|retry/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Login" }).disabled).toBe(false);
    expectNoSessionOrNavigation();
  });

  it("allows retry after failure and clears the error on successful navigation", async () => {
    apiClient.post
      .mockRejectedValueOnce(httpFailure(503, UNAVAILABLE))
      .mockResolvedValueOnce({ data: { access_token: "retry-token" } });
    const user = renderLogin();
    await submit(user);
    expect(await screen.findByText(/try again|retry/i)).toBeTruthy();
    expectNoSessionOrNavigation();
    await user.click(screen.getByRole("button", { name: "Login" }));
    await waitFor(() => expect(sessionStorage.getItem("access_token")).toBe("retry-token"));
    expect(await screen.findByRole("heading", { name: "Events" })).toBeTruthy();
    expect(screen.queryByText(/try again|retry/i)).toBeNull();
    expect(screen.getByTestId("location").textContent).toBe("/");
    expect(apiClient.post).toHaveBeenCalledTimes(2);
  });

  it.each([
    ["401", () => httpFailure(401, INVALID)],
    ["400", () => httpFailure(400, REQUIRED)],
    ["503", () => httpFailure(503, UNAVAILABLE)],
    ["network", () => new Error("Network Error")],
  ])("preserves an existing session after a failed %s login", async (_label, failure) => {
    sessionStorage.setItem("access_token", "existing-token");
    apiClient.post.mockRejectedValue(failure());
    await submit(renderLogin());
    expect(await screen.findByText(/invalid email or password|required|try again|retry/i)).toBeTruthy();
    expect(sessionStorage.getItem("access_token")).toBe("existing-token");
    expect(screen.getByTestId("location").textContent).toBe("/login");
  });
});
