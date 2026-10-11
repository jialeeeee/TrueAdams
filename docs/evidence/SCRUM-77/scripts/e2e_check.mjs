// End-to-end check of SCRUM-77 in the real app (Vite :5173 -> Flask :5000 -> Supabase).
// Not part of the test suite: it needs both servers running, Microsoft Edge, the
// SCRUM-62 demo accounts, and `npm install playwright-core@1.64.0` in the folder you run
// it from. Usage: node e2e_check.mjs <screenshot dir> '<JSON from seed_demo_requests.py>'
import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const [OUT, SEED] = process.argv.slice(2);
const seeded = JSON.parse(SEED);
const WEB = "http://localhost:5173";
const API = "http://localhost:5000/api";
const PASSWORD = "Demo1234!";
const COORD = "demo.coordinator@connectsphere.demo";
const ORGANISER = "demo.organiser@connectsphere.demo";
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

async function token(email) {
  const r = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: PASSWORD }),
  });
  return (await r.json()).access_token;
}

async function approveViaApi(email, id) {
  const r = await fetch(`${API}/events/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${await token(email)}` },
    body: JSON.stringify({ decision: "approve" }),
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
const { submitted, under_review: underReview } = seeded;

const coord = await login(COORD);

await check("E2E-01", "AC1: a submitted request offers Approve to its coordinator", async () => {
  await coord.goto(`${WEB}/events/${submitted.id}/review`);
  await coord.getByRole("heading", { name: `Review: ${submitted.title}` }).waitFor();
  await coord.getByText("Status: Submitted").waitFor();
  assert.equal(await coord.getByRole("button", { name: "Approve" }).isEnabled(), true);
  await shot(coord, "01-submitted-request-before-approval");
});

await check("E2E-02", "AC3: approving changes the status to Approved and confirms it", async () => {
  await coord.getByRole("button", { name: "Approve" }).click();
  await coord.getByText("Status: Approved").waitFor();
  assert.match(await coord.getByRole("status").innerText(), /You approved/);
  assert.match(await coord.getByRole("status").innerText(), new RegExp(ORGANISER));
  assert.equal(await coord.getByRole("button", { name: "Approve" }).count(), 0);
  await shot(coord, "02-approved-confirmation");
});

await check("E2E-03", "AC3: the approval is saved (still Approved after reloading)", async () => {
  await coord.reload();
  await coord.getByText("Status: Approved").waitFor();
  await coord.getByText(`Decided by ${COORD}`).waitFor();
});

await check("E2E-04", "AC1: approving it again is refused (HTTP 409)", async () => {
  const { status, body } = await approveViaApi(COORD, submitted.id);
  assert.equal(status, 409);
  assert.match(body.error, /only submitted requests/);
});

await check("E2E-05", "AC1: a request under review offers no Approve, and the API refuses it", async () => {
  await coord.goto(`${WEB}/events/${underReview.id}/review`);
  await coord.getByText("Status: Under review").waitFor();
  assert.equal(await coord.getByRole("button", { name: "Approve" }).count(), 0);
  await shot(coord, "03-under-review-no-approve");
  const { status, body } = await approveViaApi(COORD, underReview.id);
  assert.equal(status, 409);
  assert.match(body.error, /under_review/);
});
await coord.context().close();

await check("E2E-06", "AC2: the organiser cannot open the review page or approve", async () => {
  const organiser = await login(ORGANISER);
  await organiser.goto(`${WEB}/events/${underReview.id}/review`);
  await organiser.getByRole("alert").waitFor();
  assert.match(await organiser.getByRole("alert").innerText(), /assigned coordinator/);
  assert.equal(await organiser.getByRole("button", { name: "Approve" }).count(), 0);
  await shot(organiser, "04-organiser-refused");
  await organiser.context().close();
  assert.equal((await approveViaApi(ORGANISER, underReview.id)).status, 403);
});

await check("E2E-07", "AC2: a coordinator not assigned to the request cannot approve", async () => {
  const other = await login("demo.coordinator2@connectsphere.demo");
  await other.goto(`${WEB}/events/${underReview.id}/review`);
  await other.getByRole("alert").waitFor();
  assert.equal(await other.getByRole("button", { name: "Approve" }).count(), 0);
  await other.context().close();
  assert.equal((await approveViaApi("demo.coordinator2@connectsphere.demo", underReview.id)).status, 403);
});

await check("E2E-08", "AC4: the organiser sees Approved, with who decided, on My event requests", async () => {
  const organiser = await login(ORGANISER);
  await organiser.getByRole("link", { name: "My event requests", exact: true }).click();
  const item = organiser.locator("li", { hasText: submitted.title });
  await item.waitFor();
  assert.match(await item.innerText(), /Status: Approved · decided/);
  assert.match(await item.innerText(), new RegExp(`Decided by ${COORD}`));
  await item.scrollIntoViewIfNeeded();
  await shot(organiser, "05-organiser-my-event-requests");

  await organiser.getByRole("link", { name: "My requests", exact: true }).click();
  const row = organiser.locator("li", { hasText: submitted.title });
  await row.waitFor();
  assert.match(await row.innerText(), /Status: Approved · decided/);
  await shot(organiser, "06-organiser-my-requests");
  await organiser.context().close();
});

await browser.close();
const failed = results.filter((r) => r[1] === "FAIL").length;
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
