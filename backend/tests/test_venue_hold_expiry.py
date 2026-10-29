"""Tests for SCRUM-86 "Tentative Venue Holds Expire".

Each test names the case it automates from
docs/test-cases/SCRUM-86-tentative-holds-expire.md (TC-86-xx) and the acceptance
criteria it checks. Assumptions A1-A9 and questions Q1-Q6 are defined there.

Model (db/venue_hold_expiry.sql): VenueBooking.hold_warned_at, naive UTC: when the
coordinator was told the hold expires within 24 hours. An expired hold is stored with
the status "expired" by the expiry check, and shown as expired from its expiry.

Endpoint (JWT required, else 401)
    POST /api/venues/bookings/<id>/confirm   (the event's current coordinator, else 403)
        200 {"message", "booking", "notification": {"in_app", "email_queued"}}
        404 unknown booking
        409 {"error", "reason"}  not_a_hold | expired | event_not_approved | conflict (+conflicts)
        503 {"error", "retryable": true}

Background job
    tasks.check_hold_expiries, every 300 s (Celery beat "check-hold-expiries"):
    records expired holds and tells the coordinator ("venue_hold_expired"), and warns
    them once about holds expiring within 24 hours ("venue_hold_expiring").

"Now" is fixed at NOW (Singapore time) unless a case says otherwise.
"""

import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import SQLAlchemyError

from app import local_time, tasks
from app.extensions import celery
from app.models import VenueBooking
from app.venues import scheduling
from tests.test_venue_booking_conflicts import BLOCKS
from tests.test_venue_holds import (EXPIRED_AT, EXPIRY_AT, H2_END, H2_START, HELD_AT, NOW,
                                    HoldTestCase)

P3_START, P3_END = H2_START, H2_END
IN_24_HOURS = NOW + timedelta(hours=24)
CONFIRMED = "venue_hold_confirmed"
EXPIRING = "venue_hold_expiring"
EXPIRED = "venue_hold_expired"


class HoldExpiryTestCase(HoldTestCase):
    """HE-SEED: SCRUM-87's VH-SEED. H1 is P1 held by gus, made by each case as it needs."""

    @contextmanager
    def at(self, now):
        """Every clock the routes and the expiry check read says `now` (Singapore time)."""
        with mock.patch("app.venues.routes.singapore_now", return_value=now), \
                mock.patch("app.venues.hold_expiry.singapore_now", return_value=now):
            yield

    def run_check(self, now=NOW):
        with self.at(now):
            tasks.check_hold_expiries()

    def confirm(self, booking="P1", as_user="alice", headers=None):
        booking_id = booking if isinstance(booking, int) else (
            self.bookings[booking].id if isinstance(booking, str) else booking.id)
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.post(f"/api/venues/bookings/{booking_id}/confirm", headers=headers)

    def coordinator_list(self, event="E1", as_user="alice"):
        response = self.client.get("/api/venues/bookings",
                                   query_string={"event_id": self.events[event].id},
                                   headers=self.auth_headers(self.users[as_user]))
        self.assertEqual(response.status_code, 200, response.get_json())
        return {b["id"]: b for b in response.get_json()["bookings"]}

    def kinds(self, user):
        return [n.kind for n in self.notifications_for(user)]

    def notices(self, user, kind):
        return [n for n in self.notifications_for(user) if n.kind == kind]

    def emails_to(self, *users):
        """(subject, body) of each email queued to these seeded users. The check runs over
        every hold, so real holds in a shared database may be emailed about too."""
        addresses = {self.users[user].email for user in users}
        return [call.args[1:] for call in self.queue_email.call_args_list
                if call.args[0] in addresses]

    def warn(self, booking):
        """Record that the coordinator was already warned about this hold."""
        booking.hold_warned_at = HELD_AT
        self.db.session.commit()

    def failing_commit(self):
        return mock.patch.object(self.db.session, "commit",
                                 side_effect=SQLAlchemyError("simulated outage"))

    def assert_not_confirmed(self, booking="P1", status="tentative"):
        """Still a hold with no decision, E1 has no venue, and no confirmation went out."""
        stored = self.stored(booking)
        self.assertEqual(stored["status"], status)
        self.assertIsNone(stored["decided_at"])
        self.assertIsNone(stored["decided_by_id"])
        self.assertIsNone(self.event("E1").venue_id)
        for user in ("alice", "ben", "dana", "gus"):
            self.assertEqual(self.notices(user, CONFIRMED), [], user)
        for call in self.queue_email.call_args_list:
            self.assertNotIn("confirmed", call.args[1].lower())


