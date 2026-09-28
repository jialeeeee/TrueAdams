"""Tests for SCRUM-31 "Review and Request Clarification on an Event Request".

Each test names the case it automates from
docs/test-cases/SCRUM-31-event-clarification.md (TC-31-nn) and the acceptance
criteria it checks. Assumptions A1-A9 and questions Q1-Q6 are defined there.

Model (new tables, created by db/event_clarifications.sql)
    EventClarification  event_clarifications
        event_id    FK events.id, not null
        sender_id   FK users.id, not null
        message     Text, not null (trimmed)
        created_at  DateTime (naive UTC)
    Notification        notifications
        recipient_id  FK users.id, not null
        kind          String, not null ("clarification_requested")
        message       Text, not null
        event_id      FK events.id, nullable
        created_at    DateTime (naive UTC)
        read_at       DateTime, null until read

Endpoints (JWT required, else 401; unknown event -> 404)
    POST /api/events/<id>/clarifications   body {"message": str}
        201 {"message": str,
             "clarification": {"id", "event_id", "sender": {"id", "email"},
                               "message", "created_at"},
             "notification": {"in_app": true, "email_queued": bool}}
        403 caller is not the event's current coordinator
        400 empty message, or more than MAX_WORDS words
        409 event is not open for clarification (status not submitted / under_review)
        503 {"error", "retryable": true} if saving fails; nothing is saved
    GET /api/events/<id>/clarifications
        200 {"event": {"id", "title", "status", "organiser": {"id", "email"}},
             "clarifications": [clarification, ...oldest first], "message": str | null}
        403 caller is neither the event's current coordinator nor its organiser
    GET /api/notifications/
        200 {"notifications": [{"id", "kind", "message", "event_id",
                                "created_at", "read_at"}, ...newest first]}
    Errors are {"error": "<message shown to the user>"}.

The organiser's email is queued through tasks.send_notification_email, which is
mocked here so no test ever reaches Redis or SMTP.
"""

import unittest
from datetime import timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app import tasks
from app.models import Event, EventClarification, Notification
from tests import seed_data
from tests.base import AppTestCase

MAX_WORDS = 1000
QUESTION = "What is the expected attendance, and do any guests need wheelchair access?"


def words(count, separator=" "):
    return separator.join(f"word{i}" for i in range(count))


class ClarificationTestCase(AppTestCase):
    """Inserts CL-SEED, mocks the email queue and wraps the endpoints."""

    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.events = self.seed_events(seed_data.EVENTS, self.users)

        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.queue_email = patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- Requests ----------

    def url(self, key):
        return f"/api/events/{self.events[key].id}/clarifications"

    def send(self, key="assigned", message=QUESTION, as_user=None, headers=None, **kwargs):
        if headers is None:
            headers = self.auth_headers(as_user or self.users["alice"])
        if "data" not in kwargs:
            kwargs["json"] = {"message": message}
        return self.client.post(self.url(key), headers=headers, **kwargs)

    def thread(self, key="assigned", as_user=None):
        return self.client.get(
            self.url(key), headers=self.auth_headers(as_user or self.users["alice"])
        )

    def notifications(self, as_user):
        response = self.client.get("/api/notifications/", headers=self.auth_headers(as_user))
        self.assertEqual(response.status_code, 200)
        return response.get_json()["notifications"]

    # ---------- Reading what was saved ----------

    def saved_questions(self, key="assigned"):
        self.db.session.expire_all()
        return (
            EventClarification.query.filter_by(event_id=self.events[key].id)
            .order_by(EventClarification.id)
            .all()
        )

    def saved_notifications(self):
        """Notifications for this test's own users (real ones are ignored)."""
        self.db.session.expire_all()
        own_ids = [user.id for user in self.users.values()]
        return Notification.query.filter(Notification.recipient_id.in_(own_ids)).all()

    # ---------- Assertions ----------

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code)
        body = response.get_json()
        self.assertIsInstance(body, dict)
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip(), "error message should not be blank")
        return body["error"]

    def assert_nothing_sent(self, key="assigned"):
        self.assertEqual(self.saved_questions(key), [])
        self.assertEqual(self.saved_notifications(), [])
        self.queue_email.assert_not_called()


