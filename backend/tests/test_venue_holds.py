"""Tests for SCRUM-87 "Venue Staff Place a Tentative Hold".

Each test names the case it automates from
docs/test-cases/SCRUM-87-tentative-venue-hold.md (TC-87-xx) and the acceptance
criteria it checks. Assumptions A1-A9 and questions Q1-Q4 are defined there.

Model (db/venue_booking_holds.sql): new VenueBooking columns
    held_at          DateTime, naive UTC: when the hold was placed (it starts then)
    held_by_id       FK users.id: the Venue Staff member who placed it
    hold_expires_at  DateTime, Singapore time: when it expires, set by Venue Staff
and the status "tentative".

Endpoints (JWT required, else 401; caller not Venue Staff -> 403)
    POST  /api/venues/bookings/<id>/hold   {"expires_at": "YYYY-MM-DDTHH:MM"}
    PATCH /api/venues/bookings/<id>/hold   {"expires_at": "YYYY-MM-DDTHH:MM"}
        200 {"message", "booking": hold, "notification": {"in_app", "email_queued"}}
        400 {"error", "field"}   404 unknown booking
        409 {"error", "reason"}  POST: not_pending | event_not_approved | conflict (+conflicts)
                                 PATCH: not_a_hold | expired
        503 {"error", "retryable": true}
    GET   /api/venues/holds  200 {"holds": [hold, ...], "message"}, unexpired, soonest expiry first
    hold = SCRUM-39's booking payload + {"hold": {"held_at", "held_by": {"id", "email"},
                                                  "expires_at"}}

An unexpired hold (expiry later than now) is a "hold" conflict, a "hold" period on the
calendar, makes its time "tentative", and leaves its venue out of search. "Now" is
fixed at NOW (Singapore time) for every test, so the boundaries are exact.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import SQLAlchemyError

from app.models import VenueBooking
from tests.test_venue_booking_approval import P1_END, P1_START
from tests.test_venue_booking_conflicts import BLOCKS, ConflictCheckTestCase

HOLDS_URL = "/api/venues/holds"
NOW = datetime(2027, 3, 1, 12, 0)
EXPIRY = "2027-03-01T17:00"
EXPIRY_AT = datetime(2027, 3, 1, 17, 0)
EXPIRED_AT = datetime(2027, 2, 1, 9, 0)
# When seeded holds were placed (naive UTC).
HELD_AT = datetime(2027, 2, 20, 1, 0)
H2_START, H2_END = datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0)
OTHER_ROLES = ("alice", "dana", "hana", "farah", "admin")
_NO_BODY = object()


class HoldTestCase(ConflictCheckTestCase):
    """VH-SEED (SCRUM-40's VA-SEED), with "now" fixed at NOW."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch("app.venues.routes.singapore_now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- Seeding ----------

    def make_hold(self, booking, expires_at=EXPIRY_AT, held_by="gus"):
        """Turn a seeded request into a tentative hold, as if Venue Staff had held it."""
        booking = self.bookings[booking] if isinstance(booking, str) else booking
        booking.status = "tentative"
        booking.held_at = HELD_AT
        booking.held_by_id = self.users[held_by].id
        booking.hold_expires_at = expires_at
        self.db.session.commit()
        return booking

    def add_hold(self, event, venue, start, end, expires_at=EXPIRY_AT):
        return self.make_hold(
            self.add_booking(event, venue, "tentative", start, end, requested_by="alice"),
            expires_at)

    # ---------- Requests ----------

    def _send(self, method, booking, expires_at, as_user, headers, body):
        booking_id = booking if isinstance(booking, int) else (
            self.bookings[booking].id if isinstance(booking, str) else booking.id)
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        json = {"expires_at": expires_at} if body is _NO_BODY else body
        return self.client.open(f"/api/venues/bookings/{booking_id}/hold", method=method,
                                headers=headers, json=json)

    def hold(self, booking, expires_at=EXPIRY, as_user="gus", headers=None, body=_NO_BODY):
        return self._send("POST", booking, expires_at, as_user, headers, body)

    def change_expiry(self, booking, expires_at, as_user="gus", headers=None, body=_NO_BODY):
        return self._send("PATCH", booking, expires_at, as_user, headers, body)

    def holds(self, as_user="gus", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get(HOLDS_URL, headers=headers)

    # ---------- Assertions ----------

    def assert_not_held(self, booking="P1", event="E1"):
        """Still pending with no hold, and nothing announced."""
        stored = self.stored(booking)
        self.assertEqual(
            (stored["held_at"], stored["held_by_id"], stored["hold_expires_at"]),
            (None, None, None))
        self.assert_nothing_decided(booking, event)

    def assert_expiry_unchanged(self, booking="P1", expires_at=EXPIRY_AT):
        stored = self.stored(booking)
        self.assertEqual((stored["status"], stored["hold_expires_at"]),
                         ("tentative", expires_at))
        for user in ("alice", "ben", "dana", "gus"):
            self.assertEqual(self.notifications_for(user), [], user)
        self.queue_email.assert_not_called()

    def hold_conflict(self, record, event="E3", expires_at="2027-03-01T17:00:00"):
        return {"type": "hold", "id": record.id,
                "start": record.start_time.isoformat(), "end": record.end_time.isoformat(),
                "event": {"id": self.events[event].id, "title": self.events[event].title},
                "expires_at": expires_at}


# ---------- AC1: placing a hold ----------


class PlaceHoldTests(HoldTestCase):
    # TC-87-01 · AC1, AC2 — Venue Staff place a tentative hold on a pending request.
    def test_venue_staff_place_a_tentative_hold(self):
        started = datetime.utcnow()

        response = self.hold("P1")

        finished = datetime.utcnow()
        self.assertEqual(response.status_code, 200, response.get_json())
        stored = self.stored("P1")
        gus = self.users["gus"]
        self.assertEqual(
            (stored["status"], stored["held_by_id"], stored["hold_expires_at"],
             stored["start_time"], stored["end_time"]),
            ("tentative", gus.id, EXPIRY_AT, P1_START, P1_END))
        self.assertTrue(started <= stored["held_at"] <= finished)
        self.assertEqual((stored["decided_at"], stored["decided_by_id"]), (None, None))
        event = self.event("E1")
        self.assertEqual((event.venue_id, event.status), (None, "approved"))

        body = response.get_json()
        self.assertEqual((body["booking"]["id"], body["booking"]["status"]),
                         (self.bookings["P1"].id, "tentative"))
        self.assertEqual(body["booking"]["hold"], {
            "held_at": stored["held_at"].isoformat(),
            "held_by": {"id": gus.id, "email": gus.email},
            "expires_at": "2027-03-01T17:00:00",
        })
        for text in ("Aurora Ballroom", "Harbour Lights Festival", "2027-03-01 17:00"):
            self.assertIn(text, body["message"])

        pending = self.listed().get_json()["bookings"]
        self.assertNotIn(self.bookings["P1"].id, [b["id"] for b in pending])
        held = self.holds().get_json()["holds"]
        self.assertIn(self.bookings["P1"].id, [h["id"] for h in held])

    # TC-87-02 · AC1 — only a pending request can be placed on hold.
    def test_only_a_pending_request_can_be_held(self):
        cases = {
            "confirmed": self.add_booking("E3", "fully_recorded", "confirmed",
                                          datetime(2027, 5, 1, 10, 0), datetime(2027, 5, 1, 12, 0)),
            "rejected": self.add_booking("E2", "fully_recorded", "rejected",
                                         datetime(2027, 5, 2, 10, 0), datetime(2027, 5, 2, 12, 0)),
            "cancelled": self.add_booking("E3", "recorded_as_none", "cancelled",
                                          datetime(2027, 5, 3, 10, 0), datetime(2027, 5, 3, 12, 0)),
            "tentative": self.add_hold("E3", "fully_recorded",
                                       datetime(2027, 5, 4, 10, 0), datetime(2027, 5, 4, 12, 0)),
        }
        for status, booking in cases.items():
            with self.subTest(status=status):
                before = self.stored(booking)

                body = self.assert_error(self.hold(booking), 409, reason="not_pending")

                self.assertIn(status, body["error"])
                self.assertEqual(self.stored(booking), before)
        self.queue_email.assert_not_called()

    # TC-87-03 · AC1 — the event must still be approved.
    def test_event_must_still_be_approved(self):
        self.events["E1"].status = "cancelled"
        self.db.session.commit()

        body = self.assert_error(self.hold("P1"), 409, reason="event_not_approved")

        self.assertIn("cancelled", body["error"])
        self.assertEqual(self.stored("P1")["status"], "pending")
        self.assertIsNone(self.stored("P1")["hold_expires_at"])

    # TC-87-04 · AC1 — unknown booking.
    def test_unknown_booking_is_not_found(self):
        missing = self.missing_id(VenueBooking)
        for name, response in (("place", self.hold(missing)),
                               ("change", self.change_expiry(missing, EXPIRY))):
            with self.subTest(action=name):
                body = self.assert_error(response, 404)
                self.assertEqual(body["error"], "Booking request not found.")

    # TC-87-33 · AC1 (Q4) — approving a hold is still refused; confirming is separate.
    def test_approving_a_hold_is_refused(self):
        self.make_hold("P1")

        body = self.assert_error(self.approve("P1"), 409, reason="not_pending")

        self.assertIn("tentative", body["error"])
        self.assert_expiry_unchanged()
        self.assertIsNone(self.stored("P1")["decided_at"])


# ---------- AC2: the expiry ----------


class ExpiryTests(HoldTestCase):
    # TC-87-05 · AC2 — the expiry is required, as a date and time, and nothing else.
    def test_expiry_must_be_a_date_and_time(self):
        cases = {
            "no body": {"body": None},
            "empty object": {"body": {}},
            "empty": {"expires_at": ""},
            "null": {"expires_at": None},
            "words": {"expires_at": "tomorrow"},
            "impossible date": {"expires_at": "2027-02-30T10:00"},
            "date only": {"expires_at": "2027-03-01"},
            "number": {"expires_at": 20270301},
        }
        for name, case in cases.items():
            with self.subTest(case=name):
                response = (self.hold("P1", body=case["body"]) if "body" in case
                            else self.hold("P1", case["expires_at"]))

                body = self.assert_error(response, 400)
                self.assertEqual(body.get("field"), "expires_at")

        with self.subTest(case="another field"):
            body = self.assert_error(
                self.hold("P1", body={"expires_at": EXPIRY, "note": "Hold it"}), 400)
            self.assertEqual(body.get("field"), "note")

        self.assert_not_held()

    # TC-87-06 · AC2 (boundary) — the expiry must be in the future.
    def test_expiry_must_be_in_the_future(self):
        for expires_at in ("2027-03-01T11:59", "2027-03-01T12:00"):
            with self.subTest(expires_at=expires_at):
                body = self.assert_error(self.hold("P1", expires_at), 400)
                self.assertEqual(body.get("field"), "expires_at")
        self.assert_not_held()

        response = self.hold("P1", "2027-03-01T12:01")

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.stored("P1")["hold_expires_at"], datetime(2027, 3, 1, 12, 1))

    # TC-87-07 · AC2 (boundary, Q1) — no later than the booking's start.
    def test_expiry_must_be_no_later_than_the_start(self):
        body = self.assert_error(self.hold("P1", "2027-03-12T16:01"), 400)
        self.assertEqual(body.get("field"), "expires_at")
        self.assertIn("2027-03-12 16:00", body["error"])
        self.assert_not_held()

        self.assertEqual(self.hold("P1", "2027-03-12T16:00").status_code, 200)

        with self.subTest(case="the booking has already started"):
            started = self.add_booking("E3", "fully_recorded", "pending",
                                       datetime(2020, 1, 1, 10, 0), datetime(2020, 1, 1, 12, 0),
                                       requested_by="alice")
            body = self.assert_error(self.hold(started, EXPIRY), 400)
            self.assertEqual(body.get("field"), "expires_at")
            self.assertEqual(self.stored(started)["status"], "pending")

    # TC-87-08 · AC2 — no fixed duration: any valid expiry is kept as entered.
    def test_any_valid_expiry_is_kept_as_entered(self):
        self.assertEqual(self.hold("P1", "2027-03-01T12:05").status_code, 200)
        self.assertEqual(self.hold("P2", "2027-04-03T17:00").status_code, 200)

        self.assertEqual(self.stored("P1")["hold_expires_at"], datetime(2027, 3, 1, 12, 5))
        self.assertEqual(self.stored("P2")["hold_expires_at"], datetime(2027, 4, 3, 17, 0))


# ---------- AC3: changing the expiry ----------


class ChangeExpiryTests(HoldTestCase):
    # TC-87-09 · AC3 — Venue Staff change an unexpired hold's expiry, later or earlier.
    def test_venue_staff_change_a_holds_expiry(self):
        self.make_hold("P1")

        for expires_at, expected in (("2027-03-05T12:00", datetime(2027, 3, 5, 12, 0)),
                                     ("2027-03-02T09:00", datetime(2027, 3, 2, 9, 0))):
            with self.subTest(expires_at=expires_at):
                response = self.change_expiry("P1", expires_at)

                self.assertEqual(response.status_code, 200, response.get_json())
                stored = self.stored("P1")
                self.assertEqual(
                    (stored["status"], stored["hold_expires_at"], stored["held_at"],
                     stored["held_by_id"], stored["start_time"], stored["end_time"]),
                    ("tentative", expected, HELD_AT, self.users["gus"].id, P1_START, P1_END))
                self.assertEqual(response.get_json()["booking"]["hold"]["expires_at"],
                                 expected.isoformat())

    # TC-87-10 · AC2, AC3 — the new expiry follows the same rules.
    def test_new_expiry_follows_the_same_rules(self):
        self.make_hold("P1")

        for expires_at in ("2027-03-01T11:00", "2027-03-12T16:01", "soon"):
            with self.subTest(expires_at=expires_at):
                body = self.assert_error(self.change_expiry("P1", expires_at), 400)
                self.assertEqual(body.get("field"), "expires_at")
        self.assert_expiry_unchanged()

    # TC-87-11 · AC3 — only a tentative hold has an expiry to change.
    def test_only_a_hold_has_an_expiry_to_change(self):
        confirmed = self.add_booking("E3", "fully_recorded", "confirmed",
                                     datetime(2027, 5, 1, 10, 0), datetime(2027, 5, 1, 12, 0))
        for name, booking in (("pending", self.bookings["P2"]), ("confirmed", confirmed)):
            with self.subTest(status=name):
                before = self.stored(booking)

                self.assert_error(self.change_expiry(booking, EXPIRY), 409, reason="not_a_hold")

                self.assertEqual(self.stored(booking), before)
        self.queue_email.assert_not_called()

    # TC-87-12 · AC3 (boundary, Q4) — an expired hold can't be changed.
    def test_an_expired_hold_cannot_be_changed(self):
        expired = self.make_hold("P1", expires_at=NOW)
        live = self.make_hold("P2", expires_at=NOW + timedelta(minutes=1))

        body = self.assert_error(self.change_expiry(expired, "2027-03-02T10:00"), 409,
                                 reason="expired")

        self.assertIn("2027-03-01 12:00", body["error"])
        self.assertEqual(self.stored(expired)["hold_expires_at"], NOW)
        self.assertEqual(self.change_expiry(live, "2027-03-02T10:00").status_code, 200)


# ---------- AC4: an unexpired hold blocks the slot ----------


class BlockingTests(HoldTestCase):
    # TC-87-13 · AC4 — an unexpired hold blocks approving and holding an overlapping request.
    def test_unexpired_hold_blocks_approving_and_holding(self):
        h2 = self.add_hold("E3", "fully_recorded", H2_START, H2_END)

        for name, response in (("approve", self.approve("P1")), ("hold", self.hold("P1"))):
            with self.subTest(action=name):
                body = self.assert_error(response, 409, reason="conflict")
                self.assertEqual(body["conflicts"], [self.hold_conflict(h2)])
        self.assert_not_held()

    # TC-87-14 · AC4 — the pending list shows an unexpired hold as a conflict.
    def test_pending_list_shows_a_hold_as_a_conflict(self):
        h2 = self.add_hold("E3", "fully_recorded", H2_START, H2_END)

        self.assertEqual(self.listed_conflicts()["P1"], [self.hold_conflict(h2)])

    # TC-87-15 · AC4 (boundary) — touching holds and other venues' holds don't block.
    def test_touching_and_other_venues_holds_do_not_block(self):
        self.add_hold("E3", "fully_recorded", datetime(2027, 3, 12, 12, 0), P1_START)
        self.add_hold("E2", "fully_recorded", P1_END, datetime(2027, 3, 12, 23, 0))
        self.add_hold("E3", "recorded_as_none", P1_START, P1_END)

        self.assertEqual(self.listed_conflicts()["P1"], [])
        self.assertEqual(self.approve("P1").status_code, 200)

    # TC-87-16 · AC4 (boundary, Q4) — an expired hold blocks nothing.
    def test_expired_hold_blocks_nothing(self):
        self.add_hold("E3", "fully_recorded", H2_START, H2_END, expires_at=NOW)

        self.assertEqual(self.listed_conflicts()["P1"], [])
        self.assertEqual(self.approve("P1").status_code, 200)

    # TC-87-17 · AC4 — placing a hold is refused by the same conflicts as approving.
    def test_placing_a_hold_checks_the_usual_conflicts(self):
        clashes = {
            "confirmed booking": lambda: self.add_booking(
                "E3", "fully_recorded", "confirmed", H2_START, H2_END),
            "block": lambda: self.add_block("fully_recorded", "Electrical works",
                                            H2_START, H2_END),
            "event's confirmed venue": lambda: self.add_booking(
                "E1", "recorded_as_none", "confirmed", P1_START, P1_END),
        }
        for name, add in clashes.items():
            with self.subTest(clash=name):
                clash = add()

                body = self.assert_error(self.hold("P1"), 409, reason="conflict")

                self.assertEqual([c["id"] for c in body["conflicts"]], [clash.id])
                self.assert_not_held()
                self.db.session.delete(clash)
                self.db.session.commit()

    # TC-87-18 · AC4 (concurrency) — the booking and venue rows are locked first.
    def test_booking_and_venue_rows_are_locked_before_the_conflict_check(self):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(" ".join(statement.split()))

        sa_event.listen(self.db.engine, "before_cursor_execute", record)
        try:
            response = self.hold("P1")
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", record)

        self.assertEqual(response.status_code, 200, response.get_json())

        def first(predicate):
            return next((i for i, s in enumerate(statements) if predicate(s)), None)

        booking_lock = first(lambda s: "FROM venue_bookings" in s and s.endswith("FOR UPDATE"))
        venue_lock = first(lambda s: "FROM venues" in s and s.endswith("FOR UPDATE"))
        block_check = first(lambda s: "FROM venue_blocks" in s)
        self.assertIsNotNone(booking_lock, "the booking row is not locked")
        self.assertIsNotNone(venue_lock, "the venue row is not locked")
        self.assertIsNotNone(block_check)
        self.assertLess(booking_lock, block_check)
        self.assertLess(venue_lock, block_check)

    # TC-87-19 · AC4, AC7 — no hold when conflicts can't be checked.
    def test_no_hold_when_conflicts_cannot_be_checked(self):
        booking_id = self.bookings["P1"].id
        headers = self.auth_headers(self.users["gus"])
        with self.statements_fail(BLOCKS[1]):
            response = self.hold(booking_id, headers=headers)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"availability could not be verified")
        self.assert_not_held()
        self.assertEqual(self.hold("P1").status_code, 200)


