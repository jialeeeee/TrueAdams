"""Tests for SCRUM-60 "Record Who Decided and When".

Each test names the case it automates from
docs/test-cases/SCRUM-60-accountable-decisions.md (TC-60-nn) and the acceptance
criteria it checks. Assumptions A1-A7 and questions Q1-Q6 are there.

This story hardens the SCRUM-32 decision, so it reuses that story's DC-SEED
fixture (DecisionTestCase in tests/test_event_decisions.py). New behaviour:
    - the organiser's list items on GET /api/events/requests and /api/events/mine
      include "decided_by": {"id", "email"} | null
    - the notification and email name the decider and the time (Singapore time)
    - a reason with no visible character is a 400 with field "reason"
    - the request's row is locked and re-read before deciding
    - a decision that was saved is never reported as "not saved"
"""

import re
import unittest
from datetime import datetime, timedelta
from unittest import mock

from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from tests.test_event_decisions import REASON, DecisionTestCase

REASON_REQUIRED = "A reason is required to reject this request."


def singapore_time(utc):
    """How the notification and email show a naive UTC time (SCRUM-60 A2)."""
    local = utc + timedelta(hours=8)
    return f"{local.day} {local:%b %Y} at {local:%H:%M} (Singapore time)"


class AccountabilityTestCase(DecisionTestCase):
    def summary(self, user_key):
        user = self.users[user_key]
        return {"id": user.id, "email": user.email}

    def listed(self, url, items_key):
        """dana's list items from `url`, keyed by seed ref; real data is skipped."""
        response = self.client.get(url, headers=self.auth_headers(self.users["dana"]))
        self.assertEqual(response.status_code, 200, response.get_json())
        by_id = {event.id: key for key, event in self.requests.items()}
        return {by_id[item["id"]]: item for item in response.get_json()[items_key]
                if item["id"] in by_id}


# ---------- AC1: who decided and when is recorded and shown ----------


class WhoAndWhenTests(AccountabilityTestCase):
    # TC-60-01 · AC1 — the decision records the deciding coordinator and the time.
    def test_decision_records_the_deciding_coordinator_and_time(self):
        # R1 and E1 are both submitted and assigned to alice.
        for key, decision, reason in (("R1", "approve", None), ("E1", "reject", REASON)):
            with self.subTest(decision=decision):
                started = datetime.utcnow()

                response = self.decide(key, decision, reason=reason)

                finished = datetime.utcnow()
                self.assertEqual(response.status_code, 200, response.get_json())
                stored = self.stored(key)
                self.assertEqual(stored["decided_by_id"], self.users["alice"].id)
                self.assertTrue(started <= stored["decided_at"] <= finished)
                request = response.get_json()["request"]
                self.assertEqual(request["decided_by"], self.summary("alice"))
                self.assertEqual(request["decided_at"], stored["decided_at"].isoformat())

    # TC-60-02 · AC1 (boundary, Q1) — reassigning the event later does not change who decided.
    def test_reassigning_the_event_later_does_not_change_who_decided(self):
        self.decide("R1", "reject", reason=REASON)
        decided_at = self.stored("R1")["decided_at"].isoformat()

        reassigned = self.client.put(
            f"/api/events/{self.requests['R1'].id}/coordinator",
            json={"coordinator_id": self.users["ben"].id},
            headers=self.auth_headers(self.users["admin"]))
        self.assertEqual(reassigned.status_code, 200, reassigned.get_json())

        review = self.review("R1", as_user="ben")
        self.assertEqual(review.status_code, 200, review.get_json())
        self.assertEqual(review.get_json()["request"]["decided_by"], self.summary("alice"))
        self.assertEqual(review.get_json()["request"]["decided_at"], decided_at)
        listed = self.listed("/api/events/requests", "requests")["R1"]
        self.assertEqual((listed["decided_by"], listed["decided_at"]),
                         (self.summary("alice"), decided_at))

    # TC-60-03 · AC1 — the organiser's lists show who decided and when.
    def test_organisers_lists_show_who_decided_and_when(self):
        for url, items_key in (("/api/events/requests", "requests"),
                               ("/api/events/mine", "submitted")):
            with self.subTest(url=url):
                listed = self.listed(url, items_key)
                self.assertEqual((listed["R6"]["decided_by"], listed["R6"]["decided_at"]),
                                 (self.summary("alice"), "2026-09-12T09:00:00"))
                self.assertEqual(listed["R5"]["decided_by"], self.summary("alice"))
                self.assertEqual((listed["R1"]["decided_by"], listed["R1"]["decided_at"]),
                                 (None, None))

    # TC-60-04 · AC1 (Q2) — the organiser's notification and email name the decider and time.
    def test_notification_and_email_name_the_decider_and_the_time(self):
        self.decide("R1", "reject", reason=REASON)

        when = singapore_time(self.stored("R1")["decided_at"])
        [notification] = self.notifications_for("dana")
        _to_address, _subject, body = self.queue_email.call_args.args
        for label, message in (("in-app", notification.message), ("email", body)):
            with self.subTest(channel=label):
                self.assertIn(self.users["alice"].email, message)
                self.assertIn(when, message)
                self.assertIn(REASON, message)

    # TC-60-05 · AC1 (Q4) — a decision made meanwhile is not overwritten.
    def test_a_decision_made_meanwhile_is_not_overwritten(self):
        # This session now holds R1 as submitted, as a request that read it earlier would.
        self.assertEqual(self.requests["R1"].status, "submitted")
        first_decided_at = datetime(2026, 10, 1, 2, 0)
        # Another tab's approval reaches the database without this session seeing it.
        self.db.session.execute(
            text("update events set status = 'approved', decided_at = :at, "
                 "decided_by_id = :by where id = :id"),
            {"at": first_decided_at, "by": self.users["alice"].id, "id": self.requests["R1"].id})

        response = self.decide("R1", "reject", reason=REASON)

        self.assert_error(response, 409)
        stored = self.stored("R1")
        self.assertEqual(
            (stored["status"], stored["decided_at"], stored["decided_by_id"],
             stored["decision_note"]),
            ("approved", first_decided_at, self.users["alice"].id, None))
        self.assertEqual(self.notifications_for("dana"), [])
        self.queue_email.assert_not_called()

    # TC-60-05 · AC1 (Q4) — the request's row is locked while deciding.
    def test_the_request_row_is_locked_while_deciding(self):
        statements = []

        def record(_conn, _cursor, statement, *_args):
            statements.append(statement)

        sa_event.listen(self.connection, "before_cursor_execute", record)
        self.addCleanup(sa_event.remove, self.connection, "before_cursor_execute", record)

        self.assertEqual(self.decide("R1", "approve").status_code, 200)

        locked = [s for s in statements
                  if re.search(r"\bFROM events\b.*\bFOR UPDATE\b", s, re.IGNORECASE | re.DOTALL)]
        self.assertTrue(locked, "the events row was never read with SELECT ... FOR UPDATE")


