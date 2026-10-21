// End-to-end check of SCRUM-43 in the real app (Vite :5173 -> Flask :5000 -> Supabase).
// Not part of the test suite: it needs both servers, Microsoft Edge, the demo accounts,
// fresh events from seed_demo_availability.py, and `npm install playwright-core@1.64.0`
// in the folder you run it from.
// Usage: node e2e_check.mjs <screenshot dir> '<JSON from seed_demo_availability.py>' <repo root>
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { chromium } from "playwright-core";

const [OUT, SEED, ROOT] = process.argv.slice(2);
const { gala, untimed } = JSON.parse(SEED);
const WEB = "http://localhost:5173";
const API = "http://localhost:5000/api";
const PASSWORD = "Demo1234!";
const COORD = "demo.coordinator@connectsphere.demo";
const TECH = "demo.tech@connectsphere.demo";
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

// The demo equipment's available quantities, read from the database (not the app).
function stock() {
  const python = path.join(ROOT, "backend", ".venv", "Scripts", "python.exe");
  const script = path.join(ROOT, "docs", "evidence", "SCRUM-43", "scripts", "seed_demo_availability.py");
  const r = spawnSync(python, [script, "check"], { cwd: path.join(ROOT, "backend"), encoding: "utf-8" });
  assert.equal(r.status, 0, r.stderr);
  return JSON.parse(r.stdout.trim().split("\n").pop());
}

const browser = await chromium.launch({ channel: "msedge", headless: true });

async function login(email) {
  const context = await browser.newContext({ viewport: { width: 1100, height: 900 } });
  const page = await context.newPage();
  await page.goto(`${WEB}/login`);
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Login" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  return page;
}

const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
const lines = (page) => page.getByRole("list", { name: "Availability by requirement" }).getByRole("listitem");
const before = stock();
const tech = await login(TECH);

await check("E2E-01", "AC1: Technical Support open the check from the event's equipment requirements", async () => {
  await tech.goto(`${WEB}/events/${gala.id}/equipment`);
  await tech.getByRole("link", { name: "Check availability" }).click();
  await tech.getByRole("heading", { name: "Equipment availability" }).waitFor();
  await tech.getByRole("heading", { name: gala.title }).waitFor();
  await tech.getByText("For: 05/12/2026 18:00 SGT to 05/12/2026 23:00 SGT").waitFor();
  assert.equal(await lines(tech).count(), 3);
});

await check("E2E-02", "AC1, AC2: each requirement shows its requested and available quantity and the result", async () => {
  const [mics, projector, hologram] = await Promise.all([0, 1, 2].map((i) => lines(tech).nth(i).innerText()));
  assert.match(mics, /3 × \[Demo\] Wireless microphone[\s\S]*Requested: 3 · Available: 4[\s\S]*Enough available/);
  assert.match(mics, /confirm the technical requirements: Lapel/);
  assert.match(mics, /Counted: .*Sennheiser EW-D 43 \(2\).*Shure SLX-D 43 \(2\)/);
  assert.match(projector, /Requested: 1 · Available: 2[\s\S]*Enough available/);
  assert.match(hologram, /Requested: 1 · Available: 0[\s\S]*No suitable equipment available/);
  await tech.getByText("2 of 3 equipment requirements can be met from available equipment.").waitFor();
  await shot(tech, "01-availability-result");
});

await check("E2E-03", "AC3: the projector unavailable during the event is not counted, with the reason", async () => {
  const projector = await lines(tech).nth(1).innerText();
  assert.match(projector, /Counted: \[Demo\] BenQ LU935 \(2\)/);
  assert.match(projector, /Not counted: \[Demo\] Epson EB-L \(Unavailable 2026-12-05 17:00 to 2026-12-05 19:00: Lamp replacement\)/);
});

await check("E2E-04", "AC4: checking reserves nothing (stock unchanged in the database, same result again)", async () => {
  await tech.getByText("Checking availability does not reserve any equipment.").waitFor();
  const first = await lines(tech).allInnerTexts();
  await tech.getByRole("button", { name: "Check again" }).click();
  await lines(tech).first().waitFor();
  assert.deepEqual(await lines(tech).allInnerTexts(), first);
  assert.deepEqual(stock(), before);
  assert.doesNotMatch(await tech.locator("body").innerText(), /reserved|booked|confirmed/i);
  console.log(`  stock before and after: ${JSON.stringify(before)}`);
});

await check("E2E-05", "AC5: an event without times explains what is missing and shows no result", async () => {
  await tech.goto(`${WEB}/events/${untimed.id}/equipment-availability`);
  assert.match(await tech.getByRole("alert").innerText(),
               /start time and end time are not recorded, so equipment availability can't be checked/);
  assert.equal(await tech.getByRole("list", { name: "Availability by requirement" }).count(), 0);
  assert.equal(await tech.getByRole("button", { name: "Retry" }).count(), 0);
  const { status, body } = await apiAs(TECH, `/events/${untimed.id}/equipment-availability`);
  assert.equal(status, 422);
  assert.deepEqual(body.missing, ["start_time", "end_time"]);
  await shot(tech, "02-missing-times");
});

await check("E2E-06", "AC5: a failed check is an error with Retry, never a result", async () => {
  // The check never reaches the server, as when the connection drops. Only the API call
  // is cut off: the page's own address also ends in /equipment-availability.
  const apiCall = `${API}/events/${gala.id}/equipment-availability`;
  await tech.route(apiCall, (route) => route.abort());
  await tech.goto(`${WEB}/events/${gala.id}/equipment-availability`);
  assert.match(await tech.getByRole("alert").innerText(), /could not be completed/);
  assert.equal(await tech.getByRole("list", { name: "Availability by requirement" }).count(), 0);
  await shot(tech, "03-check-failed");
  await tech.unroute(apiCall);
  await tech.getByRole("button", { name: "Retry" }).click();
  await lines(tech).first().waitFor();
  assert.equal(await lines(tech).count(), 3);
});

await check("E2E-07", "A9: the coordinator can't run the check (HTTP 403) and isn't offered it", async () => {
  assert.equal((await apiAs(COORD, `/events/${gala.id}/equipment-availability`)).status, 403);
  const coord = await login(COORD);
  await coord.goto(`${WEB}/events/${gala.id}/equipment`);
  await coord.getByRole("heading", { name: gala.title }).waitFor();
  assert.equal(await coord.getByRole("link", { name: "Check availability" }).count(), 0);
  await coord.context().close();
});

await browser.close();
const failed = results.filter((r) => r[1] === "FAIL").length;
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
