"""Tests for SCRUM-41 "Prevent Conflicting Venue Bookings".

Each test names the case it automates from
docs/test-cases/SCRUM-41-prevent-venue-booking-conflicts.md (TC-41-xx) and the
acceptance criteria it checks. Assumptions A1-A6 and questions Q1-Q4 are defined there.
TC-41-08 to 11 and 17 are SCRUM-40's tests, in test_venue_booking_approval.py and
VenueBookingRequestsPage.test.jsx, re-run as regression.

Endpoints
    GET /api/venues/bookings
        200 each pending request also has "conflicts": the SCRUM-40 conflict entries
            it would be refused with now, in time order ([] if none were found)
        503 {"error", "retryable": true} if its conflicts cannot be checked
    POST /api/venues/bookings/<id>/approve
        409 {"error", "reason": "conflict", "conflicts"} if the database rule refuses the save
        503 {"error", "retryable": true} if the conflict check cannot be completed

Database rule (db/venue_booking_conflicts.sql): venue_bookings_no_overlapping_confirmed.
Two confirmed bookings at one venue may not have overlapping [start, end) periods.

VC-SEED is SCRUM-40's VA-SEED, so these tests build on its ApprovalTestCase.
"""

import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest import mock

import psycopg2
from sqlalchemy import event as sa_event
from sqlalchemy.exc import IntegrityError, OperationalError

from app.venues import scheduling
from tests.test_venue_booking_approval import P1_END, P1_START, ApprovalTestCase

BOOKINGS_URL = "/api/venues/bookings"
UNVERIFIED = r"availability could not be verified"

# Statements that make up the conflict check, by what they read.
VENUE_LOCK = ("locking the venue", lambda s: "FROM venues" in s and "FOR UPDATE" in s)
CONFIRMED_BOOKINGS = ("reading confirmed bookings",
                      lambda s: "FROM venue_bookings" in s and "FOR UPDATE" not in s)
BLOCKS = ("reading blocks", lambda s: "FROM venue_blocks" in s)
# Only the unexpired-holds query filters on the expiry (AC1 since reopening; SCRUM-87).
HOLDS = ("reading unexpired holds", lambda s: "hold_expires_at >" in s)


class ConflictCheckTestCase(ApprovalTestCase):
    """VC-SEED plus the pending list and targeted database failures."""

    def listed(self, headers=None):
        return self.client.get(BOOKINGS_URL,
                               headers=headers or self.auth_headers(self.users["gus"]))

    def listed_conflicts(self):
        """The conflicts listed for P1 and P2 by one call to the pending list."""
        response = self.listed()
        self.assertEqual(response.status_code, 200, response.get_json())
        by_id = {b["id"]: b for b in response.get_json()["bookings"]}
        return {key: by_id[booking.id].get("conflicts")
                for key, booking in self.bookings.items()}

    @contextmanager
    def statements_fail(self, matches):
        """Fail every statement `matches` picks out, as a dropped connection would.

        Savepoint statements still run so the test's transaction survives. Read any
        IDs and build headers first: reloading a seeded row is itself a query.
        """

        def fail(conn, cursor, statement, parameters, context, executemany):
            flat = " ".join(statement.split())
            if flat.upper().startswith(("SAVEPOINT", "ROLLBACK", "RELEASE")):
                return
            if matches(flat):
                raise OperationalError(
                    statement, parameters, psycopg2.OperationalError("simulated outage"))

        # Start cold, as a real request would, so nothing is served from memory.
        self.db.session.expire_all()
        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            yield
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)


# ---------- AC1, AC2: conflicts are identified and shown before approval ----------


class ListedConflictTests(ConflictCheckTestCase):
    # TC-41-01 · AC2, AC5 — a request with no conflicts is listed as having none.
    def test_request_without_conflicts_lists_none(self):
        self.assertEqual(self.listed_conflicts(), {"P1": [], "P2": []})

    # TC-41-02 · AC1, AC2 — overlapping bookings and blocks are listed with their periods.
    def test_overlapping_bookings_and_blocks_are_listed_with_their_periods(self):
        clash = self.add_booking("E3", "fully_recorded", "confirmed",
                                 datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))
        block = self.add_block("fully_recorded", "Electrical works",
                               datetime(2027, 3, 12, 15, 0), datetime(2027, 3, 12, 17, 0))

        conflicts = self.listed_conflicts()

        self.assertEqual(conflicts["P1"], [
            {"type": "block", "id": block.id,
             "start": "2027-03-12T15:00:00", "end": "2027-03-12T17:00:00",
             "reason": "Electrical works"},
            {"type": "booking", "id": clash.id,
             "start": "2027-03-12T18:00:00", "end": "2027-03-12T20:00:00",
             "event": {"id": self.events["E3"].id, "title": "Product Launch"}},
        ])
        self.assertEqual(conflicts["P2"], [])

    # TC-41-03 (the event's existing confirmed venue is listed) is replaced by SCRUM-85
    # TC-85-08: an event's venue elsewhere is no longer a conflict.

    # TC-41-04 · AC1 (boundary, Q1) — only real overlaps with confirmed bookings and blocks.
    def test_touching_and_unconfirmed_bookings_are_not_listed(self):
        self.add_booking("E3", "fully_recorded", "confirmed",
                         datetime(2027, 3, 12, 12, 0), P1_START)
        self.add_block("fully_recorded", "Cleaning", P1_END, datetime(2027, 3, 12, 23, 0))
        for event, status in (("E3", "pending"), ("E2", "rejected"), ("E3", "cancelled")):
            self.add_booking(event, "fully_recorded", status,
                             datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0),
                             requested_by="alice")

        self.assertEqual(self.listed_conflicts()["P1"], [])

    # TC-41-05 · AC4 (boundary) — bookings and blocks at other venues are not listed.
    def test_other_venues_are_not_listed_as_conflicts(self):
        self.add_booking("E3", "recorded_as_none", "confirmed", P1_START, P1_END)
        self.add_block("recorded_as_none", "Painting", P1_START, P1_END)

        self.assertEqual(self.listed_conflicts()["P1"], [])


