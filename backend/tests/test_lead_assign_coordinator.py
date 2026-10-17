"""Tests for SCRUM-81 "Event Coordinator Lead assigns a coordinator to a waiting event".

Each test names the case it automates from
docs/test-cases/SCRUM-81-lead-assigns-coordinator.md (TC-81-nn) and the acceptance
criteria it checks. Assumptions A1-A8 and questions Q1-Q4 are there.

Endpoints (JWT required, else 401; unknown event 404; Event Coordinator Leads only, else 403)
    GET  /api/events/<id>/assignment
        200 {"event": {"id", "title", "start_time", "status"},
             "coordinators": [{"id", "email"}], "message": str | null}
    POST /api/events/<id>/assignment   {"coordinator_id": int}
        200 {"message", "assignment": {"event_id", "coordinator", "assigned_by", "assigned_at"},
             "notification": {"in_app": true, "email_queued": bool}}
        400 malformed body; 422 not an eligible coordinator
    Both: 409 {"error", "reason": "not_in_queue" | "already_assigned", "next_step"?}
          503 {"error", "retryable": true}
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app import tasks
from app.models import Event, Notification, User
from tests import seed_data
from tests.base import AppTestCase

# Event Coordinator Leads, alongside seed_data.USERS (AQ-SEED).
LEADS = [
    {"key": "lena", "email": "lena.lead@connectsphere.test", "role": "coordinator_lead"},
    {"key": "liam", "email": "liam.lead@connectsphere.test", "role": "coordinator_lead"},
]

ASSIGNED_AT = datetime(2026, 9, 2, 15, 30)

# AQ-SEED. `coordinator` and `assigned_by` are user keys.
EVENTS = {
    "Q1": ("Harbour Lights Festival", "submitted", None, None),
    "Q2": ("Alumni Mixer", "submitted", None, None),
    "A1": ("Product Launch", "submitted", "ben", "liam"),
    "D1": ("Draft Workshop", "draft", None, None),
    "C1": ("Cancelled Meetup", "cancelled", None, None),
    "R1": ("Startup Expo", "rejected", None, None),
}

NON_LEADS = ["admin", "alice", "dana", "farah", "gus", "hana"]
NOT_IN_QUEUE = ["D1", "C1", "R1"]


class AssignCoordinatorTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS + LEADS)
        self.events = {}
        for key, (title, status, coordinator, assigned_by) in EVENTS.items():
            self.events[key] = Event(
                title=title,
                status=status,
                organiser_id=self.users["dana"].id,
                coordinator_id=self.users[coordinator].id if coordinator else None,
                coordinator_assigned_at=ASSIGNED_AT if coordinator else None,
                coordinator_assigned_by_id=self.users[assigned_by].id if assigned_by else None,
                start_time=datetime(2026, 12, 12, 17, 0),
                end_time=datetime(2026, 12, 12, 22, 0),
            )
        self._insert(Event, list(self.events.values()))

        # No test sends a real email; the mock also records what would have been sent.
        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.email = patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- Requests ----------

    def url(self, key):
        return f"/api/events/{self.events[key].id}/assignment"

    def headers(self, as_user):
        return self.auth_headers(self.users[as_user])

    def load(self, key="Q1", as_user="lena", headers=None):
        return self.client.get(self.url(key), headers=headers or self.headers(as_user))

    def assign(self, key="Q1", coordinator="alice", as_user="lena", headers=None, body=None):
        if body is None:
            body = {"coordinator_id": self.users[coordinator].id}
        return self.client.post(self.url(key), headers=headers or self.headers(as_user), json=body)

    # ---------- Reading state ----------

    def state(self, key):
        """The event's assignment as saved, read afresh from the database."""
        self.db.session.expire_all()
        event = self.db.session.get(Event, self.events[key].id)
        return (event.coordinator_id, event.coordinator_assigned_by_id,
                event.coordinator_assigned_at, event.status)

    def notifications(self, key):
        return Notification.query.filter_by(event_id=self.events[key].id).all()

    def summary(self, user_key):
        user = self.users[user_key]
        return {"id": user.id, "email": user.email}

    # ---------- Assertions ----------

    def assert_refused(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        self.assertNotIn("assignment", body)
        return body

    def assert_unchanged(self, key, before):
        self.assertEqual(self.state(key), before)
        self.assertEqual(self.notifications(key), [])
        self.email.assert_not_called()


# ---------- AC1: choosing and assigning a coordinator ----------


class AssigningTests(AssignCoordinatorTestCase):
    # TC-81-01 · AC1 — the Lead sees the waiting event and its eligible coordinators.
    def test_lead_sees_the_waiting_event_and_eligible_coordinators(self):
        response = self.load()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["event"], {
            "id": self.events["Q1"].id, "title": "Harbour Lights Festival",
            "start_time": "2026-12-12T17:00:00", "status": "submitted",
        })
        own = {user.id for user in self.users.values()}
        listed = [c for c in body["coordinators"] if c["id"] in own]
        self.assertEqual(listed, [self.summary("alice"), self.summary("ben"),
                                  self.summary("chloe")])
        self.assertIsNone(body["message"])

    # TC-81-02 · AC1 — assigning records the coordinator, the Lead and the time.
    def test_assignment_records_the_coordinator_the_lead_and_the_time(self):
        started = datetime.utcnow()
        response = self.assign()
        finished = datetime.utcnow()

        self.assertEqual(response.status_code, 200, response.get_json())
        coordinator_id, assigned_by_id, assigned_at, status = self.state("Q1")
        self.assertEqual(coordinator_id, self.users["alice"].id)
        self.assertEqual(assigned_by_id, self.users["lena"].id)
        self.assertTrue(started <= assigned_at <= finished, assigned_at)
        self.assertEqual(status, "submitted")

        body = response.get_json()
        self.assertEqual(body["assignment"], {
            "event_id": self.events["Q1"].id,
            "coordinator": self.summary("alice"),
            "assigned_by": self.summary("lena"),
            "assigned_at": assigned_at.isoformat(),
        })
        self.assertIn(self.users["alice"].email, body["message"])
        # Q2 is untouched.
        self.assertIsNone(self.state("Q2")[0])

    # TC-81-03 · AC1 — the event leaves the queue.
    def test_assigned_event_leaves_the_queue(self):
        self.assertEqual(self.assign().status_code, 200)

        body = self.assert_refused(self.load(), 409)
        self.assertEqual(body["reason"], "already_assigned")

        supervised = self.client.get("/api/events/supervised", headers=self.headers("lena"))
        listed = {e["id"]: e for e in supervised.get_json()["events"]}
        self.assertEqual(listed[self.events["Q1"].id]["coordinator"], self.summary("alice"))
        managed = self.client.get("/api/events/managed", headers=self.headers("alice"))
        self.assertIn(self.events["Q1"].id, [e["id"] for e in managed.get_json()["events"]])

    # TC-81-04 · AC1 (A3/Q3) — only an eligible coordinator can be chosen.
    def test_only_an_eligible_coordinator_can_be_chosen(self):
        before = self.state("Q1")
        choices = {key: self.users[key].id for key in ["dana", "liam", "admin"]}
        choices["missing user"] = self.missing_id(User)

        for label, user_id in choices.items():
            with self.subTest(choice=label):
                body = self.assert_refused(self.assign(body={"coordinator_id": user_id}), 422)
                self.assertEqual(body.get("field"), "coordinator_id")
        self.assert_unchanged("Q1", before)

    # TC-81-05 · AC1 — a malformed request is refused.
    def test_malformed_requests_are_refused(self):
        before = self.state("Q1")
        alice = self.users["alice"].id
        bodies = {
            "empty object": {},
            "string id": {"coordinator_id": str(alice)},
            "boolean id": {"coordinator_id": True},
            "extra field": {"coordinator_id": alice,
                            "coordinator_assigned_by_id": self.users["liam"].id},
        }

        for label, body in bodies.items():
            with self.subTest(body=label):
                self.assert_refused(self.assign(body=body), 400)
        with self.subTest(body="none"):
            response = self.client.post(self.url("Q1"), headers=self.headers("lena"))
            self.assert_refused(response, 400)
        self.assert_unchanged("Q1", before)

    # TC-81-06 · AC1 (A1/Q1) — events not waiting in the queue cannot be assigned.
    def test_events_not_waiting_in_the_queue_cannot_be_assigned(self):
        for key in NOT_IN_QUEUE:
            before = self.state(key)
            with self.subTest(event=key, action="load"):
                self.assertEqual(self.assert_refused(self.load(key), 409)["reason"],
                                 "not_in_queue")
            with self.subTest(event=key, action="assign"):
                self.assertEqual(self.assert_refused(self.assign(key), 409)["reason"],
                                 "not_in_queue")
                self.assert_unchanged(key, before)


