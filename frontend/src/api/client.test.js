import { describe, expect, it, vi } from "vitest";

// A fresh module models client initialization after a page reload; storage
// survives the module reset. The adapter prevents any actual HTTP requests.
async function initializeClient() {
  vi.resetModules();
  return (await import("./client.js")).default;
}

async function outgoingHeaders(client) {
  let headers;
  await client.get("/venues/", {
    adapter: async (config) => {
      headers = config.headers;
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    },
  });
  return headers;
}

describe("shared API client authentication", () => {
  it("uses a sessionStorage token after fresh client initialization", async () => {
    sessionStorage.setItem("access_token", "existing-session-token");
    const client = await initializeClient();
    const headers = await outgoingHeaders(client);
    expect(headers.get("Authorization")).toBe("Bearer existing-session-token");
  });

  it("uses a token stored after the client was initialized", async () => {
    const client = await initializeClient();
    sessionStorage.setItem("access_token", "new-login-token");
    const headers = await outgoingHeaders(client);
    expect(headers.get("Authorization")).toBe("Bearer new-login-token");
  });

  it("omits Authorization when there is no session token", async () => {
    const client = await initializeClient();
    const headers = await outgoingHeaders(client);
    expect(headers.has("Authorization")).toBe(false);
  });
});
