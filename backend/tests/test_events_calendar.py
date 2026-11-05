"""CF09 "Coordinators and Venue and Technical Support Staff also need one calendar showing
all events, for planning."

Each test names the case it automates in docs/test-cases/CF09-events-calendar.md (TC-CF09-xx).

Endpoint (JWT required, else 401; the User row is loaded on every request)
    GET /api/venues/calendar?from=YYYY-MM-DD[&to=YYYY-MM-DD]   (at most 31 days)
        200 {"from", "to", "events": [{"id", "title", "status", "start_time", "end_time",
             "venues": [{"id", "name", "booking_status", "start_time", "end_time"}],
             "coordinator": {"id", "email"} | null, "managed"}], "message"}
        403 not a coordinator, Venue Staff or Technical Support Staff
        400 a bad range; 503 {"retryable": true}

"Now" is fixed at NOW (Singapore time).
"""

from datetime import datetime
from unittest import mock

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app.models import Event, VenueBooking
from app.venues import routes as venue_routes
from tests.base import AppTestCase

NOW = datetime(2027, 5, 1, 9, 0)
URL = "/api/venues/calendar"
RANGE = "?from=2027-06-10&to=2027-06-12"


def at(day, hour, minute=0):
    return datetime(2027, 6, day, hour, minute)


