"""SCRUM-55 TC-55-01..05: UNEXECUTED RED preparation, no database.

See docs/test-cases/SCRUM-55-review-submitted-event-request.md. The list URL
and response are a proposed additive contract, not an existing API. The user
confirmed only submitted and under_review are eligible for this separate list.
The Flask/JWT setup follows test_authorization_http_unit.py; AppTestCase is
deliberately avoided because it opens a real Supabase connection.
"""

import socket
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query
from sqlalchemy.sql import operators

from app.events import routes
from app.models import Event, EventClarification, User


class _ReadQuery:
    """Evaluate simple production predicates over rows, never execute SQL.

    Like SCRUM-28's _UserQuery, deliberately supports only the existing query
    surface needed here. This verifies filtering decisions, not SQL semantics.
    Unsupported expressions fail loudly instead of silently returning fixtures.
    """

    def __init__(self, rows):
        self.rows = list(rows)

    def filter_by(self, **fields):
        return _ReadQuery(row for row in self.rows
                          if all(getattr(self._record(row), key) == value
                                 for key, value in fields.items()))

    @staticmethod
    def _record(row):
        return row[0] if isinstance(row, tuple) else row

    def filter(self, *expressions):
        def matches(row, expression):
            # SQLAlchemy's IN operator has no Python implementation.
            if expression.operator.__name__ == "in_op":
                return getattr(self._record(row), expression.left.key) in expression.right.value
            return expression.operator(getattr(self._record(row), expression.left.key),
                                       expression.right.value)
        return _ReadQuery(row for row in self.rows
                          if all(matches(row, expression) for expression in expressions))

    def join(self, *args):
        # Clarification rows are already paired with their sender below.
        return self

    def order_by(self, *args):
        # SCRUM-55 specifies no ordering; do not introduce a sorting requirement.
        return self

    def all(self):
        return list(self.rows)


