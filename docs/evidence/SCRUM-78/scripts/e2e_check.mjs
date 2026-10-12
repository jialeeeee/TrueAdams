// End-to-end check of SCRUM-78 in the real app (Vite :5173 -> Flask :5000 -> Supabase,
// with Redis running). Not part of the test suite: it needs both servers, Microsoft Edge,
// the SCRUM-62 demo accounts, fresh requests from
// docs/evidence/SCRUM-77/scripts/seed_demo_requests.py, and
// `npm install playwright-core@1.64.0` in the folder you run it from.
// Usage: node e2e_check.mjs <screenshot dir> '<JSON from seed_demo_requests.py>'
import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const [OUT, SEED] = process.argv.slice(2);
const { submitted, under_review: underReview } = JSON.parse(SEED);
const WEB = "http://localhost:5173";
const API = "http://localhost:5000/api";
const PASSWORD = "Demo1234!";
const COORD = "demo.coordinator@connectsphere.demo";
const ORGANISER = "demo.organiser@connectsphere.demo";
const REASON = "The riverside lawn is closed for restoration until March 2027.";
const REQUIRED = "A reason is required to reject this request.";
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

async function rejectViaApi(email, id, reason) {
  const login = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: PASSWORD }),
  });
  const { access_token: token } = await login.json();
  assert.ok(token, `login as ${email} failed with HTTP ${login.status}`);
  const r = await fetch(`${API}/events/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(reason === undefined ? { decision: "reject" } : { decision: "reject", reason }),
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
  await page.waitForURL(`${WEB}/`);
  return page;
}

const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
const reasonBox = (page) => page.getByLabel(/reason or note/i);

await check("E2E-01", "AC2: the organiser, and a coordinator not assigned, cannot reject (HTTP 403)", async () => {
  assert.equal((await rejectViaApi(ORGANISER, submitted.id, REASON)).status, 403);
  assert.equal((await rejectViaApi("demo.coordinator2@connectsphere.demo", submitted.id, REASON)).status, 403);
  const organiser = await login(ORGANISER);
  await organiser.goto(`${WEB}/events/${submitted.id}/review`);
  await organiser.getByRole("alert").waitFor();
  assert.equal(await organiser.getByRole("button", { name: "Reject" }).count(), 0);
  await organiser.context().close();
});

await check("E2E-02", "AC3: the API refuses a missing or blank reason (HTTP 400)", async () => {
  for (const reason of [undefined, "", "   ", " ​"]) {
    const { status, body } = await rejectViaApi(COORD, submitted.id, reason);
    assert.equal(status, 400, JSON.stringify(reason));
    assert.equal(body.error, REQUIRED);
    assert.equal(body.field, "reason");
  }
});

const coord = await login(COORD);

await check("E2E-03", "AC3: pressing Reject with no reason, or only spaces, says a reason is required", async () => {
  await coord.goto(`${WEB}/events/${submitted.id}/review`);
  await coord.getByText("Status: Submitted").waitFor();
  await coord.getByRole("button", { name: "Reject" }).click();
  assert.equal(await coord.getByRole("alert").innerText(), REQUIRED);
  await reasonBox(coord).fill("     ");
  await coord.getByRole("button", { name: "Reject" }).click();
  assert.equal(await coord.getByRole("alert").innerText(), REQUIRED);
  assert.equal(await coord.getByText("Status: Submitted").count(), 1);
  await shot(coord, "01-reason-required");
});

await check("E2E-04", "AC4, AC5: rejecting with a reason shows Rejected and the reason", async () => {
  await reasonBox(coord).fill(`  ${REASON}  `);
  await coord.getByRole("button", { name: "Reject" }).click();
  await coord.getByText("Status: Rejected").waitFor();
  await coord.getByText(`Reason: ${REASON}`).waitFor();
  assert.match(await coord.getByRole("status").innerText(), /You rejected/);
  assert.equal(await coord.getByRole("button", { name: "Reject" }).count(), 0);
  await shot(coord, "02-rejected-confirmation");
});

await check("E2E-05", "AC5: the reason is saved (shown again after reloading, trimmed)", async () => {
  await coord.reload();
  await coord.getByText("Status: Rejected").waitFor();
  await coord.getByText(`Reason: ${REASON}`, { exact: true }).waitFor();
});

await check("E2E-06", "AC1: rejecting it again is refused (HTTP 409)", async () => {
  const { status, body } = await rejectViaApi(COORD, submitted.id, REASON);
  assert.equal(status, 409);
  assert.match(body.error, /This request is rejected/);
});

await check("E2E-07", "AC1: a request under review offers no Reject, and the API refuses it (HTTP 409)", async () => {
  await coord.goto(`${WEB}/events/${underReview.id}/review`);
  await coord.getByText("Status: Under review").waitFor();
  assert.equal(await coord.getByRole("button", { name: "Reject" }).count(), 0);
  const { status, body } = await rejectViaApi(COORD, underReview.id, REASON);
  assert.equal(status, 409);
  assert.match(body.error, /under_review/);
});
await coord.context().close();

await check("E2E-08", "AC6: the organiser sees Rejected and the reason on both of their lists", async () => {
  const organiser = await login(ORGANISER);
  await organiser.getByRole("link", { name: "My event requests", exact: true }).click();
  const item = organiser.locator("li", { hasText: submitted.title });
  await item.waitFor();
  assert.match(await item.innerText(), /Status: Rejected · decided/);
  assert.match(await item.innerText(), new RegExp(`Reason: ${REASON}`));
  await shot(organiser, "03-organiser-my-event-requests");

  await organiser.getByRole("link", { name: "My requests", exact: true }).click();
  const row = organiser.locator("li", { hasText: submitted.title });
  await row.waitFor();
  assert.match(await row.innerText(), /Status: Rejected · decided/);
  assert.match(await row.innerText(), new RegExp(`Reason: ${REASON}`));
  await shot(organiser, "04-organiser-my-requests");
  await organiser.context().close();
});

await browser.close();
const failed = results.filter((r) => r[1] === "FAIL").length;
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