class CalendarAndSearchTests(HoldTestCase):
    def calendar(self, start="2027-03-12", end=None):
        query = {"from": start, **({"to": end} if end else {})}
        response = self.client.get(
            f"/api/venues/{self.venues['fully_recorded'].id}/availability",
            headers=self.auth_headers(self.users["alice"]), query_string=query)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def slots(self, body, date):
        """A day's slots as (HH:MM, HH:MM, status, causes), with next midnight as 24:00."""
        day = next(d for d in body["days"] if d["date"] == date)

        def clock(value):
            return "24:00" if not value.startswith(date) else value[11:16]

        return [(clock(s["start"]), clock(s["end"]), s["status"], tuple(s.get("causes", ())))
                for s in day["slots"]]

    # TC-87-20 · AC4 — the calendar shows an unexpired hold as Tentative.
    def test_calendar_shows_an_unexpired_hold_as_tentative(self):
        h2 = self.add_hold("E3", "fully_recorded", H2_START, H2_END)
        h3 = self.add_hold("E2", "fully_recorded", datetime(2027, 3, 13, 22, 0),
                           datetime(2027, 3, 13, 23, 30))

        body = self.calendar("2027-03-12", "2027-03-13")

        self.assertEqual(body["periods"], [
            {"type": "hold", "id": h2.id, "start": "2027-03-12T18:00:00",
             "end": "2027-03-12T20:00:00", "reason": None, "expires_at": "2027-03-01T17:00:00"},
            {"type": "hold", "id": h3.id, "start": "2027-03-13T22:00:00",
             "end": "2027-03-13T23:30:00", "reason": None, "expires_at": "2027-03-01T17:00:00"},
        ])
        outside = ("outside_operating_hours",)
        self.assertEqual(self.slots(body, "2027-03-12"), [
            ("00:00", "08:00", "unavailable", outside),
            ("08:00", "18:00", "available", ()),
            ("18:00", "20:00", "tentative", ("hold",)),
            ("20:00", "23:00", "available", ()),
            ("23:00", "24:00", "unavailable", outside),
        ])
        self.assertEqual(self.slots(body, "2027-03-13"), [
            ("00:00", "08:00", "unavailable", outside),
            ("08:00", "22:00", "available", ()),
            ("22:00", "23:00", "tentative", ("hold",)),
            ("23:00", "23:30", "unavailable", ("hold", "outside_operating_hours")),
            ("23:30", "24:00", "unavailable", outside),
        ])

    # TC-87-21 · AC4 (boundary, Q4) — the calendar ignores an expired hold.
    def test_calendar_ignores_an_expired_hold(self):
        self.add_hold("E3", "fully_recorded", H2_START, H2_END, expires_at=EXPIRED_AT)

        body = self.calendar()

        self.assertEqual(body["periods"], [])
        self.assertIn(("08:00", "23:00", "available", ()), self.slots(body, "2027-03-12"))

    # TC-87-22 · AC4 (Q2) — search leaves out a venue held for the searched time.
    def test_search_leaves_out_a_venue_held_for_the_time(self):
        h2 = self.add_hold("E3", "fully_recorded", H2_START, H2_END)
        aurora = self.venues["fully_recorded"].id

        def found():
            response = self.client.get(
                "/api/venues/search", headers=self.auth_headers(self.users["alice"]),
                query_string={"date": "2027-03-12", "start": "18:00", "end": "20:00"})
            self.assertEqual(response.status_code, 200, response.get_json())
            return [v["id"] for v in response.get_json()["venues"]]

        self.assertNotIn(aurora, found())

        h2.hold_expires_at = EXPIRED_AT
        self.db.session.commit()
        self.assertIn(aurora, found())