# ---------- AC1: send clarification questions ----------


class SendQuestionTests(ClarificationTestCase):
    # TC-31-01 · AC1, AC3, AC6 — the assigned coordinator sends a question.
    def test_assigned_coordinator_sends_a_question(self):
        alice, dana = self.users["alice"], self.users["dana"]

        response = self.send()

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertIn(dana.email, body["message"])
        [saved] = self.saved_questions()
        self.assertEqual((saved.sender_id, saved.message), (alice.id, QUESTION))
        self.assertIsNotNone(saved.created_at)
        self.assertEqual(
            body["clarification"],
            {
                "id": saved.id,
                "event_id": self.events["assigned"].id,
                "sender": {"id": alice.id, "email": alice.email},
                "message": QUESTION,
                "created_at": saved.created_at.isoformat(),
            },
        )
        self.assertEqual(body["notification"], {"in_app": True, "email_queued": True})

    # TC-31-02 · AC1, AC3 — questions are listed, oldest first, for coordinator and organiser.
    def test_questions_are_listed_for_the_coordinator_and_the_organiser(self):
        self.send(message="First question?")
        self.send(message="Second question?")
        event, dana = self.events["assigned"], self.users["dana"]

        for key in ("alice", "dana"):
            with self.subTest(viewer=key):
                response = self.thread(as_user=self.users[key])

                self.assertEqual(response.status_code, 200)
                body = response.get_json()
                self.assertEqual(
                    body["event"],
                    {"id": event.id, "title": "Charity Gala", "status": "submitted",
                     "organiser": {"id": dana.id, "email": dana.email}},
                )
                self.assertEqual([c["message"] for c in body["clarifications"]],
                                 ["First question?", "Second question?"])
                self.assertEqual(body["clarifications"][0]["sender"]["id"],
                                 self.users["alice"].id)
                self.assertIsNone(body["message"])

    # TC-31-03 · AC1 — an event with no questions yet shows an empty state.
    def test_event_with_no_questions_shows_an_empty_state(self):
        body = self.thread().get_json()

        self.assertEqual(body["clarifications"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())

    # TC-31-04 · AC1, AC4 (A1/Q1) — a coordinator not assigned to the event is refused.
    def test_coordinator_not_assigned_to_the_event_is_refused(self):
        cases = {
            "another event's coordinator": ("assigned", "ben"),
            "coordinator of nothing": ("assigned", "chloe"),
            "unassigned event": ("unassigned", "alice"),
        }
        for label, (event_key, user_key) in cases.items():
            with self.subTest(case=label):
                response = self.send(event_key, as_user=self.users[user_key])

                self.assertIn("assigned coordinator", self.assert_error(response, 403))
                self.assert_nothing_sent(event_key)

    # TC-31-05 · AC1 — other roles, including the event's own organiser, are refused.
    def test_other_roles_are_refused(self):
        for key in ("admin", "dana", "farah", "gus", "hana"):
            with self.subTest(user=key):
                self.assert_error(self.send(as_user=self.users[key]), 403)
                self.assert_nothing_sent()

    # TC-31-06 · AC1 (boundary) — access follows reassignment and role changes.
    def test_access_follows_reassignment_and_role_changes(self):
        alice_headers = self.auth_headers(self.users["alice"])
        ben_headers = self.auth_headers(self.users["ben"])
        self.assertEqual(self.send(headers=alice_headers).status_code, 201)

        event = self.db.session.get(Event, self.events["assigned"].id)
        event.coordinator_id = self.users["ben"].id
        self.db.session.commit()
        self.assert_error(self.send(headers=alice_headers), 403)

        self.users["ben"].role = "organiser"
        self.db.session.commit()
        self.assert_error(self.send(headers=ben_headers), 403)

        self.assertEqual(len(self.saved_questions()), 1)

    # TC-31-07 · AC1 — a valid session is required.
    def test_sending_requires_a_valid_session(self):
        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(
            identity=str(self.users["alice"].id), expires_delta=timedelta(seconds=-1)
        )
        cases = {
            "no token": {},
            "expired token": {"Authorization": f"Bearer {expired}"},
            "deleted user": ghost_headers,
        }
        for label, headers in cases.items():
            with self.subTest(case=label):
                self.assertEqual(self.send(headers=headers).status_code, 401)
                self.assert_nothing_sent()

    # TC-31-08 · AC1, AC4 — unknown event.
    def test_unknown_event_returns_not_found(self):
        response = self.client.post(
            f"/api/events/{self.missing_id(Event)}/clarifications",
            json={"message": QUESTION},
            headers=self.auth_headers(self.users["alice"]),
        )

        self.assert_error(response, 404)
        self.queue_email.assert_not_called()

    # TC-31-09 · AC1, AC4 (A2/Q2) — events not under review are refused.
    def test_event_not_open_for_clarification_is_refused(self):
        for key in ("draft", "cancelled"):
            with self.subTest(status=key):
                event = self.db.session.get(Event, self.events[key].id)
                event.coordinator_id = self.users["alice"].id
                self.db.session.commit()

                error = self.assert_error(self.send(key), 409)

                self.assertIn(key, error)
                self.assert_nothing_sent(key)

    # TC-31-09 · AC1 (A2) — "under_review" is open for clarification like "submitted".
    def test_event_under_review_is_open_for_clarification(self):
        event = self.db.session.get(Event, self.events["assigned"].id)
        event.status = "under_review"
        self.db.session.commit()

        self.assertEqual(self.send().status_code, 201)

    # TC-31-10 · AC1 (A3/Q3) — sending a question does not change the event.
    def test_sending_does_not_change_the_event(self):
        def state():
            self.db.session.expire_all()
            event = self.db.session.get(Event, self.events["assigned"].id)
            return {c.name: getattr(event, c.name) for c in Event.__table__.columns}

        before = state()
        self.send()

        self.assertEqual(state(), before)

    # TC-31-11 · AC1 — unrelated users cannot view an event's questions.
    def test_unrelated_users_cannot_view_the_questions(self):
        self.send()

        for key in ("ben", "evan", "farah", "admin"):
            with self.subTest(viewer=key):
                response = self.thread(as_user=self.users[key])

                self.assert_error(response, 403)
                text = response.get_data(as_text=True)
                for secret in (QUESTION, "Charity Gala", self.users["dana"].email):
                    self.assertNotIn(secret, text)

    # TC-31-11 · AC1 — viewing needs a session, and the event must exist.
    def test_viewing_requires_a_session_and_an_existing_event(self):
        self.assertEqual(self.client.get(self.url("assigned")).status_code, 401)
        response = self.client.get(
            f"/api/events/{self.missing_id(Event)}/clarifications",
            headers=self.auth_headers(self.users["alice"]),
        )
        self.assert_error(response, 404)


# ---------- AC2: questions are limited to 1,000 words ----------


class WordLimitTests(ClarificationTestCase):
    # TC-31-12 · AC2 (boundary) — exactly 1,000 words is accepted.
    def test_exactly_the_word_limit_is_accepted(self):
        cases = {
            "spaces": words(MAX_WORDS),
            "mixed whitespace": "\n".join(
                words(10, separator="\t") for _ in range(MAX_WORDS // 10)
            ),
        }
        for label, message in cases.items():
            with self.subTest(separators=label):
                self.assertEqual(self.send(message=message).status_code, 201)

    # TC-31-13 · AC2, AC4 (boundary) — 1,001 words is refused with an explanation.
    def test_one_word_over_the_limit_is_refused_with_an_explanation(self):
        error = self.assert_error(self.send(message=words(MAX_WORDS + 1)), 400)

        self.assertIn("1000", error.replace(",", ""))
        self.assertIn("1001", error.replace(",", ""))
        self.assert_nothing_sent()


# ---------- AC4: failures are explained and actionable ----------


class SaveFailureTests(ClarificationTestCase):
    def send_with_failing_commit(self):
        with mock.patch.object(
            self.db.session, "commit", side_effect=SQLAlchemyError("simulated outage")
        ):
            return self.send()

    # TC-31-16 · AC4, AC6 — a failed save is retryable and nothing is half-sent.
    def test_failed_save_is_retryable_and_sends_nothing(self):
        response = self.send_with_failing_commit()

        error = self.assert_error(response, 503)
        self.assertIs(response.get_json().get("retryable"), True)
        self.assertRegex(error.lower(), r"not sent")
        self.assertRegex(error.lower(), r"try again")
        self.assertNotIn("clarification", response.get_json())
        self.assert_nothing_sent()

    # TC-31-17 · AC4 — retrying after recovery sends exactly one question.
    def test_retry_after_recovery_sends_exactly_one_question(self):
        self.send_with_failing_commit()

        self.assertEqual(self.send().status_code, 201)
        self.assertEqual(len(self.saved_questions()), 1)


# ---------- AC5: empty messages cannot be sent ----------


class EmptyMessageTests(ClarificationTestCase):
    # TC-31-19 · AC5, AC4 — empty messages are refused.
    def test_empty_messages_are_refused(self):
        cases = {
            "missing": {"json": {}},
            "empty": {"json": {"message": ""}},
            "whitespace only": {"json": {"message": "   \n\t "}},
            "null": {"json": {"message": None}},
            "not text": {"json": {"message": 42}},
            "not JSON": {"data": "message=hello"},
        }
        for label, kwargs in cases.items():
            with self.subTest(body=label):
                response = self.client.post(
                    self.url("assigned"),
                    headers=self.auth_headers(self.users["alice"]),
                    **kwargs,
                )

                self.assert_error(response, 400)
                self.assert_nothing_sent()

    # TC-31-20 · AC5 (boundary) — surrounding whitespace is trimmed before saving.
    def test_surrounding_whitespace_is_trimmed(self):
        self.send(message="  Is catering needed?\n")

        self.assertEqual(self.saved_questions()[0].message, "Is catering needed?")


# ---------- AC6: the organiser is notified ----------


class NotificationTests(ClarificationTestCase):
    # TC-31-22 · AC6 — the organiser, and only the organiser, gets an in-app notification.
    def test_organiser_receives_an_in_app_notification(self):
        self.send()

        [notification] = self.notifications(self.users["dana"])
        self.assertEqual(notification["kind"], "clarification_requested")
        self.assertEqual(notification["event_id"], self.events["assigned"].id)
        self.assertIn("Charity Gala", notification["message"])
        self.assertIsNone(notification["read_at"])
        for key in ("evan", "alice"):
            with self.subTest(user=key):
                self.assertEqual(self.notifications(self.users[key]), [])

    # TC-31-22 · AC6 — notifications are listed newest first.
    def test_notifications_are_listed_newest_first(self):
        self.send(message="First question?")
        self.send(message="Second question?")

        listed = self.notifications(self.users["dana"])

        self.assertEqual(len(listed), 2)
        self.assertGreater(listed[0]["id"], listed[1]["id"])

    # TC-31-23 · AC6 — the organiser is emailed the question.
    def test_organiser_is_emailed_the_question(self):
        self.send()

        self.queue_email.assert_called_once()
        to_address, subject, body = self.queue_email.call_args.args
        self.assertEqual(to_address, self.users["dana"].email)
        self.assertIn("Charity Gala", subject)
        self.assertIn(QUESTION, body)

    # TC-31-24 · AC3, AC6 (A6/Q5) — if the email cannot be queued, the question is still sent.
    def test_question_is_still_sent_when_the_email_cannot_be_queued(self):
        self.queue_email.side_effect = ConnectionError("Redis is down")

        response = self.send()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": False})
        self.assertEqual(len(self.saved_questions()), 1)
        self.assertEqual(len(self.notifications(self.users["dana"])), 1)

    # TC-31-25 · AC6 — listing notifications requires a session.
    def test_listing_notifications_requires_a_session(self):
        self.assertEqual(self.client.get("/api/notifications/").status_code, 401)


if __name__ == "__main__":
    unittest.main()
