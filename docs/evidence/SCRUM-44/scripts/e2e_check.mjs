// End-to-end check of SCRUM-44 in the real app (Vite :5173 -> Flask :5000 -> PostgreSQL).
// Not part of the test suite: it needs both servers, Microsoft Edge, fresh events from
// seed_demo_reservations.py (a local database: the new table is not on Supabase yet), and
// `npm install playwright-core@1.64.0` in the folder you run it from.
// Usage: node e2e_check.mjs <screenshot dir> '<JSON from seed_demo_reservations.py>' <repo root>
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { chromium } from "playwright-core";

const [OUT, SEED, ROOT] = process.argv.slice(2);
const { gala, concert } = JSON.parse(SEED);
const WEB = "http://localhost:5173";
const API = "http://localhost:5000/api";
const PASSWORD = "Demo1234!";
const COORD = "demo.coordinator@connectsphere.demo";
const TECH = "demo.tech@connectsphere.demo";
const SHURE = "[Demo] Shure SLX-D 44";
const SENNHEISER = "[Demo] Sennheiser EW-D 44";
const MICS = "3 × [Demo] Wireless microphone";
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
const requirement = (page, name) =>
  page.getByRole("list", { name: "Equipment requirements" }).locator(":scope > li").filter({ hasText: name });

const tech = await login(TECH);

await check("E2E-01", "Technical Support open the event's reservations: requirements and period (AC1)", async () => {
  await tech.goto(`${WEB}/events/${gala}/equipment`);
  await tech.getByRole("link", { name: "Reserve equipment" }).click();
  await tech.getByRole("heading", { name: "Equipment reservations" }).waitFor();
  await tech.getByText("Reservation period: 05/12/2026 18:00 SGT to 05/12/2026 23:00 SGT").waitFor();
  const mics = requirement(tech, MICS);
  assert.match(await mics.innerText(), /Reserved: 0 of 3/);
  assert.match(await mics.innerText(), /Shure SLX-D 44: 2 available to reserve/);
  assert.match(await mics.innerText(), /Technical Support must confirm the technical requirements: Lapel/);
  assert.match(await requirement(tech, "1 × [Demo] Projector").innerText(),
               /Not available: \[Demo\] Epson EB-L 44 \(Unavailable 2026-12-05 17:00 to 2026-12-05 19:00: Lamp replacement\)/);
  await shot(tech, "01-reservation-page.png");
});

await check("E2E-02", "Reserving 2 Shure + 1 Sennheiser records them and confirms (AC2, AC3)", async () => {
  await tech.getByLabel(`Quantity of ${SHURE}`).fill("2");
  await tech.getByLabel(`Quantity of ${SENNHEISER}`).fill("1");
  await tech.getByRole("button", { name: `Reserve for ${MICS}` }).click();
  const status = await tech.getByRole("status").innerText();
  for (const text of [`2 × ${SHURE}`, `1 × ${SENNHEISER}`, "[Demo] Charity Gala", "2026-12-05 18:00 to 2026-12-05 23:00",
                      "The event's coordinator has been notified."]) {
    assert.ok(status.includes(text), `confirmation lacks ${text}: ${status}`);
  }
  const mics = await requirement(tech, MICS).innerText();
  assert.match(mics, /Reserved: 3 of 3/);
  assert.match(mics, /Fully reserved/);
  const { body } = await apiAs(TECH, `/events/${gala}/equipment-reservations`);
  // In the order the page lists the items (by name), so not necessarily as typed.
  const saved = body.requirements[0].reservations
    .map((r) => [r.resource.name, r.quantity, r.start_time, r.end_time, r.status]).sort();
  assert.deepEqual(saved, [[SENNHEISER, 1, "2026-12-05T18:00:00", "2026-12-05T23:00:00", "reserved"],
                           [SHURE, 2, "2026-12-05T18:00:00", "2026-12-05T23:00:00", "reserved"]]);
  await shot(tech, "02-reserved.png");
});

await check("E2E-03", "The overlapping concert can no longer have what the gala reserved (AC4)", async () => {
  await tech.goto(`${WEB}/events/${concert}/equipment-reservations`);
  const mics = await requirement(tech, "2 × [Demo] Wireless microphone").innerText();
  assert.match(mics, /Shure SLX-D 44: 0 available to reserve \(2 recorded, 2 reserved for other events at this time\)/);
  assert.match(mics, /Sennheiser EW-D 44: 1 available to reserve \(2 recorded, 1 reserved for other events at this time\)/);
  await shot(tech, "03-overlapping-event.png");
  await tech.goto(`${WEB}/events/${concert}/equipment-availability`);
  const line = await tech.getByRole("list", { name: "Availability by requirement" }).innerText();
  assert.match(line, /Requested: 2 · Available: 1/);
  assert.match(line, /Shure SLX-D 44 \(0 of 2; 2 reserved for other events at this time\)/);
});

await check("E2E-04", "Asking for more than is available is refused with the available quantity (AC5)", async () => {
  await tech.goto(`${WEB}/events/${concert}/equipment-reservations`);
  await tech.getByLabel(`Quantity of ${SENNHEISER}`).fill("2");
  await tech.getByRole("button", { name: "Reserve for 2 × [Demo] Wireless microphone" }).click();
  const alert = await tech.getByRole("alert").innerText();
  assert.equal(alert, `Only 1 × ${SENNHEISER} is available for this event's period, not 2. Nothing was reserved.`);
  assert.equal(await tech.getByLabel(`Quantity of ${SENNHEISER}`).inputValue(), "2");
  const { body } = await apiAs(TECH, `/events/${concert}/equipment-reservations`);
  assert.equal(body.requirements[0].reserved_quantity, 0);
  await shot(tech, "04-more-than-available.png");
});

