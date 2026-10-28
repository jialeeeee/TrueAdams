// End-to-end check of SCRUM-70 in the real app (Vite :5173 -> Flask :5000 -> PostgreSQL).
// Not part of the test suite: it needs both servers, Microsoft Edge, fresh events from
// seed_demo_change_reviews.py (a local database: the decision columns are not on Supabase
// yet), and `npm install playwright-core@1.64.0` in the folder you run it from.
// Usage: node e2e_check.mjs <screenshot dir> '<JSON from seed_demo_change_reviews.py>'
import assert from "node:assert/strict";
import path from "node:path";
import { chromium } from "playwright-core";

const [OUT, SEED] = process.argv.slice(2);
const { gala, launch, fair, move, grow } = JSON.parse(SEED);
const WEB = "http://localhost:5173";
const API = "http://localhost:5000/api";
const PASSWORD = "Demo1234!";
const ORGANISER = "demo.organiser@connectsphere.demo";
const COORD = "demo.coordinator@connectsphere.demo";
const OTHER_COORD = "demo.coordinator2@connectsphere.demo";
const ATTENDEES = ["demo.attendee1@connectsphere.demo", "demo.attendee2@connectsphere.demo"];
const WITHDRAWN = "demo.attendee3@connectsphere.demo";
const REASON = "The hall only holds 120 people.";
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
const coordinator = await login(COORD);
const reviewUrl = (eventId, requestId) => `${WEB}/events/${eventId}/change-requests/${requestId}`;

await check("E2E-01", "The coordinator finds the request and sees what it affects (AC1, AC2)", async () => {
  await coordinator.getByRole("link", { name: "Change requests to review" }).click();
  // By ID, since every seeding run adds events with the same titles.
  const link = coordinator.locator(`a[href="/events/${gala}/change-requests/${move}"]`);
  await link.waitFor();
  assert.equal(await coordinator.locator(`a[href="/events/${launch}/change-requests/${grow}"]`).count(), 1);
  await link.click();
  await coordinator.waitForURL(reviewUrl(gala, move));
  // allInnerTexts doesn't wait, so wait for the review to load first.
  const list = coordinator.getByRole("list", { name: "Requested changes" });
  await list.waitFor();
  const changes = await list.getByRole("listitem").allInnerTexts();
  assert.deepEqual(changes, ["Start: 2026-12-05 18:00 → 2026-12-06 18:00", "End: 2026-12-05 23:00 → 2026-12-06 23:30"]);
  const venues = coordinator.getByRole("region", { name: "Venue bookings affected" });
  await venues.getByText("[Demo] Grand Ballroom 70, 2026-12-05 18:00 to 2026-12-05 23:00 (Confirmed)").waitFor();
  await coordinator.getByRole("region", { name: "Equipment affected" }).getByText("Wireless microphone × 2 (2 reserved)").waitFor();
  await coordinator.getByRole("region", { name: "Registrations affected" })
    .getByText("2 registered attendees will be told the new date and time.").waitFor();
  await shot(coordinator, "01-review-impact.png");
});

await check("E2E-02", "Another coordinator can't open it (AC1)", async () => {
  const { status, body } = await apiAs(OTHER_COORD, `/events/${gala}/change-requests/${move}`);
  assert.equal(status, 403);
  assert.ok(!JSON.stringify(body).includes("2026-12-06"));
});

await check("E2E-03", "Accepting applies the new times and confirms it (AC3, AC8)", async () => {
  await coordinator.getByRole("button", { name: "Accept" }).click();
  const status = await coordinator.getByRole("status").innerText();
  assert.match(status, /You accepted the change request/);
  assert.match(status, /reserved equipment was released/);
  assert.match(status, /2 registered attendees were told the new date and time/);
  await coordinator.getByText("Status: Accepted").waitFor();
  assert.equal(await coordinator.getByRole("button", { name: "Accept" }).count(), 0);
  // What the change would affect is shown only before deciding.
  assert.equal(await coordinator.getByRole("region", { name: "What this change affects" }).count(), 0);
  await shot(coordinator, "02-accepted.png");
  await coordinator.goto(`${WEB}/events/${gala}/planning`);
  await coordinator.getByText("2026-12-06 18:00").first().waitFor();
  const { body } = await apiAs(COORD, `/events/${gala}/planning`);
  assert.equal(body.start_time, "2026-12-06T18:00:00");
  assert.equal(body.end_time, "2026-12-06T23:30:00");
  await shot(coordinator, "03-planning-new-times.png");
});

