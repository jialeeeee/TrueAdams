"""SCRUM-92 TC-92-01..06; see the matching test-case document.

Five isolated HTTP tests exercise production decisions, permissions and readiness.
One optional AppTestCase verifies real persistence/rollback on loopback PostgreSQL
only. No .env loading, schema creation, remote connections or borrowed test helpers.
"""

import copy
import socket
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

with mock.patch("dotenv.load_dotenv", return_value=False):
    from app.config import Config, TestConfig
    from app.events import routes
    from app.models import (
        EquipmentRequirement, EquipmentReservation, Event, Notification, User,
        Venue, VenueBooking,
    )
    from tests.base import AppTestCase


# SCRUM-92 A1/Q1: proposed additive actions, following SCRUM-91's approve URL.
ACTIONS = {"reject": "rejected", "request-changes": "changes_requested"}
DECISION_PATH = "/api/events/{event_id}/safety-checks/{action}"
# A2/Q2: Planning is the existing approved arrangement stage, not request rejection.
PLANNING_STATUS = "approved"
COMMENT = "Keep the emergency exit clear and describe the revised access route."
START = datetime(2030, 1, 16, 17)


class _ReadQuery:
    """Evaluate simple production predicates; unsupported shapes fail visibly."""

    def __init__(self, rows):
        self.rows = list(rows)

    def filter_by(self, **fields):
        return _ReadQuery(row for row in self.rows
                          if all(getattr(row, key) == value for key, value in fields.items()))

    def filter(self, *expressions):
        def matches(row, expression):
            value = getattr(row, expression.left.key)
            if expression.operator.__name__ == "in_op":
                return value in expression.right.value
            return expression.operator(value, expression.right.value)
        return _ReadQuery(row for row in self.rows
                          if all(matches(row, expression) for expression in expressions))

    def order_by(self, *args):
        return self

    def all(self):
        return list(self.rows)

    def __iter__(self):
        return iter(self.rows)