# ---------- AC5: the coordinator is notified ----------


class NotificationTests(HoldTestCase):
    # TC-87-23 · AC5 — the coordinator is told the hold was placed, with its expiry.
    def test_coordinator_is_notified_of_the_hold_and_its_expiry(self):
        response = self.hold("P1")

        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": True})
        [notification] = self.notifications_for("alice")
        self.assertEqual((notification.kind, notification.event_id),
                         ("venue_hold_placed", self.events["E1"].id))
        for text in ("Aurora Ballroom", "2027-03-12 16:00", "2027-03-12 22:30",
                     "2027-03-01 17:00"):
            self.assertIn(text, notification.message)
        for user in ("ben", "dana", "gus"):
            with self.subTest(user=user):
                self.assertEqual(self.notifications_for(user), [])
        self.queue_email.assert_called_once()
        to_address, subject, body = self.queue_email.call_args.args
        self.assertEqual(to_address, self.users["alice"].email)
        self.assertIn("Aurora Ballroom", subject)
        self.assertIn("Harbour Lights Festival", subject)
        self.assertIn("2027-03-01 17:00", body)

    # TC-87-24 · AC3, AC5 (Q3) — the coordinator is told when the expiry changes.
    def test_coordinator_is_notified_when_the_expiry_changes(self):
        self.make_hold("P1")

        self.assertEqual(self.change_expiry("P1", "2027-03-05T12:00").status_code, 200)

        [notification] = self.notifications_for("alice")
        self.assertEqual(notification.kind, "venue_hold_expiry_changed")
        self.queue_email.assert_called_once()
        to_address, _, body = self.queue_email.call_args.args
        self.assertEqual(to_address, self.users["alice"].email)
        for text in ("2027-03-01 17:00", "2027-03-05 12:00"):
            self.assertIn(text, notification.message)
            self.assertIn(text, body)

    # TC-87-25 · AC5 — the hold stands when the email can't be queued.
    def test_hold_stands_when_the_email_cannot_be_queued(self):
        self.queue_email.side_effect = ConnectionError("Redis is down")

        placed = self.hold("P1")
        changed = self.change_expiry("P1", "2027-03-05T12:00")

        for name, response in (("place", placed), ("change", changed)):
            with self.subTest(action=name):
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(response.get_json()["notification"],
                                 {"in_app": True, "email_queued": False})
        self.assertEqual(self.stored("P1")["hold_expires_at"], datetime(2027, 3, 5, 12, 0))
        self.assertEqual(len(self.notifications_for("alice")), 2)


