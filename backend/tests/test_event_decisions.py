"""Tests for SCRUM-32 "Approve or Reject an Event Request".

Each test names the case it automates from
docs/test-cases/SCRUM-32-approve-reject-event-request.md (TC-32-nn) and the
acceptance criteria it checks. Assumptions A1-A8 and questions Q1-Q5 are there.

Model (db/event_decisions.sql): new nullable Event columns
    decision_note   Text      rejection reason, or optional approval note
    decided_at      DateTime  naive UTC
    decided_by_id   FK users.id

Endpoints (JWT required, else 401; unknown request -> 404)
    GET  /api/events/<id>/review     200 {"request": request}      assigned coordinator only
    POST /api/events/<id>/decision   body {"decision": "approve" | "reject", "reason": str}
        200 {"message", "request", "notification": {"in_app": true, "email_queued": bool}}
        403 not the assigned coordinator   400 bad decision / reason   409 not submitted
        503 {"error", "retryable": true} if saving fails
    GET  /api/events/requests        200 {"requests": [summary], "message"}  organisers only
    request = SCRUM-29 fields + {"id", "status", "submitted_at", "decided_at",
                                 "decided_by": {"id", "email"} | null, "decision_note"}
    summary = {"id", "title", "status", "submitted_at", "decided_at", "decision_note",
               "decided_by"}  (decided_by added by SCRUM-60)

The organiser's email is queued through tasks.send_notification_email, mocked here.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app import tasks
from app.models import Event, Notification
from tests import seed_data
from tests.base import AppTestCase

MAX_WORDS = 1000
REASON = "The proposed date clashes with the National Day Parade."

REQUEST_FIELDS = {
    "purpose": "Celebrate the harbour's reopening",
    "description": "Lanterns along the promenade with live music.",
    "start_time": datetime(2026, 12, 12, 17, 0),
    "end_time": datetime(2026, 12, 12, 22, 0),
    "expected_attendance": 250,
    "venue_requirements": "Open-air waterfront space",
    "accessibility_needs": "Step-free access",
    "equipment_requirements": "PA system",
    "registration_required": True,
}

# DC-SEED. `organiser` and `coordinator` refer to seed_data.USERS keys.
REQUESTS = {
    "R1": {"title": "Harbour Lights Festival", "organiser": "dana", "coordinator": "alice",
           "status": "submitted", "submitted_at": datetime(2026, 9, 20, 9, 0), **REQUEST_FIELDS},
    "R2": {"title": "Winter Networking Night", "organiser": "dana", "coordinator": "ben",
           "status": "submitted", "submitted_at": datetime(2026, 9, 22, 9, 0)},
    "R3": {"title": "Spring Garden Party", "organiser": "dana", "coordinator": None,
           "status": "submitted", "submitted_at": datetime(2026, 9, 21, 9, 0)},
    "R4": {"title": "Tech Summit Draft", "organiser": "dana", "coordinator": "alice",
           "status": "draft"},
    "R5": {"title": "Product Launch", "organiser": "dana", "coordinator": "alice",
           "status": "approved", "submitted_at": datetime(2026, 9, 5, 9, 0),
           "decided_at": datetime(2026, 9, 10, 9, 0), "decision_note": "Venue confirmed"},
    "R6": {"title": "Rooftop Cinema", "organiser": "dana", "coordinator": "alice",
           "status": "rejected", "submitted_at": datetime(2026, 9, 6, 9, 0),
           "decided_at": datetime(2026, 9, 12, 9, 0),
           "decision_note": "No licensed venue is available"},
    "R7": {"title": "Cancelled Meetup", "organiser": "dana", "coordinator": "alice",
           "status": "cancelled", "submitted_at": datetime(2026, 9, 1, 9, 0)},
    "E1": {"title": "Alumni Mixer", "organiser": "evan", "coordinator": "alice",
           "status": "submitted", "submitted_at": datetime(2026, 9, 23, 9, 0)},
}


def words(count):
    return " ".join(f"word{i}" for i in range(count))


class DecisionTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.requests = {}
        for key, row in REQUESTS.items():
            fields = {k: v for k, v in row.items() if k not in ("organiser", "coordinator")}
            coordinator = self.users[row["coordinator"]].id if row["coordinator"] else None
            if row["status"] in ("approved", "rejected"):
                fields["decided_by_id"] = self.users["alice"].id
            event = Event(organiser_id=self.users[row["organiser"]].id,
                          coordinator_id=coordinator, **fields)
            self.db.session.add(event)
            self.requests[key] = event
        self.db.session.commit()

        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.queue_email = patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- Requests ----------

    def decide(self, key, decision, reason=None, as_user="alice", headers=None, **kwargs):
        body = {"decision": decision}
        if reason is not None:
            body["reason"] = reason
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        if "data" not in kwargs:
            kwargs["json"] = body
        return self.client.post(f"/api/events/{self.requests[key].id}/decision",
                                headers=headers, **kwargs)

    def review(self, key, as_user="alice"):
        return self.client.get(f"/api/events/{self.requests[key].id}/review",
                               headers=self.auth_headers(self.users[as_user]))

    def my_requests(self, as_user="dana"):
        return self.client.get("/api/events/requests", headers=self.auth_headers(self.users[as_user]))

    # ---------- Reading what was saved ----------

    def stored(self, key):
        self.db.session.expire_all()
        event = self.db.session.get(Event, self.requests[key].id)
        return {c.name: getattr(event, c.name) for c in Event.__table__.columns}

    def notifications_for(self, user_key):
        self.db.session.expire_all()
        return Notification.query.filter_by(recipient_id=self.users[user_key].id).all()

    # ---------- Assertions ----------

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        return body

    def assert_nothing_decided(self, key, before):
        self.assertEqual(self.stored(key), before)
        own = [u.id for u in self.users.values()]
        self.db.session.expire_all()
        self.assertEqual(Notification.query.filter(Notification.recipient_id.in_(own)).count(), 0)
        self.queue_email.assert_not_called()


# ---------- AC1: only submitted requests can be decided ----------


class WhoAndWhenTests(DecisionTestCase):
    # TC-32-01 · AC1 (A2/Q2) — requests that are not submitted cannot be decided.
    def test_requests_that_are_not_submitted_cannot_be_decided(self):
        for key, status in (("R4", "draft"), ("R5", "approved"), ("R6", "rejected"),
                            ("R7", "cancelled")):
            before = self.stored(key)
            for decision in ("approve", "reject"):
                with self.subTest(request=key, decision=decision):
                    body = self.assert_error(self.decide(key, decision, reason=REASON), 409)
                    self.assertIn(status, body["error"])
            self.assert_nothing_decided(key, before)

    # TC-32-02 · AC1 (A1/Q1) — only the assigned coordinator can decide.
    def test_only_the_assigned_coordinator_can_decide(self):
        before = self.stored("R1")
        for user in ("ben", "chloe", "admin", "dana", "farah", "gus", "hana"):
            with self.subTest(user=user):
                self.assert_error(self.decide("R1", "approve", as_user=user), 403)
        for key in ("R2", "R3"):
            with self.subTest(request=key):
                self.assert_error(self.decide(key, "approve"), 403)
        self.assert_nothing_decided("R1", before)

    # TC-32-03 · AC1 (boundary) — access follows reassignment and role changes.
    def test_access_follows_reassignment_and_role_changes(self):
        alice_headers = self.auth_headers(self.users["alice"])
        ben_headers = self.auth_headers(self.users["ben"])

        event = self.db.session.get(Event, self.requests["R1"].id)
        event.coordinator_id = self.users["ben"].id
        self.db.session.commit()
        self.assert_error(self.decide("R1", "approve", headers=alice_headers), 403)

        self.users["ben"].role = "organiser"
        self.db.session.commit()
        self.assert_error(self.decide("R1", "approve", headers=ben_headers), 403)

        self.assertEqual(self.stored("R1")["status"], "submitted")

    # TC-32-04 · AC1 — a valid session is required, and the request must exist.
    def test_a_valid_session_is_required_and_the_request_must_exist(self):
        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["alice"].id),
                                      expires_delta=timedelta(seconds=-1))
        before = self.stored("R1")
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                self.assertEqual(self.decide("R1", "approve", headers=headers).status_code, 401)
                response = self.client.get(f"/api/events/{self.requests['R1'].id}/review",
                                           headers=headers)
                self.assertEqual(response.status_code, 401)
        self.assert_nothing_decided("R1", before)

        missing = self.missing_id(Event)
        response = self.client.post(f"/api/events/{missing}/decision",
                                    json={"decision": "approve"},
                                    headers=self.auth_headers(self.users["alice"]))
        self.assert_error(response, 404)

    # TC-32-05 · AC1 — the decision must be approve or reject.
    def test_decision_must_be_approve_or_reject(self):
        before = self.stored("R1")
        for label, kwargs in {"missing": {"json": {"reason": REASON}},
                              "maybe": {"json": {"decision": "maybe"}},
                              "not exact": {"json": {"decision": "APPROVE "}},
                              "number": {"json": {"decision": 1}},
                              "not JSON": {"data": "decision=approve"}}.items():
            with self.subTest(body=label):
                response = self.client.post(
                    f"/api/events/{self.requests['R1'].id}/decision",
                    headers=self.auth_headers(self.users["alice"]), **kwargs)
                self.assert_error(response, 400)
        self.assert_nothing_decided("R1", before)

    # TC-32-06 · AC1, AC6 — the coordinator opens the full request to review it.
    def test_coordinator_opens_the_full_request_to_review_it(self):
        response = self.review("R1")

        self.assertEqual(response.status_code, 200)
        request = response.get_json()["request"]
        self.assertEqual(request["id"], self.requests["R1"].id)
        self.assertEqual(request["title"], "Harbour Lights Festival")
        self.assertEqual(request["status"], "submitted")
        for field, value in REQUEST_FIELDS.items():
            with self.subTest(field=field):
                expected = value.isoformat() if isinstance(value, datetime) else value
                self.assertEqual(request[field], expected)
        self.assertEqual(request["submitted_at"], "2026-09-20T09:00:00")
        self.assertEqual((request["decided_at"], request["decided_by"], request["decision_note"]),
                         (None, None, None))

        for user in ("ben", "dana"):
            with self.subTest(user=user):
                self.assert_error(self.review("R1", as_user=user), 403)


# ---------- AC2: approving ----------


class ApproveTests(DecisionTestCase):
    # TC-32-07 · AC2, AC5 — approving updates the status to Approved.
    def test_approving_updates_the_status_to_approved(self):
        before = self.stored("R1")
        started = datetime.utcnow()

        response = self.decide("R1", "approve")

        finished = datetime.utcnow()
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertIn(self.users["dana"].email, body["message"])
        self.assertEqual(body["request"]["status"], "approved")
        self.assertEqual(body["request"]["decided_by"],
                         {"id": self.users["alice"].id, "email": self.users["alice"].email})
        self.assertEqual(body["notification"], {"in_app": True, "email_queued": True})
        stored = self.stored("R1")
        self.assertEqual(stored["status"], "approved")
        self.assertTrue(started <= stored["decided_at"] <= finished)
        self.assertEqual(stored["decided_by_id"], self.users["alice"].id)
        self.assertIsNone(stored["decision_note"])
        for field in ("title", *REQUEST_FIELDS, "submitted_at", "organiser_id", "coordinator_id"):
            with self.subTest(field=field):
                self.assertEqual(stored[field], before[field])

    # TC-32-08 · AC2, AC6 — approving with an optional note.
    def test_approving_with_an_optional_note(self):
        self.decide("R1", "approve", reason="  Please book the venue by 1 Nov. ")

        self.assertEqual(self.stored("R1")["decision_note"], "Please book the venue by 1 Nov.")

    # TC-32-09 · AC1, AC2 — a decided request cannot be decided again.
    def test_a_decided_request_cannot_be_decided_again(self):
        self.decide("R1", "approve")
        decided = self.stored("R1")

        self.assert_error(self.decide("R1", "approve"), 409)
        self.assert_error(self.decide("R1", "reject", reason=REASON), 409)

        self.assertEqual(self.stored("R1"), decided)
        self.assertEqual(len(self.notifications_for("dana")), 1)
        self.queue_email.assert_called_once()


# ---------- AC3: a reason is required to reject ----------


class ReasonTests(DecisionTestCase):
    # TC-32-10 · AC3 — rejecting without a reason is refused.
    def test_rejecting_without_a_reason_is_refused(self):
        before = self.stored("R1")
        for label, body in {"missing": {"decision": "reject"},
                            "empty": {"decision": "reject", "reason": ""},
                            "whitespace": {"decision": "reject", "reason": "  \n\t "},
                            "null": {"decision": "reject", "reason": None},
                            "not text": {"decision": "reject", "reason": 42}}.items():
            with self.subTest(reason=label):
                response = self.client.post(
                    f"/api/events/{self.requests['R1'].id}/decision", json=body,
                    headers=self.auth_headers(self.users["alice"]))
                self.assertIn("reason", self.assert_error(response, 400)["error"].lower())
        self.assert_nothing_decided("R1", before)

    # TC-32-11 · AC3 (boundary, Q3) — reason length limits.
    def test_reason_length_limits(self):
        for decision in ("reject", "approve"):
            with self.subTest(decision=decision, words=MAX_WORDS + 1):
                body = self.assert_error(self.decide("R1", decision, reason=words(MAX_WORDS + 1)),
                                         400)
                text = body["error"].replace(",", "")
                self.assertIn("1000", text)
                self.assertIn("1001", text)
        self.assertEqual(self.stored("R1")["status"], "submitted")

        self.assertEqual(self.decide("R1", "reject", reason=words(MAX_WORDS)).status_code, 200)


# ---------- AC4: rejecting ----------


class RejectTests(DecisionTestCase):
    # TC-32-12 · AC4, AC5 — rejecting updates the status and records the reason.
    def test_rejecting_updates_the_status_and_records_the_reason(self):
        before = self.stored("R1")

        response = self.decide("R1", "reject", reason=REASON)

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["request"]["decision_note"], REASON)
        stored = self.stored("R1")
        self.assertEqual((stored["status"], stored["decision_note"], stored["decided_by_id"]),
                         ("rejected", REASON, self.users["alice"].id))
        self.assertIsNotNone(stored["decided_at"])
        for field in ("title", *REQUEST_FIELDS, "submitted_at"):
            with self.subTest(field=field):
                self.assertEqual(stored[field], before[field])


# ---------- AC5: the organiser is notified ----------


class NotificationTests(DecisionTestCase):
    def assert_organiser_notified(self, kind):
        [notification] = self.notifications_for("dana")
        self.assertEqual(notification.kind, kind)
        self.assertEqual(notification.event_id, self.requests["R1"].id)
        self.assertIn("Harbour Lights Festival", notification.message)
        self.assertEqual(self.notifications_for("evan"), [])
        self.assertEqual(self.notifications_for("alice"), [])
        listed = self.client.get(
            "/api/notifications/", headers=self.auth_headers(self.users["dana"])
        ).get_json()["notifications"]
        self.assertEqual([n["kind"] for n in listed], [kind])
        return notification

    # TC-32-13 · AC5 — in-app notification of an approval.
    def test_in_app_notification_of_an_approval(self):
        self.decide("R1", "approve")

        self.assert_organiser_notified("request_approved")

    # TC-32-13 · AC5 — in-app notification of a rejection, with the reason.
    def test_in_app_notification_of_a_rejection(self):
        self.decide("R1", "reject", reason=REASON)

        self.assertIn(REASON, self.assert_organiser_notified("request_rejected").message)

    # TC-32-14 · AC5 — email of the outcome.
    def test_email_of_the_outcome(self):
        self.decide("R1", "reject", reason=REASON)

        self.queue_email.assert_called_once()
        to_address, subject, body = self.queue_email.call_args.args
        self.assertEqual(to_address, self.users["dana"].email)
        self.assertIn("Harbour Lights Festival", subject)
        self.assertIn("rejected", subject.lower())
        self.assertIn(REASON, body)

    # TC-32-15 · AC5 — email cannot be queued: the decision still stands.
    def test_decision_stands_when_the_email_cannot_be_queued(self):
        self.queue_email.side_effect = ConnectionError("Redis is down")

        response = self.decide("R1", "approve")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": False})
        self.assertEqual(self.stored("R1")["status"], "approved")
        self.assertEqual(len(self.notifications_for("dana")), 1)

    # TC-32-16 · AC2, AC4, AC5 — a failed save changes nothing, and retry works.
    def test_failed_save_changes_nothing_and_retry_works(self):
        before = self.stored("R1")
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.decide("R1", "reject", reason=REASON)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not saved")
        self.assertRegex(body["error"].lower(), r"try again")
        self.assert_nothing_decided("R1", before)

        self.assertEqual(self.decide("R1", "reject", reason=REASON).status_code, 200)
        self.assertEqual(self.stored("R1")["status"], "rejected")


# ---------- AC6: the organiser can view the outcome ----------


class OrganiserViewTests(DecisionTestCase):
    # TC-32-17 · AC6 — the organiser's list of event requests.
    def test_organisers_list_of_event_requests(self):
        response = self.my_requests()

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        own = {self.requests[k].id: k for k in REQUESTS}
        listed = [own[r["id"]] for r in body["requests"] if r["id"] in own]
        self.assertEqual(listed, ["R2", "R3", "R1", "R6", "R5", "R7"])
        self.assertIsNone(body["message"])
        by_key = {own[r["id"]]: r for r in body["requests"] if r["id"] in own}
        self.assertEqual(by_key["R6"], {
            "id": self.requests["R6"].id, "title": "Rooftop Cinema", "status": "rejected",
            "submitted_at": "2026-09-06T09:00:00", "decided_at": "2026-09-12T09:00:00",
            "decision_note": "No licensed venue is available",
            # SCRUM-60: who decided is listed with the outcome.
            "decided_by": {"id": self.users["alice"].id, "email": self.users["alice"].email},
        })
        self.assertEqual((by_key["R5"]["status"], by_key["R5"]["decision_note"]),
                         ("approved", "Venue confirmed"))
        self.assertEqual((by_key["R1"]["decided_at"], by_key["R1"]["decision_note"]),
                         (None, None))

    # TC-32-18 · AC4, AC6 — the list reflects a new decision.
    def test_list_reflects_a_new_decision(self):
        self.decide("R1", "reject", reason=REASON)

        r1 = next(r for r in self.my_requests().get_json()["requests"]
                  if r["id"] == self.requests["R1"].id)

        self.assertEqual((r1["status"], r1["decision_note"]), ("rejected", REASON))
        self.assertEqual(r1["decided_at"], self.stored("R1")["decided_at"].isoformat())

    # TC-32-19 · AC6 — only organisers have a request list; the empty state.
    def test_only_organisers_have_a_request_list(self):
        newcomer = self.make_user(role="organiser")
        empty = self.client.get("/api/events/requests",
                                headers=self.auth_headers(newcomer)).get_json()
        self.assertEqual(empty["requests"], [])
        self.assertTrue(empty["message"].strip())

        for user in ("alice", "farah"):
            with self.subTest(user=user):
                self.assert_error(self.my_requests(as_user=user), 403)
        self.assertEqual(self.client.get("/api/events/requests").status_code, 401)


if __name__ == "__main__":
    unittest.main()