# ---------- AC1: confirming a hold ----------


class ConfirmTests(HoldExpiryTestCase):
    # TC-86-01 · AC1 — the coordinator confirms an unexpired hold.
    def test_coordinator_confirms_an_unexpired_hold(self):
        self.make_hold("P1")

        response = self.confirm()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual((body["booking"]["status"], body["booking"]["hold"]), ("confirmed", None))
        self.assertIn("Aurora Ballroom", body["message"])
        self.assertIn("Harbour Lights Festival", body["message"])
        stored = self.stored("P1")
        self.assertEqual((stored["status"], stored["decided_by_id"]),
                         ("confirmed", self.users["alice"].id))
        self.assertIsNotNone(stored["decided_at"])
        self.assertEqual((stored["held_at"], stored["held_by_id"], stored["hold_expires_at"]),
                         (HELD_AT, self.users["gus"].id, EXPIRY_AT))
        self.assertEqual(self.event("E1").venue_id, self.venues["fully_recorded"].id)

    # TC-86-02 · AC1 — a confirmed hold is a confirmed booking.
    def test_confirmed_hold_is_a_confirmed_booking(self):
        self.make_hold("P1")
        p3 = self.add_booking("E3", "fully_recorded", "pending", P3_START, P3_END,
                              requested_by="alice")

        self.assertEqual(self.confirm().status_code, 200)

        held = [h["id"] for h in self.holds().get_json()["holds"]]
        self.assertNotIn(self.bookings["P1"].id, held)
        body = self.assert_error(self.approve(p3.id), 409, reason="conflict")
        self.assertIn(("booking", self.bookings["P1"].id),
                      [(c["type"], c["id"]) for c in body["conflicts"]])

    # TC-86-03 · AC1 (SCRUM-85 A4) — the event's main venue stays.
    def test_events_main_venue_is_kept(self):
        self.make_hold("P1")
        self.add_booking("E1", "recorded_as_none", "confirmed",
                         datetime(2027, 3, 13, 10, 0), datetime(2027, 3, 13, 12, 0))
        civic = self.venues["recorded_as_none"].id
        self.events["E1"].venue_id = civic
        self.db.session.commit()

        self.assertEqual(self.confirm().status_code, 200)

        self.assertEqual(self.event("E1").venue_id, civic)

    # TC-86-04 · AC1 (A5, Q4) — Venue Staff are told the hold was confirmed.
    def test_venue_staff_are_told_the_hold_was_confirmed(self):
        self.users["vera"] = self.make_user(role="venue_staff")
        self.make_hold("P1")

        response = self.confirm()

        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": True})
        for user in ("gus", "vera"):
            with self.subTest(user=user):
                [notice] = self.notices(user, CONFIRMED)
                self.assertEqual(notice.event_id, self.events["E1"].id)
                for text in (self.users["alice"].email, "Aurora Ballroom",
                             "Harbour Lights Festival", "2027-03-12 16:00", "2027-03-12 22:30"):
                    self.assertIn(text, notice.message)
        addresses = [call.args[0] for call in self.queue_email.call_args_list]
        self.assertEqual(addresses.count(self.users["gus"].email), 1)
        self.assertEqual(addresses.count(self.users["vera"].email), 1)
        self.assertEqual(self.notifications_for("alice"), [])

    # TC-86-05 · AC1 — the confirmation stands when the email can't be queued.
    def test_confirmation_stands_when_the_email_cannot_be_queued(self):
        self.make_hold("P1")
        self.queue_email.side_effect = ConnectionError("Redis is down")

        response = self.confirm()

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": False})
        self.assertEqual(self.stored("P1")["status"], "confirmed")
        self.assertEqual(len(self.notices("gus", CONFIRMED)), 1)

    # TC-86-06 · AC1 (A2, Q1) — conflicts are checked again.
    def test_confirming_rechecks_conflicts(self):
        self.make_hold("P1")
        block = self.add_block("fully_recorded", "Electrical works", H2_START, H2_END)

        body = self.assert_error(self.confirm(), 409, reason="conflict")

        self.assertEqual([(c["type"], c["id"]) for c in body["conflicts"]],
                         [("block", block.id)])
        self.assert_not_confirmed()

    # TC-86-07 · AC1 — only a hold can be confirmed.
    def test_only_a_hold_can_be_confirmed(self):
        others = {
            status: self.add_booking("E1", "recorded_as_none", status,
                                     datetime(2027, 3, 13 + day, 10, 0),
                                     datetime(2027, 3, 13 + day, 12, 0))
            for day, status in enumerate(("confirmed", "rejected", "cancelled"))
        }
        cases = {"pending": self.bookings["P1"], **others}
        for status, booking in cases.items():
            with self.subTest(status=status):
                self.assert_error(self.confirm(booking), 409, reason="not_a_hold")
                self.assertEqual(self.stored(booking)["status"], status)

    # TC-86-08 · AC1 (A2, Q1) — the event must still be approved.
    def test_event_must_still_be_approved(self):
        self.make_hold("P1")
        self.events["E1"].status = "cancelled"
        self.db.session.commit()

        self.assert_error(self.confirm(), 409, reason="event_not_approved")
        self.assertEqual(self.stored("P1")["status"], "tentative")

    # TC-86-09 · AC1 — unknown booking.
    def test_unknown_booking_is_not_found(self):
        self.assert_error(self.confirm(self.missing_id(VenueBooking)), 404)

    # TC-86-10 · AC1 (A2) — the booking and venue are locked before the conflict check.
    def test_booking_and_venue_rows_are_locked_before_the_conflict_check(self):
        self.make_hold("P1")
        headers = self.auth_headers(self.users["alice"])
        booking_id = self.bookings["P1"].id
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(" ".join(statement.split()))

        sa_event.listen(self.db.engine, "before_cursor_execute", record)
        try:
            response = self.confirm(booking_id, headers=headers)
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


