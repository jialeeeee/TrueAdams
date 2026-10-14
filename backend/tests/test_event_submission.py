"""SCRUM-28 RED cases TC-28-09/10/15/16 from the coverage workbook.

Run SubmissionUnitTests alone for database-independent Flask/JWT coverage.
The fake query exercises production filtering/ordering calls over unordered
fixtures; it does not establish PostgreSQL execution or transaction guarantees.
SubmissionPersistenceTests is separate: stale identity-map state needs a real
ORM session. Existing SCRUM-29 integration tests retain rollback coverage.
"""

import socket
import unittest
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.sql.operators import desc_op

from app.events import routes
from app.models import Event, User
from tests.test_event_drafts import COMPLETE, DRAFT_FIELDS, DraftTestCase


class _UserQuery:
    """Small fake of the existing User.query surface, with no SQL execution."""

    def __init__(self, users):
        self.users = list(users)

    def filter_by(self, **fields):
        return _UserQuery(u for u in self.users
                          if all(getattr(u, key) == value for key, value in fields.items()))

    def filter(self, expression):
        # Existing reassignment helper excludes the current coordinator this way.
        return _UserQuery(u for u in self.users
                          if expression.operator(getattr(u, expression.left.key),
                                                 expression.right.value))

    def order_by(self, column):
        key = getattr(column, "key", None) or column.element.key
        return _UserQuery(sorted(self.users, key=lambda user: getattr(user, key),
                                 reverse=getattr(column, "modifier", None) is desc_op))

    def all(self):
        return list(self.users)

    def first(self):
        return next(iter(self.users), None)


class _RequestRecord(SimpleNamespace):
    """Inject the ORM read failure that expiration can expose after commit."""

    def __getattribute__(self, name):
        data = object.__getattribute__(self, "__dict__")
        if data.get("_reads_unavailable") and name in Event.__table__.columns.keys():
            raise SQLAlchemyError("simulated read outage after successful commit")
        return object.__getattribute__(self, name)


