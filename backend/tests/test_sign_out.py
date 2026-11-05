"""SCRUM-75 AC6 "A signed-in user can sign out. Afterwards protected pages and requests are
refused until they sign in again." (TC-75-09..12 in docs/test-cases/SCRUM-75-test-cases.md).

Model (db/revoked_tokens.sql): revoked_tokens, one row per signed-out token by its JWT ID.

Endpoint
    POST /api/auth/logout   (JWT required) signs out of this token only
        200 {"message": "You have signed out."}
        401 no token, or one already signed out: {"error": "You have signed out. ..."}
        503 {"error", "retryable": true} if it can't be saved; the token still works
    Every @jwt_required() route refuses a signed-out token with that 401.
"""

from datetime import datetime, timedelta

from flask_jwt_extended import decode_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from app.models import RevokedToken
from tests.base import AppTestCase

PASSWORD = "Scrum75-sign-out-password!"
SIGNED_OUT = "You have signed out. Please sign in again."


class SignOutTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user(role="attendee",
                                   password_hash=generate_password_hash(PASSWORD))

    def sign_in(self):
        response = self.client.post("/api/auth/login",
                                    json={"email": self.user.email, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.get_json())
        return {"Authorization": f"Bearer {response.get_json()['access_token']}"}

    def sign_out(self, headers):
        return self.client.post("/api/auth/logout", headers=headers)

    def protected(self, headers):
        # Any protected route: the attendee's own registrations (SCRUM-68).
        return self.client.get("/api/registrations/", headers=headers)

    def revoked(self):
        self.db.session.expire_all()
        return RevokedToken.query.filter_by(user_id=self.user.id).all()

    # TC-75-09 · AC6
    def test_tc_75_09_after_signing_out_the_token_is_refused_everywhere(self):
        headers = self.sign_in()
        self.assertEqual(self.protected(headers).status_code, 200)

        response = self.sign_out(headers)

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json(), {"message": "You have signed out."})
        for call in (lambda: self.protected(headers),
                     lambda: self.client.get("/api/notifications/", headers=headers),
                     lambda: self.client.get("/api/events/", headers=headers),
                     lambda: self.sign_out(headers)):
            refused = call()
            self.assertEqual(refused.status_code, 401, refused.get_json())
            self.assertEqual(refused.get_json(), {"error": SIGNED_OUT})

    # TC-75-09 · AC6
    def test_tc_75_09_the_signed_out_token_is_recorded_with_its_expiry(self):
        headers = self.sign_in()
        claims = decode_token(headers["Authorization"].split()[1])
        before = datetime.utcnow()

        self.sign_out(headers)

        [row] = self.revoked()
        self.assertEqual(row.jti, claims["jti"])
        self.assertTrue(before - timedelta(seconds=1) <= row.revoked_at <= datetime.utcnow())
        self.assertEqual(row.expires_at, datetime.utcfromtimestamp(claims["exp"]))

    # TC-75-10 · AC6
    def test_tc_75_10_signing_in_again_works_and_other_sessions_carry_on(self):
        laptop, phone = self.sign_in(), self.sign_in()

        self.sign_out(laptop)

        self.assertEqual(self.protected(phone).status_code, 200)
        again = self.sign_in()
        self.assertEqual(self.protected(again).status_code, 200)
        self.assertEqual(self.protected(laptop).status_code, 401)

    # TC-75-11 · AC6
    def test_tc_75_11_signing_out_needs_a_token(self):
        response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.revoked(), [])

    # TC-75-12 · AC6
    def test_tc_75_12_a_failed_sign_out_says_so_and_the_token_still_works(self):
        headers = self.sign_in()

        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO revoked_tokens"):
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            response = self.sign_out(headers)
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        self.assertEqual(response.status_code, 503, response.get_json())
        self.assertEqual(response.get_json(), {
            "error": "Signing out on the server failed. Please try again.", "retryable": True})
        self.assertEqual(self.revoked(), [])
        self.assertEqual(self.protected(headers).status_code, 200)
        # Trying again works.
        self.assertEqual(self.sign_out(headers).status_code, 200)

    # TC-75-12 · AC6 (A9)
    def test_tc_75_12_an_unreadable_check_leaves_the_route_to_report_its_own_failure(self):
        headers = self.sign_in()

        def fail(conn, cursor, statement, parameters, context, executemany):
            if "revoked_tokens" in statement:
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            with self.assertLogs(self.app.logger, level="ERROR") as logs:
                response = self.protected(headers)
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertIn("Could not check whether a token was signed out", logs.output[0])