# ---------- AC2: after the expiry ----------


class ExpiredTests(HoldExpiryTestCase):
    # TC-86-11 · AC2 (boundary) — at its expiry the hold is Expired, before the check runs.
    def test_hold_is_expired_from_its_expiry(self):
        self.make_hold("P1", expires_at=NOW)

        for label in ("before the check", "once recorded"):
            with self.subTest(hold=label):
                if label == "once recorded":
                    self.run_check()
                listed = self.coordinator_list()[self.bookings["P1"].id]

                self.assertEqual(listed["status"], "expired")
                self.assertEqual(listed["hold"],
                                 {"expires_at": "2027-03-01T12:00:00", "expired": True})
                held = [h["id"] for h in self.holds().get_json()["holds"]]
                self.assertNotIn(self.bookings["P1"].id, held)

    # TC-86-12 · AC2 (boundary) — the expiry check records expired holds.
    def test_expiry_check_records_expired_holds(self):
        h1 = self.make_hold("P1", expires_at=NOW)
        h2 = self.add_hold("E3", "fully_recorded", H2_START, H2_END, expires_at=EXPIRED_AT)
        h3 = self.make_hold("P2", expires_at=NOW + timedelta(minutes=1))

        self.run_check()

        self.assertEqual([self.stored(h)["status"] for h in (h1, h2, h3)],
                         ["expired", "expired", "tentative"])

    # TC-86-13 · AC2 — an expired hold is never treated as a confirmed booking.
    def test_expired_hold_is_never_a_confirmed_booking(self):
        self.make_hold("P1", expires_at=NOW)
        self.run_check()
        p3 = self.add_booking("E3", "fully_recorded", "pending", P3_START, P3_END,
                              requested_by="alice")

        self.assertEqual(self.approve(p3.id).status_code, 200)

        self.assertEqual(self.stored(p3)["status"], "confirmed")
        self.assertIsNone(self.event("E1").venue_id)

    # TC-86-14 · AC2 (SCRUM-87 AC3) — a recorded Expired hold's expiry can't be changed.
    def test_recorded_expired_hold_cannot_be_changed(self):
        self.make_hold("P1", expires_at=NOW)
        self.run_check()

        self.assert_error(self.change_expiry("P1", "2027-03-05T12:00"), 409, reason="expired")

        stored = self.stored("P1")
        self.assertEqual((stored["status"], stored["hold_expires_at"]), ("expired", NOW))

    # TC-86-15 · AC2 — the check leaves confirmed bookings alone.
    def test_expiry_check_leaves_confirmed_bookings_alone(self):
        hold = self.make_hold("P1", expires_at=EXPIRED_AT)
        hold.status = "confirmed"
        self.db.session.commit()

        self.run_check()

        self.assertEqual(self.stored("P1")["status"], "confirmed")
        self.assertEqual(self.notifications_for("alice"), [])
        self.assertEqual(self.emails_to("alice"), [])


