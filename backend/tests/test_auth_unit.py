"""SCRUM-75 TC-75-01..06: isolated HTTP evidence when local Postgres is down.

Real password hashing/JWT, mocked user lookup; no engine or network access.
Persisted integration coverage remains in test_auth.AuthTests.
"""

import socket
import unittest
from types import SimpleNamespace
from unittest import mock

from flask import Flask
from flask_jwt_extended import JWTManager, decode_token
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from app.auth import routes
from app.events.routes import events_bp


class AuthHttpUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "Scrum75-test-password!"
        cls.password_hash = generate_password_hash(cls.password)

    def setUp(self):
        for target, attribute in ((Engine, "connect"), (Engine, "raw_connection"),
                                  (socket.socket, "connect")):
            guard = mock.patch.object(target, attribute, side_effect=AssertionError("Unexpected database/network access"))
            guard.start()
            self.addCleanup(guard.stop)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="scrum-75-isolated-unit-secret-32-bytes")
        JWTManager(self.app)
        self.app.register_blueprint(routes.auth_bp, url_prefix="/api/auth")
        self.app.register_blueprint(events_bp, url_prefix="/api/events")
        self.client = self.app.test_client()
        self.user = SimpleNamespace(id=75, email="signin@test.invalid", role="coordinator",
                                    password_hash=self.password_hash)
        user_model = mock.patch.object(routes, "User")
        self.query = user_model.start().query
        self.addCleanup(user_model.stop)
        self.query.filter_by.return_value.first.return_value = self.user
        session = mock.patch.object(routes.db, "session")
        self.session = session.start()
        self.addCleanup(session.stop)

    def login(self, **overrides):
        return self.client.post("/api/auth/login", json={
            "email": self.user.email, "password": self.password, **overrides,
        })

    def assert_refused(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertNotIn("access_token", response.get_json())
        self.assertFalse(response.headers.getlist("Set-Cookie"))
        return response.get_json()

    def test_success_returns_token_and_stored_role(self):
        # SCRUM-76 TC-76-01: extend existing login evidence for both Week 7 roles.
        for role in ("coordinator", "coordinator_lead", "safety_officer"):
            with self.subTest(role=role):
                self.user.role = role
                response = self.login()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["role"], role)
                with self.app.app_context():
                    self.assertEqual(decode_token(response.get_json()["access_token"])["sub"], "75")

    def test_invalid_credentials_never_issue_a_token(self):
        with mock.patch.object(routes, "create_access_token") as issue:
            for known_user in (self.user, None):
                with self.subTest(known_user=known_user is not None):
                    self.query.filter_by.return_value.first.return_value = known_user
                    body = self.assert_refused(self.login(password="incorrect"), 401)
                    self.assertEqual(body["error"], "Email or password is incorrect")
            issue.assert_not_called()

    def test_empty_credentials_name_only_missing_fields_without_issuing_token(self):
        with mock.patch.object(routes, "create_access_token") as issue:
            for fields in (("email",), ("password",), ("email", "password")):
                with self.subTest(fields=fields):
                    body = self.assert_refused(self.login(**dict.fromkeys(fields, "")), 400)
                    self.assertEqual(body["missing"], list(fields))
                    for field in fields:
                        self.assertIn(field, body["error"].lower())
            self.query.filter_by.assert_not_called()
            issue.assert_not_called()

    def test_outage_is_retryable_without_issuing_token(self):
        self.query.filter_by.side_effect = SQLAlchemyError("private outage detail")
        with mock.patch.object(routes, "create_access_token") as issue:
            response = self.login()
            body = self.assert_refused(response, 503)
            self.assertTrue(body["retryable"])
            self.assertIn("try again", body["error"])
            self.assertNotIn("private outage detail", response.get_data(as_text=True))
            self.session.rollback.assert_called_once()
            issue.assert_not_called()

    def test_protected_request_without_browser_token_is_refused(self):
        response = self.client.get("/api/events/75/planning")
        self.assertEqual(response.status_code, 401)
        self.session.get.assert_not_called()