class SubmissionUnitTests(unittest.TestCase):
    def setUp(self):
        for target in ("connect", "raw_connection"):
            guard = mock.patch.object(
                Engine, target, side_effect=AssertionError("Database access in unit test")
            )
            guard.start()
            self.addCleanup(guard.stop)
        network = mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("Network access in unit test")
        )
        network.start()
        self.addCleanup(network.stop)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="scrum-28-isolated-unit-secret-32-bytes")
        JWTManager(self.app)
        self.app.register_blueprint(routes.events_bp, url_prefix="/api/events")
        self.client = self.app.test_client()
        # Deliberately unordered. Lowest-ID users are ineligible; email order also
        # favours the wrong coordinator, so first-row/email selection cannot pass.
        self.users = {
            9: SimpleNamespace(id=9, role="coordinator", email="alpha@test.invalid"),
            1: SimpleNamespace(id=1, role="organiser", email="owner@test.invalid"),
            2: SimpleNamespace(id=2, role="admin", email="admin@test.invalid"),
            3: SimpleNamespace(id=3, role="attendee", email="former-coordinator@test.invalid"),
            5: SimpleNamespace(id=5, role="coordinator", email="zulu@test.invalid"),
        }
        self.event = _RequestRecord(**{c.name: None for c in Event.__table__.columns})
        self.event.__dict__.update(
            id=7, organiser_id=1, status="draft", created_at=datetime(2026, 10, 1),
            last_saved_at=datetime(2026, 10, 1), **COMPLETE
        )
        self.session = mock.MagicMock()
        self.session.get.side_effect = self.load
        session_patch = mock.patch.object(routes.db, "session", self.session)
        session_patch.start()
        self.addCleanup(session_patch.stop)
        query_patch = mock.patch.object(
            User, "query", new_callable=mock.PropertyMock,
            side_effect=lambda: _UserQuery(self.users.values())
        )
        query_patch.start()
        self.addCleanup(query_patch.stop)

    def load(self, model, record_id, **kwargs):
        if model is User:
            return self.users.get(record_id)
        if model is Event and record_id == self.event.id:
            return self.event
        return None

    def headers(self, user_id=1):
        with self.app.app_context():
            token = create_access_token(identity=str(user_id))
        return {"Authorization": f"Bearer {token}"}

    def submit(self):
        return self.client.post("/api/events/drafts/7/submit", headers=self.headers())

    # TC-28-09: AC4/5. Production routes, not a mocked selector or permission rule.
    def test_submission_assigns_reviewer_and_preserves_access_boundaries(self):
        before = {field: getattr(self.event, field) for field in DRAFT_FIELDS}
        response = self.submit()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.event.coordinator_id, 5, "Select lowest current coordinator ID.")
        self.assertIsInstance(self.event.coordinator_assigned_at, datetime)
        self.assertEqual(response.get_json()["id"], 7)
        self.assertEqual(response.get_json()["status"], "submitted")
        self.assertEqual({field: getattr(self.event, field) for field in DRAFT_FIELDS}, before)
        self.session.commit.assert_called_once()
        self.session.add.assert_not_called()  # Submission does not insert another row/reservation.
        review = self.client.get("/api/events/7/review", headers=self.headers(5))
        self.assertEqual(review.status_code, 200, review.get_json())
        self.assertEqual(review.get_json()["request"]["id"], 7)
        for user_id in (1, 2, 9):
            with self.subTest(viewer=user_id):
                refused = self.client.get("/api/events/7/review", headers=self.headers(user_id))
                self.assertEqual(refused.status_code, 403)
                self.assertNotIn(COMPLETE["title"], refused.get_data(as_text=True))

    # TC-28-10: AC4/6. No candidate is an operational refusal, never a partial save.
    def test_no_eligible_coordinator_uses_agreed_submission_outcome(self):
        for user in self.users.values():
            if user.role == "coordinator":
                user.role = "attendee"
        before = deepcopy(self.event.__dict__)
        response = self.submit()
        self.assertEqual(response.status_code, 503, response.get_json())
        body = response.get_json()
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"coordinator.*availab")
        self.assertEqual(self.event.__dict__, before)
        self.session.commit.assert_not_called()
        self.session.add.assert_not_called()
        # A later current-role change enables safe retry on the same identity.
        self.users[5].role = "coordinator"
        retried = self.submit()
        self.assertEqual(retried.status_code, 200, retried.get_json())
        self.assertEqual(retried.get_json()["id"], 7)
        self.assertEqual(self.event.coordinator_id, 5)

    # TC-28-15: AC4/6. Inject response-read failure; not proof of durable DB commit.
    def test_successful_submission_survives_post_commit_read_outage(self):
        def commit_then_disable_reads():
            self.event._reads_unavailable = True

        self.session.commit.side_effect = commit_then_disable_reads
        response = self.submit()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.session.commit.assert_called_once()
        self.session.rollback.assert_not_called()
        self.assertEqual(response.get_json()["id"], 7)
        self.assertEqual(response.get_json()["status"], "submitted")
        self.assertIsNotNone(response.get_json()["submitted_at"])

        # TC-28-15 also distinguishes a lost COMMIT acknowledgement from a
        # confirmed rollback. This fault injection does not prove DB durability.
        with self.subTest(outcome="unknown commit outcome"):
            self.event.__dict__.update(_reads_unavailable=False, status="draft",
                                       submitted_at=None, coordinator_id=None,
                                       coordinator_assigned_at=None)
            self.session.commit.reset_mock()
            self.session.rollback.reset_mock()
            self.session.commit.side_effect = DBAPIError(
                "COMMIT", {}, Exception("simulated connection loss"),
                connection_invalidated=True,
            )
            response = self.submit()
            self.assertEqual(response.status_code, 503, response.get_json())
            self.assertIs(response.get_json().get("outcome_uncertain"), True)
            self.assertIs(response.get_json().get("retryable"), True)
            self.assertIn("could not confirm", response.get_json()["error"])
            self.assertNotIn("still saved as a draft", response.get_json()["error"])
            self.session.rollback.assert_called_once()


class SubmissionPersistenceTests(DraftTestCase):
    # TC-28-16: AC4/5. Real identity-map/persistence invariant, no mandated lock API.
    def test_stale_draft_cannot_overwrite_submitted_request(self):
        for action in ("save", "submit"):
            with self.subTest(action=action):
                event = Event(organiser_id=self.users["dana"].id, status="draft", **COMPLETE)
                self.db.session.add(event)
                self.db.session.commit()
                event_id = event.id
                self.assertEqual(event.status, "draft")  # Cache the pre-transition row.
                at = datetime(2026, 10, 14, 1, 0)
                coordinator_id = self.users["alice"].id
                self.db.session.execute(
                    text("update events set status = 'submitted', submitted_at = :at, "
                         "coordinator_id = :coordinator, coordinator_assigned_at = :at "
                         "where id = :id"),
                    {"at": at, "coordinator": coordinator_id, "id": event_id},
                )
                url = f"/api/events/drafts/{event_id}"
                response = (
                    self.client.put(url, json={"description": "Stale edit"}, headers=self.headers())
                    if action == "save" else
                    self.client.post(f"{url}/submit", headers=self.headers())
                )
                self.assert_error(response, 409)
                stored = self.stored(event_id)
                self.assertEqual(stored["status"], "submitted")
                self.assertEqual(stored["submitted_at"], at)
                self.assertEqual(stored["coordinator_id"], coordinator_id)
                self.assertEqual(stored["coordinator_assigned_at"], at)
                self.assertEqual(stored["description"], COMPLETE["description"])
