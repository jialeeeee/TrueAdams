"""SCRUM-95 TC-95-01..05: isolated HTTP tests and one local persistence check.

See docs/test-cases/SCRUM-95-clarification-resubmission.md for the proposed
resubmission contract and working assumptions. Unit tests do not use AppTestCase;
the persistence class checks for loopback PostgreSQL before its setup. Real routes/JWT/models are exercised;
only persistence and the email queue are replaced. This verifies ORM write intent
and rollback handling, not PostgreSQL durability or RLS.
"""

import socket
import unittest
from datetime import datetime
from unittest import mock

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy import inspect
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query
from sqlalchemy.sql import operators

from app.events import routes
from app.config import TestConfig
from app.models import Event, EventClarification, Notification, User
from tests.base import AppTestCase, get_test_app


# SCRUM-95 A1/Q1: one reply and optional permitted edits saved on resubmission.
RESUBMIT_URL = "/api/events/7/resubmit"
REPLY = "The accessible entrance will be staffed throughout the event."
DESCRIPTION = "An updated description with the accessible entrance arrangements."
# Must match MAX_CLARIFICATION_WORDS in backend/app/events/routes.py (AC2).
MAX_WORDS = 1000


class ClarificationResubmissionTests(unittest.TestCase):
    def setUp(self):
        for target, name in ((Engine, "connect"), (Engine, "raw_connection"),
                             (socket.socket, "connect"), (socket.socket, "connect_ex")):
            guard = mock.patch.object(target, name, side_effect=AssertionError(
                "Database/network access forbidden in isolated SCRUM-95 tests"))
            guard.start()
            self.addCleanup(guard.stop)
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True, JWT_SECRET_KEY="scrum-95-isolated-secret-at-least-32-bytes")
        JWTManager(self.app)
        self.app.register_blueprint(routes.events_bp, url_prefix="/api/events")
        self.client = self.app.test_client()
        self.owner = User(id=1, role="organiser", email="owner@test.invalid")
        self.coordinator = User(id=2, role="coordinator", email="coordinator@test.invalid")
        self.other = User(id=3, role="organiser", email="other@test.invalid")
        self.event = Event(id=7, title="Charity Gala", organiser_id=1, coordinator_id=2,
                           status="under_review", description="Original description",
                           start_time=datetime(2026, 12, 12, 17),
                           end_time=datetime(2026, 12, 12, 20),
                           review_started_at=datetime(2026, 10, 29, 2),
                           review_started_by_id=2)
        self.foreign = Event(id=8, title="Private request", organiser_id=3,
                             coordinator_id=2, status="under_review")
        self.questions = [
            EventClarification(id=20, event_id=7, sender_id=2,
                               message="Who will staff the accessible entrance?",
                               created_at=datetime(2026, 10, 29, 3)),
            EventClarification(id=21, event_id=8, sender_id=2,
                               message="Private question for the other organiser",
                               created_at=datetime(2026, 10, 29, 4)),
        ]
        self.rows = {User: [self.owner, self.coordinator, self.other],
                     Event: [self.event, self.foreign]}
        self.session = mock.MagicMock()
        self.session.get.side_effect = lambda model, key, **kwargs: next(
            (row for row in self.rows[model] if row.id == key), None)
        # Construct the real ORM query; intercept only execution, below.
        self.session.query.side_effect = lambda *models: Query(models, session=self.session)
        # GREEN needs a real pending-question read; intercept its SQL execution
        # just as the original owner-history test intercepts Query.all().
        latest = mock.patch.object(Query, "first", autospec=True, side_effect=lambda query: max(
            (row for row in self.questions
             if row.event_id == query.statement.whereclause.right.value),
            key=lambda row: (row.created_at, row.id), default=None))
        latest.start()
        self.addCleanup(latest.stop)
        session = mock.patch.object(routes.db, "session", self.session)
        session.start()
        self.addCleanup(session.stop)
        email = mock.patch.object(routes.tasks.send_notification_email, "delay")
        self.email = email.start()
        self.addCleanup(email.stop)

    def headers(self, user=None):
        with self.app.app_context():
            token = create_access_token(identity=str((user or self.owner).id))
        return {"Authorization": f"Bearer {token}"}

    def resubmit(self, message=REPLY, changes=None):
        return self.client.post(RESUBMIT_URL, headers=self.headers(),
                                json={"message": message, "changes": changes or {}})

    def added(self, model):
        return [call.args[0] for call in self.session.add.call_args_list
                if isinstance(call.args[0], model)]

    # TC-95-01 / AC1: existing behavior should pass, not manufacture a RED gap.
    def test_owner_reads_only_own_questions_and_foreign_access_exposes_nothing(self):
        def history(query):
            # Inspect the actual production filter, rather than give it a
            # prefiltered successful fixture regardless of the query it builds.
            predicate = query.statement.whereclause
            self.assertTrue(predicate.left.shares_lineage(
                EventClarification.__table__.c.event_id))
            self.assertIs(predicate.operator, operators.eq)
            return [(row, self.coordinator) for row in self.questions
                    if row.event_id == predicate.right.value]

        with mock.patch.object(Query, "all", autospec=True, side_effect=history) as read:
            response = self.client.get("/api/events/7/clarifications", headers=self.headers())
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual([row["message"] for row in response.get_json()["clarifications"]],
                             [self.questions[0].message])
            self.assertNotIn(self.questions[1].message, response.get_data(as_text=True))
            denied = self.client.get("/api/events/8/clarifications", headers=self.headers())
            self.assertEqual(denied.status_code, 403, denied.get_json())
            self.assertTrue(denied.get_json()["error"].strip())
            self.assertNotIn("clarifications", denied.get_json())
            for secret in (self.questions[1].message, self.foreign.title, self.other.email):
                self.assertNotIn(secret, denied.get_data(as_text=True))
            read.assert_called_once()
        self.session.commit.assert_not_called()

    # TC-95-02 / AC2: whitespace-delimited words, not a character limit (A2/Q2).
    def test_reply_refuses_blank_and_over_limit_but_saves_exactly_1000_words(self):
        for message in ("", " \t\n ", "word " * (MAX_WORDS + 1)):
            with self.subTest(words=len(message.split())):
                response = self.resubmit(message)
                self.assertEqual(response.status_code, 400, response.get_json())
                self.assertTrue(response.get_json()["error"].strip())
                self.session.add.assert_not_called()
                self.session.commit.assert_not_called()
                self.email.assert_not_called()
        message = " \t" + " \n".join(["reply"] * MAX_WORDS) + " \n"
        self.assertGreater(len(message), 1000)
        response = self.resubmit(message)
        self.assertEqual(response.status_code, 200, response.get_json())
        [reply] = self.added(EventClarification)
        self.assertEqual((reply.event_id, reply.sender_id, reply.message),
                         (7, self.owner.id, message.strip()))
        self.session.commit.assert_called_once()

    # TC-95-03, TC-95-04 / AC3, AC4: one successful flow avoids duplicate tests.
    def test_resubmit_keeps_reply_and_permitted_edit_notifies_and_review_can_continue(self):
        def committed():
            [reply] = self.added(EventClarification)
            [notice] = self.added(Notification)
            self.assertEqual((reply.event_id, reply.sender_id, reply.message), (7, 1, REPLY))
            self.assertEqual((notice.event_id, notice.recipient_id), (7, self.coordinator.id))
            self.assertTrue(notice.message.strip())
            self.assertEqual((self.event.description, self.event.status), (DESCRIPTION, "submitted"))
            self.email.assert_not_called()  # Email follows the shared commit.

        self.session.commit.side_effect = committed
        response = self.resubmit(changes={"description": DESCRIPTION})
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["request"]["status"], "submitted")
        self.assertEqual(body["request"]["description"], DESCRIPTION)
        self.assertEqual(self.event.coordinator_id, self.coordinator.id)
        self.assertIs(body["notification"]["in_app"], True)
        self.assertIs(body["notification"]["email_queued"], True)
        self.session.commit.assert_called_once()
        self.email.assert_called_once()
        self.assertEqual(self.email.call_args.args[0], self.coordinator.email)
        # Read back through the existing history route; coordinator sees the reply.
        [reply] = self.added(EventClarification)
        reply.id, reply.created_at = 22, datetime(2026, 10, 30, 1)
        with mock.patch.object(Query, "all", return_value=[
                (self.questions[0], self.coordinator), (reply, self.owner)]):
            history = self.client.get("/api/events/7/clarifications",
                                      headers=self.headers(self.coordinator))
        self.assertEqual(history.status_code, 200, history.get_json())
        self.assertEqual(history.get_json()["clarifications"][-1]["message"], REPLY)
        self.session.commit.side_effect = None
        continued = self.client.post("/api/events/7/review", headers=self.headers(self.coordinator))
        self.assertEqual(continued.status_code, 200, continued.get_json())
        self.assertEqual(continued.get_json()["request"]["status"], "under_review")

    # TC-95-05 / AC5: verify rollback intent, not simulated database durability.
    def test_save_failure_rolls_back_reply_edits_status_and_notification_without_email(self):
        self.session.commit.side_effect = SQLAlchemyError("Private simulated save error")
        response = self.resubmit(changes={"description": DESCRIPTION})
        self.assertEqual(response.status_code, 503, response.get_json())
        body = response.get_json()
        self.assertTrue(body["error"].strip())
        self.assertIs(body["retryable"], True)
        self.assertNotIn("request", body)
        self.assertNotIn("notification", body)
        self.assertNotIn("Private simulated", response.get_data(as_text=True))
        # All new rows must belong to the one attempted transaction.
        self.assertEqual(len(self.added(EventClarification)), 1)
        self.assertEqual(len(self.added(Notification)), 1)
        self.session.commit.assert_called_once()
        self.session.rollback.assert_called_once()
        self.email.assert_not_called()


    # TC-95-01/03/04: RED lacked guards for the new owner-only editing exception.
    def test_resubmission_refuses_other_owners_closed_or_answered_requests_and_restricted_edits(self):
        denied = self.client.post(RESUBMIT_URL, headers=self.headers(self.other),
                                  json={"message": REPLY, "changes": {"description": DESCRIPTION}})
        self.assertEqual(denied.status_code, 403, denied.get_json())
        self.assertNotIn(self.event.title, denied.get_data(as_text=True))
        self.event.status = "approved"
        self.assertEqual(self.resubmit().status_code, 409)
        self.event.status = "under_review"
        self.questions.append(EventClarification(id=22, event_id=7, sender_id=1,
                              message="Already answered", created_at=datetime(2026, 10, 30, 1)))
        self.assertEqual(self.resubmit().status_code, 409)
        self.questions.pop()
        response = self.resubmit(changes={"description": DESCRIPTION, "expected_attendance": 150})
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertIn("requires_review", response.get_json())
        self.assertEqual(self.event.description, "Original description")
        self.session.add.assert_not_called()
        self.session.commit.assert_not_called()
        self.email.assert_not_called()