class SafetyRejectionChangesUnitTests(unittest.TestCase):
    def setUp(self):
        for target, name in ((Engine, "connect"), (Engine, "raw_connection"),
                             (socket.socket, "connect")):
            guard = mock.patch.object(target, name,
                side_effect=AssertionError("Database/network access in SCRUM-92 unit test"))
            guard.start()
            self.addCleanup(guard.stop)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="scrum-92-isolated-secret-at-least-32-bytes")
        JWTManager(self.app)
        self.app.register_blueprint(routes.events_bp, url_prefix="/api/events")
        self.client = self.app.test_client()
        self.officer = SimpleNamespace(id=92, role="safety_officer", email="officer@test.invalid")
        self.coordinator = SimpleNamespace(id=2, role="coordinator", email="current@test.invalid")
        self.other = SimpleNamespace(id=3, role="coordinator", email="other@test.invalid")
        self.event = SimpleNamespace(**{column.name: None for column in Event.__table__.columns})
        vars(self.event).update(id=1, title="Safety corrections workshop", status=PLANNING_STATUS,
            organiser_id=4, coordinator_id=2, venue_id=10, start_time=START,
            end_time=START + timedelta(hours=2), expected_attendance=40,
            description="Original access route", equipment_requirements="One microphone",
            last_saved_at=datetime(2026, 1, 1), created_at=datetime(2026, 1, 1))
        self.rows = {
            Event: [self.event], User: [self.officer, self.coordinator, self.other],
            Venue: [SimpleNamespace(id=10, name="Meeting Room", location="Level 1")],
            VenueBooking: [SimpleNamespace(id=20, event_id=1, venue_id=10, status="confirmed",
                start_time=START, end_time=self.event.end_time, setup_minutes=0,
                turnaround_minutes=0, hold_expires_at=None)],
            EquipmentRequirement: [SimpleNamespace(id=30, event_id=1,
                equipment_type="Microphone", quantity=1)],
            EquipmentReservation: [SimpleNamespace(id=40, event_id=1, requirement_id=30,
                resource_id=50, quantity=1, status="reserved")],
            Notification: [],
        }
        self.session = mock.MagicMock()
        self.session.get.side_effect = lambda model, key, **kwargs: next(
            (row for row in self.rows[model] if row.id == key), None)
        session = mock.patch.object(routes.db, "session", self.session)
        session.start()
        self.addCleanup(session.stop)
        self.session.query.side_effect = lambda model: _ReadQuery(self.rows[model])
        for model in self.rows:
            query = mock.patch.object(model, "query", new_callable=mock.PropertyMock,
                side_effect=lambda model=model: _ReadQuery(self.rows[model]))
            query.start()
            self.addCleanup(query.stop)
        for patcher in (
            mock.patch.object(routes, "singapore_now", return_value=START - timedelta(hours=1)),
            mock.patch.object(routes.tasks.send_notification_email, "delay"),
        ):
            result = patcher.start()
            self.addCleanup(patcher.stop)
            if hasattr(result, "assert_not_called"):
                self.email = result
        # Validate fixtures using real production readiness before missing routes
        # can hide fixture errors. No eligibility/decision helper is patched.
        self.assertEqual([item["id"] for item in routes._safety_check_items([self.event])], [1])

    def headers(self, user):
        with self.app.app_context():
            token = create_access_token(identity=str(user.id),
                                        additional_claims={"role": "safety_officer"})
        return {"Authorization": f"Bearer {token}"}

    def decide(self, action, body=None, user=None, authenticated=True):
        return self.client.post(DECISION_PATH.format(event_id=1, action=action),
            json={"comment": COMMENT} if body is None else body,
            headers=self.headers(user or self.officer) if authenticated else {})

    def no_writes(self, before):
        self.assertEqual(vars(self.event), before)
        self.session.add.assert_not_called()
        self.session.add_all.assert_not_called()
        self.session.commit.assert_not_called()
        self.email.assert_not_called()

    # TC-92-01 / AC1: both actions, omitted/empty/whitespace comment and exact text.
    def test_both_actions_require_a_comment_and_preserve_the_supplied_text(self):
        initial = copy.deepcopy(vars(self.event))
        for action, decision in ACTIONS.items():
            for body in ({}, {"comment": ""}, {"comment": " \t\n "}, {"comment": COMMENT}):
                with self.subTest(action=action, body=body):
                    vars(self.event).update(copy.deepcopy(initial))
                    self.session.reset_mock()
                    self.email.reset_mock()
                    response = self.decide(action, body)
                    valid = body.get("comment") == COMMENT
                    self.assertEqual(response.status_code, 200 if valid else 400, response.get_json())
                    if valid:
                        self.assertEqual(self.event.safety_decision, decision)
                        self.assertEqual(self.event.safety_comment, COMMENT)
                        self.assertEqual(self.event.last_saved_at, initial["last_saved_at"])
                        self.assertEqual(response.get_json()["safety_check"]["comment"], COMMENT)
                        self.session.commit.assert_called_once()
                    else:
                        self.assertTrue(response.get_json().get("error"))
                        self.assertEqual(response.get_json().get("field"), "comment")
                        self.no_writes(initial)

    # TC-92-02/03 / AC2/3: production response and coordinator read, not durability.
    def test_planning_outcome_and_comment_notify_the_assigned_coordinator(self):
        initial = copy.deepcopy(vars(self.event))
        for action, decision in ACTIONS.items():
            with self.subTest(action=action):
                vars(self.event).update(copy.deepcopy(initial))
                # Existing SCRUM-91 summary already handles negative outcomes;
                # exercise that reuse before testing decision submission.
                vars(self.event).update(safety_decision=decision, safety_decided_by_id=self.officer.id,
                    safety_comment=COMMENT, safety_decided_at=datetime(2026, 10, 29, 8))
                existing = self.client.get("/api/events/1/planning", headers=self.headers(self.coordinator))
                self.assertEqual(existing.status_code, 200, existing.get_json())
                self.assertEqual(existing.get_json()["safety_check"], {
                    "decision": decision, "comment": COMMENT,
                    "officer": {"id": self.officer.id, "email": self.officer.email},
                    "decided_at": "2026-10-29T08:00:00",
                })
                vars(self.event).update(copy.deepcopy(initial))
                self.session.reset_mock()
                earliest = datetime.utcnow()
                response = self.decide(action)
                latest = datetime.utcnow()
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(self.event.status, PLANNING_STATUS)
                self.assertEqual(self.event.safety_decision, decision)
                self.assertEqual(self.event.safety_decided_by_id, self.officer.id)
                self.assertLessEqual(earliest, self.event.safety_decided_at)
                self.assertLessEqual(self.event.safety_decided_at, latest)
                notification = self.session.add.call_args.args[0]
                self.assertIsInstance(notification, Notification)
                self.assertEqual(notification.recipient_id, self.coordinator.id)
                self.assertEqual(notification.event_id, self.event.id)
                self.assertIn(COMMENT, notification.message)
                self.assertIn("rejected" if action == "reject" else "changes", notification.message.lower())
                self.session.commit.assert_called_once()
                view = self.client.get("/api/events/1/planning", headers=self.headers(self.coordinator))
                self.assertEqual(view.status_code, 200, view.get_json())
                self.assertEqual(view.get_json()["safety_check"], {
                    "decision": decision, "officer": {"id": self.officer.id, "email": self.officer.email},
                    "comment": COMMENT, "decided_at": self.event.safety_decided_at.isoformat(),
                })

    # TC-92-04 / AC4: seed a recorded negative outcome; exercise actual queue,
    # permitted coordinator PATCH, SCRUM-91 approval and SCRUM-93 confirmation.
    def test_recheck_waits_for_coordinator_correction_and_new_approval(self):
        initial = copy.deepcopy(vars(self.event))
        for decision in ACTIONS.values():
            with self.subTest(decision=decision):
                vars(self.event).update(copy.deepcopy(initial))
                vars(self.event).update(safety_decision=decision, safety_decided_by_id=self.officer.id,
                    safety_comment=COMMENT, safety_decided_at=datetime.utcnow() - timedelta(minutes=1))
                self.rows[EquipmentReservation][0].status = "reserved"
                self.session.reset_mock()
                self.email.reset_mock()  # Isolate the prior subtest's successful approval email.
                existing_gate = self.client.post("/api/events/1/confirm",
                    headers=self.headers(self.coordinator))
                self.assertEqual(existing_gate.status_code, 409, existing_gate.get_json())
                self.assertEqual(existing_gate.get_json()["missing"], ["Approved safety check"])
                self.assertEqual(self.event.status, PLANNING_STATUS)
                self.session.commit.assert_not_called()
                self.assertEqual(self.queue_ids(), [], "Awaiting coordinator corrections, not a new check")
                premature = self.client.post("/api/events/1/safety-checks/approve",
                    json={}, headers=self.headers(self.officer))
                self.assertEqual(premature.status_code, 409, premature.get_json())
                self.assertEqual(self.event.safety_decision, decision)
                before = copy.deepcopy(vars(self.event))
                denied = self.client.patch("/api/events/1", json={"description": "Unrelated edit"},
                                           headers=self.headers(self.other))
                self.assertEqual(denied.status_code, 403, denied.get_json())
                self.no_writes(before)
                self.assertEqual(self.queue_ids(), [])
                unchanged = self.client.patch("/api/events/1", json={"description": self.event.description},
                                               headers=self.headers(self.coordinator))
                self.assertEqual(unchanged.status_code, 200, unchanged.get_json())
                self.assertEqual(self.event.last_saved_at, before["last_saved_at"])
                self.assertEqual(self.queue_ids(), [])
                correction = "Emergency exit kept clear; access route moved to the east entrance."
                saved = self.client.patch("/api/events/1", json={"description": correction},
                                          headers=self.headers(self.coordinator))
                self.assertEqual(saved.status_code, 200, saved.get_json())
                self.assertEqual(self.event.description, correction)
                self.assertEqual(self.queue_ids(), [1])
                # An update alone does not override SCRUM-90's equipment readiness.
                self.rows[EquipmentReservation][0].status = "released"
                self.assertEqual(self.queue_ids(), [])
                self.rows[EquipmentReservation][0].status = "reserved"
                self.assertEqual(self.queue_ids(), [1])
                refused = self.client.post("/api/events/1/confirm", headers=self.headers(self.coordinator))
                self.assertEqual(refused.status_code, 409, refused.get_json())
                self.assertIn("Approved safety check", refused.get_json()["missing"])
                self.assertEqual(self.event.status, PLANNING_STATUS)
                approved = self.client.post("/api/events/1/safety-checks/approve",
                                             json={}, headers=self.headers(self.officer))
                self.assertEqual(approved.status_code, 200, approved.get_json())
                confirmed = self.client.post("/api/events/1/confirm", headers=self.headers(self.coordinator))
                self.assertEqual(confirmed.status_code, 200, confirmed.get_json())
                self.assertEqual(self.event.status, "confirmed")

    def queue_ids(self):
        response = self.client.get("/api/events/safety-checks", headers=self.headers(self.officer))
        self.assertEqual(response.status_code, 200, response.get_json())
        return [item["id"] for item in response.get_json()["events"]]

    # TC-92-05 / AC5: stored role wins over the privileged token claim.
    def test_other_roles_and_missing_authentication_cannot_write(self):
        for action in ACTIONS:
            for role in (None, "admin", "coordinator", "coordinator_lead", "organiser",
                         "venue_staff", "tech_staff", "attendee"):
                with self.subTest(action=action, role=role):
                    self.officer.role = role
                    before = copy.deepcopy(vars(self.event))
                    response = self.decide(action, authenticated=role is not None)
                    self.assertEqual(response.status_code, 401 if role is None else 403)
                    self.no_writes(before)

    # TC-92-06 / AC6: actual HTTP failure branch; no mocked rollback durability claim.
    def test_save_failure_returns_retryable_error_without_success_or_email(self):
        initial = copy.deepcopy(vars(self.event))
        for action in ACTIONS:
            with self.subTest(action=action):
                # A mock rollback is not an ORM rollback; use a fresh event state
                # so an earlier failed action cannot poison the next fixture.
                vars(self.event).update(copy.deepcopy(initial))
                self.session.reset_mock()
                self.session.commit.side_effect = SQLAlchemyError("Private simulated save failure")
                response = self.decide(action)
                self.assertEqual(response.status_code, 503, response.get_json())
                body = response.get_json()
                self.assertTrue(body.get("error"))
                self.assertIs(body.get("retryable"), True)
                self.assertNotIn("safety_check", body)
                self.assertNotIn("Private simulated save failure", body["error"])
                self.session.commit.assert_called_once()
                self.session.rollback.assert_called_once()
                self.email.assert_not_called()