# ---------- AC6: competing approvals cannot both be confirmed ----------


class DatabaseRuleTests(ConflictCheckTestCase):
    # TC-41-12 · AC6 (Q3) — the database refuses two overlapping confirmed bookings.
    def test_database_refuses_overlapping_confirmed_bookings(self):
        self.add_booking("E3", "fully_recorded", "confirmed",
                         datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))

        self.bookings["P1"].status = "confirmed"
        with self.assertRaises(IntegrityError):
            self.db.session.commit()
        self.db.session.rollback()

    # TC-41-13 · AC4, AC5, AC6 (Q3) — the rule allows everything that is not a conflict.
    # Passes before the rule exists; fails if the rule is drawn too widely.
    def test_database_rule_allows_what_is_not_a_conflict(self):
        self.add_booking("E3", "fully_recorded", "confirmed",
                         datetime(2027, 3, 12, 12, 0), P1_START)
        self.add_booking("E2", "recorded_as_none", "confirmed", P1_START, P1_END)

        self.bookings["P1"].status = "confirmed"
        self.db.session.commit()
        self.add_booking("E3", "fully_recorded", "pending",
                         datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))
        self.add_booking(None, "fully_recorded", "cancelled",
                         datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))

        self.assertEqual(self.stored("P1")["status"], "confirmed")

    # TC-41-14 · AC3, AC6 (Q3) — an approval refused by the database rule is a conflict.
    def test_approval_refused_by_the_database_rule_is_a_conflict(self):
        clash = self.add_booking("E3", "fully_recorded", "confirmed",
                                 datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))
        check = scheduling.blocking_bookings
        calls = []

        def checked_before_the_competing_save(*args):
            # The first check misses the clash, as if a competing approval that did not
            # take the lock saved it just after; any later check sees it.
            calls.append(args)
            return [] if len(calls) == 1 else check(*args)

        with mock.patch.object(scheduling, "blocking_bookings",
                               side_effect=checked_before_the_competing_save):
            response = self.approve("P1")

        body = self.assert_error(response, 409, reason="conflict")
        self.assertRegex(body["error"].lower(), r"clash")
        self.assertEqual(body["conflicts"], [{
            "type": "booking", "id": clash.id,
            "start": "2027-03-12T18:00:00", "end": "2027-03-12T20:00:00",
            "event": {"id": self.events["E3"].id, "title": "Product Launch"},
        }])
        self.assert_nothing_decided()


# ---------- AC7: the check cannot be completed ----------


class UnverifiedAvailabilityTests(ConflictCheckTestCase):
    # TC-41-15 · AC7 — approving when availability could not be verified.
    def test_unverified_availability_prevents_approval(self):
        booking_id = self.bookings["P1"].id
        headers = self.auth_headers(self.users["gus"])
        for label, matches in (VENUE_LOCK, CONFIRMED_BOOKINGS, BLOCKS):
            with self.subTest(failing=label):
                with self.statements_fail(matches):
                    response = self.approve(booking_id, headers=headers)

                body = self.assert_error(response, 503)
                self.assertIs(body.get("retryable"), True)
                self.assertRegex(body["error"].lower(), UNVERIFIED)
                self.assertNotIn("booking", body)
                self.assert_nothing_decided()

        self.assertEqual(self.approve("P1").status_code, 200)

    # TC-41-16 · AC7 (Q4) — the list when availability could not be verified.
    def test_list_reports_unverified_availability(self):
        headers = self.auth_headers(self.users["gus"])
        with self.statements_fail(BLOCKS[1]):
            response = self.listed(headers)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), UNVERIFIED)
        self.assertNotIn("bookings", body)


# ---------- Reopened 26 Oct 2026: AC1 adds unexpired tentative holds ----------
#
# Holds already conflict through SCRUM-87 (TC-87-13 to 18 cover AC1-AC6 for them);
# these close the gap for AC7, when the holds part of the check fails.


class UnverifiedHoldsTests(ConflictCheckTestCase):
    # TC-41-18 · AC1, AC7 — approving when the holds can't be read.
    def test_unreadable_holds_prevent_approval(self):
        booking_id = self.bookings["P1"].id
        headers = self.auth_headers(self.users["gus"])
        with self.statements_fail(HOLDS[1]):
            response = self.approve(booking_id, headers=headers)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), UNVERIFIED)
        self.assert_nothing_decided()
        self.assertEqual(self.approve("P1").status_code, 200)

    # TC-41-19 · AC1, AC7 — the pending list when the holds can't be read.
    def test_list_with_unreadable_holds_reports_unverified_availability(self):
        headers = self.auth_headers(self.users["gus"])
        with self.statements_fail(HOLDS[1]):
            response = self.listed(headers)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), UNVERIFIED)
        self.assertNotIn("bookings", body)


if __name__ == "__main__":
    unittest.main()
