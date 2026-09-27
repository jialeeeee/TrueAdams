"""SCRUM-27: first RED increment for Flask credential-based login.

Login returns 200 with access_token; invalid credentials return 401 with the
same public error; missing/empty credentials return 400; lookup outages return
503 with retry guidance. Errors follow the existing {"error": str} convention.
Venue details exercise established permissions without inventing event rules.
All fixtures use AppTestCase's rolled-back PostgreSQL transaction.
"""

import json

from flask_jwt_extended import decode_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from app.models import User
from tests.base import AppTestCase, run_email


class AuthTests(AppTestCase):
    PASSWORD = "Scrum27-test-password!"

    def make_login_user(self, role="attendee"):
        return self.make_user(
            role=role, password_hash=generate_password_hash(self.PASSWORD)
        )

    def login(self, email, password):
        return self.client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )

    def assert_login_error(self, response, status):
        self.assertEqual(response.status_code, status)
        body = response.get_json()
        self.assertIsInstance(body, dict)
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        self.assertNotIn("access_token", body)
        return body

    def test_valid_credentials_return_usable_access_token(self):
        user = self.make_login_user(role="coordinator")
        venue = self.make_venue()
        user_id, email, password_hash = user.id, user.email, user.password_hash
        venue_id = venue.id

        response = self.login(email, self.PASSWORD)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIsInstance(body, dict)
        token = body.get("access_token")
        self.assertIsInstance(token, str)
        self.assertTrue(token)
        claims = decode_token(token)
        self.assertEqual(claims["sub"], str(user_id))
        self.assertEqual(claims["type"], "access")
        for payload in (body, claims):
            serialized = json.dumps(payload)
            self.assertNotIn(self.PASSWORD, serialized)
            self.assertNotIn(password_hash, serialized)
            self.assertNotIn('"password"', serialized)
            self.assertNotIn('"password_hash"', serialized)

        protected = self.client.get(
            f"/api/venues/{venue_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(protected.status_code, 200)
        self.assertEqual(protected.get_json()["id"], venue_id)

    def test_invalid_credentials_are_rejected(self):
        user = self.make_login_user()
        unknown_email = run_email("unknown-auth-user@test.invalid")
        self.assertIsNone(User.query.filter_by(email=unknown_email).first())
        errors = []
        cases = (
            ("wrong password", user.email, "Incorrect-test-password!"),
            ("unknown email", unknown_email, self.PASSWORD),
        )
        for label, email, password in cases:
            with self.subTest(case=label):
                body = self.assert_login_error(self.login(email, password), 401)
                self.assertNotIn(email, body["error"])
                errors.append(body["error"])
        if len(errors) == len(cases):
            self.assertEqual(errors[0], errors[1])

    def test_missing_or_empty_credentials_are_rejected(self):
        email = run_email("missing-credentials@test.invalid")
        cases = (
            ("missing email", {"password": self.PASSWORD}),
            ("missing password", {"email": email}),
            ("empty email", {"email": "", "password": self.PASSWORD}),
            ("empty password", {"email": email, "password": ""}),
        )
        for label, payload in cases:
            with self.subTest(case=label):
                response = self.client.post("/api/auth/login", json=payload)
                self.assert_login_error(response, 400)

    def test_authentication_service_failure_is_retryable(self):
        user = self.make_login_user()
        email = user.email
        internal_detail = "SCRUM27 simulated private database outage"
        failed_lookups = []

        def fail_user_lookup(conn, cursor, statement, parameters, context, executemany):
            # Inspect SQLAlchemy's compiled SELECT tables, not a particular ORM
            # query method. Savepoints and rollback statements remain untouched.
            compiled = context.compiled
            query = compiled.statement if compiled is not None else None
            if query is not None and getattr(query, "is_select", False):
                if any(
                    table.is_derived_from(User.__table__)
                    for table in query.get_final_froms()
                ):
                    failed_lookups.append(True)
                    raise OperationalError(statement, parameters, Exception(internal_detail))

        self.db.session.expire_all()
        sa_event.listen(self.connection, "before_cursor_execute", fail_user_lookup)
        try:
            response = self.login(email, self.PASSWORD)
        finally:
            sa_event.remove(self.connection, "before_cursor_execute", fail_user_lookup)

        body = self.assert_login_error(response, 503)
        self.assertTrue(failed_lookups, "The outage must occur during a user lookup")
        self.assertRegex(body["error"].lower(), r"retry|try again")
        public_response = response.get_data(as_text=True)
        for detail in (internal_detail, "OperationalError", "SELECT", self.PASSWORD):
            self.assertNotIn(detail, public_response)

    def test_login_token_preserves_role_restrictions(self):
        user = self.make_login_user(role="attendee")
        venue = self.make_venue(name="Restricted planning venue")
        venue_id, venue_name = venue.id, venue.name

        response = self.login(user.email, self.PASSWORD)

        self.assertEqual(response.status_code, 200)
        token = response.get_json().get("access_token")
        self.assertIsInstance(token, str)
        self.assertTrue(token)
        protected = self.client.get(
            f"/api/venues/{venue_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(protected.status_code, 403)
        body = protected.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        self.assertNotIn(venue_name, protected.get_data(as_text=True))