class CalendarTestCase(AppTestCase):
    """EC-SEED."""

    def setUp(self):
        super().setUp()
        roles = {"alice": "coordinator", "ben": "coordinator", "gus": "venue_staff",
                 "hana": "tech_staff", "dana": "organiser", "farah": "attendee",
                 "lena": "coordinator_lead", "sam": "safety_officer", "admin": "admin"}
        self.users = {key: self.make_user(role=role) for key, role in roles.items()}
        self.hall = self.make_venue(name="Calendar Hall")
        self.annex = self.make_venue(name="Calendar Annex")
        self.garden = self.make_venue(name="Calendar Garden")
        self.events = {
            "E1": self.event("Harbour Talk", "approved", "alice", at(10, 10), at(10, 12)),
            "E2": self.event("Night Market", "confirmed", "ben", at(11, 22), at(12, 2)),
            "E3": self.event("Book Fair", "submitted", None, at(12, 9), at(12, 17)),
            "E4": self.event("Film Night", "under_review", "ben", at(12, 19), at(12, 21)),
        }
        self.left_out = [
            self.event("Draft", "draft", "alice", at(10, 9), at(10, 10)),
            self.event("Rejected", "rejected", "alice", at(10, 9), at(10, 10)),
            self.event("Cancelled", "cancelled", "alice", at(10, 9), at(10, 10)),
            self.event("Later", "approved", "alice", at(20, 9), at(20, 10)),
            # Half-open: ending as the range starts, or starting as it ends, isn't in it.
            self.event("Ends at the start", "approved", "alice", at(9, 22), at(10, 0)),
            self.event("Starts at the end", "approved", "alice", at(13, 0), at(13, 2)),
        ]
        e1 = self.events["E1"]
        self.book(e1, self.hall, "confirmed", at(10, 10), at(10, 12))
        self.book(e1, self.annex, "tentative", at(10, 9), at(10, 11),
                  hold_expires_at=datetime(2027, 6, 1, 12, 0))
        self.book(e1, self.garden, "pending", at(10, 11), at(10, 12))
        for status in ("rejected", "cancelled", "replaced", "expired"):
            self.book(e1, self.garden, status, at(10, 10), at(10, 12))
        self.book(e1, self.annex, "tentative", at(10, 10), at(10, 12), hold_expires_at=NOW)
        clock = mock.patch.object(venue_routes, "singapore_now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def event(self, title, status, coordinator, start, end):
        row = Event(title=title, status=status, organiser_id=self.users["dana"].id,
                    coordinator_id=self.users[coordinator].id if coordinator else None,
                    start_time=start, end_time=end)
        self.db.session.add(row)
        self.db.session.commit()
        return row

    def book(self, event, venue, status, start, end, **extra):
        self.db.session.add(VenueBooking(
            event_id=event.id, venue_id=venue.id, status=status, start_time=start,
            end_time=end, venue_requirements="x", requested_by_id=self.users["alice"].id,
            **extra))
        self.db.session.commit()

    def calendar(self, query=RANGE, user="alice", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[user])
        return self.client.get(f"{URL}{query}", headers=headers)

    def loaded(self, query=RANGE, user="alice"):
        response = self.calendar(query, user)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def ours(self, body):
        """Only the events this test created: real data may be present (AGENTS.md)."""
        ids = {event.id for event in self.events.values()}
        ids |= {event.id for event in self.left_out}
        return [item for item in body["events"] if item["id"] in ids]


class ContentTests(CalendarTestCase):
    # TC-CF09-01 · A2, A4
    def test_tc_cf09_01_every_event_with_a_plan_in_the_range_soonest_first(self):
        body = self.loaded()

        self.assertEqual((body["from"], body["to"]), ("2027-06-10", "2027-06-12"))
        self.assertEqual([item["title"] for item in self.ours(body)],
                         ["Harbour Talk", "Night Market", "Book Fair", "Film Night"])
        e1 = self.ours(body)[0]
        self.assertEqual((e1["status"], e1["start_time"], e1["end_time"]),
                         ("approved", "2027-06-10T10:00:00", "2027-06-10T12:00:00"))
        self.assertEqual(e1["coordinator"], {"id": self.users["alice"].id,
                                             "email": self.users["alice"].email})
        self.assertIsNone(self.ours(body)[2]["coordinator"])

    # TC-CF09-02 · A3
    def test_tc_cf09_02_each_event_lists_the_venues_booked_or_requested_for_it(self):
        [e1] = [item for item in self.loaded()["events"] if item["id"] == self.events["E1"].id]

        self.assertEqual([(v["name"], v["booking_status"], v["start_time"]) for v in e1["venues"]], [
            ("Calendar Annex", "tentative", "2027-06-10T09:00:00"),
            ("Calendar Hall", "confirmed", "2027-06-10T10:00:00"),
            ("Calendar Garden", "pending", "2027-06-10T11:00:00"),
        ])

    # TC-CF09-03 · A2
    def test_tc_cf09_03_an_event_running_into_the_range_is_shown(self):
        body = self.loaded("?from=2027-06-12")

        self.assertEqual([item["title"] for item in self.ours(body)],
                         ["Night Market", "Book Fair", "Film Night"])

    # TC-CF09-04 · A4
    def test_tc_cf09_04_only_the_events_own_coordinator_may_open_it(self):
        def managed(user):
            return {item["title"]: item["managed"] for item in self.ours(self.loaded(user=user))}

        self.assertEqual(managed("alice"), {"Harbour Talk": True, "Night Market": False,
                                            "Book Fair": False, "Film Night": False})
        self.assertEqual(set(managed("gus").values()), {False})

    # TC-CF09-05 · A2
    def test_tc_cf09_05_no_events_says_so(self):
        body = self.loaded("?from=2031-01-01")

        self.assertEqual(self.ours(body), [])
        if not body["events"]:
            self.assertEqual(body["message"], "No events are planned for these dates.")


class AccessTests(CalendarTestCase):
    # TC-CF09-06 · A1
    def test_tc_cf09_06_coordinators_venue_and_tech_staff_only(self):
        for user in ("alice", "gus", "hana"):
            with self.subTest(allowed=user):
                self.assertEqual(self.calendar(user=user).status_code, 200)
        for user in ("dana", "farah", "lena", "sam", "admin"):
            with self.subTest(denied=user):
                response = self.calendar(user=user)
                self.assertEqual(response.status_code, 403, response.get_json())
                self.assertNotIn("events", response.get_json())
        self.assertEqual(self.calendar(headers={}).status_code, 401)

    # TC-CF09-06 · A1 (CF01)
    def test_tc_cf09_06_the_role_may_be_an_additional_one(self):
        self.users["dana"].additional_roles = ["tech_staff"]
        self.db.session.commit()

        self.assertEqual(self.calendar(user="dana").status_code, 200)


class RangeTests(CalendarTestCase):
    # TC-CF09-07 · A5
    def test_tc_cf09_07_the_range_follows_the_venue_calendars_rules(self):
        for query in ("", "?from=10-06-2027", "?from=2027-06-12&to=2027-06-10",
                      "?from=2027-06-01&to=2027-07-02"):
            with self.subTest(query=query):
                response = self.calendar(query)
                self.assertEqual(response.status_code, 400, response.get_json())
                self.assertTrue(response.get_json()["error"])
        self.assertEqual(self.calendar("?from=2027-06-01&to=2027-07-01").status_code, 200)

    # TC-CF09-08 · A6
    def test_tc_cf09_08_a_failed_load_is_an_error_not_an_empty_calendar(self):
        def fail(conn, cursor, statement, parameters, context, executemany):
            if "FROM venue_bookings" in statement:
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            response = self.calendar()
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        self.assertEqual(response.status_code, 503, response.get_json())
        self.assertEqual(response.get_json(), {
            "error": "The events calendar could not be loaded. Please try again.",
            "retryable": True})
