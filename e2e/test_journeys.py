"""End-to-end tests: ConnectSphere's critical journeys through the running system.

Week 9: a few end-to-end tests for the critical journeys, through a real browser, with as
few test doubles as practical. These drive the React app (Vite dev server, which proxies
/api to Flask) against the Flask API, a PostgreSQL database seeded by backend/seed_demo.py,
Redis, and the Celery worker and beat. Every step is checked twice: on the page the user
sees, and in the database row it should have changed.

The concurrency checks send genuinely simultaneous HTTP requests. The backend suite can't:
each of its tests runs inside one rolled-back transaction, so a second connection never
sees its rows (SCRUM-45 TC-45-22).

Each test starts from the seeded demo data and touches its own events, so the tests can
run in any order. How to run them, locally and in CI, is in e2e/README.md.

Environment
    DATABASE_URL     the database the API uses (read to check what was saved)
    DEMO_PASSWORD    the password seed_demo.py gave every demo account
    E2E_BASE_URL     the front end (default http://localhost:5173)
    E2E_API_URL      the API (default http://localhost:5000/api)
    E2E_OUTPUT       where screenshots go (default e2e/output)
    E2E_SLOW=1       also run the hold-expiry check, which waits for Celery beat
                     (up to one 5-minute beat interval); CI runs it after merging
"""
import json
import os
import re
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from playwright.sync_api import sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:5173")
API = os.environ.get("E2E_API_URL", "http://localhost:5000/api")
OUTPUT = Path(os.environ.get("E2E_OUTPUT", Path(__file__).parent / "output"))
PASSWORD = os.environ.get("DEMO_PASSWORD", "")
SINGAPORE = timezone(timedelta(hours=8))

# The demo data seed_demo.py adds (its docstring describes the journey).
DRAFT, UNASSIGNED, REVIEW, FESTIVAL, SEMINAR, GALA, EXPO = (
    "[Demo] Draft Workshop", "[Demo] Unassigned Talk", "[Demo] Review Panel",
    "[Demo] Planning Festival", "[Demo] Held Seminar", "[Demo] Ready Gala",
    "[Demo] Confirmed Expo")
AURORA, HARBOUR = "[Demo] Aurora Ballroom", "[Demo] Harbour Room"


def email(who):
    return f"demo.{who}@connectsphere.demo"


def query(sql, *params):
    """One row from the database the API uses."""
    with psycopg2.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()


def event_id(title):
    return query("select id from events where title = %s", title)[0]


def user_id(who):
    return query("select id from users where email = %s", email(who))[0]