# ---------- AC2: the coordinator is notified ----------


class NotificationTests(AssignCoordinatorTestCase):
    # TC-81-07 · AC2 (A5) — the new coordinator is notified in the app and by email.
    def test_new_coordinator_is_notified_in_app_and_by_email(self):
        response = self.assign()

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": True})
        [notification] = self.notifications("Q1")
        self.assertEqual(notification.recipient_id, self.users["alice"].id)
        self.assertEqual(notification.kind, "coordinator_assigned")
        self.assertIn("Harbour Lights Festival", notification.message)
        self.email.assert_called_once()
        to_address, subject, body = self.email.call_args.args
        self.assertEqual(to_address, self.users["alice"].email)
        self.assertIn("Harbour Lights Festival", subject + body)

    # TC-81-08 · AC2 (A5) — an email queue failure does not undo the assignment.
    def test_email_queue_failure_keeps_the_assignment_and_in_app_notification(self):
        self.email.side_effect = ConnectionError("broker down")

        response = self.assign()

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": False})
        self.assertEqual(self.state("Q1")[0], self.users["alice"].id)
        self.assertEqual(len(self.notifications("Q1")), 1)


# ---------- AC3: already assigned ----------


class AlreadyAssignedTests(AssignCoordinatorTestCase):
    # TC-81-09 · AC3 (A6/Q4) — refused, pointing to the reassign function.
    def test_event_with_a_coordinator_is_refused_with_the_reassign_function(self):
        before = self.state("A1")

        body = self.assert_refused(self.assign("A1"), 409)

        self.assertEqual(body["reason"], "already_assigned")
        self.assertIn("reassign", body["error"].lower())
        self.assertEqual(body["next_step"]["method"], "PUT")
        self.assertTrue(body["next_step"]["url"].endswith(
            f"/api/events/{self.events['A1'].id}/coordinator"))
        self.assertEqual(before[:3], (self.users["ben"].id, self.users["liam"].id, ASSIGNED_AT))
        self.assert_unchanged("A1", before)

    # TC-81-10 · AC3 — when another Lead assigns first, the second is refused.
    def test_second_lead_is_refused_after_another_lead_assigns_first(self):
        self.assertEqual(self.assign(coordinator="ben", as_user="liam").status_code, 200)
        after_first = self.state("Q1")

        body = self.assert_refused(self.assign(coordinator="alice", as_user="lena"), 409)

        self.assertEqual(body["reason"], "already_assigned")
        self.assertEqual(self.state("Q1"), after_first)
        self.assertEqual(after_first[:2], (self.users["ben"].id, self.users["liam"].id))
        self.assertEqual([n.recipient_id for n in self.notifications("Q1")],
                         [self.users["ben"].id])
        self.assertEqual(self.email.call_count, 1)


