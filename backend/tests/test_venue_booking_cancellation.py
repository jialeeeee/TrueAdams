"""Tests for SCRUM-94 "Coordinator Cancels a Venue Booking".

Each test names the case it automates from
docs/test-cases/SCRUM-94-cancel-venue-booking.md (TC-94-xx) and the acceptance
criteria it checks. Assumptions A1-A7 and questions Q1-Q5 are defined there.
TC-94-07 to 09 and 21 are frontend cases, in VenueBookingRequestPage.test.jsx.

Endpoint
    POST /api/venues/bookings/<id>/cancel      (no body)
        200 {"message", "booking": the event's saved-request payload (SCRUM-69),
             "notification": {"in_app": true, "email_queued": bool}}
        401 session · 404 unknown booking · 403 not the event's current coordinator
        409 {"error", "reason": "not_cancellable"} unless pending, tentative or confirmed
        503 {"error", "retryable": true} if the cancellation can't be read or saved

CB-SEED is SCRUM-40's VA-SEED plus E1's bookings C1, T1, R1 and X1.
"""

import unittest
from datetime import datetime
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import SQLAlchemyError

from app.models import Event, Notification, User, VenueBooking
from tests.test_venue_booking_approval import P1_END, P1_START, ApprovalTestCase

CANCEL_URL = "/api/venues/bookings/{}/cancel"
CANCELLATION_NOTIFICATION = "venue_booking_cancelled"
HELD_AT = datetime(2026, 10, 20, 2, 0)
APPROVED_AT = datetime(2026, 10, 21, 3, 0)


class CancellationTestCase(ApprovalTestCase):
    """CB-SEED, plus helpers to cancel bookings and read what was saved."""

    def setUp(self):
        super().setUp()
        gus = self.users["gus"]
        confirmed = self.add_booking("E1", "recorded_as_none", "confirmed", P1_START, P1_END,
                                     requested_by="alice")
        confirmed.decided_at, confirmed.decided_by_id = APPROVED_AT, gus.id
        hold = self.add_booking("E1", "fully_recorded", "tentative",
                                datetime(2027, 3, 13, 9, 0), datetime(2027, 3, 13, 12, 0),
                                requested_by="alice")
        hold.held_at, hold.held_by_id = HELD_AT, gus.id
        hold.hold_expires_at = datetime(2027, 3, 1, 12, 0)
        rejected = self.add_booking("E1", "recorded_as_none", "rejected",
                                    datetime(2027, 3, 11, 10, 0), datetime(2027, 3, 11, 12, 0),
                                    requested_by="alice")
        rejected.decided_at, rejected.decided_by_id = APPROVED_AT, gus.id
        rejected.rejection_reason = "No stage power."
        cancelled = self.add_booking("E1", "partially_recorded", "cancelled",
                                     datetime(2027, 3, 11, 13, 0), datetime(2027, 3, 11, 15, 0),
                                     requested_by="alice")
        # Approving C1 made Civic Hall E1's venue (SCRUM-40 A4).
        self.events["E1"].venue_id = self.venues["recorded_as_none"].id
        self.db.session.commit()
        self.bookings.update(C1=confirmed, T1=hold, R1=rejected, X1=cancelled)

    # ---------- Requests ----------

    def cancel(self, booking, as_user="alice", headers=None):
        booking_id = booking if isinstance(booking, int) else self.bookings[booking].id
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.post(CANCEL_URL.format(booking_id), headers=headers)

    def planning(self, event="E1", as_user="alice"):
        response = self.client.get(f"/api/events/{self.events[event].id}/planning",
                                   headers=self.auth_headers(self.users[as_user]))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    # ---------- Reading what was saved ----------

    def cancellation_notices(self, user):
        self.db.session.expire_all()
        return Notification.query.filter_by(recipient_id=user.id,
                                            kind=CANCELLATION_NOTIFICATION).all()

    def event_columns(self, key="E1"):
        event = self.event(key)
        return {c.name: getattr(event, c.name) for c in Event.__table__.columns}

    # ---------- Assertions ----------

    def assert_cancelled(self, response, booking):
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.stored(booking)["status"], "cancelled")
        return response.get_json()

    def assert_nothing_announced(self):
        self.assertEqual(self.cancellation_notices(self.users["gus"]), [])
        self.queue_email.assert_not_called()


# ---------- AC1: only the event's coordinator, and only a live booking ----------