# ---------- AC6: only Venue Staff ----------


class PermissionTests(HoldTestCase):
    # TC-87-26 · AC6 — only Venue Staff can place a hold.
    def test_only_venue_staff_can_place_a_hold(self):
        for user in OTHER_ROLES:
            with self.subTest(user=user):
                self.assert_error(self.hold("P1", as_user=user), 403)
        self.assert_not_held()

    # TC-87-27 · AC6 — only Venue Staff can change a hold's expiry or list the holds.
    def test_only_venue_staff_can_change_or_list_holds(self):
        self.make_hold("P1")

        for user in OTHER_ROLES:
            with self.subTest(user=user):
                self.assert_error(self.change_expiry("P1", "2027-03-05T12:00", as_user=user), 403)
                listed = self.holds(as_user=user)
                self.assert_error(listed, 403)
                self.assertNotIn("holds", listed.get_json())
        self.assert_expiry_unchanged()

    # TC-87-28 · AC6 — a valid session is required.
    def test_a_valid_session_is_required(self):
        self.make_hold("P2")
        ghost = self.make_user(role="venue_staff")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["gus"].id),
                                      expires_delta=timedelta(seconds=-1))
        sessions = {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                    "deleted user": ghost_headers}
        for label, headers in sessions.items():
            with self.subTest(session=label):
                self.assertEqual(self.hold("P1", headers=headers).status_code, 401)
                self.assertEqual(
                    self.change_expiry("P2", "2027-03-05T12:00", headers=headers).status_code,
                    401)
                self.assertEqual(self.holds(headers=headers).status_code, 401)
        self.assert_not_held()
        self.assert_expiry_unchanged("P2")


