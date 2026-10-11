// End-to-end check of SCRUM-62 in the real app (Vite :5173 -> Flask :5000 -> Supabase),
// using the [Demo] data from seed_demo_data.py. Not part of the test suite: it needs
// both servers running, Microsoft Edge installed, and `npm install playwright-core@1.64.0`
// in the folder you run it from (kept out of frontend/package.json on purpose).
// Usage: node e2e_check.mjs <screenshot dir>
import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const OUT = process.argv[2];
const WEB = "http://localhost:5173";
const PASSWORD = "Demo1234!";
const COORD = "demo.coordinator@connectsphere.demo";
const results = [];

function check(id, description, fn) {
  return fn().then(
    () => { results.push([id, description, "PASS"]); console.log(`PASS ${id} ${description}`); },
    (e) => { results.push([id, description, "FAIL"]); console.log(`FAIL ${id} ${description}\n  ${e.message}`); },
  );
}

const browser = await chromium.launch({ channel: "msedge", headless: true });

async function login(email) {
  const context = await browser.newContext({ viewport: { width: 1100, height: 800 } });
  const page = await context.newPage();
  await page.goto(`${WEB}/login`);
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Login" }).click();
  await page.waitForURL(`${WEB}/`);
  return page;
}

const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
const value = (page, label) =>
  page.locator("dt", { hasText: new RegExp(`^${label}$`) }).locator("xpath=following-sibling::dd").innerText();
const items = (page) => page.locator("main, section").first().locator("li");

// Another coordinator's event, to try opening it directly.
const other = await login("demo.coordinator2@connectsphere.demo");
await other.getByRole("link", { name: "My managed events", exact: true }).click();
const otherHref = await other.getByRole("link", { name: "[Demo] Product Launch" }).getAttribute("href");
await other.context().close();

const page = await login(COORD);

await check("E2E-01", "AC1: nav link opens the list with name, proposed date and status, soonest first", async () => {
  await page.getByRole("link", { name: "My managed events", exact: true }).click();
  await page.getByRole("heading", { name: "My managed events" }).waitFor();
  await page.getByRole("link", { name: "[Demo] Alumni Mixer" }).waitFor();
  const rows = await items(page).allInnerTexts();
  assert.deepEqual(rows.map((r) => r.split("\n").filter(Boolean)), [
    ["[Demo] Winter Networking Night", "Proposed date: 2026-10-30 19:00", "Status: Cancelled"],
    ["[Demo] Alumni Mixer", "Proposed date: 2026-11-20 18:30", "Status: Approved"],
    ["[Demo] Harbour Lights Festival", "Proposed date: 2026-12-12 17:00", "Status: Submitted"],
    ["Not recorded", "Proposed date: Not recorded", "Status: Under review"],
  ]);
  await shot(page, "01-managed-events-list");
});

await check("E2E-02", "AC1: another coordinator's event is not listed", async () => {
  assert.equal(await page.getByText("[Demo] Product Launch").count(), 0);
});

await check("E2E-03", "AC2, AC3: opening an event shows its planning information, status and coordinator", async () => {
  await page.getByRole("link", { name: "[Demo] Harbour Lights Festival" }).click();
  await page.waitForURL(/\/events\/\d+\/planning$/);
  await page.getByRole("heading", { name: "[Demo] Harbour Lights Festival" }).waitFor();
  await page.getByText("Status: Submitted").waitFor();
  await page.getByText(`Coordinator: ${COORD}`).waitFor();
  assert.equal(await page.locator("dt").count(), 16);
  assert.equal(await value(page, "Venue"), "[Demo] Aurora Ballroom, Level 3, Marina Tower, 10 Bayfront Ave");
  assert.equal(await value(page, "Start"), "2026-12-12 17:00");
  assert.equal(await value(page, "Expected attendance"), "350");
  assert.equal(await page.getByText("Not recorded").count(), 0);
  await shot(page, "02-planning-fully-recorded");
});