class ReviewRequestsUnitTests(unittest.TestCase):
    def setUp(self):
        for method in ("connect", "raw_connection"):
            guard = mock.patch.object(Engine, method,
                                      side_effect=AssertionError("Database access in unit test"))
            guard.start()
            self.addCleanup(guard.stop)
        network = mock.patch.object(socket.socket, "connect",
                                    side_effect=AssertionError("Network access in unit test"))
        network.start()
        self.addCleanup(network.stop)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="scrum-55-isolated-unit-secret-32-bytes")
        JWTManager(self.app)
        self.app.register_blueprint(routes.events_bp, url_prefix="/api/events")
        self.client = self.app.test_client()
        self.users = {
            1: SimpleNamespace(id=1, role="organiser", email="owner@test.invalid"),
            2: SimpleNamespace(id=2, role="coordinator", email="current@test.invalid"),
            3: SimpleNamespace(id=3, role="coordinator", email="other@test.invalid"),
        }
        self.events = [
            self.event(7, "Selected request", "submitted", 2),
            self.event(8, "Private draft", "draft", 2),
            self.event(9, "Other coordinator's request", "submitted", 3),
            self.event(10, "Unassigned request", "submitted", None),
            self.event(11, "Request under review", "under_review", 2),
            self.event(12, "Approved request", "approved", 2),
            self.event(13, "Rejected request", "rejected", 2),
            self.event(14, "Cancelled request", "cancelled", 2),
        ]
        self.session = mock.MagicMock()
        self.session.get.side_effect = self.load
        patcher = mock.patch.object(routes.db, "session", self.session)
        patcher.start()
        self.addCleanup(patcher.stop)
        query = mock.patch.object(Event, "query", new_callable=mock.PropertyMock,
                                  side_effect=lambda: _ReadQuery(self.events))
        self.event_query = query.start()
        self.addCleanup(query.stop)

    @staticmethod
    def event(event_id, title, status, coordinator_id):
        values = {column.name: None for column in Event.__table__.columns}
        values.update(id=event_id, title=title, status=status, coordinator_id=coordinator_id,
                      organiser_id=1, start_time=datetime(2026, 12, 12, 17),
                      submitted_at=None if status == "draft" else datetime(2026, 10, 14, 1))
        return SimpleNamespace(**values)

    def load(self, model, record_id, **kwargs):
        if model is User:
            return self.users.get(record_id)
        if model is Event:
            return next((event for event in self.events if event.id == record_id), None)
        raise AssertionError(f"Unexpected model read: {model}")

    def headers(self, user_id=2, **kwargs):
        with self.app.app_context():
            token = create_access_token(identity=str(user_id), **kwargs)
        return {"Authorization": f"Bearer {token}"}

    def listing(self, headers=None):
        return self.client.get("/api/events/review-requests",
                               headers=self.headers() if headers is None else headers)

    def assert_read_only(self):
        self.session.add.assert_not_called()
        self.session.delete.assert_not_called()
        self.session.commit.assert_not_called()

    # TC-55-01: AC1, AC2. Returning every fixture cannot satisfy this assertion.
    def test_list_includes_only_assigned_submitted_and_under_review_requests(self):
        response = self.listing()
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertCountEqual(body["requests"], [{
            "id": 7, "title": "Selected request", "status": "submitted",
            "organiser": {"id": 1, "email": "owner@test.invalid"},
            "start_time": "2026-12-12T17:00:00", "submitted_at": "2026-10-14T01:00:00",
        }, {
            "id": 11, "title": "Request under review", "status": "under_review",
            "organiser": {"id": 1, "email": "owner@test.invalid"},
            "start_time": "2026-12-12T17:00:00", "submitted_at": "2026-10-14T01:00:00",
        }])
        self.assertIsNone(body["message"])
        self.assert_read_only()

    # TC-55-02: AC3. Existing rows, but none eligible for this coordinator.
    def test_no_eligible_requests_has_an_explanatory_empty_state(self):
        self.events = [event for event in self.events if event.id not in (7, 11)]
        response = self.listing()
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["requests"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())

    # TC-55-03: AC6. New endpoint needs its own guard; existing guards aren't inherited.
    def test_list_requires_a_valid_session_and_current_coordinator_role(self):
        for headers in ({}, self.headers(999)):
            with self.subTest(session=headers != {}):
                self.assertEqual(self.listing(headers).status_code, 401)
        headers = self.headers(additional_claims={"role": "coordinator"})
        for role in ("admin", "organiser", "venue_staff", "tech_staff", "attendee"):
            with self.subTest(role=role):
                self.users[2].role = role
                response = self.listing(headers)
                self.assertEqual(response.status_code, 403)
                self.assertTrue(response.get_json()["error"].strip())
                self.assertNotIn("Selected request", response.get_data(as_text=True))
                self.assertNotIn("owner@test.invalid", response.get_data(as_text=True))
        self.assert_read_only()

    # TC-55-04: AC7. A failed event read must not look like an empty successful list.
    def test_list_load_failure_is_retryable_and_recovery_returns_requests(self):
        self.event_query.side_effect = SQLAlchemyError("Private outage detail")
        response = self.listing()
        self.assertEqual(response.status_code, 503, response.get_json())
        body = response.get_json()
        self.assertIs(body["retryable"], True)
        self.assertTrue(body["error"].strip())
        self.assertNotIn("requests", body)
        self.assertNotIn("Private outage", response.get_data(as_text=True))
        self.session.rollback.assert_called_once()
        self.event_query.side_effect = lambda: _ReadQuery(self.events)
        recovered = self.listing()
        self.assertEqual(recovered.status_code, 200, recovered.get_json())
        self.assertCountEqual([row["id"] for row in recovered.get_json()["requests"]], [7, 11])

    # TC-55-05: AC5. Existing tests check viewers, not two events' message isolation.
    def test_clarification_history_contains_only_the_selected_requests_messages(self):
        sender = self.users[2]
        selected = SimpleNamespace(id=20, event_id=7, message="Selected question?",
                                   sender_id=2, created_at=datetime(2026, 10, 14, 2))
        unrelated = SimpleNamespace(id=21, event_id=9, message="Private other question?",
                                    sender_id=3, created_at=datetime(2026, 10, 14, 3))
        self.session.query.return_value = _ReadQuery([(selected, sender), (unrelated, self.users[3])])
        response = self.client.get("/api/events/7/clarifications", headers=self.headers())
        self.assertEqual(response.status_code, 200, response.get_json())
        self.session.query.assert_called_once_with(EventClarification, User)
        self.assertEqual(response.get_json()["event"]["id"], 7)
        self.assertEqual([row["message"] for row in response.get_json()["clarifications"]],
                         ["Selected question?"])
        self.assertNotIn(unrelated.message, response.get_data(as_text=True))
        self.assert_read_only()

    # TC-55-11: compile the actual route's ORM query, without executing SQL.
    def test_real_orm_query_scopes_assignment_and_status_and_preserves_null_submission(self):
        statements = []
        self.events[0].submitted_at = None

        def capture(query):
            statements.append(query.statement)
            return [self.events[0], self.events[4]]

        with mock.patch.object(Event, "query", Query(Event, session=self.session)), \
             mock.patch.object(Query, "all", autospec=True, side_effect=capture):
            response = self.listing()

        self.assertEqual(response.status_code, 200, response.get_json())
        [statement] = statements
        # Compilation uses only model metadata and the local PostgreSQL dialect.
        statement.compile(dialect=postgresql.dialect())
        predicates = {clause.left.key: clause for clause in statement.whereclause.clauses}
        self.assertEqual(set(predicates), {"coordinator_id", "status"})
        self.assertIs(predicates["coordinator_id"].operator, operators.eq)
        self.assertEqual(predicates["coordinator_id"].right.value, 2)
        self.assertIs(predicates["status"].operator, operators.in_op)
        self.assertEqual(set(predicates["status"].right.value), {"submitted", "under_review"})
        by_id = {row["id"]: row for row in response.get_json()["requests"]}
        self.assertIsNone(by_id[7]["submitted_at"])
        self.assertEqual(by_id[11]["submitted_at"], "2026-10-14T01:00:00")
        self.assert_read_only()

    # TC-55-12: a secondary read outage is an error, not a missing organiser.
    def test_organiser_read_failure_does_not_return_partial_or_fabricated_data(self):
        def load(model, record_id, **kwargs):
            if model is User and record_id == 1:
                raise SQLAlchemyError("Private organiser outage")
            return self.load(model, record_id, **kwargs)

        self.session.get.side_effect = load
        response = self.listing()

        self.assertEqual(response.status_code, 503, response.get_json())
        self.assertIs(response.get_json()["retryable"], True)
        self.assertNotIn("requests", response.get_json())
        self.assertNotIn("Private organiser outage", response.get_data(as_text=True))
        self.session.rollback.assert_called_once()
        self.assert_read_only()