def api(method, path, token=None, body=None):
    request = urllib.request.Request(
        API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def token(who):
    status, body = api("POST", "/auth/login", body={"email": email(who), "password": PASSWORD})
    assert status == 200, body
    return body["access_token"]


def together(*calls):
    """Run the calls at the same instant, each on its own thread, and return the results."""
    results = [None] * len(calls)
    barrier = threading.Barrier(len(calls))

    def run(index, call):
        barrier.wait()
        results[index] = call()

    threads = [threading.Thread(target=run, args=pair) for pair in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


class BrowserJourneys(unittest.TestCase):
    """E2E-01 to E2E-10: each role's step of the journey from draft to registration."""

    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 820})
        # A screenshot of where each test ended, kept as evidence and for diagnosis.
        self.addCleanup(self.page.close)
        self.addCleanup(lambda: self.page.screenshot(path=OUTPUT / f"{self.id().split('.')[-1]}.png"))

    def sign_in(self, who, path):
        page = self.page
        page.goto(BASE + "/login")
        page.get_by_placeholder("Email").fill(email(who))
        page.get_by_placeholder("Password").fill(PASSWORD)
        page.get_by_role("button", name="Login").click()
        page.wait_for_url(re.compile(r"^(?!.*/login).*$"))
        page.goto(BASE + path)
        page.wait_for_load_state("networkidle")
        return page

    def expect_text(self, text):
        self.page.get_by_text(text).first.wait_for()

    def eventually(self, read, expected, timeout=20):
        """The database reaches `expected` once the page's request has finished; a click
        returns before its request does, so poll rather than read once."""
        deadline = time.monotonic() + timeout
        value = read()
        while value != expected and time.monotonic() < deadline:
            time.sleep(0.25)
            value = read()
        self.assertEqual(value, expected)

    # E2E-01 · CF02, CF03 (SCRUM-28, 29)
    def test_e2e_01_organiser_submits_a_complete_draft(self):
        draft = event_id(DRAFT)
        page = self.sign_in("organiser", f"/events/drafts/{draft}")
        page.get_by_role("button", name="Submit for review").click()
        self.expect_text("Submitted")
        # W705: submitted with its time, and waiting in the Lead's queue with no coordinator.
        self.eventually(lambda: query("select status, submitted_at is not null, coordinator_id "
                                      "from events where id = %s", draft), ("submitted", True, None))

    # E2E-02 · CF05, W705 (SCRUM-80, 81)
    def test_e2e_02_lead_assigns_a_coordinator_to_a_waiting_event(self):
        waiting = event_id(UNASSIGNED)
        page = self.sign_in("lead", f"/events/{waiting}/assign")
        page.get_by_role("combobox").select_option(label=email("coordinator2"))
        page.get_by_role("button", name="Assign coordinator").click()
        self.eventually(lambda: query("select coordinator_id, coordinator_assigned_by_id from events "
                                      "where id = %s", waiting), (user_id("coordinator2"), user_id("lead")))
        told = query("select count(*) from notifications where recipient_id = %s and event_id = %s",
                     user_id("coordinator2"), waiting)[0]
        self.assertEqual(told, 1)

    # E2E-03 · CF04, CF06 (SCRUM-32, 77, 60)
    def test_e2e_03_coordinator_approves_a_submitted_request(self):
        request = event_id(REVIEW)
        page = self.sign_in("coordinator", f"/events/{request}/review")
        page.get_by_role("button", name="Approve").click()
        self.eventually(lambda: query("select status, decided_by_id, decided_at is not null from events "
                                      "where id = %s", request), ("approved", user_id("coordinator"), True))
        told = query("select count(*) from notifications where recipient_id = %s and event_id = %s",
                     user_id("organiser"), request)[0]
        self.assertEqual(told, 1)

    # E2E-04 and E2E-10 · CF13, CF14, CF20 (SCRUM-40, 41)
    def test_e2e_04_venue_staff_approve_a_request_and_the_coordinator_is_told(self):
        festival = event_id(FESTIVAL)
        page = self.sign_in("venue", "/venues/bookings")
        request = page.get_by_role("listitem", name=FESTIVAL).filter(has_text=AURORA)
        request.get_by_text("No conflicts found.").wait_for()
        request.get_by_role("button", name="Approve").click()
        self.eventually(lambda: query(
            "select status, decided_by_id from venue_bookings where event_id = %s and venue_id = "
            "(select id from venues where name = %s)", festival, AURORA), ("confirmed", user_id("venue")))

        page = self.sign_in("coordinator", "/notifications")
        self.expect_text(f'Your venue request for "{FESTIVAL}" at {AURORA}')
        self.assertIn("was approved by", page.inner_text("body"))

    # E2E-05 · CF16, CF17 (SCRUM-43, 44)
    def test_e2e_05_technical_support_reserve_equipment(self):
        festival = event_id(FESTIVAL)
        page = self.sign_in("tech", f"/events/{festival}/equipment-reservations")
        page.get_by_label(re.compile("Quantity of")).first.fill("2")
        page.get_by_role("button", name=re.compile("Reserve for")).first.click()
        self.expect_text("Reserved: 2 of 2")
        self.eventually(lambda: query("select coalesce(sum(quantity), 0) from equipment_reservations "
                                      "where event_id = %s and status = 'reserved'", festival)[0], 2)

    # E2E-06 and E2E-07 · W706, CF06 (SCRUM-90, 91, 93)
    def test_e2e_06_safety_approval_then_the_coordinator_confirms(self):
        gala = event_id(GALA)
        page = self.sign_in("safety", "/events/safety-checks")
        item = page.get_by_role("listitem").filter(has_text=GALA)
        item.get_by_role("button", name="Approve safety check").click()
        item.get_by_text("Safety check approved.").wait_for()
        self.eventually(lambda: query("select safety_decision, safety_decided_by_id from events "
                                      "where id = %s", gala), ("approved", user_id("safety")))

        page = self.sign_in("coordinator", f"/events/{gala}/planning")
        page.get_by_role("button", name="Mark event Confirmed").click()
        self.expect_text("Event confirmed.")
        self.eventually(lambda: query("select status, confirmed_by_id, confirmed_at is not null from events "
                                      "where id = %s", gala), ("confirmed", user_id("coordinator"), True))

    # E2E-08 · CF18 (SCRUM-45, 74)
    def test_e2e_08_attendee_registers_for_a_published_event(self):
        expo = event_id(EXPO)
        page = self.sign_in("attendee3", f"/events/{expo}/register")
        page.get_by_role("button", name="Register").click()
        page.get_by_text(re.compile(r"\bregistered\b", re.I)).first.wait_for()
        self.eventually(lambda: query("select count(*) from registrations where event_id = %s and "
                                      "attendee_id = %s and status = 'registered'", expo, user_id("attendee3"))[0], 1)

    # E2E-09 · CF01 (SCRUM-27, 76)
    def test_e2e_09_a_direct_address_without_the_relationship_is_refused(self):
        gala = event_id(GALA)
        page = self.sign_in("attendee1", f"/events/{gala}/planning")
        self.expect_text("You are not allowed to view this event's planning information.")
        self.assertEqual(page.get_by_role("button", name="Mark event Confirmed").count(), 0)
        self.assertEqual(page.get_by_role("button", name="Cancel event").count(), 0)
        self.assertNotIn(HARBOUR, page.inner_text("body"))