await check("E2E-04", "AC5: unrecorded planning fields show Not recorded; registration 'No' is shown as No", async () => {
  await page.getByRole("link", { name: "Back to my managed events" }).click();
  await page.getByRole("link", { name: "[Demo] Alumni Mixer" }).click();
  await page.getByRole("heading", { name: "[Demo] Alumni Mixer" }).waitFor();
  await page.getByText("Status: Approved").waitFor();
  for (const label of ["Description", "Venue", "Expected attendance", "Venue requirements",
    "Accessibility needs", "Equipment requirements"]) {
    assert.equal(await value(page, label), "Not recorded", label);
  }
  assert.equal(await value(page, "Attendee registration required"), "No");
  for (const dd of await page.locator("dd").allInnerTexts()) assert.notEqual(dd.trim(), "");
  await shot(page, "03-planning-partly-recorded");
});

await check("E2E-05", "AC5: an event with no name or date opens and shows Not recorded", async () => {
  await page.getByRole("link", { name: "Back to my managed events" }).click();
  await page.getByRole("link", { name: "Not recorded" }).click();
  await page.getByRole("heading", { name: "Not recorded" }).waitFor();
  await page.getByText("Status: Under review").waitFor();
  assert.equal(await value(page, "Start"), "Not recorded");
  for (const dd of await page.locator("dd").allInnerTexts()) assert.notEqual(dd.trim(), "");
  await shot(page, "04-planning-nothing-recorded");
});

await check("E2E-06", "AC2: a cancelled event still opens", async () => {
  await page.getByRole("link", { name: "Back to my managed events" }).click();
  await page.getByRole("link", { name: "[Demo] Winter Networking Night" }).click();
  await page.getByText("Status: Cancelled").waitFor();
});

await check("E2E-07", "Another coordinator's event opened by URL is refused, with no details and no Retry", async () => {
  await page.goto(`${WEB}${otherHref}`);
  await page.getByRole("alert").waitFor();
  assert.match(await page.getByRole("alert").innerText(), /not allowed/i);
  assert.equal(await page.getByRole("button", { name: "Retry" }).count(), 0);
  assert.equal(await page.getByText("[Demo] Product Launch").count(), 0);
  await shot(page, "05-planning-refused");
});

await check("E2E-08", "Load failure shows an error with Retry; Retry loads the list", async () => {
  // The browser cannot reach the API the first time, as if the connection dropped.
  let fail = true;
  await page.route("**/api/events/managed", (route) => (fail ? route.abort() : route.continue()));
  await page.getByRole("link", { name: "My managed events", exact: true }).click();
  await page.getByRole("alert").waitFor();
  assert.match(await page.getByRole("alert").innerText(), /could not be loaded/);
  await shot(page, "06-list-load-failure");
  fail = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await page.getByRole("link", { name: "[Demo] Alumni Mixer" }).waitFor();
  assert.equal(await page.getByRole("alert").count(), 0);
});
await page.context().close();

await check("E2E-09", "AC4: a coordinator with no events sees the empty-state message", async () => {
  const empty = await login("demo.coordinator3@connectsphere.demo");
  await empty.getByRole("link", { name: "My managed events", exact: true }).click();
  await empty.getByText("You have no events assigned to you yet.").waitFor();
  assert.equal(await empty.locator("section li").count(), 0);
  await shot(empty, "07-empty-state");
  await empty.context().close();
});

await check("E2E-10", "A1: a non-coordinator is told the list is for coordinators", async () => {
  const organiser = await login("demo.organiser@connectsphere.demo");
  await organiser.getByRole("link", { name: "My managed events", exact: true }).click();
  await organiser.getByRole("alert").waitFor();
  assert.match(await organiser.getByRole("alert").innerText(), /Only event coordinators/);
  await shot(organiser, "08-non-coordinator-refused");
  await organiser.context().close();
});

await browser.close();
const failed = results.filter((r) => r[2] === "FAIL").length;
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