class WhoAndWhichTests(CancellationTestCase):
    # TC-94-01 · AC1, AC3 — the coordinator cancels a pending request.
    def test_coordinator_cancels_a_pending_request(self):
        body = self.assert_cancelled(self.cancel("P1"), "P1")

        self.assertIn("Aurora Ballroom", body["message"])
        self.assertIn("Harbour Lights Festival", body["message"])
        booking = body["booking"]
        self.assertEqual((booking["id"], booking["status"]), (self.bookings["P1"].id, "cancelled"))
        self.assertEqual(booking["venue"]["name"], "Aurora Ballroom")
        self.assertEqual((booking["start_time"], booking["end_time"]),
                         (P1_START.isoformat(), P1_END.isoformat()))

    # TC-94-02 · AC1, AC3 — a hold and a confirmed booking can be cancelled too.
    def test_hold_and_confirmed_booking_can_be_cancelled(self):
        for key in ("T1", "C1"):
            with self.subTest(booking=key):
                body = self.assert_cancelled(self.cancel(key), key)
                self.assertEqual(body["booking"]["status"], "cancelled")

    # TC-94-03 · AC1 — rejected and cancelled bookings can't be cancelled.
    def test_rejected_and_cancelled_bookings_cannot_be_cancelled(self):
        for key, status in (("R1", "rejected"), ("X1", "cancelled")):
            with self.subTest(booking=key):
                before = self.stored(key)
                body = self.assert_error(self.cancel(key), 409, reason="not_cancellable")
                self.assertIn(status, body["error"])
                self.assertEqual(self.stored(key), before)
        self.assert_nothing_announced()

    # TC-94-04 · AC1 — anyone but the event's coordinator is refused, and learns nothing.
    def test_anyone_but_the_events_coordinator_is_refused(self):
        before = {key: self.stored(key) for key in ("P1", "C1")}
        event_before = self.event_columns()
        for user in ("ben", "gus", "dana", "admin", "farah"):
            for key in ("P1", "C1"):
                with self.subTest(user=user, booking=key):
                    body = self.assert_error(self.cancel(key, as_user=user), 403)
                    self.assertEqual(set(body), {"error"})
                    for detail in ("Aurora Ballroom", "Civic Hall", "Harbour Lights"):
                        self.assertNotIn(detail, body["error"])
        self.assertEqual({key: self.stored(key) for key in ("P1", "C1")}, before)
        self.assertEqual(self.event_columns(), event_before)
        self.assert_nothing_announced()

    # TC-94-05 · AC1 (A1) — after a reassignment, only the new coordinator may cancel.
    def test_only_the_current_coordinator_may_cancel(self):
        self.events["E1"].coordinator_id = self.users["chloe"].id
        self.db.session.commit()
        before = self.stored("P1")

        self.assert_error(self.cancel("P1", as_user="alice"), 403)
        self.assertEqual(self.stored("P1"), before)

        self.assert_cancelled(self.cancel("P1", as_user="chloe"), "P1")

    # TC-94-06 · AC1 (A6) — unknown bookings are 404 for everyone; bad sessions are 401.
    def test_unknown_booking_and_invalid_sessions(self):
        unknown = self.missing_id(VenueBooking)
        for user in ("alice", "ben"):
            with self.subTest(user=user):
                self.assert_error(self.cancel(unknown, as_user=user), 404)

        before = self.stored("P1")
        deleted_user = create_access_token(identity=str(self.missing_id(User)))
        for label, headers in (("no token", {}),
                               ("deleted user", {"Authorization": f"Bearer {deleted_user}"})):
            with self.subTest(session=label):
                response = self.cancel("P1", headers=headers)
                self.assertEqual(response.status_code, 401, response.get_data(as_text=True))
        self.assertEqual(self.stored("P1"), before)
        self.assert_nothing_announced()


# ---------- AC3: cancelled, kept, and the venue released ----------