class ClarificationResubmissionLocalTests(AppTestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(TestConfig.SQLALCHEMY_DATABASE_URI or "postgresql://")
        if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1", "::1"}:
            raise unittest.SkipTest("SCRUM-95 persistence requires loopback PostgreSQL; never use remote databases.")
        super().setUpClass()
        # The existing local container may predate other stories' model columns.
        # Read metadata only; GREEN explicitly forbids repairing schemas here.
        with get_test_app().app_context():
            from app.extensions import db
            actual = {column["name"] for column in inspect(db.engine).get_columns(Event.__tablename__)}
        missing = set(Event.__table__.columns.keys()) - actual
        if missing:
            raise unittest.SkipTest("Local events schema lacks model columns: " + ", ".join(sorted(missing)))

    # TC-95-03/04/05: the actual atomicity gap left by persistence mocks.
    def test_local_postgresql_commits_together_and_rolls_back_a_failed_resubmission(self):
        organiser = self.make_user(role="organiser")
        coordinator = self.make_user(role="coordinator")
        with mock.patch.object(routes.tasks.send_notification_email, "delay") as email:
            for fails in (False, True):
                with self.subTest(commit_fails=fails):
                    email.reset_mock()
                    event = self.make_event(organiser=organiser, coordinator_id=coordinator.id,
                                            status="under_review", description="Original description")
                    event_id = event.id
                    self.db.session.add(EventClarification(event_id=event_id, sender_id=coordinator.id,
                                                           message="Who will staff the entrance?"))
                    self.db.session.commit()
                    headers = self.auth_headers(organiser)
                    if fails:
                        with mock.patch.object(self.db.session, "commit", side_effect=SQLAlchemyError("Save failed")):
                            response = self.client.post(f"/api/events/{event_id}/resubmit", headers=headers,
                                json={"message": REPLY, "changes": {"description": DESCRIPTION}})
                    else:
                        response = self.client.post(f"/api/events/{event_id}/resubmit", headers=headers,
                            json={"message": REPLY, "changes": {"description": DESCRIPTION}})
                    self.assertEqual(response.status_code, 503 if fails else 200, response.get_json())
                    self.db.session.expire_all()
                    saved = self.db.session.get(Event, event_id)
                    self.assertEqual((saved.status, saved.description),
                                     ("under_review", "Original description") if fails else ("submitted", DESCRIPTION))
                    self.assertEqual(saved.coordinator_id, coordinator.id)
                    replies = EventClarification.query.filter_by(event_id=event_id, sender_id=organiser.id).all()
                    notices = Notification.query.filter_by(event_id=event_id, recipient_id=coordinator.id).all()
                    self.assertEqual([row.message for row in replies], [] if fails else [REPLY])
                    self.assertEqual(len(notices), 0 if fails else 1)
                    if fails:
                        email.assert_not_called()
                    else:
                        email.assert_called_once()
                        history = self.client.get(f"/api/events/{event_id}/clarifications", headers=headers)
                        self.assertEqual(history.status_code, 200, history.get_json())
                        self.assertIs(history.get_json()["can_resubmit"], False)

