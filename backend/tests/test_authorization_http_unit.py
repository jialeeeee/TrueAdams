"""SCRUM-27 TC-27-01..08: Flask/JWT unit tests with mocked persistence.

Since SCRUM-82 only an Event Coordinator Lead (user 6) may reassign; the current
coordinator (2) and the admin (5) are refused.

No AppTestCase, app factory, engine, Supabase, credentials or SMTP. These verify
route guards and side-effect calls, NOT database durability or real row locks.
The equivalent persisted workflows stay in tests/test_authorization.py.
"""

import re
import socket
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

import jwt as token_codec

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.events import routes
from app.models import Event, User


class AuthorizationHttpUnitTests(unittest.TestCase):
    def setUp(self):
        # Fail loudly if isolation regresses; no engine is initialized here.
        for target in ("connect", "raw_connection"):
            guard = mock.patch.object(Engine, target, side_effect=AssertionError("Database access in unit test"))
            guard.start()
            self.addCleanup(guard.stop)
        network = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("Network access in unit test"))
        network.start()
        self.addCleanup(network.stop)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="scrum-27-isolated-unit-secret-32-bytes")
        JWTManager(self.app)
        self.app.register_blueprint(routes.events_bp, url_prefix="/api/events")
        self.client = self.app.test_client()
        self.users = {
            1: SimpleNamespace(id=1, role="organiser", email="owner@test.invalid"),
            2: SimpleNamespace(id=2, role="coordinator", email="current@test.invalid"),
            3: SimpleNamespace(id=3, role="coordinator", email="replacement@test.invalid"),
            4: SimpleNamespace(id=4, role="attendee", email="attendee@test.invalid"),
            5: SimpleNamespace(id=5, role="admin", email="admin@test.invalid"),
            6: SimpleNamespace(id=6, role="coordinator_lead", email="lead@test.invalid"),
        }
        self.event = SimpleNamespace(**{c.name: None for c in Event.__table__.columns})
        self.event.__dict__.update(id=7, title="Private event", status="submitted", organiser_id=1,
                                   coordinator_id=2, coordinator_assigned_at=datetime(2026, 10, 1),
                                   created_at=datetime(2026, 10, 1))
        self.session = mock.MagicMock()
        self.session.get.side_effect = self.load
        # Supply response fields normally populated by INSERT defaults; no SQL.
        self.session.add.side_effect = self.add_response_defaults
        patcher = mock.patch.object(routes.db, "session", self.session)
        patcher.start()
        self.addCleanup(patcher.stop)
        candidates = mock.patch.object(routes, "_eligible_coordinators", return_value=[self.users[3]])
        self.candidates = candidates.start()
        self.addCleanup(candidates.stop)
        email = mock.patch.object(routes.tasks.send_notification_email, "delay")
        self.email = email.start()
        self.addCleanup(email.stop)
        self.session.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = []

    def load(self, model, record_id, **kwargs):
        if model is User:
            return self.users.get(record_id)
        if model is Event:
            return self.event if record_id == self.event.id else None
        return None

    def add_response_defaults(self, row):
        row.id = 100
        row.created_at = datetime(2026, 10, 13)

    def headers(self, user_id=2, **kwargs):
        with self.app.app_context():
            token = create_access_token(identity=str(user_id), **kwargs)
        return {"Authorization": f"Bearer {token}"}

    def reassign(self, caller=6, target=3, body=None):
        return self.client.put("/api/events/7/coordinator", headers=self.headers(caller),
                               json={"coordinator_id": target} if body is None else body)

    def assert_refused_unchanged(self, response, before, status=403):
        self.assertEqual(response.status_code, status)
        self.assertEqual(self.event.__dict__, before)
        self.session.commit.assert_not_called()
        self.session.add.assert_not_called()
        self.email.assert_not_called()
        self.assertNotIn(self.event.title, response.get_data(as_text=True))

    def test_unrelated_coordinator_cannot_reassign_or_self_assign(self):
        before = dict(self.event.__dict__)
        for target in (2, 3):
            with self.subTest(target=target):
                self.assert_refused_unchanged(self.reassign(caller=3, target=target), before)
        response = self.client.get("/api/events/7/eligible-coordinators", headers=self.headers(3))
        self.assertEqual(response.status_code, 403)
        self.candidates.assert_not_called()

    def test_lead_can_reassign_and_lock_is_requested(self):
        response = self.reassign()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.event.coordinator_id, 3)
        self.session.get.assert_any_call(Event, 7, with_for_update=True, populate_existing=True)
        self.session.commit.assert_called_once()

    # SCRUM-82: the former admin override and the current coordinator are refused, and
    # even a Lead cannot assign an unassigned event here (the SCRUM-81 queue does).
    def test_admin_and_current_coordinator_cannot_reassign(self):
        before = dict(self.event.__dict__)
        for caller in (5, 2):
            with self.subTest(caller=caller):
                self.assert_refused_unchanged(self.reassign(caller=caller), before)
        self.event.coordinator_id = None
        before = dict(self.event.__dict__)
        self.assert_refused_unchanged(self.reassign(), before, 409)

    def test_old_coordinator_loses_reads_and_writes_new_coordinator_gains_them(self):
        previous, replacement = self.headers(2), self.headers(3)
        self.assertEqual(self.reassign().status_code, 200)
        for suffix in ("planning", "review", "clarifications"):
            with self.subTest(read=suffix):
                self.assertEqual(self.client.get(f"/api/events/7/{suffix}", headers=previous).status_code, 403)
                self.assertEqual(self.client.get(f"/api/events/7/{suffix}", headers=replacement).status_code, 200)
        # SCRUM-82: listing replacements is the Lead's, not either coordinator's.
        for headers in (previous, replacement):
            self.assertEqual(self.client.get("/api/events/7/eligible-coordinators", headers=headers).status_code, 403)
        # The reassignment itself saved and notified; only the refused writes below may not.
        for call in (self.session.commit, self.session.add, self.email):
            call.reset_mock()
        for method, suffix, body in (("PATCH", "", {"title": "Forged"}),
                                     ("POST", "/decision", {"decision": "approve"}),
                                     ("POST", "/clarifications", {"message": "Question?"}),
                                     ("PUT", "/coordinator", {"coordinator_id": 2})):
            with self.subTest(write=suffix):
                before = dict(self.event.__dict__)
                response = self.client.open(f"/api/events/7{suffix}", method=method, json=body, headers=previous)
                self.assert_refused_unchanged(response, before)
        self.assertEqual(self.client.patch("/api/events/7", json={"title": "Allowed"}, headers=replacement).status_code, 200)
        self.assertEqual(self.client.post("/api/events/7/clarifications", json={"message": "Question?"}, headers=replacement).status_code, 201)
        self.assertEqual(self.client.post("/api/events/7/decision", json={"decision": "approve"}, headers=replacement).status_code, 200)

    def test_former_organiser_loses_owner_reads_but_retains_new_role_permissions(self):
        headers = self.headers(1)
        for role in ("attendee", "coordinator", "venue_staff", "tech_staff"):
            with self.subTest(role=role):
                self.users[1].role = role
                expected = 403 if role == "attendee" else 200
                self.assertEqual(self.client.get("/api/events/7/coordinator", headers=headers).status_code, expected)
                self.assertEqual(self.client.get("/api/events/7/clarifications", headers=headers).status_code, 403)

    def test_read_only_clarification_history_has_no_sending_capability(self):
        response = self.client.get("/api/events/7/clarifications", headers=self.headers(1))
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.get_json()["can_send"], False)
        response = self.client.get("/api/events/7/clarifications", headers=self.headers(2))
        self.assertIs(response.get_json()["can_send"], True)

    def test_unrelated_organiser_and_attendee_direct_reads_are_denied(self):
        for role in ("organiser", "attendee", "venue_staff", "tech_staff"):
            self.users[4].role = role
            for suffix in ("planning", "review", "clarifications", "eligible-coordinators"):
                with self.subTest(role=role, path=suffix):
                    response = self.client.get(f"/api/events/7/{suffix}", headers=self.headers(4))
                    self.assertEqual(response.status_code, 403)
                    self.assertNotIn(self.event.title, response.get_data(as_text=True))

    def test_forged_role_claim_cannot_authorize_reassignment(self):
        before = dict(self.event.__dict__)
        for claim in ("admin", "coordinator_lead"):
            with self.subTest(claim=claim):
                headers = self.headers(4, additional_claims={"role": claim})
                response = self.client.put("/api/events/7/coordinator", json={"coordinator_id": 4}, headers=headers)
                self.assert_refused_unchanged(response, before)

    def test_forged_relationship_fields_are_rejected_before_mutation(self):
        before = dict(self.event.__dict__)
        for field in ("organiser_id", "event_id", "coordinator_assigned_at", "status", "user_id"):
            with self.subTest(field=field):
                self.assert_refused_unchanged(self.reassign(body={"coordinator_id": 3, field: 3}), before, 400)

    def test_planning_cannot_smuggle_identity_or_noneditable_fields(self):
        before = dict(self.event.__dict__)
        for field in ("organiser_id", "coordinator_id", "status", "decided_by_id", "registration_capacity",
                      "registration_opens_at", "registration_closes_at"):
            with self.subTest(field=field):
                response = self.client.patch("/api/events/7", json={field: 4}, headers=self.headers())
                self.assert_refused_unchanged(response, before, 422)

    def test_authorization_precedes_validation(self):
        before = dict(self.event.__dict__)
        self.assert_refused_unchanged(self.reassign(caller=3, body={"coordinator_id": "invalid"}), before)

    def test_missing_deleted_and_nonnumeric_user_sessions_are_rejected(self):
        for headers in ({}, self.headers(999), self.headers("not-an-id")):
            with self.subTest(headers_present=bool(headers)):
                self.assertEqual(self.client.get("/api/events/7/coordinator", headers=headers).status_code, 401)

    def test_invalid_tokens_never_reach_the_user_lookup(self):
        with self.app.app_context():
            refresh = create_refresh_token(identity="2")
            wrong_signature = token_codec.encode({"sub": "2", "type": "access"},
                "wrong-isolated-unit-secret-at-least-32-bytes", algorithm="HS256")
        tokens = ("malformed", create_token_expired(self.app), refresh, wrong_signature)
        self.session.get.reset_mock()
        for token in tokens:
            with self.subTest(token_type=token == refresh):
                for route in self.app.url_map.iter_rules():
                    if not hasattr(self.app.view_functions[route.endpoint], "__wrapped__"):
                        continue
                    for method in route.methods - {"HEAD", "OPTIONS"}:
                        # Every ID in the path, e.g. SCRUM-42's <int:requirement_id> too.
                        path = re.sub(r"<int:\w+>", "7", route.rule)
                        response = self.client.open(path, method=method, json={},
                            headers={"Authorization": f"Bearer {token}"})
                        self.assertIn(response.status_code, (401, 422), (method, path))
        self.session.get.assert_not_called()

    def test_database_failure_is_retryable_and_rolls_back(self):
        self.session.get.side_effect = SQLAlchemyError("Private outage detail")
        response = self.reassign()
        self.assertEqual(response.status_code, 503)
        self.assertIs(response.get_json()["retryable"], True)
        self.assertNotIn("Private outage", response.get_data(as_text=True))
        self.session.rollback.assert_called_once()
        self.session.commit.assert_not_called()

    def test_failed_commit_requests_rollback_without_a_success_payload(self):
        self.session.commit.side_effect = SQLAlchemyError("Private commit detail")
        response = self.reassign()
        self.assertEqual(response.status_code, 503)
        self.assertIs(response.get_json()["retryable"], True)
        self.assertNotIn("coordinator", response.get_json())
        self.assertNotIn("Private commit", response.get_data(as_text=True))
        self.session.rollback.assert_called_once()


def create_token_expired(app):
    with app.app_context():
        return create_access_token(identity="2", expires_delta=timedelta(seconds=-1))