class ReleasedTests(CancellationTestCase):
    # TC-94-10 · AC3 — the record is kept with only its status changed.
    def test_record_is_kept_with_only_its_status_changed(self):
        before = self.stored("C1")
        event_ids = [event.id for event in self.events.values()]
        own_ids = lambda: {b.id for b in VenueBooking.query.filter(  # noqa: E731
            VenueBooking.event_id.in_(event_ids))}
        ids_before = own_ids()

        self.assert_cancelled(self.cancel("C1"), "C1")

        after = self.stored("C1")
        self.assertEqual(after.pop("status"), "cancelled")
        before.pop("status")
        self.assertEqual(after, before)
        self.assertEqual((after["decided_at"], after["decided_by_id"]),
                         (APPROVED_AT, self.users["gus"].id))
        self.assertEqual(own_ids(), ids_before)

    def add_clash_with_p2(self, status):
        """E3's (alice's) booking at Civic Hall overlapping E2's pending P2 on 3 Apr 2027."""
        clash = self.add_booking("E3", "recorded_as_none", status, datetime(2027, 4, 3, 18, 0),
                                 datetime(2027, 4, 3, 20, 0), requested_by="alice")
        if status == "tentative":
            clash.held_at, clash.held_by_id = HELD_AT, self.users["gus"].id
            clash.hold_expires_at = datetime(2027, 4, 1, 12, 0)
            self.db.session.commit()
        return clash

    def assert_cancelling_frees_p2(self, clash):
        refused = self.assert_error(self.approve("P2"), 409, reason="conflict")
        self.assertEqual([conflict["id"] for conflict in refused["conflicts"]], [clash.id])

        self.assert_cancelled(self.cancel(clash.id), clash)

        listed = self.client.get("/api/venues/bookings",
                                 headers=self.auth_headers(self.users["gus"])).get_json()
        p2 = next(b for b in listed["bookings"] if b["id"] == self.bookings["P2"].id)
        self.assertEqual(p2["conflicts"], [])
        approved = self.approve("P2")
        self.assertEqual(approved.status_code, 200, approved.get_json())

    # TC-94-11 · AC3 — a cancelled confirmed booking no longer blocks the venue.
    def test_cancelling_a_confirmed_booking_frees_the_venue_slot(self):
        self.assert_cancelling_frees_p2(self.add_clash_with_p2("confirmed"))

    # TC-94-11 · AC3 — a cancelled hold no longer blocks the venue.
    def test_cancelling_a_hold_frees_the_venue_slot(self):
        self.assert_cancelling_frees_p2(self.add_clash_with_p2("tentative"))

    # TC-94-12 · AC3 (A3, Q3) — cancelling the confirmed venue clears the event's venue.
    def test_cancelling_the_confirmed_venue_clears_the_events_venue(self):
        civic = self.venues["recorded_as_none"]
        before = self.event_columns()
        for key in ("T1", "P1"):
            with self.subTest(cancelled=key):
                self.assert_cancelled(self.cancel(key), key)
                self.assertEqual(self.planning()["venue"]["id"], civic.id)

        self.assert_cancelled(self.cancel("C1"), "C1")

        self.assertIsNone(self.planning()["venue"])
        after = self.event_columns()
        self.assertIsNone(after.pop("venue_id"))
        before.pop("venue_id")
        self.assertEqual(after, before)

    # TC-94-13 · AC3 — with its pending request cancelled, the event can request again.
    def test_event_can_request_a_venue_again_after_cancelling_its_pending_request(self):
        self.assert_cancelled(self.cancel("P1"), "P1")

        response = self.client.post("/api/venues/bookings", json={
            "event_id": self.events["E1"].id, "venue_id": self.venues["partially_recorded"].id,
            "start_time": "2027-03-12T16:00", "end_time": "2027-03-12T22:30",
            "venue_requirements": "Breakout space for 40",
        }, headers=self.auth_headers(self.users["alice"]))

        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["booking"]["status"], "pending")


# ---------- AC4: Venue Staff are notified ----------


class NotificationTests(CancellationTestCase):
    # TC-94-14 · AC4 (A4, Q4) — every Venue Staff member is told, in-app and by email.
    def test_venue_staff_are_notified_in_app_and_by_email(self):
        vera = self.make_user(role="venue_staff")
        staff = [self.users["gus"], vera]
        with mock.patch.object(self.db.session, "commit", wraps=self.db.session.commit) as commit:
            commits_at_queue = []
            self.queue_email.side_effect = lambda *args: commits_at_queue.append(commit.call_count)
            body = self.assert_cancelled(self.cancel("C1"), "C1")

        self.assertEqual(body["notification"], {"in_app": True, "email_queued": True})
        for member in staff:
            with self.subTest(staff=member.email):
                notices = self.cancellation_notices(member)
                self.assertEqual(len(notices), 1)
                self.assertEqual(notices[0].event_id, self.events["E1"].id)
                for detail in ("Civic Hall", "Harbour Lights Festival", "2027-03-12 16:00",
                               "2027-03-12 22:30", "confirmed", self.users["alice"].email):
                    self.assertIn(detail, notices[0].message)
        emailed = [call.args[0] for call in self.queue_email.call_args_list]
        for member in staff:
            self.assertEqual(emailed.count(member.email), 1)
        # Staff can't open the event's planning view, so the email points to their own list.
        for call in self.queue_email.call_args_list:
            to_address, subject, body = call.args
            self.assertIn("Harbour Lights Festival", subject)
            self.assertTrue(body.startswith(self.cancellation_notices(self.users["gus"])[0].message))
            self.assertIn("Sign in to ConnectSphere to see the venue requests.", body)
            self.assertNotIn("planning information", body)
        self.assertTrue(commits_at_queue and set(commits_at_queue) == {1},
                        "Emails must be queued after the cancellation is committed")

    # TC-94-15 · AC4, AC6 — an email that can't be queued doesn't undo the cancellation.
    def test_email_queue_failure_does_not_undo_the_cancellation(self):
        self.queue_email.side_effect = ConnectionError("Redis unavailable")

        body = self.assert_cancelled(self.cancel("P1"), "P1")

        self.assertEqual(body["notification"], {"in_app": True, "email_queued": False})
        self.assertEqual(len(self.cancellation_notices(self.users["gus"])), 1)


