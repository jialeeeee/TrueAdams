"""Tests for SCRUM-31's reopened criteria: starting a review (AC7-AC10).

Each test names the case it automates from
docs/test-cases/SCRUM-31-event-clarification.md (TC-31-26 to 39). Assumptions
A10-A16 and questions Q7-Q10 are defined there.

Model (db/event_review_start.sql): new Event columns
    review_started_at     DateTime, naive UTC: when the coordinator started reviewing
    review_started_by_id  FK users.id: the coordinator who started it

Endpoint
    POST /api/events/<id>/review   (no body)
        200 {"message", "request": SCRUM-32's review payload, which now includes
             "review_started_at" and "review_started_by": {"id", "email"} | null}
        401 session · 404 unknown event · 403 not the event's assigned coordinator
        409 {"error"} the request is not submitted
        503 {"error", "retryable": true} if saving fails
    GET /api/events/<id>/review returns the same two new fields.

Once a review has started, the coordinator can still approve or reject (A13).

The seed data is SCRUM-32's DC-SEED (DecisionTestCase), plus R8 (under review) and
lena, a Coordinator Lead.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import SQLAlchemyError

from app.models import Event, Notification
from tests.test_event_decisions import DecisionTestCase

REASON = "The proposed date clashes with the National Day Parade."
# Everyone who may not start R1's review: other roles, and its own organiser.
OTHER_USERS = ("admin", "lena", "dana", "farah", "gus", "hana")


class ReviewStartTestCase(DecisionTestCase):
    def setUp(self):
        super().setUp()
        self.users["lena"] = self.make_user(role="coordinator_lead")
        # R8: alice's, and already under review (as in SCRUM-77/78).
        self.requests["R8"] = Event(
            title="Spring Fair", status="under_review",
            organiser_id=self.users["dana"].id, coordinator_id=self.users["alice"].id,
            submitted_at=datetime(2026, 9, 24, 9, 0),
        )
        self.db.session.add(self.requests["R8"])
        self.db.session.commit()

    def start(self, key, as_user="alice", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.post(f"/api/events/{self.requests[key].id}/review", headers=headers)

    def summary(self, key):
        user = self.users[key]
        return {"id": user.id, "email": user.email}


# ---------- AC7: only the assigned coordinator can start a review ----------


class OnlyAssignedCoordinatorTests(ReviewStartTestCase):
    # TC-31-26 · AC7 (Q1) — another coordinator can't start the review.
    def test_another_coordinator_cannot_start_the_review(self):
        before = self.stored("R1")

        self.assert_error(self.start("R1", as_user="ben"), 403)

        self.assert_nothing_decided("R1", before)

    # TC-31-27 · AC7 — no other role can start a review.
    def test_no_other_role_can_start_a_review(self):
        before = self.stored("R1")
        for user in OTHER_USERS:
            with self.subTest(user=user):
                body = self.assert_error(self.start("R1", as_user=user), 403)
                self.assertNotIn("Harbour Lights Festival", body["error"])
        self.assert_nothing_decided("R1", before)

    # TC-31-28 · AC7 (Q1) — a request with no coordinator can't be started.
    def test_request_without_a_coordinator_cannot_be_started(self):
        before = self.stored("R3")

        self.assert_error(self.start("R3"), 403)

        self.assert_nothing_decided("R3", before)

    # TC-31-29 · AC7 — a valid session is required.
    def test_a_valid_session_is_required(self):
        before = self.stored("R1")
        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["alice"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                self.assertEqual(self.start("R1", headers=headers).status_code, 401)
        self.assert_nothing_decided("R1", before)

    # TC-31-30 · AC7 — unknown event.
    def test_unknown_event_is_not_found(self):
        response = self.client.post(f"/api/events/{self.missing_id(Event)}/review",
                                    headers=self.auth_headers(self.users["alice"]))

        self.assert_error(response, 404)


# ---------- AC8: a submitted request becomes under review, recording who and when ----------


class StartReviewTests(ReviewStartTestCase):
    # TC-31-31 · AC8 — the assigned coordinator starts reviewing a submitted request.
    def test_assigned_coordinator_starts_the_review(self):
        before = self.stored("R1")
        started = datetime.utcnow()

        response = self.start("R1")

        finished = datetime.utcnow()
        self.assertEqual(response.status_code, 200, response.get_json())
        stored = self.stored("R1")
        self.assertEqual((stored["status"], stored["review_started_by_id"]),
                         ("under_review", self.users["alice"].id))
        self.assertTrue(started <= stored["review_started_at"] <= finished)
        changed = ("status", "review_started_at", "review_started_by_id")
        self.assertEqual({k: v for k, v in stored.items() if k not in changed},
                         {k: v for k, v in before.items() if k not in changed})
        body = response.get_json()
        self.assertEqual(
            (body["request"]["status"], body["request"]["review_started_at"],
             body["request"]["review_started_by"]),
            ("under_review", stored["review_started_at"].isoformat(), self.summary("alice")))
        self.assertIn("Harbour Lights Festival", body["message"])

    # TC-31-32 · AC8 — the new status shows wherever the request is listed.
    def test_status_shows_wherever_the_request_is_listed(self):
        self.assertEqual(self.start("R1").status_code, 200)
        r1 = self.requests["R1"].id

        review = self.review("R1").get_json()["request"]
        self.assertEqual((review["status"], review["review_started_by"]),
                         ("under_review", self.summary("alice")))
        self.assertIsNotNone(review["review_started_at"])

        alice = self.auth_headers(self.users["alice"])
        queue = self.client.get("/api/events/review-requests", headers=alice).get_json()
        self.assertEqual(next(r for r in queue["requests"] if r["id"] == r1)["status"],
                         "under_review")
        mine = self.my_requests().get_json()["requests"]
        self.assertEqual(next(r for r in mine if r["id"] == r1)["status"], "under_review")
        grouped = self.client.get("/api/events/mine",
                                  headers=self.auth_headers(self.users["dana"])).get_json()
        self.assertEqual(next(r for r in grouped["submitted"] if r["id"] == r1)["status"],
                         "under_review")

    # TC-31-33 · AC8 (Q9) — starting a review notifies nobody.
    def test_starting_a_review_notifies_nobody(self):
        self.assertEqual(self.start("R1").status_code, 200)

        own = [u.id for u in self.users.values()]
        self.db.session.expire_all()
        self.assertEqual(Notification.query.filter(Notification.recipient_id.in_(own)).count(), 0)
        self.queue_email.assert_not_called()

    # TC-31-34 · AC8 (Q7, Q8) — once started, the coordinator can still ask and decide.
    def test_coordinator_can_ask_and_decide_once_the_review_has_started(self):
        alice = self.auth_headers(self.users["alice"])
        self.assertEqual(self.start("R1").status_code, 200)

        asked = self.client.post(f"/api/events/{self.requests['R1'].id}/clarifications",
                                 headers=alice, json={"message": "Is the date flexible?"})
        self.assertEqual(asked.status_code, 201, asked.get_json())
        approved = self.decide("R1", "approve")
        self.assertEqual(approved.status_code, 200, approved.get_json())
        self.assertEqual((self.stored("R1")["status"], self.stored("R1")["decided_by_id"]),
                         ("approved", self.users["alice"].id))

        self.assertEqual(self.start("E1").status_code, 200)
        rejected = self.decide("E1", "reject", reason=REASON)
        self.assertEqual(rejected.status_code, 200, rejected.get_json())
        self.assertEqual((self.stored("E1")["status"], self.stored("E1")["decision_note"]),
                         ("rejected", REASON))


# ---------- AC9: a request that is not submitted can't be started ----------


class OnlySubmittedTests(ReviewStartTestCase):
    # TC-31-35 · AC9 — a request that is not submitted can't be started.
    def test_request_that_is_not_submitted_cannot_be_started(self):
        for key, status in (("R4", "draft"), ("R5", "approved"), ("R6", "rejected"),
                            ("R7", "cancelled"), ("R8", "under_review")):
            with self.subTest(request=key, status=status):
                before = self.stored(key)

                body = self.assert_error(self.start(key), 409)

                self.assertIn(status, body["error"])
                self.assertEqual(self.stored(key), before)
        self.queue_email.assert_not_called()

    # TC-31-36 · AC9 — starting twice keeps the first start.
    def test_starting_twice_keeps_the_first_start(self):
        self.assertEqual(self.start("R1").status_code, 200)
        first = self.stored("R1")

        body = self.assert_error(self.start("R1"), 409)

        self.assertIn("under_review", body["error"])
        self.assertEqual(self.stored("R1"), first)

    # TC-31-37 · AC9 (concurrency) — the row is locked before its status is checked.
    def test_request_row_is_locked_before_its_status_is_checked(self):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(" ".join(statement.split()))

        sa_event.listen(self.db.engine, "before_cursor_execute", record)
        try:
            response = self.start("R1")
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", record)

        self.assertEqual(response.status_code, 200, response.get_json())
        lock = next((i for i, s in enumerate(statements)
                     if "FROM events" in s and s.endswith("FOR UPDATE")), None)
        update = next((i for i, s in enumerate(statements) if s.startswith("UPDATE events")),
                      None)
        self.assertIsNotNone(lock, "the request's row is not locked")
        self.assertIsNotNone(update)
        self.assertLess(lock, update)


# ---------- AC10: a failed save leaves the status unchanged ----------


class SaveFailureTests(ReviewStartTestCase):
    def failing_commit(self):
        return mock.patch.object(self.db.session, "commit",
                                 side_effect=SQLAlchemyError("simulated outage"))

    # TC-31-38 · AC10 — saving fails: the status is unchanged and an error is shown.
    def test_failed_save_leaves_the_request_submitted(self):
        before = self.stored("R1")

        with self.failing_commit():
            response = self.start("R1")

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not started")
        self.assertRegex(body["error"].lower(), r"try again")
        self.assertNotIn("request", body)
        self.assert_nothing_decided("R1", before)
        self.assertEqual(self.start("R1").status_code, 200)

    # TC-31-39 · AC10 (Q7) — a failed decision under review doesn't claim "submitted".
    def test_failed_decision_does_not_claim_the_request_is_submitted(self):
        before = self.stored("R8")

        with self.failing_commit():
            response = self.decide("R8", "approve")

        body = self.assert_error(response, 503)
        self.assertRegex(body["error"].lower(), r"not saved")
        self.assertNotIn("submitted", body["error"].lower())
        self.assert_nothing_decided("R8", before)


if __name__ == "__main__":
    unittest.main()
