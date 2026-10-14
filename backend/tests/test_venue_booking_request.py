"""Tests for SCRUM-39 "Submit a Venue Booking Request".

Each test names the case it automates from
docs/test-cases/SCRUM-39-venue-booking-request.md (TC-39-xx) and the acceptance
criteria it checks. Assumptions A1-A10 and questions Q1-Q8 are defined there.

Model (db/venue_booking_requests.sql): new VenueBooking columns
    venue_requirements  Text, the requirements Venue Staff assess the request against
    requested_by_id     FK users.id, the coordinator who made the request
    plus a unique index allowing one `pending` booking per event (A6).
    The existing `created_at` is the time of the request.

Endpoints
    POST /api/venues/bookings   body {"event_id", "venue_id", "start_time", "end_time",
                                      "venue_requirements"}   (times "YYYY-MM-DDTHH:MM")
        201 {"message", "booking"}
        401 session · 403 not a coordinator / not this event's coordinator
        400 {"error", "fields": {field: problem}} missing or invalid details (all at once)
        404 unknown event / venue · 409 event not approved, or a request already pending
        503 {"error", "retryable": true} if saving fails
    GET  /api/venues/bookings   200 {"bookings": [booking], "message"}  Venue Staff only;
                                pending requests, oldest first
    booking = {"id", "status", "event": {"id", "title", "expected_attendance"},
               "venue": {"id", "name", "location"}, "start_time", "end_time",
               "venue_requirements", "requested_by": {"id", "email"}, "requested_at"}

Real bookings may exist in the shared database, so list assertions look only at this
test's own rows.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.models import Event, VenueBlock, VenueBooking
from tests import seed_data
from tests.base import AppTestCase

BOOKINGS_URL = "/api/venues/bookings"
MAX_REQUIREMENTS = 5000

# VB-SEED events. `organiser` and `coordinator` refer to seed_data.USERS keys.
EVENTS = {
    "E1": {"title": "Harbour Lights Festival", "organiser": "dana", "coordinator": "alice",
           "status": "approved", "start_time": datetime(2027, 3, 12, 17, 0),
           "end_time": datetime(2027, 3, 12, 22, 0), "expected_attendance": 250,
           "venue_requirements": "Open-air waterfront space for 250"},
    "E2": {"title": "Winter Networking Night", "organiser": "dana", "coordinator": "ben",
           "status": "approved", "start_time": datetime(2027, 4, 3, 18, 0),
           "end_time": datetime(2027, 4, 3, 21, 0), "expected_attendance": 80,
           "venue_requirements": "Theatre layout for 80"},
    "E3": {"title": "Spring Garden Party", "organiser": "dana", "coordinator": "alice",
           "status": "submitted", "start_time": datetime(2027, 3, 20, 15, 0),
           "end_time": datetime(2027, 3, 20, 18, 0)},
    "E4": {"title": "Tech Summit Draft", "organiser": "dana", "coordinator": "alice",
           "status": "draft"},
    "E5": {"title": "Rooftop Cinema", "organiser": "dana", "coordinator": "alice",
           "status": "rejected", "start_time": datetime(2027, 3, 5, 19, 0),
           "end_time": datetime(2027, 3, 5, 22, 0)},
    "E6": {"title": "Cancelled Meetup", "organiser": "dana", "coordinator": "alice",
           "status": "cancelled", "start_time": datetime(2027, 3, 6, 19, 0),
           "end_time": datetime(2027, 3, 6, 21, 0)},
}

REQUIREMENTS = "Open-air waterfront space for 250, stage power"


class BookingRequestTestCase(AppTestCase):
    """Inserts VB-SEED and wraps the booking request endpoints."""

    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.venues = self.seed_venues(seed_data.VENUES)
        self.events = {}
        for key, row in EVENTS.items():
            fields = {k: v for k, v in row.items() if k not in ("organiser", "coordinator")}
            event = Event(organiser_id=self.users[row["organiser"]].id,
                          coordinator_id=self.users[row["coordinator"]].id, **fields)
            self.db.session.add(event)
            self.events[key] = event
        self.db.session.commit()

    # ---------- Requests ----------

    def valid(self, event="E1", venue="fully_recorded", **overrides):
        """The valid request for E1 (TC docs), with any fields replaced or removed."""
        body = {
            "event_id": self.events[event].id,
            "venue_id": self.venues[venue].id,
            "start_time": "2027-03-12T16:00",
            "end_time": "2027-03-12T22:30",
            "venue_requirements": REQUIREMENTS,
        }
        body.update(overrides)
        return {k: v for k, v in body.items() if v is not ...}

    def submit(self, body=None, as_user="alice", headers=None, **kwargs):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        if "data" not in kwargs:
            kwargs["json"] = self.valid() if body is None else body
        return self.client.post(BOOKINGS_URL, headers=headers, **kwargs)

    def listed(self, as_user="gus"):
        return self.client.get(BOOKINGS_URL, headers=self.auth_headers(self.users[as_user]))

    # ---------- Reading what was saved ----------

    def bookings_for(self, event="E1"):
        self.db.session.expire_all()
        return (VenueBooking.query.filter_by(event_id=self.events[event].id)
                .order_by(VenueBooking.id).all())

    def own_booking_count(self):
        self.db.session.expire_all()
        ids = [e.id for e in self.events.values()]
        return VenueBooking.query.filter(VenueBooking.event_id.in_(ids)).count()

    def seed_booking(self, event, venue, status, start, end):
        booking = VenueBooking(event_id=self.events[event].id if event else None,
                               venue_id=self.venues[venue].id, status=status,
                               start_time=start, end_time=end)
        self.db.session.add(booking)
        self.db.session.commit()
        return booking

    # ---------- Assertions ----------

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        return body

    def assert_fields(self, response, *fields):
        body = self.assert_error(response, 400)
        self.assertIsInstance(body.get("fields"), dict, body)
        for field in fields:
            with self.subTest(field=field):
                self.assertIn(field, body["fields"])
                self.assertTrue(body["fields"][field].strip())
        return body

    def assert_nothing_saved(self):
        self.assertEqual(self.own_booking_count(), 0)


# ---------- AC1: select an event you coordinate and a venue ----------


class SelectEventAndVenueTests(BookingRequestTestCase):
    # TC-39-01 · AC1, AC2, AC4 — the coordinator requests a venue for an approved event.
    def test_coordinator_requests_a_venue_for_an_approved_event(self):
        started = datetime.utcnow()

        response = self.submit()

        finished = datetime.utcnow()
        self.assertEqual(response.status_code, 201, response.get_json())
        body = response.get_json()
        message = body["message"]
        self.assertIn("Aurora Ballroom", message)
        self.assertIn("Harbour Lights Festival", message)
        self.assertIn("pending", message.lower())
        [saved] = self.bookings_for("E1")
        self.assertEqual(
            (saved.status, saved.venue_id, saved.start_time, saved.end_time,
             saved.venue_requirements, saved.requested_by_id),
            ("pending", self.venues["fully_recorded"].id, datetime(2027, 3, 12, 16, 0),
             datetime(2027, 3, 12, 22, 30), REQUIREMENTS, self.users["alice"].id),
        )
        self.assertTrue(started <= saved.created_at <= finished)
        self.assertEqual(body["booking"]["id"], saved.id)
        self.assertEqual(body["booking"]["status"], "pending")

    # TC-39-02 · AC1 (A1/Q1) — a coordinator who does not coordinate the event is refused.
    def test_coordinator_who_does_not_coordinate_the_event_is_refused(self):
        for user in ("ben", "chloe"):
            with self.subTest(user=user):
                response = self.submit(as_user=user)
                self.assert_error(response, 403)
                text = response.get_data(as_text=True)
                self.assertNotIn("Harbour Lights Festival", text)
                self.assertNotIn("Open-air waterfront", text)
        self.assert_nothing_saved()

    # TC-39-03 · AC1 — other roles are refused.
    def test_other_roles_are_refused(self):
        for user in ("dana", "gus", "hana", "farah", "admin"):
            with self.subTest(user=user):
                self.assert_error(self.submit(as_user=user), 403)
        self.assert_nothing_saved()

    # TC-39-04 · AC1 — a valid session is required.
    def test_a_valid_session_is_required(self):
        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["alice"].id),
                                      expires_delta=timedelta(seconds=-1))
        sessions = {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                    "deleted user": ghost_headers}
        for label, headers in sessions.items():
            with self.subTest(session=label):
                self.assertEqual(self.submit(headers=headers).status_code, 401)
                self.assertEqual(self.client.get(BOOKINGS_URL, headers=headers).status_code, 401)
        self.assert_nothing_saved()

    # TC-39-05 · AC1, AC3 — unknown event or venue.
    def test_unknown_event_or_venue(self):
        from app.models import Venue

        event_missing = self.submit(self.valid(event_id=self.missing_id(Event)))
        self.assertIn("event", self.assert_error(event_missing, 404)["error"].lower())

        venue_missing = self.submit(self.valid(venue_id=self.missing_id(Venue)))
        self.assertIn("venue", self.assert_error(venue_missing, 404)["error"].lower())
        self.assert_nothing_saved()

    # TC-39-06 · AC1 (A2/Q2) — only approved events can have a venue requested.
    def test_only_approved_events_can_have_a_venue_requested(self):
        for key, status in (("E3", "submitted"), ("E4", "draft"), ("E5", "rejected"),
                            ("E6", "cancelled")):
            with self.subTest(event=key):
                body = self.assert_error(self.submit(self.valid(event=key)), 409)
                self.assertIn(status, body["error"])
        self.assert_nothing_saved()

    # TC-39-07 · AC1 (boundary) — access follows reassignment and role changes.
    def test_access_follows_reassignment_and_role_changes(self):
        alice_headers = self.auth_headers(self.users["alice"])
        ben_headers = self.auth_headers(self.users["ben"])

        event = self.db.session.get(Event, self.events["E1"].id)
        event.coordinator_id = self.users["ben"].id
        self.db.session.commit()
        self.assert_error(self.submit(headers=alice_headers), 403)

        self.users["ben"].role = "organiser"
        self.db.session.commit()
        self.assert_error(self.submit(headers=ben_headers), 403)
        self.assert_nothing_saved()


# ---------- AC2: what the request contains ----------


class RequestContentTests(BookingRequestTestCase):
    # TC-39-08 · AC2 — the request records the event, venue, times and requirements.
    def test_request_records_event_venue_times_and_requirements(self):
        booking = self.submit().get_json()["booking"]

        [saved] = self.bookings_for("E1")
        alice, venue = self.users["alice"], self.venues["fully_recorded"]
        self.assertEqual(booking, {
            "id": saved.id,
            "status": "pending",
            "event": {"id": self.events["E1"].id, "title": "Harbour Lights Festival",
                      "expected_attendance": 250},
            "venue": {"id": venue.id, "name": "Aurora Ballroom",
                      "location": "Level 3, Marina Tower, 10 Bayfront Ave"},
            "start_time": "2027-03-12T16:00:00",
            "end_time": "2027-03-12T22:30:00",
            "venue_requirements": REQUIREMENTS,
            "requested_by": {"id": alice.id, "email": alice.email},
            "requested_at": saved.created_at.isoformat(),
        })

    # TC-39-09 · AC2 (Q3) — requested times may differ from the event's proposed times.
    def test_requested_times_may_differ_from_the_events_times(self):
        self.assertEqual(self.submit().status_code, 201)

        self.db.session.expire_all()
        event = self.db.session.get(Event, self.events["E1"].id)
        self.assertEqual((event.start_time, event.end_time),
                         (datetime(2027, 3, 12, 17, 0), datetime(2027, 3, 12, 22, 0)))
        [saved] = self.bookings_for("E1")
        self.assertEqual((saved.start_time, saved.end_time),
                         (datetime(2027, 3, 12, 16, 0), datetime(2027, 3, 12, 22, 30)))

    # TC-39-10 · AC2 (boundary) — requirements are trimmed.
    def test_requirements_are_trimmed(self):
        self.submit(self.valid(venue_requirements="  Stage power and a loading bay \n"))

        self.assertEqual(self.bookings_for("E1")[0].venue_requirements,
                         "Stage power and a loading bay")


# ---------- AC3: missing or invalid information prevents submission ----------


class InvalidInformationTests(BookingRequestTestCase):
    # TC-39-12 · AC3 — missing required information is identified, all at once.
    def test_missing_required_information_is_identified(self):
        only_event = {"event_id": self.events["E1"].id}
        self.assert_fields(self.submit(only_event),
                           "venue_id", "start_time", "end_time", "venue_requirements")

        for field in ("venue_id", "start_time", "end_time", "venue_requirements"):
            with self.subTest(missing=field):
                self.assert_fields(self.submit(self.valid(**{field: ...})), field)
        for blank in ("", "   "):
            with self.subTest(requirements=repr(blank)):
                self.assert_fields(self.submit(self.valid(venue_requirements=blank)),
                                   "venue_requirements")
        with self.subTest(missing="event_id"):
            self.assert_fields(self.submit(self.valid(event_id=...)), "event_id")
        self.assert_nothing_saved()

    # TC-39-13 · AC3 (boundary) — invalid values are identified.
    def test_invalid_values_are_identified(self):
        cases = [
            ("start_time", {"start_time": "tomorrow"}),
            ("start_time", {"start_time": "12/03/2027 16:00"}),
            ("start_time", {"start_time": "2027-02-30T10:00"}),
            ("end_time", {"end_time": "2027-03-12T16:00"}),          # equal to start
            ("end_time", {"end_time": "2027-03-12T15:59"}),          # before start
            ("start_time", {"start_time": "2020-01-01T10:00",
                            "end_time": "2020-01-01T12:00"}),          # in the past
            ("venue_requirements", {"venue_requirements": 42}),
            ("venue_requirements", {"venue_requirements": "x" * (MAX_REQUIREMENTS + 1)}),
            ("venue_id", {"venue_id": "7"}),
            ("venue_id", {"venue_id": True}),
            ("venue_id", {"venue_id": 1.5}),
            ("event_id", {"event_id": "7"}),
            ("event_id", {"event_id": True}),
            ("event_id", {"event_id": 1.5}),
            ("budget", {"budget": 5000}),
        ]
        for field, overrides in cases:
            with self.subTest(field=field, overrides=str(overrides)[:60]):
                self.assert_fields(self.submit(self.valid(**overrides)), field)

        with self.subTest(case="not JSON"):
            response = self.submit(data="event_id=1")
            self.assert_error(response, 400)
        self.assert_nothing_saved()

    # TC-39-14 · AC3 (boundary) — boundary values that are accepted.
    def test_boundary_values_are_accepted(self):
        one_minute = self.submit(self.valid(start_time="2027-03-12T16:00",
                                            end_time="2027-03-12T16:01"))
        self.assertEqual(one_minute.status_code, 201, one_minute.get_json())

        longest = self.submit(self.valid(event="E2", venue="recorded_as_none",
                                         venue_requirements="x" * MAX_REQUIREMENTS),
                              as_user="ben")
        self.assertEqual(longest.status_code, 201, longest.get_json())


# ---------- AC4: saved as Pending, and visible to Venue Staff ----------


class SavedAndVisibleTests(BookingRequestTestCase):
    # TC-39-16 · AC4 — saved against the event and venue as Pending.
    def test_saved_against_the_event_and_venue_as_pending(self):
        self.submit()

        [saved] = self.bookings_for("E1")
        self.assertEqual((saved.event_id, saved.venue_id, saved.status),
                         (self.events["E1"].id, self.venues["fully_recorded"].id, "pending"))
        self.db.session.expire_all()
        self.assertEqual(self.db.session.get(Event, self.events["E1"].id).status, "approved")

    # TC-39-17 · AC4 (Q8) — Venue Staff see pending requests, oldest first.
    def test_venue_staff_see_pending_requests(self):
        first = self.submit().get_json()["booking"]
        second = self.submit(self.valid(event="E2", venue="recorded_as_none",
                                        start_time="2027-04-03T17:00",
                                        end_time="2027-04-03T21:30",
                                        venue_requirements="Theatre layout for 80"),
                             as_user="ben").get_json()["booking"]
        rejected = self.seed_booking("E3", "fully_recorded", "rejected",
                                     datetime(2027, 3, 20, 15, 0), datetime(2027, 3, 20, 18, 0))
        confirmed = self.seed_booking("E5", "fully_recorded", "confirmed",
                                      datetime(2027, 3, 5, 19, 0), datetime(2027, 3, 5, 22, 0))

        response = self.listed()

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        own = {first["id"], second["id"], rejected.id, confirmed.id}
        listed = [b for b in body["bookings"] if b["id"] in own]
        self.assertEqual([b["id"] for b in listed], [first["id"], second["id"]])
        self.assertEqual(listed[0], first)
        self.assertEqual(listed[1]["event"]["title"], "Winter Networking Night")
        self.assertEqual(listed[1]["requested_by"]["id"], self.users["ben"].id)
        self.assertIsNone(body["message"])

    # TC-39-18 · AC4 — only Venue Staff can list requests; empty state.
    def test_only_venue_staff_can_list_requests(self):
        for user in ("alice", "dana", "hana", "farah", "admin"):
            with self.subTest(user=user):
                self.assert_error(self.listed(as_user=user), 403)

        # Hide every pending request, real ones included; rolled back after the test.
        VenueBooking.query.filter_by(status="pending").update(
            {"status": "cancelled"}, synchronize_session=False)
        self.db.session.commit()
        body = self.listed().get_json()
        self.assertEqual(body["bookings"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())


# ---------- AC5: submitting does not confirm the booking ----------


class NotConfirmedTests(BookingRequestTestCase):
    # TC-39-21 · AC5 — a pending request does not block the venue or set the event's venue.
    def test_pending_request_does_not_block_the_venue(self):
        self.submit()
        headers = self.auth_headers(self.users["alice"])
        aurora = self.venues["fully_recorded"]

        calendar = self.client.get(f"/api/venues/{aurora.id}/availability",
                                   query_string={"from": "2027-03-12"}, headers=headers).get_json()
        self.assertEqual(calendar["periods"], [])
        statuses = {s["status"] for d in calendar["days"] for s in d["slots"]
                    if "2027-03-12T16:00:00" <= s["start"] < "2027-03-12T22:30:00"}
        self.assertNotIn("unavailable", statuses)

        found = self.client.get("/api/venues/search", headers=headers, query_string={
            "date": "2027-03-12", "start": "18:00", "end": "20:00"}).get_json()
        self.assertIn(aurora.id, [v["id"] for v in found["venues"]])

        self.db.session.expire_all()
        self.assertIsNone(self.db.session.get(Event, self.events["E1"].id).venue_id)

    # TC-39-22 · AC5 (Q4, Q7) — accepted even where the venue looks unavailable or unsuitable.
    def test_request_is_accepted_where_the_venue_looks_unavailable(self):
        self.seed_booking(None, "fully_recorded", "confirmed",
                          datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))
        self.db.session.add(VenueBlock(venue_id=self.venues["fully_recorded"].id,
                                       reason="Electrical works",
                                       start_time=datetime(2027, 3, 12, 15, 0),
                                       end_time=datetime(2027, 3, 12, 17, 0)))
        self.db.session.commit()

        clashing = self.submit()
        self.assertEqual(clashing.status_code, 201, clashing.get_json())

        for venue in ("recorded_as_none", "unavailable"):  # too small; not bookable
            with self.subTest(venue=venue):
                for booking in self.bookings_for("E1"):  # free E1 for a new request
                    booking.status = "rejected"
                self.db.session.commit()
                response = self.submit(self.valid(venue=venue))
                self.assertEqual(response.status_code, 201, response.get_json())


# ---------- One pending request per event (A6) ----------


class OnePendingRequestTests(BookingRequestTestCase):
    # TC-39-23 · AC1, AC4 (Q6) — a second request while one is pending is refused.
    def test_second_request_while_one_is_pending_is_refused(self):
        self.submit()
        before = [(b.id, b.venue_id, b.status) for b in self.bookings_for("E1")]

        for venue in ("fully_recorded", "recorded_as_none"):
            with self.subTest(venue=venue):
                body = self.assert_error(self.submit(self.valid(venue=venue)), 409)
                self.assertIn("pending", body["error"].lower())

        self.assertEqual([(b.id, b.venue_id, b.status) for b in self.bookings_for("E1")], before)

    # TC-39-24 · AC1 — a new request is allowed once the earlier one is no longer pending.
    def test_new_request_allowed_once_earlier_one_is_not_pending(self):
        self.seed_booking("E1", "recorded_as_none", "rejected",
                          datetime(2027, 3, 12, 17, 0), datetime(2027, 3, 12, 22, 0))

        self.assertEqual(self.submit().status_code, 201)

    # TC-39-25 · AC4 (data integrity) — the database allows one pending request per event.
    def test_database_allows_only_one_pending_request_per_event(self):
        self.seed_booking("E1", "fully_recorded", "pending",
                          datetime(2027, 3, 12, 16, 0), datetime(2027, 3, 12, 22, 0))

        self.db.session.add(VenueBooking(
            event_id=self.events["E1"].id, venue_id=self.venues["recorded_as_none"].id,
            status="pending", start_time=datetime(2027, 3, 12, 16, 0),
            end_time=datetime(2027, 3, 12, 22, 0)))
        with self.assertRaises(IntegrityError):
            self.db.session.commit()
        self.db.session.rollback()


# ---------- AC6: failures ----------


class FailureTests(BookingRequestTestCase):
    def submit_with_failing_commit(self):
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            return self.submit()

    # TC-39-26 · AC6 — a failed save reports nothing as sent.
    def test_failed_save_reports_nothing_as_sent(self):
        response = self.submit_with_failing_commit()

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not sent")
        self.assertRegex(body["error"].lower(), r"try again")
        self.assertNotIn("booking", body)
        self.assert_nothing_saved()

    # TC-39-27 · AC6 — retry succeeds after recovery.
    def test_retry_succeeds_after_recovery(self):
        self.submit_with_failing_commit()

        self.assertEqual(self.submit().status_code, 201)
        self.assertEqual(len(self.bookings_for("E1")), 1)

    # TC-39-29 · AC4 — Venue Staff's list fails to load: an error, never an empty list.
    def test_list_failure_is_retryable_and_not_shown_as_empty(self):
        headers = self.auth_headers(self.users["gus"])
        self.db.session.expire_all()

        def fail(conn, cursor, statement, parameters, context, executemany):
            if "venue_bookings" in statement and not statement.lstrip().upper().startswith(
                    ("SAVEPOINT", "ROLLBACK", "RELEASE")):
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            response = self.client.get(BOOKINGS_URL, headers=headers)
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("bookings", body)

    # TC-39-30 · AC4, AC6 (Q6) — a submission that loses a race reports the pending request.
    def test_submission_losing_a_race_reports_the_pending_request(self):
        refused = IntegrityError("INSERT INTO venue_bookings ...", {},
                                 Exception("duplicate key: venue_bookings_one_pending_per_event"))
        with mock.patch.object(self.db.session, "commit", side_effect=refused):
            response = self.submit()

        body = self.assert_error(response, 409)
        self.assertIn("pending", body["error"].lower())
        self.assertNotIn("booking", body)
        self.assert_nothing_saved()


if __name__ == "__main__":
    unittest.main()
