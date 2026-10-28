"""SCRUM-91 TC-91-01..05: focused approval tests; see the story test-case document.

HTTP unit tests mock persistence, never approval/permission logic. Two AppTestCase
checks cover actual durability/rollback only on a configured local PostgreSQL test
database. AC3 remains blocked until SCRUM-93 supplies event confirmation.
"""

import socket
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from app.config import Config, TestConfig
from app.events import routes
from app.models import (
    EquipmentRequirement, EquipmentReservation, Event, Notification, User, Venue,
    VenueBooking,
)
from tests.base import AppTestCase


# SCRUM-91 A1/Q1: proposed additive approval action; not a confirmation endpoint.
APPROVAL_PATH = "/api/events/{event_id}/safety-checks/approve"
COMMENT = "Exits and access routes checked."
START = datetime(2030, 1, 16, 17)


class SafetyApprovalUnitTests(unittest.TestCase):
    def setUp(self):
        for target, name in ((Engine, "connect"), (Engine, "raw_connection"),
                             (socket.socket, "connect")):
            guard = mock.patch.object(target, name,
                side_effect=AssertionError("Database/network access in isolated SCRUM-91 test"))
            guard.start()
            self.addCleanup(guard.stop)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="scrum-91-isolated-secret-at-least-32-bytes")
        JWTManager(self.app)
        self.app.register_blueprint(routes.events_bp, url_prefix="/api/events")
        self.client = self.app.test_client()
        self.officer = SimpleNamespace(id=91, role="safety_officer", email="officer@test.invalid")
        self.coordinator = SimpleNamespace(id=92, role="coordinator", email="coordinator@test.invalid")
        self.event = SimpleNamespace(**{column.name: None for column in Event.__table__.columns})
        self.event.__dict__.update(id=1, title="Safety review meeting", status="approved",
            organiser_id=93, coordinator_id=92, venue_id=10, start_time=START,
            end_time=START + timedelta(hours=2), expected_attendance=40,
            created_at=START - timedelta(days=7))
        venue = SimpleNamespace(id=10, name="Meeting Room", location="Level 1")
        booking = SimpleNamespace(id=11, event_id=1, venue_id=10, status="confirmed",
            start_time=self.event.start_time, end_time=self.event.end_time,
            setup_minutes=0, turnaround_minutes=0, hold_expires_at=None)
        self.rows = {User: [self.officer, self.coordinator], Event: [self.event],
                     Venue: [venue], VenueBooking: [booking], EquipmentRequirement: [],
                     EquipmentReservation: [], Notification: []}
        self.session = mock.MagicMock()
        self.session.get.side_effect = lambda model, key, **kwargs: next(
            (row for row in self.rows[model] if row.id == key), None)
        session = mock.patch.object(routes.db, "session", self.session)
        session.start()
        self.addCleanup(session.stop)
        # Only ready positive fixtures are needed here. SQL eligibility is owned
        # by SCRUM-90; no route, role, approval or readiness helper is replaced.
        self.queries = {}
        for model, rows in self.rows.items():
            query = mock.MagicMock()
            for method in ("filter", "filter_by", "order_by", "with_for_update"):
                getattr(query, method).return_value = query
            query.all.return_value = rows
            query.first.return_value = rows[0] if rows else None
            self.queries[model] = query
            patcher = mock.patch.object(model, "query", query)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.session.query.side_effect = lambda model: self.queries[model]
        for patcher in (
            mock.patch.object(routes, "singapore_now", return_value=START - timedelta(hours=1)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        email = mock.patch.object(routes.tasks.send_notification_email, "delay")
        self.email = email.start()
        self.addCleanup(email.stop)

    def headers(self, user):
        with self.app.app_context():
            # A privileged claim must not override the current stored role (AC4).
            token = create_access_token(identity=str(user.id),
                                        additional_claims={"role": "safety_officer"})
        return {"Authorization": f"Bearer {token}"}

    def approve(self, body, authenticated=True):
        return self.client.post(APPROVAL_PATH.format(event_id=self.event.id), json=body,
            headers=self.headers(self.officer) if authenticated else {})

    # TC-91-01 / AC1: one method, with/without an optional comment.
    def test_officer_can_approve_with_or_without_a_comment(self):
        initial = vars(self.event).copy()
        for body in ({"comment": COMMENT}, {}):
            with self.subTest(body=body):
                vars(self.event).clear()
                vars(self.event).update(initial)
                self.session.reset_mock()
                response = self.approve(body)
                self.assertEqual(response.status_code, 200, response.get_json())
                decision = response.get_json()["safety_check"]
                self.assertEqual(decision["decision"], "approved")
                self.assertEqual(decision["comment"], body.get("comment"))
                self.assertEqual(self.event.status, "approved")
                self.assertEqual(self.event.safety_decided_by_id, self.officer.id)
                notification = self.session.add.call_args.args[0]
                self.assertIsInstance(notification, Notification)
                self.assertEqual(notification.recipient_id, self.coordinator.id)
                self.session.commit.assert_called_once()

    # TC-91-05 / AC5: exercise the HTTP failure branch without PostgreSQL too;
    # the local test below remains necessary to prove actual row rollback.
    def test_failed_save_returns_an_error_and_rolls_back_without_email(self):
        self.session.commit.side_effect = SQLAlchemyError("Private simulated save failure")
        response = self.approve({"comment": COMMENT})
        self.assertEqual(response.status_code, 503, response.get_json())
        body = response.get_json()
        self.assertTrue(body.get("error"))
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("safety_check", body)
        self.assertNotIn("Private simulated save failure", body["error"])
        self.session.commit.assert_called_once()
        self.session.rollback.assert_called_once()
        self.email.assert_not_called()

    # TC-91-03 / AC3: verify the existing backend refusal, then explicitly report
    # the missing dependency rather than invent a new confirmation route.
    def test_confirmation_before_and_after_safety_approval(self):
        response = self.client.patch("/api/events/1", json={"status": "confirmed"},
                                     headers=self.headers(self.coordinator))
        self.assertEqual(response.status_code, 422, response.get_json())
        self.assertIn("status", response.get_json()["fields"])
        self.assertEqual(self.event.status, "approved")
        self.session.commit.assert_not_called()
        self.skipTest("AC3 blocked by SCRUM-93: no event-confirmation action exists; planning PATCH "
                      "rejects status edits regardless of safety approval.")

    # TC-91-04 / AC4: every existing non-officer role and missing authentication.
    def test_other_roles_and_unauthenticated_callers_cannot_change_anything(self):
        for role in (None, "admin", "coordinator", "coordinator_lead", "organiser",
                     "venue_staff", "tech_staff", "attendee"):
            with self.subTest(role=role):
                self.officer.role = role
                before = vars(self.event).copy()
                response = self.approve({"comment": COMMENT}, authenticated=role is not None)
                self.assertEqual(response.status_code, 401 if role is None else 403)
                body = response.get_json()
                self.assertTrue(body.get("error") or (role is None and body.get("msg")))
                self.assertNotIn("safety_check", body)
                self.assertEqual(vars(self.event), before)
                self.session.add.assert_not_called()
                self.session.add_all.assert_not_called()
                self.session.commit.assert_not_called()
                self.email.assert_not_called()


class SafetyApprovalLocalTests(AppTestCase):
    @classmethod
    def setUpClass(cls):
        # AppTestCase's only class setup is the required-URL check. Let the
        # per-test safety guard below handle an absent URL as an explicit skip.
        if TestConfig.SQLALCHEMY_DATABASE_URI:
            super().setUpClass()

    def setUp(self):
        # Check before AppTestCase can create an app/connection. Never fall back
        # to DATABASE_URL. Tests never execute DDL or a schema builder.
        uri = TestConfig.SQLALCHEMY_DATABASE_URI
        if not uri:
            self.skipTest("Persistence needs a configured local PostgreSQL TEST_DATABASE_URL.")
        url = make_url(uri)
        if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1", "::1"}:
            self.skipTest("Remote/shared databases are forbidden; requires local PostgreSQL.")
        if Config.SQLALCHEMY_DATABASE_URI:
            development = make_url(Config.SQLALCHEMY_DATABASE_URI)
            if (url.host, url.port, url.database) == (development.host, development.port, development.database):
                self.skipTest("TEST_DATABASE_URL must target a separate test database.")
        super().setUp()
        self.officer = self.make_user(role="safety_officer")
        self.coordinator = self.make_user(role="coordinator")
        self.venue = self.make_venue()
        self.event = self.make_event(status="approved", venue=self.venue,
            start_time=START, coordinator_id=self.coordinator.id, expected_attendance=40,
            decision_note="Coordinator request approval", decided_by_id=self.coordinator.id,
            decided_at=START - timedelta(days=7))
        self.event_id = self.event.id
        self.db.session.add(VenueBooking(event_id=self.event_id, venue_id=self.venue.id,
            start_time=self.event.start_time, end_time=self.event.end_time, status="confirmed"))
        self.db.session.commit()
        clock = mock.patch.object(routes, "singapore_now", return_value=START - timedelta(hours=1))
        clock.start()
        self.addCleanup(clock.stop)
        email = mock.patch.object(routes.tasks.send_notification_email, "delay")
        self.email = email.start()
        self.addCleanup(email.stop)

    def approve(self):
        return self.client.post(APPROVAL_PATH.format(event_id=self.event_id),
            json={"comment": COMMENT}, headers=self.auth_headers(self.officer))

    def stored_event(self):
        self.db.session.expire_all()
        event = self.db.session.get(Event, self.event_id)
        return {column.name: getattr(event, column.name) for column in Event.__table__.columns}

    # TC-91-02 / AC2: real persistence, independent coordinator read and notification.
    def test_persisted_decision_is_visible_to_the_notified_coordinator(self):
        before = datetime.utcnow()
        response = self.approve()
        after = datetime.utcnow()
        self.assertEqual(response.status_code, 200, response.get_json())
        stored = self.stored_event()
        self.assertEqual(stored["safety_decision"], "approved")
        self.assertEqual(stored["safety_decided_by_id"], self.officer.id)
        self.assertEqual(stored["safety_comment"], COMMENT)
        self.assertLessEqual(before, stored["safety_decided_at"])
        self.assertLessEqual(stored["safety_decided_at"], after)
        # Existing coordinator request approval is a separate record (SCRUM-32).
        self.assertEqual(stored["decision_note"], "Coordinator request approval")
        self.assertEqual(stored["decided_by_id"], self.coordinator.id)
        view = self.client.get(f"/api/events/{self.event_id}/planning",
                               headers=self.auth_headers(self.coordinator))
        self.assertEqual(view.status_code, 200, view.get_json())
        self.assertEqual(view.get_json()["safety_check"], {
            "decision": "approved", "comment": COMMENT,
            "officer": {"id": self.officer.id, "email": self.officer.email},
            "decided_at": stored["safety_decided_at"].isoformat(),
        })
        notifications = self.client.get("/api/notifications/",
                                        headers=self.auth_headers(self.coordinator))
        self.assertEqual(notifications.status_code, 200, notifications.get_json())
        own = [row for row in notifications.get_json()["notifications"]
               if row["event_id"] == self.event_id]
        self.assertEqual(len(own), 1)
        self.assertIn("approved", own[0]["message"].lower())
        self.assertIn(self.event.title, own[0]["message"])

    # TC-91-05 / AC5: force failure after SQL flush so rollback must undo writes.
    def test_failed_commit_rolls_back_decision_and_notification_together(self):
        before = self.stored_event()
        flush = self.db.session.flush

        def fail_after_flush():
            flush()
            raise SQLAlchemyError("Private simulated save failure")

        with mock.patch.object(self.db.session, "commit", side_effect=fail_after_flush) as commit:
            response = self.approve()
        self.assertEqual(response.status_code, 503, response.get_json())
        commit.assert_called_once()
        body = response.get_json()
        self.assertTrue(body.get("error"))
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("Private simulated save failure", body["error"])
        self.assertNotIn("safety_check", body)
        self.assertEqual(self.stored_event(), before)
        self.assertEqual(Notification.query.filter_by(event_id=self.event_id).count(), 0)
        self.email.assert_not_called()
