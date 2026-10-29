// End-to-end check of SCRUM-96 in the real app (Vite :5173 -> Flask :5000 -> PostgreSQL).
// Not part of the test suite: it needs both servers, Microsoft Edge, fresh events from
// seed_demo_tech_view.py (a local database), and `npm install playwright-core@1.64.0` in
// the folder you run it from.
// Usage: node e2e_check.mjs <screenshot dir> '<JSON from seed_demo_tech_view.py>'
import assert from "node:assert/strict";
import path from "node:path";
import { chromium } from "playwright-core";

const [OUT, SEED] = process.argv.slice(2);
const { gala, draft } = JSON.parse(SEED);
const WEB = "http://localhost:5173";
const API = "http://localhost:5000/api";
const PASSWORD = "Demo1234!";
const TECH = "demo.tech@connectsphere.demo";
const ORGANISER = "demo.organiser@connectsphere.demo";
const OTHER_COORD = "demo.coordinator2@connectsphere.demo";
const DENIED = "You are not allowed to view this event's equipment requirements.";
const NO_REPLY = "The equipment requirements could not be loaded. Check your connection and try again.";
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
const equipmentUrl = (id) => `${WEB}/events/${id}/equipment`;
const items = (page) => page.getByRole("list", { name: "Recorded equipment requirements" }).getByRole("listitem");
const tech = await login(TECH);

await check("E2E-01", "Technical Support open the gala from Equipment requests and see each type, quantity and technical requirements (AC1)", async () => {
  await tech.getByRole("link", { name: "Equipment requests" }).click();
  // By ID, since every seeding run adds events with the same titles.
  const link = tech.locator(`a[href="/events/${gala}/equipment"]`);
  await link.waitFor();
  await link.click();
  await tech.waitForURL(equipmentUrl(gala));
  await items(tech).first().waitFor();
  const texts = await items(tech).allInnerTexts();
  assert.equal(texts.length, 2);
  assert.match(texts[0], /2 × Wireless microphone/);
  assert.match(texts[0], /Technical requirements: Lapel, with spare batteries/);
  assert.match(texts[0], /Status: Requested/);
  assert.match(texts[1], /1 × Projector/);
  assert.match(texts[1], /Technical requirements: None recorded/);
  await tech.getByText("From the organiser's request: Two wireless microphones and a projector").waitFor();
  assert.equal(await tech.getByLabel("Equipment type").count(), 0, "no record form for Technical Support");
  await shot(tech, "01-tech-sees-requirements.png");
});

await check("E2E-02", "Technical Support record an arrangement and see it when they open the event again (AC1, story)", async () => {
  await tech.getByLabel("Arrangement status for 2 × Wireless microphone").selectOption("being_arranged");
  await tech.getByLabel("Note for 2 × Wireless microphone").fill(NOTE);
  await tech.getByRole("button", { name: "Update 2 × Wireless microphone" }).click();
  await tech.getByRole("status").getByText(/Being arranged/).waitFor();
  await tech.reload();
  await items(tech).first().waitFor();
  const first = await items(tech).first().innerText();
  assert.match(first, /Status: Being arranged/);
  assert.match(first, new RegExp(`Note from Technical Support: ${NOTE}`));
  await shot(tech, "02-arrangement-recorded.png");
});

await check("E2E-03", "The organiser and another coordinator are refused without Retry or details, and nothing changes (AC2)", async () => {
  const before = await apiAs(TECH, `/events/${gala}/equipment-requirements`);
  assert.equal(before.status, 200);
  for (const email of [ORGANISER, OTHER_COORD]) {
    const page = await login(email);
    await page.goto(equipmentUrl(gala));
    const alert = page.getByRole("alert");
    await alert.waitFor();
    assert.equal(await alert.innerText(), DENIED);
    assert.equal(await page.getByRole("button", { name: "Retry" }).count(), 0);
    assert.equal(await page.getByText("Charity Gala").count(), 0);
    assert.equal(await page.getByText("Wireless microphone").count(), 0);
    if (email === ORGANISER) await shot(page, "03-organiser-refused.png");
    const api = await apiAs(email, `/events/${gala}/equipment-requirements`);
    assert.equal(api.status, 403);
    assert.deepEqual(api.body, { error: DENIED });
    await page.context().close();
  }
  const after = await apiAs(TECH, `/events/${gala}/equipment-requirements`);
  assert.deepEqual(after.body.requirements, before.body.requirements);
});

await check("E2E-04", "A draft's equipment page is \"Event not found.\" for Technical Support, without its title or note (AC1, AC2)", async () => {
  await tech.goto(equipmentUrl(draft));
  const alert = tech.getByRole("alert");
  await alert.waitFor();
  assert.equal(await alert.innerText(), "Event not found.");
  assert.equal(await tech.getByRole("button", { name: "Retry" }).count(), 0);
  assert.equal(await tech.getByText("Harbour Lights").count(), 0);
  assert.equal(await tech.getByText(/Smoke machine/).count(), 0);
  const api = await apiAs(TECH, `/events/${draft}/equipment-requirements`);
  assert.equal(api.status, 404);
  assert.deepEqual(api.body, { error: "Event not found." });
  await shot(tech, "04-draft-not-found.png");
});

await check("E2E-05", "When the requirements can't be loaded, the page says why and Retry loads them (AC3)", async () => {
  const pattern = `**/api/events/${gala}/equipment-requirements`;
  await tech.route(pattern, (route) => route.abort("internetdisconnected"));
  await tech.goto(equipmentUrl(gala));
  const alert = tech.getByRole("alert");
  await alert.waitFor();
  assert.equal(await alert.innerText(), NO_REPLY);
  assert.equal(await tech.getByRole("list", { name: "Recorded equipment requirements" }).count(), 0);
  await shot(tech, "05-load-failed.png");
  await tech.unroute(pattern);
  await tech.getByRole("button", { name: "Retry" }).click();
  await items(tech).first().waitFor();
  assert.equal(await items(tech).count(), 2);
  assert.equal(await tech.getByRole("alert").count(), 0);
  await shot(tech, "06-after-retry.png");
});

await browser.close();
const passed = results.filter(([, r]) => r === "PASS").length;
console.log(`\n${passed}/${results.length} passed`);
process.exit(passed === results.length ? 0 : 1);
