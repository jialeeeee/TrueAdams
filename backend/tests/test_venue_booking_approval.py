"""Tests for SCRUM-40 "Approve a Venue Booking Request".

Each test names the case it automates from
docs/test-cases/SCRUM-40-approve-venue-booking.md (TC-40-xx) and the acceptance
criteria it checks. Assumptions A1-A8 and questions Q1-Q6 are defined there.
TC-40-01 (viewing pending requests) is SCRUM-39's TC-39-17, in
test_venue_booking_request.py.

Model (db/venue_booking_decisions.sql): new VenueBooking columns
    decided_at     DateTime, naive UTC: when the request was approved
    decided_by_id  FK users.id: the Venue Staff member who approved it

Endpoint
    POST /api/venues/bookings/<id>/approve     (no body)
        200 {"message", "booking": booking + {"decided_at", "decided_by"},
             "notification": {"in_app": true, "email_queued": bool}}
        401 session · 403 not Venue Staff · 404 unknown booking
        409 {"error", "reason": "not_pending" | "event_not_approved" | "already_started"
                                | "conflict", "conflicts": [...] (for "conflict")}
        503 {"error", "retryable": true} if saving fails
    conflict = {"type": "booking", "id", "start", "end", "event": {"id", "title"} | null}
             | {"type": "block", "id", "start", "end", "reason"}

The coordinator's email is queued through tasks.send_notification_email, mocked here.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import SQLAlchemyError

from app import tasks
from app.models import Event, Notification, VenueBlock, VenueBooking
from tests import seed_data
from tests.base import AppTestCase

REQUIREMENTS = "Open-air waterfront space for 250, stage power"

# VA-SEED events, all approved and organised by dana. `coordinator` is a USERS key.
EVENTS = {
    "E1": {"title": "Harbour Lights Festival", "coordinator": "alice",
           "start_time": datetime(2027, 3, 12, 17, 0), "end_time": datetime(2027, 3, 12, 22, 0),
           "expected_attendance": 250},
    "E2": {"title": "Winter Networking Night", "coordinator": "ben",
           "start_time": datetime(2027, 4, 3, 18, 0), "end_time": datetime(2027, 4, 3, 21, 0),
           "expected_attendance": 80},
    "E3": {"title": "Product Launch", "coordinator": "alice",
           "start_time": datetime(2027, 3, 20, 10, 0), "end_time": datetime(2027, 3, 20, 12, 0),
           "expected_attendance": 60},
}
P1_START, P1_END = datetime(2027, 3, 12, 16, 0), datetime(2027, 3, 12, 22, 30)


class ApprovalTestCase(AppTestCase):
    """Inserts VA-SEED, mocks the email queue and wraps the approve endpoint."""

    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.venues = self.seed_venues(seed_data.VENUES)
        self.events = {}
        for key, row in EVENTS.items():
            fields = {k: v for k, v in row.items() if k != "coordinator"}
            self.events[key] = Event(organiser_id=self.users["dana"].id, status="approved",
                                     coordinator_id=self.users[row["coordinator"]].id, **fields)
            self.db.session.add(self.events[key])
        self.db.session.commit()
        self.bookings = {
            "P1": self.add_booking("E1", "fully_recorded", "pending", P1_START, P1_END,
                                   requested_by="alice"),
            "P2": self.add_booking("E2", "recorded_as_none", "pending",
                                   datetime(2027, 4, 3, 17, 0), datetime(2027, 4, 3, 21, 30),
                                   requested_by="ben"),
        }

        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.queue_email = patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- Seeding ----------

    def add_booking(self, event, venue, status, start, end, requested_by=None):
        booking = VenueBooking(
            event_id=self.events[event].id if event else None,
            venue_id=self.venues[venue].id, status=status, start_time=start, end_time=end,
            venue_requirements=REQUIREMENTS if requested_by else None,
            requested_by_id=self.users[requested_by].id if requested_by else None,
        )
        self.db.session.add(booking)
        self.db.session.commit()
        return booking

    def add_block(self, venue, reason, start, end):
        block = VenueBlock(venue_id=self.venues[venue].id, reason=reason,
                           start_time=start, end_time=end)
        self.db.session.add(block)
        self.db.session.commit()
        return block

    # ---------- Requests ----------

    def approve(self, booking, as_user="gus", headers=None):
        booking_id = booking if isinstance(booking, int) else self.bookings[booking].id
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.post(f"/api/venues/bookings/{booking_id}/approve", headers=headers)

    # ---------- Reading what was saved ----------

    def stored(self, booking):
        self.db.session.expire_all()
        row = self.db.session.get(VenueBooking, self.bookings[booking].id
                                  if isinstance(booking, str) else booking.id)
        return {c.name: getattr(row, c.name) for c in VenueBooking.__table__.columns}

    def event(self, key):
        self.db.session.expire_all()
        return self.db.session.get(Event, self.events[key].id)

    def notifications_for(self, user_key):
        self.db.session.expire_all()
        return Notification.query.filter_by(recipient_id=self.users[user_key].id).all()

    # ---------- Assertions ----------

    def assert_error(self, response, status_code, reason=None):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        if reason is not None:
            self.assertEqual(body.get("reason"), reason)
        return body

    def assert_nothing_decided(self, booking="P1", event="E1"):
        """The request is still pending with no decision, and nothing was announced."""
        stored = self.stored(booking)
        self.assertEqual(stored["status"], "pending")
        self.assertIsNone(stored["decided_at"])
        self.assertIsNone(stored["decided_by_id"])
        self.assertIsNone(self.event(event).venue_id)
        for user in ("alice", "ben", "dana", "gus"):
            self.assertEqual(self.notifications_for(user), [], user)
        self.queue_email.assert_not_called()


# ---------- AC2: only pending requests can be approved ----------


class OnlyPendingTests(ApprovalTestCase):
    # TC-40-03 · AC2 — a request that is not pending cannot be approved.
    def test_request_that_is_not_pending_cannot_be_approved(self):
        cases = {
            "confirmed": self.add_booking("E3", "fully_recorded", "confirmed",
                                          datetime(2027, 5, 1, 10, 0), datetime(2027, 5, 1, 12, 0)),
            "rejected": self.add_booking("E2", "fully_recorded", "rejected",
                                         datetime(2027, 5, 2, 10, 0), datetime(2027, 5, 2, 12, 0)),
            "cancelled": self.add_booking("E3", "recorded_as_none", "cancelled",
                                          datetime(2027, 5, 3, 10, 0), datetime(2027, 5, 3, 12, 0)),
        }
        for status, booking in cases.items():
            with self.subTest(status=status):
                before = self.stored(booking)
                body = self.assert_error(self.approve(booking.id), 409, reason="not_pending")
                self.assertIn(status, body["error"])
                self.assertEqual(self.stored(booking), before)
        self.queue_email.assert_not_called()

    # TC-40-04 · AC2 — approving twice keeps the first decision.
    def test_approving_twice_keeps_the_first_decision(self):
        self.assertEqual(self.approve("P1").status_code, 200)
        decided = self.stored("P1")

        self.assert_error(self.approve("P1"), 409, reason="not_pending")

        self.assertEqual(self.stored("P1"), decided)
        self.assertEqual(len(self.notifications_for("alice")), 1)
        self.queue_email.assert_called_once()

    # TC-40-05 · AC2 (A1/Q1) — only Venue Staff can approve.
    def test_only_venue_staff_can_approve(self):
        for user in ("alice", "dana", "hana", "farah", "admin"):
            with self.subTest(user=user):
                self.assert_error(self.approve("P1", as_user=user), 403)
        self.assert_nothing_decided()

    # TC-40-06 · AC2 — a valid session is required.
    def test_a_valid_session_is_required(self):
        ghost = self.make_user(role="venue_staff")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["gus"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                self.assertEqual(self.approve("P1", headers=headers).status_code, 401)
        self.assert_nothing_decided()

    # TC-40-07 · AC2 — unknown booking.
    def test_unknown_booking_returns_not_found(self):
        body = self.assert_error(self.approve(self.missing_id(VenueBooking)), 404)

        self.assertEqual(body["error"], "Booking request not found.")


# ---------- AC3 and AC5: conflicts block approval and are explained ----------


class ConflictTests(ApprovalTestCase):
    # TC-40-08, TC-40-25 · AC3, AC5 — an overlapping confirmed booking blocks approval.
    def test_overlapping_confirmed_booking_blocks_approval(self):
        clash = self.add_booking("E3", "fully_recorded", "confirmed",
                                 datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))

        body = self.assert_error(self.approve("P1"), 409, reason="conflict")

        self.assertRegex(body["error"].lower(), r"clash|conflict")
        self.assertEqual(body["conflicts"], [{
            "type": "booking", "id": clash.id,
            "start": "2027-03-12T18:00:00", "end": "2027-03-12T20:00:00",
            "event": {"id": self.events["E3"].id, "title": "Product Launch"},
        }])
        self.assert_nothing_decided()

    # TC-40-09, TC-40-25 · AC3, AC5 — an overlapping block blocks approval.
    def test_overlapping_block_blocks_approval(self):
        block = self.add_block("fully_recorded", "Electrical works",
                               datetime(2027, 3, 12, 15, 0), datetime(2027, 3, 12, 17, 0))

        body = self.assert_error(self.approve("P1"), 409, reason="conflict")

        self.assertEqual(body["conflicts"], [{
            "type": "block", "id": block.id,
            "start": "2027-03-12T15:00:00", "end": "2027-03-12T17:00:00",
            "reason": "Electrical works",
        }])
        self.assert_nothing_decided()

    # TC-40-10 · AC3, AC5 — every conflict is listed, in time order.
    def test_every_conflict_is_listed_in_time_order(self):
        clash = self.add_booking(None, "fully_recorded", "confirmed",
                                 datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))
        block = self.add_block("fully_recorded", None,
                               datetime(2027, 3, 12, 15, 0), datetime(2027, 3, 12, 17, 0))

        body = self.assert_error(self.approve("P1"), 409, reason="conflict")

        self.assertEqual([(c["type"], c["id"]) for c in body["conflicts"]],
                         [("block", block.id), ("booking", clash.id)])
        self.assertIsNone(body["conflicts"][0]["reason"])
        self.assertIsNone(body["conflicts"][1]["event"])

    # TC-40-11 · AC3 (boundary) — periods that only touch do not conflict.
    def test_periods_that_only_touch_do_not_conflict(self):
        self.add_booking("E3", "fully_recorded", "confirmed",
                         datetime(2027, 3, 12, 12, 0), P1_START)
        self.add_block("fully_recorded", "Cleaning", P1_END, datetime(2027, 3, 12, 23, 0))

        self.assertEqual(self.approve("P1").status_code, 200)

    # TC-40-12 · AC3 (Q2) — pending, rejected and cancelled bookings do not conflict.
    def test_bookings_that_are_not_confirmed_do_not_conflict(self):
        self.add_booking("E3", "fully_recorded", "pending",
                         datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))
        self.add_booking("E2", "fully_recorded", "rejected",
                         datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))
        self.add_booking("E3", "fully_recorded", "cancelled",
                         datetime(2027, 3, 12, 18, 0), datetime(2027, 3, 12, 20, 0))

        self.assertEqual(self.approve("P1").status_code, 200)

    # TC-40-13 · AC3 — another venue's bookings and blocks do not conflict.
    def test_another_venues_bookings_and_blocks_do_not_conflict(self):
        self.add_booking("E3", "recorded_as_none", "confirmed", P1_START, P1_END)
        self.add_block("recorded_as_none", "Painting", P1_START, P1_END)

        self.assertEqual(self.approve("P1").status_code, 200)

    # TC-40-14 · AC3 (Q2) — suitability does not block approval.
    def test_suitability_does_not_block_approval(self):
        with self.subTest(case="outside operating hours"):  # P2: Civic Hall on a Saturday
            self.assertEqual(self.approve("P2").status_code, 200)

        with self.subTest(case="venue not currently bookable"):
            dockside = self.add_booking("E3", "unavailable", "pending",
                                        datetime(2027, 3, 20, 9, 0), datetime(2027, 3, 20, 13, 0),
                                        requested_by="alice")
            self.assertEqual(self.approve(dockside.id).status_code, 200)

        with self.subTest(case="capacity smaller than attendance"):
            self.bookings["P1"].status = "rejected"
            self.db.session.commit()
            small = self.add_booking("E1", "recorded_as_none", "pending",
                                     datetime(2027, 3, 12, 10, 0), datetime(2027, 3, 12, 12, 0),
                                     requested_by="alice")
            self.assertEqual(self.approve(small.id).status_code, 200)

    # TC-40-15 (an event can have only one confirmed venue) is replaced by SCRUM-85,
    # which lets an event have several: see test_several_venues.py (TC-85-07, 09).

    # TC-40-16 · AC3 (A7) — decisions on the same venue are made one at a time.
    def test_booking_and_venue_rows_are_locked_before_the_conflict_check(self):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(" ".join(statement.split()))

        sa_event.listen(self.db.engine, "before_cursor_execute", record)
        try:
            response = self.approve("P1")
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


# ---------- AC4: approval confirms the booking and is visible to the coordinator ----------


class ApproveTests(ApprovalTestCase):
    # TC-40-17 · AC4 — approving confirms the booking and records the decision.
    def test_approving_confirms_the_booking_and_records_the_decision(self):
        started = datetime.utcnow()

        response = self.approve("P1")

        finished = datetime.utcnow()
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        stored = self.stored("P1")
        gus = self.users["gus"]
        self.assertEqual(
            (stored["status"], stored["event_id"], stored["venue_id"],
             stored["start_time"], stored["end_time"], stored["decided_by_id"]),
            ("confirmed", self.events["E1"].id, self.venues["fully_recorded"].id,
             P1_START, P1_END, gus.id),
        )
        self.assertTrue(started <= stored["decided_at"] <= finished)
        booking = body["booking"]
        self.assertEqual(booking["id"], self.bookings["P1"].id)
        self.assertEqual(booking["status"], "confirmed")
        self.assertEqual(booking["decided_at"], stored["decided_at"].isoformat())
        self.assertEqual(booking["decided_by"], {"id": gus.id, "email": gus.email})
        self.assertEqual(booking["venue"]["name"], "Aurora Ballroom")
        for text in ("Aurora Ballroom", "Harbour Lights Festival", self.users["alice"].email):
            self.assertIn(text, body["message"])
        self.assertEqual(body["notification"], {"in_app": True, "email_queued": True})

    # TC-40-18 · AC4 (Q5) — the event's venue is set; its status is unchanged.
    def test_events_venue_is_set_and_status_unchanged(self):
        before = self.event("E1")
        before = {c.name: getattr(before, c.name) for c in Event.__table__.columns}

        self.approve("P1")

        after = self.event("E1")
        after = {c.name: getattr(after, c.name) for c in Event.__table__.columns}
        aurora = self.venues["fully_recorded"]
        self.assertEqual(after.pop("venue_id"), aurora.id)
        before.pop("venue_id")
        self.assertEqual(after, before)
        self.assertEqual(after["status"], "approved")

        planning = self.client.get(f"/api/events/{self.events['E1'].id}/planning",
                                   headers=self.auth_headers(self.users["alice"])).get_json()
        self.assertEqual(planning["venue"], {"id": aurora.id, "name": "Aurora Ballroom",
                                             "location": aurora.location})

    # TC-40-19 · AC4 — the confirmed booking now blocks the venue.
    def test_confirmed_booking_now_blocks_the_venue(self):
        self.approve("P1")
        alice = self.auth_headers(self.users["alice"])
        aurora = self.venues["fully_recorded"]

        calendar = self.client.get(f"/api/venues/{aurora.id}/availability", headers=alice,
                                   query_string={"from": "2027-03-12"}).get_json()
        self.assertIn(("booking", self.bookings["P1"].id),
                      [(p["type"], p["id"]) for p in calendar["periods"]])
        at_six = next(s for s in calendar["days"][0]["slots"]
                      if s["start"] <= "2027-03-12T18:00:00" < s["end"])
        self.assertEqual(at_six["status"], "unavailable")

        found = self.client.get("/api/venues/search", headers=alice, query_string={
            "date": "2027-03-12", "start": "18:00", "end": "20:00"}).get_json()
        self.assertNotIn(aurora.id, [v["id"] for v in found["venues"]])

        pending = self.client.get("/api/venues/bookings",
                                  headers=self.auth_headers(self.users["gus"])).get_json()
        self.assertNotIn(self.bookings["P1"].id, [b["id"] for b in pending["bookings"]])

    # TC-40-20 · AC4 (Q6) — the coordinator is notified in the app.
    def test_coordinator_is_notified_in_the_app(self):
        self.approve("P1")

        [notification] = self.notifications_for("alice")
        self.assertEqual((notification.kind, notification.event_id),
                         ("venue_booking_approved", self.events["E1"].id))
        for text in ("Aurora Ballroom", "2027-03-12 16:00", "2027-03-12 22:30",
                     self.users["gus"].email):
            self.assertIn(text, notification.message)
        listed = self.client.get("/api/notifications/",
                                 headers=self.auth_headers(self.users["alice"])).get_json()
        self.assertEqual([n["kind"] for n in listed["notifications"]], ["venue_booking_approved"])
        for user in ("ben", "dana", "gus"):
            with self.subTest(user=user):
                self.assertEqual(self.notifications_for(user), [])

    # TC-40-21 · AC4 — the coordinator is emailed.
    def test_coordinator_is_emailed(self):
        self.approve("P1")

        self.queue_email.assert_called_once()
        to_address, subject, body = self.queue_email.call_args.args
        self.assertEqual(to_address, self.users["alice"].email)
        self.assertIn("Harbour Lights Festival", subject)
        self.assertIn("Aurora Ballroom", subject)
        self.assertIn("approved", body.lower())

    # TC-40-22 · AC4 — the approval stands when the email cannot be queued.
    def test_approval_stands_when_the_email_cannot_be_queued(self):
        self.queue_email.side_effect = ConnectionError("Redis is down")

        response = self.approve("P1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": False})
        self.assertEqual(self.stored("P1")["status"], "confirmed")
        self.assertEqual(len(self.notifications_for("alice")), 1)


# ---------- AC6: a failed save changes nothing ----------


class SaveFailureTests(ApprovalTestCase):
    def approve_with_failing_commit(self):
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            return self.approve("P1")

    # TC-40-27 · AC6 — saving fails: nothing changes and an error is returned.
    def test_failed_save_changes_nothing(self):
        response = self.approve_with_failing_commit()

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not saved")
        self.assertRegex(body["error"].lower(), r"try again")
        self.assertNotIn("booking", body)
        self.assert_nothing_decided()

    # TC-40-28 · AC6 — retry succeeds after recovery.
    def test_retry_succeeds_after_recovery(self):
        self.approve_with_failing_commit()

        self.assertEqual(self.approve("P1").status_code, 200)
        self.assertEqual(self.stored("P1")["status"], "confirmed")
        self.assertEqual(len(self.notifications_for("alice")), 1)


# ---------- Other states that prevent approval (AC3, A4) ----------


class EventStateTests(ApprovalTestCase):
    # TC-40-30 · AC3 (Q4) — the event is no longer approved.
    def test_event_no_longer_approved_blocks_approval(self):
        for status in ("cancelled", "rejected"):
            with self.subTest(status=status):
                self.events["E1"].status = status
                self.db.session.commit()

                body = self.assert_error(self.approve("P1"), 409, reason="event_not_approved")

                self.assertIn(status, body["error"])
                self.assertEqual(self.stored("P1")["status"], "pending")

    # TC-40-31 · AC3 (Q4) — the requested time has already started.
    def test_requested_time_already_started_blocks_approval(self):
        past = self.add_booking("E3", "fully_recorded", "pending",
                                datetime(2020, 1, 1, 10, 0), datetime(2020, 1, 1, 12, 0),
                                requested_by="alice")

        self.assert_error(self.approve(past.id), 409, reason="already_started")

        self.assertEqual(self.stored(past)["status"], "pending")


if __name__ == "__main__":
    unittest.main()
