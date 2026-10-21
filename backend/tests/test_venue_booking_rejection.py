"""SCRUM-69 tests; see docs/test-cases/SCRUM-69-reject-venue-booking.md.

AC1 reuses SCRUM-39 tests.
Guard/validation tests use Flask/JWT with mocked persistence and no network.
Persistence/transaction tests reuse SCRUM-40 fixtures, but refuse any database
except the explicitly authorised local Docker target before opening a connection.
No schema changes or real email are performed by this module.
"""

import smtplib
import socket
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from app import tasks
from app.config import TestConfig
from app.models import Event, User, VenueBooking
from app.venues import routes
from tests.test_venue_booking_approval import ApprovalTestCase, REQUIREMENTS


REASON = "The required stage power cannot be provided for this arrangement."
REJECT_URL = "/api/venues/bookings/{}/reject"
# AC3 specifies characters, unlike the event decision's separate word limit.
MAX_REASON_LENGTH = 500
# Exact local Docker target and the existing throwaway CI service; never Supabase.
LOCAL_TEST_TARGETS = {
    ("127.0.0.1", 5433, "postgres", "connectsphere_test"),
    ("localhost", 5432, "postgres", "connectsphere_test"),
}


class RejectionGuardUnitTests(unittest.TestCase):
    """Exercise the real HTTP boundary without a database or external services."""

    def setUp(self):
        for method in ("connect", "raw_connection"):
            guard = mock.patch.object(
                Engine, method, side_effect=AssertionError("Database access in isolated test"))
            guard.start()
            self.addCleanup(guard.stop)
        network = mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("Network access in isolated test"))
        network.start()
        self.addCleanup(network.stop)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="scrum-69-isolated-secret-at-least-32-bytes")
        JWTManager(self.app)
        self.app.register_blueprint(routes.venues_bp, url_prefix="/api/venues")
        self.client = self.app.test_client()
        self.user = SimpleNamespace(id=9, role="venue_staff", email="staff@test.invalid")
        values = {column.name: None for column in VenueBooking.__table__.columns}
        values.update(id=11, event_id=7, venue_id=3, status="pending",
                      start_time=datetime(2027, 3, 12, 16), end_time=datetime(2027, 3, 12, 22, 30),
                      venue_requirements=REQUIREMENTS, requested_by_id=2)
        self.booking = SimpleNamespace(**values)
        self.session = mock.MagicMock()
        self.session.get.side_effect = self.load
        persistence = mock.patch.object(routes.db, "session", self.session)
        persistence.start()
        self.addCleanup(persistence.stop)
        email = mock.patch.object(tasks.send_notification_email, "delay")
        self.email = email.start()
        self.addCleanup(email.stop)

    def load(self, model, record_id, **kwargs):
        if model is User:
            return self.user if record_id == self.user.id else None
        if model is VenueBooking:
            return self.booking if record_id == self.booking.id else None
        raise AssertionError(f"Unexpected read in a refused request: {model}")

    def headers(self, identity="9", **kwargs):
        with self.app.app_context():
            token = create_access_token(identity=identity, additional_claims={"role": "venue_staff"},
                                        **kwargs)
        return {"Authorization": f"Bearer {token}"}

    def reject(self, body=None, booking_id=11, headers=None, **kwargs):
        if "data" not in kwargs:
            kwargs["json"] = {"reason": REASON} if body is None else body
        return self.client.post(REJECT_URL.format(booking_id),
                                headers=self.headers() if headers is None else headers, **kwargs)

    def assert_refused(self, response, status, before, field=None):
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        body = response.get_json()
        self.assertIsInstance(body, dict, "The rejection endpoint must return a JSON error")
        self.assertTrue(body.get("error", "").strip())
        if field:
            self.assertEqual(body.get("field"), field)
        self.assertEqual(vars(self.booking), before)
        self.session.add.assert_not_called()
        self.session.commit.assert_not_called()
        self.email.assert_not_called()
        return body

    # TC-69-03 · AC2/AC5: a tentative hold stays non-pending even after expiry.
    def test_only_pending_requests_can_be_rejected(self):
        for status, expiry in (("confirmed", None), ("rejected", None), ("cancelled", None),
                               ("tentative", datetime(2099, 1, 1)),
                               ("tentative", datetime(2020, 1, 1))):
            with self.subTest(status=status, expiry=expiry):
                self.booking.status = status
                self.booking.hold_expires_at = expiry
                self.booking.decided_at = datetime(2026, 10, 1)
                self.booking.decided_by_id = 9
                before = vars(self.booking).copy()
                body = self.assert_refused(self.reject(), 409, before)
                self.assertEqual(body.get("reason"), "not_pending")
                self.assertIn(status, body["error"])

    # TC-69-05 · AC2, A1: JWT role claims never confer permission.
    def test_rejection_uses_current_stored_venue_staff_role(self):
        headers = self.headers()
        for role in ("coordinator", "organiser", "tech_staff", "attendee", "admin", "coordinator_lead"):
            with self.subTest(role=role):
                self.user.role = role
                before = vars(self.booking).copy()
                response = self.reject(headers=headers)
                self.assert_refused(response, 403, before)
                self.assertNotIn(REQUIREMENTS, response.get_data(as_text=True))

    # TC-69-06 · AC2: invalid authentication cannot reach writes.
    def test_rejection_requires_valid_session(self):
        cases = {
            "missing": {},
            "expired": self.headers(expires_delta=timedelta(seconds=-1)),
            "deleted user": self.headers(identity="999"),
            "invalid identity": self.headers(identity="not-an-id"),
        }
        for label, headers in cases.items():
            with self.subTest(session=label):
                before = vars(self.booking).copy()
                response = self.reject(headers=headers)
                self.assertEqual(response.status_code, 401, response.get_data(as_text=True))
                self.assertEqual(vars(self.booking), before)
                self.session.commit.assert_not_called()
                self.email.assert_not_called()

    # TC-69-07 · AC2: independent of the unresolved combined-error precedence.
    def test_unknown_request_is_not_found(self):
        body = self.assert_refused(self.reject(booking_id=999), 404, vars(self.booking).copy())
        self.assertEqual(body["error"], "Booking request not found.")

    # TC-69-09 · AC3: missing/null/empty/whitespace are all blank.
    def test_rejection_reason_is_required(self):
        for body in ({}, {"reason": None}, {"reason": ""}, {"reason": "   "},
                     {"reason": "\t\r\n"}, {"reason": "\u2003\u00a0"}):
            with self.subTest(body=body):
                self.assert_refused(self.reject(body), 400, vars(self.booking).copy(), "reason")

    # TC-69-10 · AC3: no coercion to a string.
    def test_rejection_reason_must_be_text(self):
        for reason in (23, True, [], {}):
            with self.subTest(reason=reason):
                self.assert_refused(self.reject({"reason": reason}), 400,
                                    vars(self.booking).copy(), "reason")

    # TC-69-10 · AC3: malformed and non-object bodies are not usable reasons.
    def test_rejection_requires_json_object(self):
        for data in ("", "{", "[]", '"reason"', "null"):
            with self.subTest(data=data):
                self.assert_refused(self.reject(data=data, content_type="application/json"),
                                    400, vars(self.booking).copy())

    # TC-69-12 · AC3: direct API use must enforce the boundary too.
    def test_rejection_refuses_501_character_reason(self):
        self.assert_refused(self.reject({"reason": "x" * (MAX_REASON_LENGTH + 1)}),
                            400, vars(self.booking).copy(), "reason")

    # TC-69-20 · AC4/AC6: failed reads never become a missing record or a success.
    def test_rejection_read_failure_is_retryable(self):
        self.session.get.side_effect = SQLAlchemyError("simulated read failure")
        body = self.assert_refused(self.reject(), 503, vars(self.booking).copy())
        self.assertIs(body.get("retryable"), True)
        self.session.rollback.assert_called()