await check("E2E-04", "Registered attendees are told the new details; the one who withdrew isn't (AC9)", async () => {
  for (const email of ATTENDEES) {
    const { body } = await apiAs(email, "/notifications/");
    const note = body.notifications.find((n) => n.kind === "event_details_changed" && n.event_id === gala);
    assert.ok(note, `${email} was not told`);
    for (const text of ["[Demo] Charity Gala 70", "2026-12-06 18:00", "2026-12-06 23:30", "[Demo] Grand Ballroom 70"]) {
      assert.ok(note.message.includes(text), `${email}'s notification lacks ${text}`);
    }
  }
  const { body } = await apiAs(WITHDRAWN, "/notifications/");
  assert.equal(body.notifications.filter((n) => n.event_id === gala).length, 0);
});

await check("E2E-05", "A rejection needs a reason of at most 500 characters (AC4)", async () => {
  await coordinator.goto(reviewUrl(launch, grow));
  await coordinator.getByRole("button", { name: "Reject" }).click();
  await coordinator.getByText("A reason is required to reject this change request.").waitFor();
  await coordinator.getByLabel(/Reason for rejecting/).fill("x".repeat(501));
  await coordinator.getByText("501 / 500 characters").waitFor();
  assert.equal(await coordinator.getByRole("button", { name: "Reject" }).isDisabled(), true);
  await shot(coordinator, "04-reason-too-long.png");
  const { body } = await apiAs(COORD, `/events/${launch}/change-requests/${grow}`);
  assert.equal(body.request.status, "pending_review");
});

await check("E2E-06", "A failed save keeps the reason and changes nothing (AC6)", async () => {
  await coordinator.getByLabel(/Reason for rejecting/).fill(REASON);
  await coordinator.route("**/decision", (route) => route.abort());
  await coordinator.getByRole("button", { name: "Reject" }).click();
  assert.match(await coordinator.getByRole("alert").innerText(), /was not saved/);
  assert.equal(await coordinator.getByLabel(/Reason for rejecting/).inputValue(), REASON);
  await shot(coordinator, "05-save-failed.png");
  await coordinator.unroute("**/decision");
  const { body } = await apiAs(COORD, `/events/${launch}/change-requests/${grow}`);
  assert.equal(body.request.status, "pending_review");
});

await check("E2E-07", "Rejecting with a reason; the organiser sees the outcome (AC3, AC4, AC7)", async () => {
  await coordinator.getByRole("button", { name: "Reject" }).click();
  await coordinator.getByText("Status: Rejected").waitFor();
  await coordinator.getByText(`Reason: ${REASON}`).waitFor();
  const organiser = await login(ORGANISER);
  await organiser.goto(`${WEB}/events/${launch}/change-request`);
  const outcome = organiser.getByRole("region", { name: "Your last change request" });
  await outcome.getByText("Status: Rejected").waitFor();
  await outcome.getByText(`Reason: ${REASON}`).waitFor();
  await shot(organiser, "06-organiser-sees-rejection.png");
  const { body } = await apiAs(ORGANISER, "/notifications/");
  const kinds = body.notifications.filter((n) => [gala, launch].includes(n.event_id)).map((n) => n.kind);
  assert.ok(kinds.includes("change_request_accepted"), "no acceptance notification");
  assert.ok(kinds.includes("change_request_rejected"), "no rejection notification");
});

await check("E2E-08", "An event waiting for a coordinator says so to the organiser (AC5)", async () => {
  const organiser = await login(ORGANISER);
  await organiser.goto(`${WEB}/events/${fair}/change-request`);
  await organiser.getByText(/waiting for a coordinator/).waitFor();
  assert.equal(await organiser.getByRole("button", { name: "Submit change request" }).count(), 0);
  await shot(organiser, "07-waiting-for-coordinator.png");
});

await browser.close();
const passed = results.filter(([, r]) => r === "PASS").length;
console.log(`\n${passed}/${results.length} passed`);
process.exit(passed === results.length ? 0 : 1);
