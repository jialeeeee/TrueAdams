// End-to-end check of SCRUM-97 in the real app (Vite :5173 -> Flask :5000 -> PostgreSQL).
// Not part of the test suite: it needs both servers, Microsoft Edge, a fresh event from
// seed_demo_tech_update.py (a local database), and `npm install playwright-core@1.64.0` in
// the folder you run it from.
// Usage: node e2e_check.mjs <screenshot dir> '<JSON from seed_demo_tech_update.py>'
import assert from "node:assert/strict";
import path from "node:path";
import { chromium } from "playwright-core";

const [OUT, SEED] = process.argv.slice(2);
const { gala, mic } = JSON.parse(SEED);
const WEB = "http://localhost:5173";
const API = "http://localhost:5000/api";
const PASSWORD = "Demo1234!";
const TECH = "demo.tech@connectsphere.demo";
const TECH2 = "demo.tech2@connectsphere.demo";
const COORDINATOR = "demo.coordinator@connectsphere.demo";
const ORGANISER = "demo.organiser@connectsphere.demo";
const TECH_ONLY = "Only Technical Support Staff can update equipment arrangements.";
const NO_REPLY = "The arrangement was not saved, and the recorded requirements are unchanged. Check your connection and try again.";
const NOTE = "Two lapel mics held at the AV store";
const REQUIREMENTS = `/events/${gala}/equipment-requirements`;
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