class SafetyRejectionChangesLocalTests(AppTestCase):
    @classmethod
    def setUpClass(cls):
        # Guard below runs before AppTestCase can open any connection.
        pass

    def setUp(self):
        uri = TestConfig.SQLALCHEMY_DATABASE_URI
        if not uri:
            self.skipTest("No explicit loopback PostgreSQL TEST_DATABASE_URL; .env is not loaded.")
        url = make_url(uri)
        if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1", "::1"}:
            self.skipTest("Remote/shared databases forbidden; requires loopback PostgreSQL.")
        if Config.SQLALCHEMY_DATABASE_URI:
            development = make_url(Config.SQLALCHEMY_DATABASE_URI)
            if (url.host, url.port, url.database) == (development.host, development.port, development.database):
                self.skipTest("Use a separate local test database, never development data.")
        super().setUp()
        self.officer = self.make_user(role="safety_officer")
        self.coordinator = self.make_user(role="coordinator")
        venue = self.make_venue()
        self.venue = venue
        self.event = self.make_event(status=PLANNING_STATUS, venue=venue, start_time=START,
            coordinator_id=self.coordinator.id, expected_attendance=40)
        self.event_id = self.event.id
        self.db.session.add(VenueBooking(event_id=self.event_id, venue_id=venue.id,
            start_time=START, end_time=self.event.end_time, status="confirmed"))
        self.db.session.commit()
        for patcher in (
            mock.patch.object(routes, "singapore_now", return_value=START - timedelta(hours=1)),
            mock.patch.object(routes.tasks.send_notification_email, "delay"),
        ):
            result = patcher.start()
            self.addCleanup(patcher.stop)
            if hasattr(result, "assert_not_called"):
                self.email = result

    def stored(self):
        self.db.session.expire_all()
        event = self.db.session.get(Event, self.event_id)
        return {column.name: getattr(event, column.name) for column in Event.__table__.columns}

    # TC-92-03/06 / AC3/6: a real flush then failed commit must leave no partial
    # decision or notification; retry and independent coordinator read prove storage.
    def test_flushed_failure_is_atomic_and_retry_persists_coordinator_visible_decision(self):
        for action, decision in ACTIONS.items():
            with self.subTest(action=action):
                before = self.stored()
                count = Notification.query.filter_by(event_id=self.event_id).count()
                self.email.reset_mock()
                flush = self.db.session.flush

                def fail_after_flush():
                    self.assertEqual(self.event.safety_decision, decision)
                    self.assertEqual(self.event.safety_comment, COMMENT)
                    self.assertEqual(self.event.status, PLANNING_STATUS)
                    flush()
                    self.assertEqual(Notification.query.filter_by(event_id=self.event_id).count(), count + 1)
                    raise SQLAlchemyError("Private simulated save failure")

                path = DECISION_PATH.format(event_id=self.event_id, action=action)
                with mock.patch.object(self.db.session, "commit", side_effect=fail_after_flush):
                    response = self.client.post(path, json={"comment": COMMENT},
                                               headers=self.auth_headers(self.officer))
                self.assertEqual(response.status_code, 503, response.get_json())
                self.assertEqual(self.stored(), before)
                self.assertEqual(Notification.query.filter_by(event_id=self.event_id).count(), count)
                self.email.assert_not_called()
                earliest = datetime.utcnow()
                saved = self.client.post(path, json={"comment": COMMENT},
                                         headers=self.auth_headers(self.officer))
                latest = datetime.utcnow()
                self.assertEqual(saved.status_code, 200, saved.get_json())
                stored = self.stored()
                self.assertEqual(stored["safety_decision"], decision)
                self.assertEqual(stored["safety_decided_by_id"], self.officer.id)
                self.assertEqual(stored["safety_comment"], COMMENT)
                self.assertLessEqual(earliest, stored["safety_decided_at"])
                self.assertLessEqual(stored["safety_decided_at"], latest)
                notifications = Notification.query.filter_by(event_id=self.event_id).all()
                self.assertEqual(len(notifications), count + 1)
                self.assertEqual(notifications[-1].recipient_id, self.coordinator.id)
                self.assertIn(COMMENT, notifications[-1].message)
                view = self.client.get(f"/api/events/{self.event_id}/planning",
                                       headers=self.auth_headers(self.coordinator))
                self.assertEqual(view.status_code, 200, view.get_json())
                self.assertEqual(view.get_json()["safety_check"], {
                    "decision": decision, "comment": COMMENT,
                    "officer": {"id": self.officer.id, "email": self.officer.email},
                    "decided_at": stored["safety_decided_at"].isoformat(),
                })
                # Fresh eligible event for the other action; no production reset.
                if action == "reject":
                    self.venue = self.make_venue()  # Separate venue avoids overlapping confirmed fixtures.
                    self.event = self.make_event(status=PLANNING_STATUS, venue=self.venue,
                        start_time=START, coordinator_id=self.coordinator.id, expected_attendance=40)
                    self.event_id = self.event.id
                    self.db.session.add(VenueBooking(event_id=self.event_id, venue_id=self.event.venue_id,
                        start_time=START, end_time=self.event.end_time, status="confirmed"))
                    self.db.session.commit()
