// End-to-end check of SCRUM-46 in the real app (Vite :5173 -> Flask :5000 -> PostgreSQL).
// Not part of the test suite: it needs both servers, Microsoft Edge, fresh events from
// seed_demo_change_requests.py (a local database: the new table is not on Supabase yet), and
// `npm install playwright-core@1.64.0` in the folder you run it from.
// Usage: node e2e_check.mjs <screenshot dir> '<JSON from seed_demo_change_requests.py>'
import assert from "node:assert/strict";
import path from "node:path";
import { chromium } from "playwright-core";

const [OUT, SEED] = process.argv.slice(2);
const { gala, fair, books } = JSON.parse(SEED);
const WEB = "http://localhost:5173";
const API = "http://localhost:5000/api";
const PASSWORD = "Demo1234!";
const ORGANISER = "demo.organiser@connectsphere.demo";
const COORD = "demo.coordinator@connectsphere.demo";
const results = [];

async function check(id, description, fn) {
  try {
    await fn();
    results.push([id, "PASS"]);
    console.log(`PASS ${id} ${description}`);
  } catch (e) {
    results.push([id, "FAIL"]);
    console.log(`FAIL ${id} ${description}\n  ${e.message.split("\n")[0]}`);
  }
}

async function apiAs(email, url) {
  const login = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: PASSWORD }),
  });
  const { access_token: token } = await login.json();
  assert.ok(token, `login as ${email} failed with HTTP ${login.status}`);
  const r = await fetch(`${API}${url}`, { headers: { Authorization: `Bearer ${token}` } });
  return { status: r.status, body: await r.json() };
}

const browser = await chromium.launch({ channel: "msedge", headless: true });

async function login(email) {
  const context = await browser.newContext({ viewport: { width: 1100, height: 1000 } });
  const page = await context.newPage();
  await page.goto(`${WEB}/login`);
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Login" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  return page;
}

const shot = (page, name) => page.screenshot({ path: path.join(OUT, name), fullPage: true });
const organiser = await login(ORGANISER);

await check("E2E-01", "The organiser opens the form from an approved request; it shows the current values (AC1, AC2)", async () => {
  // By ID, since every seeding run adds events with the same titles.
  const link = (id) => organiser.locator(`a[href="/events/${id}/change-request"]`);
  await organiser.goto(`${WEB}/events/mine`);
  await link(gala).waitFor();
  assert.equal(await link(books).count(), 0);
  assert.equal(await link(gala).innerText(), "Request a change");
  await link(gala).click();
  await organiser.waitForURL(`${WEB}/events/${gala}/change-request`);
  assert.equal(await organiser.getByLabel("Start", { exact: true }).inputValue(), "2026-12-05T18:00");
  assert.equal(await organiser.getByLabel("Expected attendance", { exact: true }).inputValue(), "200");
  assert.equal(await organiser.getByLabel("Venue requirements", { exact: true }).inputValue(), "Ballroom for 200");
  await organiser.getByText(`Coordinator: ${COORD}`).waitFor();
  await shot(organiser, "01-change-request-form.png");
});

await check("E2E-02", "Negative attendance and an end before the start are refused with the reasons (AC4)", async () => {
  await organiser.getByLabel("End", { exact: true }).fill("2026-12-05T17:00");
  await organiser.getByLabel("Expected attendance", { exact: true }).fill("-5");
  await organiser.getByRole("button", { name: "Submit change request" }).click();
  await organiser.getByText("The end must be after the start.").waitFor();
  await organiser.getByText("Expected attendance must be a whole number of at least 1.").waitFor();
  assert.equal(await organiser.getByLabel("Expected attendance", { exact: true }).inputValue(), "-5");
  await shot(organiser, "02-invalid-refused.png");
  const { body } = await apiAs(ORGANISER, `/events/${gala}/change-requests`);
  assert.equal(body.pending_request, null);
});