async function apiAs(email, url, { method = "GET", body } = {}) {
  const login = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: PASSWORD }),
  });
  const { access_token: token } = await login.json();
  assert.ok(token, `login as ${email} failed with HTTP ${login.status}`);
  const r = await fetch(`${API}${url}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return { status: r.status, body: await r.json() };
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

const shot = (page, name) => page.screenshot({ path: path.join(OUT, name), fullPage: true });
const equipmentUrl = `${WEB}/events/${gala}/equipment`;
const items = (page) => page.getByRole("list", { name: "Recorded equipment requirements" }).getByRole("listitem");
const updatedBy = (email) => new RegExp(`Arrangement updated by ${email.replace(/\./g, "\\.")} on \\S`);

async function arrange(page, name, status, note) {
  await page.getByLabel(`Arrangement status for ${name}`).selectOption(status);
  await page.getByLabel(`Note for ${name}`).fill(note);
  await page.getByRole("button", { name: `Update ${name}` }).click();
}

const tech = await login(TECH);
await tech.goto(equipmentUrl);
await items(tech).first().waitFor();

await check("E2E-01", "Technical Support update the microphones; the page shows the status, note, who and when, and they are still there after a reload (AC1)", async () => {
  assert.equal(await tech.getByText(/Arrangement updated by/).count(), 0, "nothing updated yet");
  await arrange(tech, "2 × Wireless microphone", "being_arranged", NOTE);
  await tech.getByRole("status").getByText("Arrangement status updated to Being arranged.").waitFor();
  await tech.reload();
  await items(tech).first().waitFor();
  const first = await items(tech).first().innerText();
  assert.match(first, /Status: Being arranged/);
  assert.match(first, new RegExp(`Note from Technical Support: ${NOTE}`));
  assert.match(first, updatedBy(TECH));
  const api = await apiAs(TECH, REQUIREMENTS);
  const saved = api.body.requirements.find((r) => r.id === mic);
  assert.equal(saved.arrangement_updated_by.email, TECH);
  assert.ok(saved.arrangement_updated_at, "the time is saved");
  await shot(tech, "01-update-saved-with-who-and-when.png");
});

await check("E2E-02", "A second Technical Support member's update replaces who and when; pressing Update again without a change keeps them (AC1)", async () => {
  const tech2 = await login(TECH2);
  await tech2.goto(equipmentUrl);
  await items(tech2).first().waitFor();
  await arrange(tech2, "2 × Wireless microphone", "unavailable", "Only one lapel mic in stock");
  await tech2.getByRole("status").getByText(/Suitable equipment unavailable/).waitFor();
  assert.match(await items(tech2).first().innerText(), updatedBy(TECH2));
  const before = (await apiAs(TECH, REQUIREMENTS)).body.requirements.find((r) => r.id === mic);

  await tech.reload();
  await items(tech).first().waitFor();
  await tech.getByRole("button", { name: "Update 2 × Wireless microphone" }).click();
  await tech.getByRole("status").getByText("No changes were made to the arrangement for 2 × Wireless microphone.").waitFor();
  assert.match(await items(tech).first().innerText(), updatedBy(TECH2));
  const after = (await apiAs(TECH, REQUIREMENTS)).body.requirements.find((r) => r.id === mic);
  assert.deepEqual(after, before);
  await shot(tech, "02-unchanged-update-keeps-who-and-when.png");
  await tech2.context().close();
});

await check("E2E-03", "The coordinator sees who and when but can't update; their and the organiser's updates are refused and change nothing (AC2)", async () => {
  const coordinator = await login(COORDINATOR);
  await coordinator.goto(equipmentUrl);
  await items(coordinator).first().waitFor();
  assert.equal(await coordinator.getByLabel(/^Arrangement status for/).count(), 0, "no arrangement controls");
  assert.match(await items(coordinator).first().innerText(), updatedBy(TECH2));
  await shot(coordinator, "03-coordinator-sees-but-cannot-update.png");

  const before = await apiAs(TECH, REQUIREMENTS);
  for (const email of [COORDINATOR, ORGANISER]) {
    const refused = await apiAs(email, `${REQUIREMENTS}/${mic}/arrangement`, {
      method: "PATCH", body: { status: "being_arranged", note: "Not my job" },
    });
    assert.equal(refused.status, 403, email);
    assert.deepEqual(refused.body, { error: TECH_ONLY });
  }
  const after = await apiAs(TECH, REQUIREMENTS);
  assert.deepEqual(after.body.requirements, before.body.requirements);
  await coordinator.context().close();
});

await check("E2E-04", "When the coordinator changes the requirement after it was opened, the update is refused and the page shows the new details (AC1)", async () => {
  await tech.reload();
  await items(tech).first().waitFor();
  const edited = await apiAs(COORDINATOR, `${REQUIREMENTS}/${mic}`, {
    method: "PUT",
    body: { equipment_type: "Wireless microphone", quantity: 5, technical_requirements: "Lapel, with spare batteries" },
  });
  assert.equal(edited.status, 200);

  await arrange(tech, "2 × Wireless microphone", "being_arranged", "Two held");
  const alert = tech.getByRole("alert");
  await alert.waitFor();
  assert.match(await alert.innerText(), /has changed this requirement since you opened it, so your update was not saved\. It is now 5 × Wireless microphone/);
  await tech.getByText("5 × Wireless microphone", { exact: true }).waitFor();
  assert.equal(await tech.getByText("2 × Wireless microphone").count(), 0);
  const first = await items(tech).first().innerText();
  assert.match(first, /Status: Requested/);
  assert.doesNotMatch(first, /Two held/);
  await shot(tech, "04-changed-details-refused.png");

  await arrange(tech, "5 × Wireless microphone", "being_arranged", "Five lapel mics held");
  await tech.getByRole("status").getByText(/Being arranged/).waitFor();
  assert.match(await items(tech).first().innerText(), updatedBy(TECH));
});

await check("E2E-05", "When the update can't be saved, the page says the requirements are unchanged, keeps the entry, and Update saves it once the connection is back (AC3)", async () => {
  const pattern = `**/api/events/${gala}/equipment-requirements/*/arrangement`;
  await tech.route(pattern, (route) => route.abort("internetdisconnected"));
  await arrange(tech, "1 × Projector", "unavailable", "Projector booked elsewhere");
  const alert = tech.getByRole("alert");
  await alert.waitFor();
  assert.equal(await alert.innerText(), NO_REPLY);
  const projector = await items(tech).nth(1).innerText();
  assert.match(projector, /Status: Requested/);
  assert.doesNotMatch(projector, /Arrangement updated by/);
  assert.equal(await tech.getByLabel("Arrangement status for 1 × Projector").inputValue(), "unavailable");
  assert.equal(await tech.getByLabel("Note for 1 × Projector").inputValue(), "Projector booked elsewhere");
  const stored = (await apiAs(TECH, REQUIREMENTS)).body.requirements[1];
  assert.equal(stored.status, "requested");
  await shot(tech, "05-save-failed.png");

  await tech.unroute(pattern);
  await tech.getByRole("button", { name: "Update 1 × Projector" }).click();
  await tech.getByRole("status").getByText(/Suitable equipment unavailable/).waitFor();
  assert.equal(await tech.getByRole("alert").count(), 0);
  assert.match(await items(tech).nth(1).innerText(), updatedBy(TECH));
  await shot(tech, "06-saved-on-trying-again.png");
});

await browser.close();
const passed = results.filter(([, r]) => r === "PASS").length;
console.log(`\n${passed}/${results.length} passed`);
process.exit(passed === results.length ? 0 : 1);