# ---------- AC3: the coordinator is notified ----------


class NotificationTests(HoldExpiryTestCase):
    # TC-86-16 · AC3 (boundary) — the coordinator is warned 24 hours before.
    def test_coordinator_is_warned_24_hours_before(self):
        self.make_hold("P1", expires_at=IN_24_HOURS)
        self.make_hold("P2", expires_at=IN_24_HOURS + timedelta(minutes=1))

        self.run_check()

        [notice] = self.notifications_for("alice")
        self.assertEqual((notice.kind, notice.event_id), (EXPIRING, self.events["E1"].id))
        for text in ("Aurora Ballroom", "2027-03-12 16:00", "2027-03-12 22:30",
                     "2027-03-02 12:00"):
            self.assertIn(text, notice.message)
        self.assertRegex(notice.message.lower(), r"confirm")
        [(subject, body)] = self.emails_to("alice")
        self.assertIn("Aurora Ballroom", subject)
        self.assertIn("2027-03-02 12:00", body)
        self.assertIsNotNone(self.stored("P1")["hold_warned_at"])
        self.assertEqual(self.notifications_for("ben"), [])
        self.assertEqual(self.emails_to("ben"), [])
        self.assertIsNone(self.stored("P2")["hold_warned_at"])

    # TC-86-17 · AC3 — the warning is sent once.
    def test_warning_is_sent_once(self):
        self.make_hold("P1", expires_at=IN_24_HOURS)

        self.run_check()
        self.run_check()

        self.assertEqual(self.kinds("alice"), [EXPIRING])
        self.assertEqual(len(self.emails_to("alice")), 1)

    # TC-86-18 · AC3, AC4 — the coordinator is told when the hold expires.
    def test_coordinator_is_told_when_the_hold_expires(self):
        self.warn(self.make_hold("P1", expires_at=NOW))

        self.run_check()
        self.run_check()

        [notice] = self.notifications_for("alice")
        self.assertEqual((notice.kind, notice.event_id), (EXPIRED, self.events["E1"].id))
        for text in ("Aurora Ballroom", "2027-03-12 16:00", "2027-03-12 22:30",
                     "2027-03-01 12:00"):
            self.assertIn(text, notice.message)
        self.assertRegex(notice.message.lower(), r"new venue request")
        [(_, body)] = self.emails_to("alice")
        self.assertIn("2027-03-01 12:00", body)
        self.assertRegex(body.lower(), r"new venue request")

    # TC-86-19 · AC3 (Q3) — no separate warning for a hold placed with under 24 hours.
    def test_no_separate_warning_for_a_hold_placed_with_under_24_hours(self):
        self.assertEqual(self.hold("P1", "2027-03-01T17:00").status_code, 200)
        self.queue_email.reset_mock()

        self.run_check()

        self.assertEqual(self.kinds("alice"), ["venue_hold_placed"])
        self.assertEqual(self.emails_to("alice"), [])

    # TC-86-20 · AC3 (Q3) — changing the expiry makes the warning due again, or not.
    def test_changing_the_expiry_rearms_the_warning(self):
        self.warn(self.make_hold("P1", expires_at=datetime(2027, 3, 1, 17, 0)))
        later = datetime(2027, 3, 4, 12, 0)

        self.assertEqual(self.change_expiry("P1", "2027-03-05T12:00").status_code, 200)
        self.assertIsNone(self.stored("P1")["hold_warned_at"])
        self.run_check()
        self.assertEqual(self.notices("alice", EXPIRING), [])

        self.run_check(later)
        [warning] = self.notices("alice", EXPIRING)
        self.assertIn("2027-03-05 12:00", warning.message)

        with self.at(later):
            self.assertEqual(self.change_expiry("P1", "2027-03-04T18:00").status_code, 200)
        self.run_check(later)
        self.assertEqual(len(self.notices("alice", EXPIRING)), 1)

    # TC-86-21 · AC3 — a hold found already expired gets only the expiry notice.
    def test_expired_hold_gets_only_the_expiry_notice(self):
        self.make_hold("P1", expires_at=EXPIRED_AT)

        self.run_check()

        self.assertEqual(self.kinds("alice"), [EXPIRED])

    # TC-86-22 · AC3 — the check carries on when an email can't be queued.
    def test_check_carries_on_when_an_email_cannot_be_queued(self):
        self.make_hold("P1", expires_at=NOW)
        self.make_hold("P2", expires_at=datetime(2027, 3, 2, 10, 0))
        self.queue_email.side_effect = ConnectionError("Redis is down")

        self.run_check()

        self.assertEqual(self.stored("P1")["status"], "expired")
        self.assertIsNotNone(self.stored("P2")["hold_warned_at"])
        self.assertEqual(self.kinds("alice"), [EXPIRED])
        self.assertEqual(self.kinds("ben"), [EXPIRING])

    # TC-86-23 · AC3 — a failed check changes nothing.
    def test_failed_check_changes_nothing(self):
        self.make_hold("P1", expires_at=NOW)

        with self.failing_commit():
            self.run_check()

        self.assertEqual(self.stored("P1")["status"], "tentative")
        self.assertEqual(self.notifications_for("alice"), [])
        self.assertEqual(self.emails_to("alice"), [])

        self.run_check()
        self.assertEqual(self.stored("P1")["status"], "expired")
        self.assertEqual(self.kinds("alice"), [EXPIRED])

    # TC-86-24 · AC2, AC3 — a hold with nobody to tell still expires.
    def test_hold_without_a_coordinator_still_expires(self):
        hold = self.make_hold(
            self.add_booking(None, "fully_recorded", "tentative", H2_START, H2_END),
            expires_at=NOW)

        self.run_check()

        self.assertEqual(self.stored(hold)["status"], "expired")
        self.assertEqual(self.emails_to(*self.users), [])

    # TC-86-25 · AC3 (Q2) — the check runs every 5 minutes.
    def test_check_runs_every_five_minutes(self):
        entry = celery.conf.beat_schedule.get("check-hold-expiries")

        self.assertEqual(entry, {"task": "tasks.check_hold_expiries", "schedule": 300})
        self.assertIn("tasks.check_hold_expiries", celery.tasks)