# ---------- AC7: a failed save changes nothing ----------


class SaveFailureTests(HoldTestCase):
    def failing_commit(self):
        return mock.patch.object(self.db.session, "commit",
                                 side_effect=SQLAlchemyError("simulated outage"))

    # TC-87-29 · AC7 — placing a hold fails to save.
    def test_failed_hold_save_changes_nothing(self):
        with self.failing_commit():
            response = self.hold("P1")

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not saved")
        self.assertNotIn("booking", body)
        self.assert_not_held()
        self.assertEqual(self.hold("P1").status_code, 200)

    # TC-87-30 · AC7 — changing an expiry fails to save.
    def test_failed_expiry_change_changes_nothing(self):
        self.make_hold("P1")

        with self.failing_commit():
            response = self.change_expiry("P1", "2027-03-05T12:00")

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not saved")
        self.assert_expiry_unchanged()


# ---------- The holds list (A8) ----------


class HoldsListTests(HoldTestCase):
    # TC-87-31 · AC3 — Venue Staff see the unexpired holds, soonest expiry first.
    def test_venue_staff_see_unexpired_holds_soonest_expiry_first(self):
        h1 = self.make_hold("P1")
        h4 = self.add_hold("E3", "fully_recorded", datetime(2027, 5, 1, 10, 0),
                           datetime(2027, 5, 1, 12, 0), expires_at=datetime(2027, 3, 1, 13, 0))
        gone = self.add_hold("E2", "fully_recorded", datetime(2027, 5, 2, 10, 0),
                             datetime(2027, 5, 2, 12, 0), expires_at=EXPIRED_AT)

        response = self.holds()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        ours = [h for h in body["holds"] if h["id"] in {h1.id, h4.id, gone.id}]
        self.assertEqual([h["id"] for h in ours], [h4.id, h1.id])
        gus = self.users["gus"]
        self.assertEqual(ours[1]["hold"], {"held_at": HELD_AT.isoformat(),
                                           "held_by": {"id": gus.id, "email": gus.email},
                                           "expires_at": "2027-03-01T17:00:00"})
        self.assertEqual((ours[1]["status"], ours[1]["venue"]["name"],
                          ours[1]["event"]["title"]),
                         ("tentative", "Aurora Ballroom", "Harbour Lights Festival"))
        self.assertIsNone(body["message"])

        with self.subTest(case="no unexpired holds"):
            # Real holds may exist: expire every hold inside this test's transaction.
            VenueBooking.query.filter_by(status="tentative").update(
                {"hold_expires_at": EXPIRED_AT})
            self.db.session.commit()

            body = self.holds().get_json()

            self.assertEqual(body["holds"], [])
            self.assertTrue(body["message"].strip())

    # TC-87-32 · AC3, AC7 — the holds list fails to load.
    def test_holds_list_failure_is_reported(self):
        headers = self.auth_headers(self.users["gus"])
        with self.statements_fail(lambda s: "FROM venue_bookings" in s):
            response = self.holds(headers=headers)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("holds", body)


if __name__ == "__main__":
    unittest.main()
