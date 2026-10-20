// End-to-end check of SCRUM-42 in the real app (Vite :5173 -> Flask :5000 -> Supabase).
// Not part of the test suite: it needs both servers, Microsoft Edge, the SCRUM-62 demo
// accounts, fresh events from seed_demo_equipment.py, and
// `npm install playwright-core@1.64.0` in the folder you run it from.
// Usage: node e2e_check.mjs <screenshot dir> '<JSON from seed_demo_equipment.py>' <repo root>
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { chromium } from "playwright-core";

const [OUT, SEED, ROOT] = process.argv.slice(2);
const { gala, closed, equipment } = JSON.parse(SEED);
const WEB = "http://localhost:5173";
const API = "http://localhost:5000/api";
const PASSWORD = "Demo1234!";
const COORD = "demo.coordinator@connectsphere.demo";
const TECH = "demo.tech@connectsphere.demo";
const NOTE = "Two lapel mics held at the AV store";
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

async function apiAs(email, method, url, body) {
  const login = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: PASSWORD }),
  });
  const { access_token: token } = await login.json();
  assert.ok(token, `login as ${email} failed with HTTP ${login.status}`);
  const r = await fetch(`${API}${url}`, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return { status: r.status, body: await r.json() };
}

// What the database holds, read by seed_demo_equipment.py (not through the app).
function stored(eventId) {
  const python = path.join(ROOT, "backend", ".venv", "Scripts", "python.exe");
  const script = path.join(ROOT, "docs", "evidence", "SCRUM-42", "scripts", "seed_demo_equipment.py");
  const r = spawnSync(python, [script, "check", String(eventId)],
                      { cwd: path.join(ROOT, "backend"), encoding: "utf-8" });
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
const items = (page) => page.getByRole("list", { name: "Recorded equipment requirements" }).getByRole("listitem");

async function enter(page, type, quantity, technical = "") {
  await page.getByLabel("Equipment type", { exact: true }).fill(type);
  await page.getByLabel("Quantity", { exact: true }).fill(quantity);
  await page.getByLabel("Technical requirements (optional)").fill(technical);
}

const coord = await login(COORD);

await check("E2E-01", "AC1: the coordinator opens the event's equipment requirements from its planning page", async () => {
  await coord.goto(`${WEB}/events/${gala.id}/planning`);
  await coord.getByRole("link", { name: "Equipment requirements" }).click();
  await coord.getByRole("heading", { name: "Equipment requirements" }).waitFor();
  await coord.getByRole("heading", { name: gala.title }).waitFor();
  await coord.getByText("From the organiser's request: Two wireless microphones and a projector").waitFor();
  await coord.getByText("No equipment requirements have been recorded for this event.").waitFor();
  await shot(coord, "01-nothing-recorded-yet");
});

await check("E2E-02", "AC2: an invalid entry names each problem and saves nothing", async () => {
  await enter(coord, "   ", "0");
  await coord.getByRole("button", { name: "Record requirement" }).click();
  await coord.getByRole("alert").waitFor();
  await coord.getByText("Enter the equipment type.").waitFor();
  await coord.getByText("Quantity must be a whole number from 1 to 1000.").waitFor();
  assert.equal(await coord.getByLabel("Quantity", { exact: true }).inputValue(), "0");
  assert.equal(await items(coord).count(), 0);
  await shot(coord, "02-invalid-entry");
});

await check("E2E-03", "AC1, AC3, AC5, AC6: requirements are recorded, without reserving anything", async () => {
  await enter(coord, "Wireless microphone", "2", "Lapel, with spare batteries");
  await coord.getByRole("button", { name: "Record requirement" }).click();
  assert.match(await coord.getByRole("status").innerText(), /Recorded 2 × Wireless microphone.*does not reserve any equipment/);
  // No such equipment exists: it can still be recorded (AC6).
  await enter(coord, "Hologram projector", "1");
  await coord.getByRole("button", { name: "Record requirement" }).click();
  await coord.getByRole("status").filter({ hasText: "Hologram projector" }).waitFor();
  assert.equal(await items(coord).count(), 2);
  assert.match(await items(coord).nth(0).innerText(), /2 × Wireless microphone[\s\S]*Lapel, with spare batteries[\s\S]*Status: Requested/);
  assert.match(await items(coord).nth(1).innerText(), /1 × Hologram projector[\s\S]*None recorded[\s\S]*Status: Requested/);
  await shot(coord, "03-requirements-recorded");
});

await check("E2E-04", "AC2: the same requirement can't be recorded twice", async () => {
  await enter(coord, "wireless MICROPHONE", "1", "lapel,  with spare batteries");
  await coord.getByRole("button", { name: "Record requirement" }).click();
  await coord.getByText(/already recorded for this event\. Change its quantity instead\./).waitFor();
  assert.equal(await items(coord).count(), 2);
});

await check("E2E-05", "AC3: the saved requirements are shown again after reloading", async () => {
  await coord.reload();
  await items(coord).first().waitFor();
  assert.equal(await items(coord).count(), 2);
  assert.match(await items(coord).nth(0).innerText(), /2 × Wireless microphone/);
});

await check("E2E-06", "AC1: the coordinator corrects one requirement and removes another", async () => {
  await coord.getByRole("button", { name: "Edit 2 × Wireless microphone" }).click();
  await coord.getByLabel("Quantity", { exact: true }).fill("3");
  await coord.getByRole("button", { name: "Save changes" }).click();
  assert.match(await coord.getByRole("status").innerText(), /Updated 3 × Wireless microphone/);
  await enter(coord, "Projector", "1");
  await coord.getByRole("button", { name: "Record requirement" }).click();
  await coord.getByRole("button", { name: "Remove 1 × Projector" }).click();
  assert.match(await coord.getByRole("status").innerText(), /Removed 1 × Projector/);
  assert.equal(await items(coord).count(), 2);
});

await check("E2E-07", "AC1, AC4: other users can't record, change or see the requirements (HTTP 403)", async () => {
  const url = `/events/${gala.id}/equipment-requirements`;
  const body = { equipment_type: "Speaker", quantity: 1 };
  assert.equal((await apiAs("demo.coordinator2@connectsphere.demo", "POST", url, body)).status, 403);
  assert.equal((await apiAs("demo.organiser@connectsphere.demo", "GET", url)).status, 403);
  assert.equal((await apiAs(TECH, "POST", url, body)).status, 403);
  assert.equal((await apiAs(COORD, "GET", "/events/equipment-requests")).status, 403);
});

const tech = await login(TECH);

await check("E2E-08", "AC4: Technical Support Staff see the event among the equipment requests", async () => {
  await tech.getByRole("link", { name: "Equipment requests" }).click();
  const item = tech.locator("li", { hasText: gala.title });
  await item.waitFor();
  assert.match(await item.innerText(), /2 requirements — Requested: 2 · Being arranged: 0 · Suitable equipment unavailable: 0/);
  assert.equal(await tech.locator("li", { hasText: closed.title }).count(), 0);
  await shot(tech, "04-equipment-requests");
});

await check("E2E-09", "AC4, AC6: Technical Support update each requirement as arrangements are made", async () => {
  await tech.getByRole("link", { name: gala.title }).click();
  const microphones = tech.getByLabel("Arrangement status for 3 × Wireless microphone");
  await microphones.waitFor();
  assert.deepEqual(await microphones.locator("option").allInnerTexts(),
                   ["Requested", "Being arranged", "Suitable equipment unavailable"]);
  assert.equal(await tech.getByLabel("Equipment type", { exact: true }).count(), 0);
  await microphones.selectOption("being_arranged");
  await tech.getByLabel("Note for 3 × Wireless microphone").fill(NOTE);
  await tech.getByRole("button", { name: "Update 3 × Wireless microphone" }).click();
  assert.match(await tech.getByRole("status").innerText(), /Arrangement status updated to Being arranged/);
  await tech.getByLabel("Arrangement status for 1 × Hologram projector").selectOption("unavailable");
  await tech.getByLabel("Note for 1 × Hologram projector").fill("No supplier can provide one");
  await tech.getByRole("button", { name: "Update 1 × Hologram projector" }).click();
  await tech.getByRole("status").filter({ hasText: "Suitable equipment unavailable" }).waitFor();
  await shot(tech, "05-arrangements-updated");
});

await check("E2E-10", "AC4, AC6: the coordinator sees the arrangements; the unavailable one stays recorded, not reserved", async () => {
  await coord.reload();
  await items(coord).first().waitFor();
  assert.match(await items(coord).nth(0).innerText(), new RegExp(`Status: Being arranged[\\s\\S]*Note from Technical Support: ${NOTE}`));
  assert.match(await items(coord).nth(1).innerText(), /1 × Hologram projector[\s\S]*Status: Suitable equipment unavailable/);
  assert.doesNotMatch(await coord.locator("body").innerText(), /reserved|fulfilled/i);
  await shot(coord, "06-coordinator-sees-arrangements");
});

await check("E2E-11", "AC5: the database shows the requirements and the equipment's quantity unchanged", async () => {
  const db = stored(gala.id);
  assert.equal(db.equipment.quantity_available, equipment.quantity_available);
  assert.deepEqual(db.requirements, [
    ["Wireless microphone", 3, "Lapel, with spare batteries", "being_arranged", NOTE],
    ["Hologram projector", 1, null, "unavailable", "No supplier can provide one"],
  ]);
  console.log(`  ${db.equipment.name}: ${db.equipment.quantity_available} available before and after`);
});

await check("E2E-12", "AC1: a cancelled event's requirements are read-only (HTTP 409 to change them)", async () => {
  await coord.goto(`${WEB}/events/${closed.id}/equipment`);
  await coord.getByText("This event is cancelled, so its equipment requirements can no longer be changed.").waitFor();
  assert.match(await items(coord).nth(0).innerText(), /1 × Projector/);
  assert.equal(await coord.getByRole("button", { name: "Record requirement" }).count(), 0);
  assert.equal(await coord.getByRole("button", { name: /^Edit / }).count(), 0);
  const r = await apiAs(COORD, "POST", `/events/${closed.id}/equipment-requirements`, { equipment_type: "Speaker", quantity: 1 });
  assert.equal(r.status, 409);
  await shot(coord, "07-cancelled-read-only");
});

await check("E2E-13", "AC7: when saving fails, the coordinator is told and nothing changes", async () => {
  await coord.goto(`${WEB}/events/${gala.id}/equipment`);
  await items(coord).first().waitFor();
  // The save never reaches the server, as when the connection drops.
  await coord.route("**/equipment-requirements", (route) =>
    route.request().method() === "POST" ? route.abort() : route.continue());
  await enter(coord, "Speaker", "2");
  await coord.getByRole("button", { name: "Record requirement" }).click();
  assert.match(await coord.getByRole("alert").innerText(), /not saved, and the recorded requirements are unchanged/);
  assert.equal(await coord.getByLabel("Equipment type", { exact: true }).inputValue(), "Speaker");
  await shot(coord, "08-save-failed");
  await coord.unroute("**/equipment-requirements");
  await coord.reload();
  await items(coord).first().waitFor();
  assert.equal(await items(coord).count(), 2);
  assert.equal(stored(gala.id).requirements.length, 2);
});

await browser.close();
const failed = results.filter((r) => r[1] === "FAIL").length;
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