await check("E2E-05", "No suitable equipment: the hologram projector can't be reserved (AC6)", async () => {
  await tech.goto(`${WEB}/events/${gala}/equipment-reservations`);
  const hologram = requirement(tech, "1 × [Demo] Hologram projector");
  assert.match(await hologram.innerText(), /No suitable equipment is available to reserve/);
  assert.equal(await hologram.getByRole("button").count(), 0);
  assert.equal(await hologram.getByRole("spinbutton").count(), 0);
});

await check("E2E-06", "A failed save says so, keeps the entry and changes nothing (AC7)", async () => {
  await tech.route("**/api/events/*/equipment-reservations", (route) =>
    (route.request().method() === "POST" ? route.abort() : route.continue()));
  await tech.getByLabel("Quantity of [Demo] BenQ LU935 44").fill("1");
  await tech.getByRole("button", { name: "Reserve for 1 × [Demo] Projector" }).click();
  const alert = await requirement(tech, "1 × [Demo] Projector").getByRole("alert").innerText();
  assert.match(alert, /The equipment was not reserved/);
  assert.equal(await tech.getByLabel("Quantity of [Demo] BenQ LU935 44").inputValue(), "1");
  await shot(tech, "05-save-failed.png");
  await tech.unroute("**/api/events/*/equipment-reservations");
  const { body } = await apiAs(TECH, `/events/${gala}/equipment-reservations`);
  assert.equal(body.requirements[1].reserved_quantity, 0);
  assert.equal(body.requirements[0].reservations.length, 2);
});

const coordinator = await login(COORD);

await check("E2E-07", "The coordinator is notified and can see, not make, the reservations (AC8)", async () => {
  const { body } = await apiAs(COORD, "/notifications/");
  const note = body.notifications.find((n) => n.kind === "equipment_reserved" && n.event_id === gala);
  assert.ok(note, "no equipment_reserved notification for the gala");
  for (const text of [`2 × ${SHURE}`, `1 × ${SENNHEISER}`, MICS, "[Demo] Charity Gala"]) {
    assert.ok(note.message.includes(text), `notification lacks ${text}: ${note.message}`);
  }
  await coordinator.goto(`${WEB}/events/${gala}/equipment`);
  await coordinator.getByRole("link", { name: "Reserved equipment" }).click();
  const mics = await requirement(coordinator, MICS).innerText();
  assert.match(mics, new RegExp(`2 × \\[Demo\\] Shure SLX-D 44 reserved by ${TECH}`));
  assert.equal(await coordinator.getByRole("button", { name: /^Reserve for/ }).count(), 0);
  await shot(coordinator, "06-coordinator-view.png");
});

await check("E2E-08", "Changing the requirement releases its reservation; the units are free again (AC9)", async () => {
  await coordinator.goto(`${WEB}/events/${gala}/equipment`);
  await coordinator.getByRole("button", { name: `Edit ${MICS}` }).click();
  await coordinator.getByLabel("Quantity", { exact: true }).fill("4");
  await coordinator.getByRole("button", { name: "Save changes" }).click();
  assert.match(await coordinator.getByRole("status").innerText(), /Its reserved equipment was released\./);
  await tech.goto(`${WEB}/events/${concert}/equipment-reservations`);
  assert.match(await requirement(tech, "2 × [Demo] Wireless microphone").innerText(),
               /Shure SLX-D 44: 2 available to reserve/);
  await tech.goto(`${WEB}/events/${gala}/equipment-reservations`);
  const released = await tech.getByRole("list", { name: "Released reservations" }).innerText();
  assert.match(released, new RegExp(`2 × \\[Demo\\] Shure SLX-D 44 released: The equipment requirement was changed\\.`));
  await shot(tech, "07-released-after-change.png");
});

await check("E2E-09", "Cancelling the event releases its reservations (AC9)", async () => {
  // Reserve for the concert, then cancel it as a cancel feature would (there is none yet).
  await tech.goto(`${WEB}/events/${concert}/equipment-reservations`);
  await tech.getByLabel(`Quantity of ${SHURE}`).fill("2");
  await tech.getByRole("button", { name: "Reserve for 2 × [Demo] Wireless microphone" }).click();
  await tech.getByRole("status").waitFor();
  let gala_ = await apiAs(TECH, `/events/${gala}/equipment-reservations`);
  assert.equal(gala_.body.requirements[0].options.find((o) => o.name === SHURE).available_to_reserve, 0);
  const python = path.join(ROOT, "backend", ".venv", "Scripts", "python.exe");
  const script = path.join(ROOT, "docs", "evidence", "SCRUM-44", "scripts", "seed_demo_reservations.py");
  const r = spawnSync(python, [script, "cancel", String(concert)], { cwd: path.join(ROOT, "backend"), encoding: "utf-8" });
  assert.equal(r.status, 0, r.stderr);
  gala_ = await apiAs(TECH, `/events/${gala}/equipment-reservations`);
  assert.equal(gala_.body.requirements[0].options.find((o) => o.name === SHURE).available_to_reserve, 2);
  await tech.goto(`${WEB}/events/${concert}/equipment-reservations`);
  await tech.getByText("This event is cancelled, so equipment can't be reserved for it.").waitFor();
  assert.match(await tech.getByRole("list", { name: "Released reservations" }).innerText(),
               /2 × \[Demo\] Shure SLX-D 44 released: The event was cancelled\./);
  await shot(tech, "08-released-after-cancel.png");
});

await browser.close();
const passed = results.filter(([, r]) => r === "PASS").length;
console.log(`\n${passed}/${results.length} passed`);
process.exit(passed === results.length ? 0 : 1);