# ---------- AC4: an expired hold can't be confirmed ----------


class ExpiredConfirmTests(HoldExpiryTestCase):
    # TC-86-26 · AC4 (boundary) — confirming an expired hold is refused.
    def test_expired_hold_cannot_be_confirmed(self):
        self.make_hold("P1", expires_at=NOW)

        for label, status in (("at its expiry", "tentative"), ("recorded", "expired")):
            with self.subTest(hold=label):
                if status == "expired":
                    self.run_check()
                body = self.assert_error(self.confirm(), 409, reason="expired")
                self.assertIn("2027-03-01 12:00", body["error"])
                self.assertRegex(body["error"].lower(), r"new venue request")
                self.assert_not_confirmed(status=status)

    # TC-86-35 · AC4 (boundary, PR review) — the hold expires while it is being confirmed.
    def test_hold_expiring_during_confirmation_is_not_confirmed(self):
        self.make_hold("P1", expires_at=NOW)
        clock = [NOW - timedelta(minutes=1)]
        read_blocks = scheduling.blocks

        def slow_conflict_check(*args):
            clock[0] = NOW  # The expiry passes while the conflicts are being read.
            return read_blocks(*args)

        with mock.patch("app.venues.routes.singapore_now", side_effect=lambda: clock[0]), \
                mock.patch.object(scheduling, "blocks", side_effect=slow_conflict_check):
            response = self.confirm()

        body = self.assert_error(response, 409, reason="expired")
        self.assertIn("2027-03-01 12:00", body["error"])
        self.assert_not_confirmed()