# ---------- AC2: a reason made only of spaces is refused ----------


class BlankReasonTests(AccountabilityTestCase):
    # TC-60-06 · AC2 (Q3) — reasons made only of spaces are refused, saying a reason is required.
    def test_reasons_made_only_of_spaces_are_refused(self):
        before = self.stored("R1")
        for label, reason in {"spaces": "     ", "tabs and line breaks": " \t\n ",
                              "non-breaking spaces": "  ",
                              "ideographic space": "　",
                              "zero-width spaces": "​​",
                              "byte-order mark": "﻿",
                              "mixed": " ​ \t"}.items():
            with self.subTest(reason=label):
                body = self.assert_error(self.decide("R1", "reject", reason=reason), 400)
                self.assertEqual(body["error"], REASON_REQUIRED)
                self.assertEqual(body.get("field"), "reason")
        self.assert_nothing_decided("R1", before)

    # TC-60-07 · AC2 (boundary) — a reason with visible text is accepted and trimmed.
    def test_a_reason_with_visible_text_is_accepted_and_trimmed(self):
        response = self.decide("R1", "reject", reason="x")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.stored("R1")["decision_note"], "x")

        response = self.decide("E1", "reject", reason="  Venue unavailable 　")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.stored("E1")["decision_note"], "Venue unavailable")


# ---------- AC3: the coordinator sees a confirmation ----------


class ConfirmationTests(AccountabilityTestCase):
    # TC-60-08 · AC3 — the reply confirms the outcome.
    def test_the_reply_confirms_the_outcome(self):
        dana = self.users["dana"].email
        for key, decision, reason, status in (("R1", "reject", REASON, "rejected"),
                                              ("E1", "approve", None, "approved")):
            with self.subTest(decision=decision):
                response = self.decide(key, decision, reason=reason)

                self.assertEqual(response.status_code, 200, response.get_json())
                body = response.get_json()
                organiser = dana if key == "R1" else self.users["evan"].email
                title = self.requests[key].title
                self.assertEqual(body["message"],
                                 f'You {status} "{title}". {organiser} has been notified.')
                self.assertEqual(body["request"]["status"], status)
                self.assertEqual(body["request"]["decided_by"], self.summary("alice"))
                self.assertEqual(body["request"]["decided_at"],
                                 self.stored(key)["decided_at"].isoformat())


# ---------- AC4: a failed save changes nothing and can be retried ----------


class SaveFailureTests(AccountabilityTestCase):
    # TC-60-09 · AC4 — a failed save is reported, changes nothing, and can be resent.
    def test_a_failed_save_changes_nothing_and_the_same_reason_can_be_resent(self):
        before = self.stored("R1")
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            failed = self.decide("R1", "reject", reason=REASON)

        body = self.assert_error(failed, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not saved")
        self.assertRegex(body["error"].lower(), r"try again")
        self.assert_nothing_decided("R1", before)

        retried_at = datetime.utcnow()
        retry = self.decide("R1", "reject", reason=REASON)

        self.assertEqual(retry.status_code, 200, retry.get_json())
        stored = self.stored("R1")
        self.assertEqual((stored["status"], stored["decision_note"], stored["decided_by_id"]),
                         ("rejected", REASON, self.users["alice"].id))
        self.assertGreaterEqual(stored["decided_at"], retried_at)

    # TC-60-10 · AC4 (Q5) — a saved decision is never reported as failed.
    def test_a_saved_decision_is_never_reported_as_failed(self):
        real_commit = self.db.session.commit
        connection_lost = mock.patch.object(
            Session, "execute",
            side_effect=OperationalError("SELECT", {}, Exception("server closed the connection")))

        def commit_then_lose_the_connection():
            real_commit()
            connection_lost.start()

        with mock.patch.object(self.db.session, "commit",
                               side_effect=commit_then_lose_the_connection):
            try:
                response = self.decide("R1", "reject", reason=REASON)
            finally:
                connection_lost.stop()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertIn("rejected", body["message"])
        self.assertEqual((body["request"]["status"], body["request"]["decided_by"]),
                         ("rejected", self.summary("alice")))
        stored = self.stored("R1")
        self.assertEqual(body["request"]["decided_at"], stored["decided_at"].isoformat())
        self.assertEqual(stored["status"], "rejected")
        self.assertEqual(len(self.notifications_for("dana")), 1)
        self.queue_email.assert_called_once()
        self.assertEqual(self.queue_email.call_args.args[0], self.users["dana"].email)


if __name__ == "__main__":
    unittest.main()