# ---------- AC4: only the Lead ----------


class AccessTests(AssignCoordinatorTestCase):
    # TC-81-11 · AC4 (A2/Q2) — every other role is denied and nothing changes.
    def test_only_leads_can_assign(self):
        before = self.state("Q1")

        for user in NON_LEADS:
            for action, response in [("load", lambda: self.load(as_user=user)),
                                     ("assign", lambda: self.assign(as_user=user))]:
                with self.subTest(user=user, action=action):
                    reply = response()
                    self.assert_refused(reply, 403)
                    self.assertNotIn("event", reply.get_json())
                    self.assertNotIn("coordinators", reply.get_json())
                    self.assertNotIn("Harbour Lights Festival", reply.get_data(as_text=True))
        self.assert_unchanged("Q1", before)

    # TC-81-12 · AC4 — a valid session is required.
    def test_a_valid_session_is_required(self):
        before = self.state("Q1")
        ghost = self.make_user(role="coordinator_lead")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["lena"].id),
                                      expires_delta=timedelta(seconds=-1))
        sessions = {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                    "deleted user": ghost_headers}

        for label, headers in sessions.items():
            with self.subTest(session=label, action="load"):
                self.assertEqual(self.client.get(self.url("Q1"), headers=headers).status_code, 401)
            with self.subTest(session=label, action="assign"):
                response = self.client.post(self.url("Q1"), headers=headers,
                                            json={"coordinator_id": self.users["alice"].id})
                self.assertEqual(response.status_code, 401)
        self.assert_unchanged("Q1", before)

    # TC-81-13 · AC4 — a Lead whose role changes is denied at once.
    def test_lead_whose_role_changes_is_denied_at_once(self):
        before = self.state("Q1")
        lena_headers = self.headers("lena")
        self.users["lena"].role = "coordinator"
        self.db.session.commit()

        self.assert_refused(self.assign(headers=lena_headers), 403)
        self.assert_unchanged("Q1", before)

    # TC-81-14 · AC4 — an unknown event.
    def test_unknown_event_is_not_found(self):
        url = f"/api/events/{self.missing_id(Event)}/assignment"
        headers = self.headers("lena")

        self.assertEqual(self.client.get(url, headers=headers).status_code, 404)
        response = self.client.post(url, headers=headers,
                                    json={"coordinator_id": self.users["alice"].id})
        self.assertEqual(response.status_code, 404)