# ---------- AC5: only the event's coordinator ----------


class PermissionTests(HoldExpiryTestCase):
    # TC-86-27 · AC5 — anyone else is denied.
    def test_only_the_events_coordinator_can_confirm(self):
        self.users["lead"] = self.make_user(role="coordinator_lead")
        self.make_hold("P1")

        for user in ("ben", "gus", "dana", "hana", "farah", "admin", "lead"):
            with self.subTest(user=user):
                self.assert_error(self.confirm(as_user=user), 403)
        self.assert_not_confirmed()

    # TC-86-28 · AC5 — a valid session is required.
    def test_a_valid_session_is_required(self):
        self.make_hold("P1")
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
                self.assertEqual(self.confirm(headers=headers).status_code, 401)
        self.assert_not_confirmed()


# ---------- AC6: a failed confirmation changes nothing ----------


class SaveFailureTests(HoldExpiryTestCase):
    # TC-86-29 · AC6 — saving the confirmation fails.
    def test_failed_confirmation_changes_nothing(self):
        self.make_hold("P1")

        with self.failing_commit():
            response = self.confirm()

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"still tentative")
        self.assert_not_confirmed()
        self.assertEqual(self.confirm().status_code, 200)

    # TC-86-30 · AC6 — conflicts can't be checked.
    def test_no_confirmation_when_conflicts_cannot_be_checked(self):
        self.make_hold("P1")
        booking_id = self.bookings["P1"].id
        headers = self.auth_headers(self.users["alice"])

        with self.statements_fail(BLOCKS[1]):
            response = self.confirm(booking_id, headers=headers)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"availability could not be verified")
        self.assertRegex(body["error"].lower(), r"still tentative")
        self.assert_not_confirmed()


# ---------- AC7: times are in SGT ----------


class _Clock(datetime):
    """The real clock, stopped at 2027-03-01 04:30 UTC (12:30 in Singapore)."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2027, 3, 1, 4, 30, tzinfo=timezone.utc).astimezone(tz)


class SingaporeTimeTests(HoldExpiryTestCase):
    # TC-86-31 · AC7 — expiry is judged by Singapore time.
    def test_expiry_is_judged_by_singapore_time(self):
        self.make_hold("P1", expires_at=datetime(2027, 3, 1, 12, 0))
        self.make_hold("P2", expires_at=datetime(2027, 3, 1, 13, 0))

        # Only the clock is fixed: every "now" comes from Singapore time read off it.
        with mock.patch.object(local_time, "datetime", _Clock), \
                mock.patch("app.venues.routes.singapore_now", local_time.singapore_now):
            refused = self.confirm()
            tasks.check_hold_expiries()

        self.assert_error(refused, 409, reason="expired")
        self.assertEqual((self.stored("P1")["status"], self.stored("P2")["status"]),
                         ("expired", "tentative"))
        [notice] = self.notifications_for("alice")
        self.assertIn("2027-03-01 12:00 (Singapore time)", notice.message)


if __name__ == "__main__":
    unittest.main()
