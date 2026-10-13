import { afterEach, describe, expect, it } from "vitest";
import { isSignedIn, readToken, signOut } from "./session.js";

// Display-only helper for the nav (Login / Log out). The backend still decides
// whether a token is valid.

function jwt(payload) {
  const encode = (value) => btoa(JSON.stringify(value)).replace(/=+$/, "");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode(payload)}.signature`;
}

const NOW_SECONDS = Math.floor(Date.now() / 1000);

afterEach(() => sessionStorage.clear());

describe("session", () => {
  it("is signed out when no token is stored", () => {
    expect(readToken()).toBeNull();
    expect(isSignedIn()).toBe(false);
  });

  it("is signed in with a stored token that has not expired", () => {
    sessionStorage.setItem("access_token", jwt({ sub: "3", exp: NOW_SECONDS + 600 }));
    expect(isSignedIn()).toBe(true);
  });

  it("is signed out when the stored token has expired", () => {
    sessionStorage.setItem("access_token", jwt({ sub: "3", exp: NOW_SECONDS - 5 }));
    expect(isSignedIn()).toBe(false);
  });

  it("treats a token it cannot read as signed in and leaves the server to judge it", () => {
    sessionStorage.setItem("access_token", "not-a-jwt");
    expect(isSignedIn()).toBe(true);
  });

  it("is signed out for a blank token", () => {
    sessionStorage.setItem("access_token", "   ");
    expect(isSignedIn()).toBe(false);
  });

  it("signOut removes the stored token", () => {
    sessionStorage.setItem("access_token", "issued-token");
    signOut();
    expect(sessionStorage.getItem("access_token")).toBeNull();
  });
});