# ---------- AC5: no eligible coordinator, or the save fails ----------


class FailureTests(AssignCoordinatorTestCase):
    # TC-81-15 · AC5 — no eligible coordinator exists.
    def test_no_eligible_coordinator_is_reported_and_nothing_changes(self):
        before = self.state("Q1")
        # Every coordinator, real ones included; rolled back after the test.
        User.query.filter(User.role == "coordinator").update(
            {"role": "organiser"}, synchronize_session="fetch"
        )
        self.db.session.commit()

        response = self.load()
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["coordinators"], [])
        self.assertRegex(body["message"].lower(), r"no eligible coordinator")

        refused = self.assert_refused(self.assign(), 422)
        self.assertRegex(refused["error"].lower(), r"no eligible coordinator")
        self.assert_unchanged("Q1", before)

    # TC-81-16 · AC5 (A8) — the save fails, nothing changes, and retry works.
    def test_save_failure_changes_nothing_and_retry_works(self):
        before = self.state("Q1")
        session = self.db.session()
        with mock.patch.object(session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.assign()

        body = self.assert_refused(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not saved")
        self.assertRegex(body["error"].lower(), r"try again")
        self.assert_unchanged("Q1", before)

        self.assertEqual(self.assign().status_code, 200)
        self.assertEqual(self.state("Q1")[0], self.users["alice"].id)

    # TC-81-17 · A8 — loading fails.
    def test_load_failure_is_reported(self):
        headers = self.headers("lena")
        session = self.db.session()
        with mock.patch.object(session, "execute",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.load(headers=headers)

        body = self.assert_refused(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("event", body)
        self.assertNotIn("Harbour Lights Festival", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