# ---------- AC5: the event's other bookings are unchanged ----------


class OtherBookingsTests(CancellationTestCase):
    # TC-94-16 · AC5 — cancelling one booking leaves the others as they were.
    def test_other_bookings_are_unchanged(self):
        everything = ("P1", "C1", "T1", "R1", "X1", "P2")
        for cancelled in ("C1", "P1"):
            with self.subTest(cancelled=cancelled):
                others = [key for key in everything if key != cancelled]
                before = {key: self.stored(key) for key in others}

                self.assert_cancelled(self.cancel(cancelled), cancelled)

                self.assertEqual({key: self.stored(key) for key in others}, before)


# ---------- AC6: a failed save changes nothing ----------


class FailedSaveTests(CancellationTestCase):
    def assert_unchanged_after_failure(self, response, key, before, event_before):
        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertIn("unchanged", body["error"].lower())
        self.assertEqual(self.stored(key), before)
        self.assertEqual(self.event_columns(), event_before)
        self.assert_nothing_announced()

    # TC-94-17 · AC6 — the cancellation can't be saved.
    def test_failed_save_leaves_the_booking_unchanged(self):
        before, event_before = self.stored("C1"), self.event_columns()
        headers = self.auth_headers(self.users["alice"])
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("commit failed")) as commit:
            response = self.cancel("C1", headers=headers)
        commit.assert_called_once()
        self.assert_unchanged_after_failure(response, "C1", before, event_before)

    # TC-94-18 · AC4, AC6 — a notification can't be saved, so nothing is.
    def test_failed_notification_leaves_the_booking_unchanged(self):
        before, event_before = self.stored("P1"), self.event_columns()
        headers = self.auth_headers(self.users["alice"])
        attempted = []

        def fail_notification(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("INSERT INTO NOTIFICATIONS"):
                attempted.append(statement)
                raise SQLAlchemyError("notification insert failed")

        sa_event.listen(self.connection, "before_cursor_execute", fail_notification)
        try:
            response = self.cancel("P1", headers=headers)
        finally:
            sa_event.remove(self.connection, "before_cursor_execute", fail_notification)
        self.assertTrue(attempted, "The notification INSERT failure was not exercised")
        self.assert_unchanged_after_failure(response, "P1", before, event_before)

    # TC-94-19 · AC6 — a booking that can't be read is a failure, not "not found".
    def test_failed_read_is_reported_not_treated_as_missing(self):
        before, event_before = self.stored("P1"), self.event_columns()
        booking_id = self.bookings["P1"].id
        headers = self.auth_headers(self.users["alice"])

        def fail_booking_read(conn, cursor, statement, parameters, context, executemany):
            flat = " ".join(statement.split())
            if "FROM venue_bookings" in flat and "FOR UPDATE" in flat:
                raise SQLAlchemyError("simulated outage")

        sa_event.listen(self.connection, "before_cursor_execute", fail_booking_read)
        try:
            response = self.cancel(booking_id, headers=headers)
        finally:
            sa_event.remove(self.connection, "before_cursor_execute", fail_booking_read)
        self.assert_unchanged_after_failure(response, "P1", before, event_before)

    # TC-94-20 · AC1, AC6 — cancelling twice keeps the first cancellation.
    def test_cancelling_twice_keeps_the_first_cancellation(self):
        self.assert_cancelled(self.cancel("P1"), "P1")
        first = self.stored("P1")
        emails = self.queue_email.call_count

        self.assert_error(self.cancel("P1"), 409, reason="not_cancellable")

        self.assertEqual(self.stored("P1"), first)
        self.assertEqual(len(self.cancellation_notices(self.users["gus"])), 1)
        self.assertEqual(self.queue_email.call_count, emails)


if __name__ == "__main__":
    unittest.main()