class ConcurrentRequests(unittest.TestCase):
    """CON-01 to CON-04: what only real simultaneous requests and the scheduler can show."""

    # CON-01 · CF18 (SCRUM-45 TC-45-22)
    def test_con_01_two_attendees_take_the_last_place_at_the_same_moment(self):
        festival = event_id(FESTIVAL)
        coordinator = token("coordinator")
        settings = api("GET", f"/events/{festival}/registration-settings", coordinator)[1]
        taken = query("select count(*) from registrations where event_id = %s and status = 'registered'",
                      festival)[0]
        status, body = api("PUT", f"/events/{festival}/registration-settings", coordinator,
                           {"capacity": taken + 1, "opens_at": settings["opens_at"][:16],
                            "closes_at": settings["closes_at"][:16]})
        self.assertEqual(status, 200, body)
        first, second = token("attendee2"), token("attendee3")

        results = together(lambda: api("POST", "/registrations/", first, {"event_id": festival}),
                           lambda: api("POST", "/registrations/", second, {"event_id": festival}))

        self.assertEqual(sorted(status for status, _ in results), [201, 409])
        self.assertEqual([body.get("reason") for status, body in results if status == 409], ["full"])
        self.assertEqual(query("select count(*) from registrations where event_id = %s "
                               "and status = 'registered'", festival)[0], taken + 1)

    # CON-02 · CF18, CF01 (SCRUM-45 AC2, SCRUM-76): an organiser who is also an attendee.
    def test_con_02_one_person_registers_twice_at_the_same_moment(self):
        expo = event_id(EXPO)
        multi = token("multi")

        results = together(lambda: api("POST", "/registrations/", multi, {"event_id": expo}),
                           lambda: api("POST", "/registrations/", multi, {"event_id": expo}))

        self.assertTrue(all(status in (200, 201) for status, _ in results), results)
        self.assertEqual(query("select count(*) from registrations where event_id = %s and "
                               "attendee_id = %s and status = 'registered'", expo, user_id("multi"))[0], 1)

    # CON-03 · CF13, CF14 (SCRUM-41 AC6, TC-41-11/12)
    def test_con_03_two_overlapping_requests_approved_at_the_same_moment(self):
        coordinator, venue = token("coordinator"), token("venue")
        harbour = query("select id from venues where name = %s", HARBOUR)[0]
        ids = []
        for title, start, end in ((FESTIVAL, "10:00", "12:00"), (SEMINAR, "11:00", "13:00")):
            status, body = api("POST", "/venues/bookings", coordinator, {
                "event_id": event_id(title), "venue_id": harbour,
                "start_time": f"2027-01-15T{start}", "end_time": f"2027-01-15T{end}",
                "venue_requirements": "End-to-end concurrency check"})
            self.assertEqual(status, 201, body)
            ids.append(body["booking"]["id"])

        results = together(*(lambda b=b: api("POST", f"/venues/bookings/{b}/approve", venue) for b in ids))

        self.assertEqual(sorted(status for status, _ in results), [200, 409])
        self.assertEqual([body.get("reason") for status, body in results if status == 409], ["conflict"])
        self.assertEqual(query("select count(*) from venue_bookings where id = any(%s) "
                               "and status = 'confirmed'", ids)[0], 1)

    # CON-04 · W704, CF09, CF20 (SCRUM-86 TC-86-25, TC-86-36)
    @unittest.skipUnless(os.environ.get("E2E_SLOW") == "1",
                         "Waits up to one Celery beat interval (5 minutes); set E2E_SLOW=1.")
    def test_con_04_a_hold_expires_on_its_own_through_beat_and_the_worker(self):
        coordinator, venue = token("coordinator"), token("venue")
        seminar = event_id(SEMINAR)
        aurora = query("select id from venues where name = %s", AURORA)[0]
        status, body = api("POST", "/venues/bookings", coordinator, {
            "event_id": seminar, "venue_id": aurora, "start_time": "2027-01-20T09:00",
            "end_time": "2027-01-20T11:00", "venue_requirements": "End-to-end hold expiry check"})
        self.assertEqual(status, 201, body)
        booking = body["booking"]["id"]
        expires = (datetime.now(SINGAPORE) + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M")
        status, body = api("POST", f"/venues/bookings/{booking}/hold", venue, {"expires_at": expires})
        self.assertEqual(status, 200, body)

        deadline = time.monotonic() + 11 * 60
        while time.monotonic() < deadline:
            if query("select status from venue_bookings where id = %s", booking)[0] == "expired":
                break
            time.sleep(10)

        self.assertEqual(query("select status from venue_bookings where id = %s", booking)[0], "expired")
        told = query("select count(*) from notifications where event_id = %s and recipient_id = %s "
                     "and kind = 'venue_hold_expired'", seminar, user_id("coordinator"))[0]
        self.assertEqual(told, 1)


if __name__ == "__main__":
    unittest.main()