class RejectionPersistenceTests(ApprovalTestCase):
    """Local-only persistence and transaction checks using existing VA-SEED helpers."""

    @classmethod
    def setUpClass(cls):
        url = make_url(TestConfig.SQLALCHEMY_DATABASE_URI or "postgresql://")
        actual = (url.host, url.port, url.database, url.username)
        if actual not in LOCAL_TEST_TARGETS:
            raise RuntimeError(f"UNSAFE DATABASE TARGET: {actual}; expected local Docker or CI")
        super().setUpClass()

    def reject(self, reason=REASON, booking="P1"):
        return self.client.post(REJECT_URL.format(self.bookings[booking].id), json={"reason": reason},
                                headers=self.auth_headers(self.users["gus"]))

    def assert_success(self, response):
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def own_booking_ids(self):
        event_ids = [event.id for event in self.events.values()]
        return {row.id for row in VenueBooking.query.filter(VenueBooking.event_id.in_(event_ids))}

    def assert_rejected(self, reason=REASON):
        self.db.session.expire_all()
        row = self.db.session.get(VenueBooking, self.bookings["P1"].id)
        self.assertEqual(row.status, "rejected")
        # A missing model column becomes an explanatory assertion, not AttributeError.
        self.assertEqual(getattr(row, "rejection_reason", None), reason)
        return row

    # TC-69-02/16 · AC2–AC5: the request row remains; no confirmed booking or hold.
    def test_reject_pending_request_records_decision_without_creating_booking(self):
        original = self.stored("P1")
        original_event = {c.name: getattr(self.event("E1"), c.name) for c in Event.__table__.columns}
        original_ids = self.own_booking_ids()
        started = datetime.utcnow()
        body = self.assert_success(self.reject())
        finished = datetime.utcnow()
        row = self.assert_rejected()
        self.assertEqual(self.own_booking_ids(), original_ids)
        self.assertEqual(row.decided_by_id, self.users["gus"].id)
        self.assertTrue(started <= row.decided_at <= finished)
        for name, value in original.items():
            if name not in {"status", "decided_at", "decided_by_id", "rejection_reason"}:
                self.assertEqual(getattr(row, name), value, name)
        self.assertEqual({c.name: getattr(self.event("E1"), c.name) for c in Event.__table__.columns},
                         original_event)
        for field in ("held_at", "held_by_id", "hold_expires_at"):
            self.assertIsNone(getattr(row, field))
        self.assertEqual(body["booking"]["status"], "rejected")
        self.assertEqual(body["booking"]["rejection_reason"], REASON)
        self.assertEqual(body["booking"]["decided_at"], row.decided_at.isoformat())
        self.assertEqual(body["booking"]["decided_by"]["id"], self.users["gus"].id)
        pending = self.client.get("/api/venues/bookings",
                                  headers=self.auth_headers(self.users["gus"])).get_json()
        self.assertNotIn(row.id, [booking["id"] for booking in pending["bookings"]])
        self.assertIn(self.bookings["P2"].id, [booking["id"] for booking in pending["bookings"]])

    # TC-69-11 · AC3/AC4: use fresh rows already provided by VA-SEED.
    def test_rejection_accepts_exactly_500_characters_without_truncation(self):
        reason = "x" * MAX_REASON_LENGTH
        body = self.assert_success(self.reject(reason))
        self.assert_rejected(reason)
        self.assertEqual(body["booking"]["rejection_reason"], reason)
        self.assertIn(reason, self.notifications_for("alice")[0].message)

    # TC-69-17 · AC4/AC6: persisted notification API is the coordinator's read path.
    def test_rejection_notifies_coordinator_with_full_reason(self):
        body = self.assert_success(self.reject())
        [notification] = self.notifications_for("alice")
        self.assertEqual((notification.kind, notification.event_id),
                         ("venue_booking_rejected", self.events["E1"].id))
        for text in (REASON, "Harbour Lights Festival", "Aurora Ballroom",
                     "2027-03-12 16:00", "2027-03-12 22:30", self.users["gus"].email):
            self.assertIn(text, notification.message)
        self.assertIn("rejected", notification.message.lower())
        listed = self.client.get("/api/notifications/",
                                 headers=self.auth_headers(self.users["alice"])).get_json()
        saved = [item for item in listed["notifications"] if item["id"] == notification.id]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["message"], notification.message)
        for user in ("ben", "dana", "gus"):
            self.assertEqual(self.notifications_for(user), [])
            own = self.client.get("/api/notifications/",
                                  headers=self.auth_headers(self.users[user])).get_json()
            self.assertNotIn(notification.id, [item["id"] for item in own["notifications"]])
        self.queue_email.assert_called_once()
        to_address, subject, message = self.queue_email.call_args.args
        self.assertEqual(to_address, self.users["alice"].email)
        self.assertIn("Harbour Lights Festival", subject)
        self.assertIn("Aurora Ballroom", subject)
        self.assertIn(REASON, message)
        self.assertIn("rejected", message.lower())
        self.assertEqual(body["notification"], {"in_app": True, "email_queued": True})

    # TC-69-18 · AC6: requester and current coordinator need not be the same user.
    def test_rejection_notifies_current_coordinator_after_reassignment(self):
        self.events["E1"].coordinator_id = self.users["ben"].id
        self.db.session.commit()
        self.assert_success(self.reject())
        [notification] = self.notifications_for("ben")
        self.assertIn(REASON, notification.message)
        self.assertEqual(self.notifications_for("alice"), [])
        self.queue_email.assert_called_once()
        self.assertEqual(self.queue_email.call_args.args[0], self.users["ben"].email)

    # TC-69-04 · AC2/AC4/AC6: double-clicks/lost responses must not overwrite history.
    def test_repeat_rejection_preserves_first_decision(self):
        self.assert_success(self.reject())
        before = self.stored("P1")
        body = self.assert_error(self.reject("A different reason."), 409, "not_pending")
        self.assertIn("rejected", body["error"])
        self.assertEqual(self.stored("P1"), before)
        self.assertEqual(len(self.notifications_for("alice")), 1)
        self.queue_email.assert_called_once()

    # TC-69-21 · AC4–AC6: existing fixture permits route rollback without committing rows.
    def test_failed_commit_rolls_back_decision_and_notification(self):
        before = self.stored("P1")
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("commit failed")) as commit:
            response = self.reject()
        body = self.assert_error(response, 503)
        commit.assert_called_once()
        self.assertIs(body.get("retryable"), True)
        self.assertEqual(self.stored("P1"), before)
        self.assert_nothing_decided()
        self.assert_success(self.reject())
        self.assert_rejected()
        self.assertEqual(len(self.notifications_for("alice")), 1)
        self.queue_email.assert_called_once()

    # TC-69-21 · AC4/AC6: fail a real notification INSERT after staging the decision.
    def test_notification_insert_failure_rolls_back_decision(self):
        before = self.stored("P1")
        headers = self.auth_headers(self.users["gus"])
        url = REJECT_URL.format(self.bookings["P1"].id)
        attempted = []

        def fail_notification(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("INSERT INTO NOTIFICATIONS"):
                attempted.append(statement)
                raise SQLAlchemyError("notification insert failed")

        sa_event.listen(self.connection, "before_cursor_execute", fail_notification)
        try:
            response = self.client.post(url, json={"reason": REASON}, headers=headers)
        finally:
            sa_event.remove(self.connection, "before_cursor_execute", fail_notification)
        body = self.assert_error(response, 503)
        self.assertTrue(attempted, "The notification INSERT failure was not exercised")
        self.assertIs(body.get("retryable"), True)
        self.assertEqual(self.stored("P1"), before)
        self.assert_nothing_decided()

    # TC-69-19/21 · AC4/AC6: broker failure after commit does not undo saved data.
    def test_queue_failure_after_commit_preserves_rejection_and_notification(self):
        commit_counts_at_queue = []
        with mock.patch.object(self.db.session, "commit", wraps=self.db.session.commit) as commit:
            def fail_queue(*args):
                # Assert outside the callback: the queue helper catches exceptions.
                commit_counts_at_queue.append(commit.call_count)
                raise ConnectionError("Redis unavailable")

            self.queue_email.side_effect = fail_queue
            body = self.assert_success(self.reject())
        self.assertEqual(commit_counts_at_queue, [1], "Email must follow the decision commit")
        self.assert_rejected()
        self.assertEqual(len(self.notifications_for("alice")), 1)
        self.assertEqual(body["notification"], {"in_app": True, "email_queued": False})
        self.queue_email.assert_called_once()

    # TC-69-19 · AC4/AC6: simulate eager task delivery failure; never contact SMTP.
    def test_email_delivery_failure_does_not_undo_committed_rejection(self):
        self.queue_email.side_effect = lambda *args: tasks.send_notification_email.run(*args)
        with mock.patch.object(tasks.smtplib, "SMTP",
                               side_effect=smtplib.SMTPException("simulated delivery failure")) as smtp:
            self.assert_success(self.reject())
        smtp.assert_called_once()
        self.assert_rejected()
        self.assertEqual(len(self.notifications_for("alice")), 1)
        self.queue_email.assert_called_once()

    # TC-69-14 · AC4: saved request rows remain readable without Notification queries.
    def test_coordinator_recovers_saved_decision_without_notifications(self):
        self.assert_success(self.reject())
        # A new coordinator must recover prior decisions even though notifications
        # belonged to the earlier coordinator (GREEN instruction, AC4).
        self.events["E1"].coordinator_id = self.users["ben"].id
        self.db.session.commit()
        headers = self.auth_headers(self.users["ben"])
        event_id = self.events["E1"].id

        def forbid_notifications(conn, cursor, statement, parameters, context, executemany):
            if "FROM notifications" in statement:
                raise AssertionError("Saved decisions must not depend on notifications")

        sa_event.listen(self.connection, "before_cursor_execute", forbid_notifications)
        try:
            response = self.client.get("/api/venues/bookings", query_string={"event_id": event_id},
                                       headers=headers)
        finally:
            sa_event.remove(self.connection, "before_cursor_execute", forbid_notifications)
        body = self.assert_success(response)
        [booking] = body["bookings"]
        self.assertEqual(booking["id"], self.bookings["P1"].id)
        self.assertEqual(booking["status"], "rejected")
        self.assertEqual(booking["rejection_reason"], REASON)
        self.assertEqual(booking["decided_by"]["id"], self.users["gus"].id)
        self.assertIsNotNone(booking["decided_at"])

    # TC-69-15 · AC4: the event filter must never bypass coordinator ownership.
    def test_saved_decisions_require_current_coordinator_and_report_read_failure(self):
        self.assert_success(self.reject())
        event_id = self.events["E1"].id
        self.users["lead"] = self.make_user(role="coordinator_lead")
        for user in ("ben", "dana", "gus", "admin", "lead"):
            with self.subTest(user=user):
                response = self.client.get("/api/venues/bookings", query_string={"event_id": event_id},
                                           headers=self.auth_headers(self.users[user]))
                self.assert_error(response, 403)
                self.assertNotIn(REASON, response.get_data(as_text=True))
        unsigned = self.client.get("/api/venues/bookings", query_string={"event_id": event_id})
        self.assertEqual(unsigned.status_code, 401)
        headers = self.auth_headers(self.users["alice"])
        with mock.patch.object(self.db.session, "get", side_effect=SQLAlchemyError("read failed")):
            response = self.client.get("/api/venues/bookings", query_string={"event_id": event_id},
                                       headers=headers)
        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("bookings", body)