await check("E2E-03", "A failed save says so, keeps the entries and saves nothing (AC8)", async () => {
  await organiser.getByLabel("End", { exact: true }).fill("2026-12-05T23:00");
  await organiser.getByLabel("Expected attendance", { exact: true }).fill("250");
  await organiser.route("**/api/events/*/change-requests", (route) =>
    (route.request().method() === "POST" ? route.abort() : route.continue()));
  await organiser.getByRole("button", { name: "Submit change request" }).click();
  assert.match(await organiser.getByRole("alert").innerText(), /was not submitted/);
  assert.equal(await organiser.getByLabel("Expected attendance", { exact: true }).inputValue(), "250");
  await shot(organiser, "03-save-failed.png");
  await organiser.unroute("**/api/events/*/change-requests");
  const { body } = await apiAs(ORGANISER, `/events/${gala}/change-requests`);
  assert.equal(body.pending_request, null);
});

await check("E2E-04", "A valid request is saved as Pending Review and confirmed (AC2, AC3, AC6)", async () => {
  await organiser.getByLabel("Start", { exact: true }).fill("2026-12-05T17:00");
  await organiser.getByRole("button", { name: "Submit change request" }).click();
  const status = await organiser.getByRole("status").innerText();
  assert.match(status, /Pending Review/);
  assert.match(status, /\[Demo\] Charity Gala 46/);
  await organiser.getByText("Status: Pending Review").waitFor();
  const changes = await organiser.getByRole("list", { name: "Requested changes" }).getByRole("listitem").allInnerTexts();
  assert.deepEqual(changes, ["Start: 2026-12-05 18:00 → 2026-12-05 17:00", "Expected attendance: 200 → 250"]);
  await shot(organiser, "04-pending-review.png");
});

await check("E2E-05", "The approved event is not changed, and a second request waits (AC6, AC7)", async () => {
  const coordinatorView = await apiAs(COORD, `/events/${gala}/planning`);
  assert.equal(coordinatorView.body.start_time, "2026-12-05T18:00:00");
  assert.equal(coordinatorView.body.expected_attendance, 200);
  await organiser.goto(`${WEB}/events/${gala}/change-request`);
  await organiser.getByText(/already pending review/).waitFor();
  assert.equal(await organiser.getByRole("button", { name: "Submit change request" }).count(), 0);
  await shot(organiser, "05-already-pending.png");
});

await check("E2E-06", "The coordinator is notified of the proposed changes (AC9)", async () => {
  const { body } = await apiAs(COORD, "/notifications/");
  const note = body.notifications.find((n) => n.kind === "change_requested" && n.event_id === gala);
  assert.ok(note, "no change_requested notification for the gala");
  for (const text of ["[Demo] Charity Gala 46", "Start: 2026-12-05 18:00 → 2026-12-05 17:00",
                      "Expected attendance: 200 → 250"]) {
    assert.ok(note.message.includes(text), `notification lacks ${text}: ${note.message}`);
  }
});

await check("E2E-07", "An event with no coordinator says why and offers no form (AC5)", async () => {
  await organiser.goto(`${WEB}/events/${fair}/change-request`);
  await organiser.getByText(/has no coordinator yet/).waitFor();
  assert.equal(await organiser.getByLabel("Start", { exact: true }).count(), 0);
  await shot(organiser, "06-no-coordinator.png");
});

await check("E2E-08", "A submitted event can't take a request, even by its address (AC1)", async () => {
  await organiser.goto(`${WEB}/events/${books}/change-request`);
  await organiser.getByText(/only be requested for approved events/).waitFor();
  assert.equal(await organiser.getByRole("button", { name: "Submit change request" }).count(), 0);
  const coordinator = await apiAs(COORD, `/events/${gala}/change-requests`);
  assert.equal(coordinator.status, 403);
});

await browser.close();
const passed = results.filter(([, r]) => r === "PASS").length;
console.log(`\n${passed}/${results.length} passed`);
process.exit(passed === results.length ? 0 : 1);
