"""Tests for SCRUM-82 "Event Coordinator Lead reassigns an event to a different coordinator".

Each test names the case it automates from
docs/test-cases/SCRUM-82-lead-reassigns-coordinator.md (TC-82-nn) and the acceptance
criteria it checks. Assumptions A1-A7 and questions Q1-Q4 are there.

Endpoints (JWT required, else 401; unknown event 404; Event Coordinator Leads only, else 403)
    GET /api/events/<id>/eligible-coordinators
        200 {"event_id", "event": {"id", "title", "start_time", "status"},
             "current_coordinator": {"id", "email"},
             "coordinators": [{"id", "email"}], "message": str | null}
    PUT /api/events/<id>/coordinator   {"coordinator_id": int}
        200 {"message", "event_id", "coordinator", "previous_coordinator", "assigned_by",
             "assigned_at", "notification": {"in_app": true, "email_queued": bool}}
        400 malformed body; 409 the current coordinator; 422 not an eligible coordinator
    Both: 409 {"error", "reason": "not_assigned", "next_step"} with no coordinator yet,
          409 for a draft or cancelled event; 503 {"error", "retryable": true}
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

ASSIGNED_AT = datetime(2026, 9, 1, 10, 0)

# RA-SEED. `coordinator` and `assigned_by` are user keys.
EVENTS = {
    "E1": ("Harbour Lights Festival", "submitted", "alice", "lena"),
    "E2": ("Alumni Mixer", "approved", "ben", "lena"),
    "E3": ("Product Launch", "submitted", "ben", "liam"),
    "W1": ("Tech Summit 2026", "submitted", None, None),
    "C1": ("Cancelled Meetup", "cancelled", "alice", "lena"),
}

NON_LEADS = ["admin", "alice", "ben", "dana", "farah", "gus", "hana"]


class ReassignTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS + seed_data.LEADS)
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

    def headers(self, as_user):
        return self.auth_headers(self.users[as_user])

    def eligible(self, key="E1", as_user="lena", headers=None):
        return self.client.get(f"/api/events/{self.events[key].id}/eligible-coordinators",
                               headers=headers or self.headers(as_user))

    def reassign(self, key="E1", to="chloe", as_user="lena", headers=None, coordinator_id=None):
        if coordinator_id is None:
            coordinator_id = self.users[to].id
        return self.client.put(f"/api/events/{self.events[key].id}/coordinator",
                               headers=headers or self.headers(as_user),
                               json={"coordinator_id": coordinator_id})

    def supervised_ids(self, lead):
        response = self.client.get("/api/events/supervised", headers=self.headers(lead))
        self.assertEqual(response.status_code, 200, response.get_json())
        return {item["id"]: item for item in response.get_json()["events"]}

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
        self.assertNotIn("coordinator", body)
        self.assertNotIn("coordinators", body)
        return body

    def assert_unchanged(self, key, before):
        self.assertEqual(self.state(key), before)
        self.assertEqual(self.notifications(key), [])
        self.email.assert_not_called()


# ---------- AC1: starting a reassignment from the Lead's list ----------


class StartingTests(ReassignTestCase):
    # TC-82-01 · AC1 — every event in the Lead's list can be opened for reassignment.
    def test_every_event_in_the_leads_list_can_be_opened_for_reassignment(self):
        listed = self.supervised_ids("lena")
        self.assertEqual(set(listed), {self.events["E1"].id, self.events["E2"].id})

        for key in ("E1", "E2"):
            with self.subTest(event=key):
                self.assertEqual(self.eligible(key).status_code, 200)

        body = self.eligible("E1").get_json()
        self.assertEqual(body["event"], {
            "id": self.events["E1"].id, "title": "Harbour Lights Festival",
            "start_time": "2026-12-12T17:00:00", "status": "submitted",
        })
        self.assertEqual(body["current_coordinator"], self.summary("alice"))
        own = {user.id for user in self.users.values()}
        self.assertEqual([c for c in body["coordinators"] if c["id"] in own],
                         [self.summary("ben"), self.summary("chloe")])
        self.assertIsNone(body["message"])


# ---------- AC2: reassigning ----------


class ReassigningTests(ReassignTestCase):
    # TC-82-02 · AC2 (A4) — the coordinator is replaced and the Lead and time recorded.
    def test_reassignment_replaces_the_coordinator_and_records_the_lead_and_time(self):
        started = datetime.utcnow()
        response = self.reassign()
        finished = datetime.utcnow()

        self.assertEqual(response.status_code, 200, response.get_json())
        coordinator_id, assigned_by_id, assigned_at, status = self.state("E1")
        self.assertEqual(coordinator_id, self.users["chloe"].id)
        self.assertEqual(assigned_by_id, self.users["lena"].id)
        self.assertTrue(started <= assigned_at <= finished, assigned_at)
        self.assertEqual(status, "submitted")
        self.assertEqual(
            Event.query.filter_by(id=self.events["E1"].id,
                                  coordinator_id=self.users["alice"].id).count(), 0)

        body = response.get_json()
        self.assertEqual(body["coordinator"], self.summary("chloe"))
        self.assertEqual(body["previous_coordinator"], self.summary("alice"))
        self.assertEqual(body["assigned_by"], self.summary("lena"))
        self.assertEqual(body["assigned_at"], assigned_at.isoformat())
        self.assertIn(self.users["chloe"].email, body["message"])

    # TC-82-03 · AC2 (A1/Q1) — another Lead can reassign; the event moves to their list.
    def test_another_lead_can_reassign_and_the_event_moves_to_their_list(self):
        response = self.reassign(as_user="liam")

        self.assertEqual(response.status_code, 200, response.get_json())
        liams = self.supervised_ids("liam")
        self.assertEqual(liams[self.events["E1"].id]["coordinator"], self.summary("chloe"))
        self.assertNotIn(self.events["E1"].id, self.supervised_ids("lena"))

    # TC-82-04 · AC2 (A2/Q3) — no coordinator yet, or cancelled: cannot be reassigned.
    def test_unassigned_and_cancelled_events_cannot_be_reassigned(self):
        for key in ("W1", "C1"):
            before = self.state(key)
            with self.subTest(event=key, action="load"):
                self.assert_refused(self.eligible(key), 409)
            with self.subTest(event=key, action="reassign"):
                body = self.assert_refused(self.reassign(key), 409)
                if key == "W1":
                    self.assertEqual(body["reason"], "not_assigned")
                    self.assertEqual(body["next_step"]["method"], "POST")
                    self.assertTrue(body["next_step"]["url"].endswith(
                        f"/api/events/{self.events['W1'].id}/assignment"))
                self.assert_unchanged(key, before)


# ---------- AC3: the event follows the new coordinator ----------


class FollowingTests(ReassignTestCase):
    # TC-82-05 · AC3 — the event appears for the new coordinator, not the previous one.
    def test_event_appears_for_the_new_coordinator_and_not_the_previous_one(self):
        alice, chloe = self.headers("alice"), self.headers("chloe")
        event_id = self.events["E1"].id

        self.assertEqual(self.reassign().status_code, 200)

        def managed(headers):
            response = self.client.get("/api/events/managed", headers=headers)
            return [item["id"] for item in response.get_json()["events"]]

        self.assertIn(event_id, managed(chloe))
        self.assertNotIn(event_id, managed(alice))
        planning = f"/api/events/{event_id}/planning"
        self.assertEqual(self.client.get(planning, headers=chloe).status_code, 200)
        self.assertEqual(self.client.get(planning, headers=alice).status_code, 403)


# ---------- AC4: both coordinators are notified ----------


class NotificationTests(ReassignTestCase):
    # TC-82-06 · AC4 (A5/Q4) — the new and the previous coordinator are notified.
    def test_new_and_previous_coordinators_are_notified(self):
        response = self.reassign()

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": True})
        by_recipient = {n.recipient_id: n for n in self.notifications("E1")}
        self.assertEqual(set(by_recipient), {self.users["chloe"].id, self.users["alice"].id})
        self.assertEqual(by_recipient[self.users["chloe"].id].kind, "coordinator_assigned")
        self.assertEqual(by_recipient[self.users["alice"].id].kind, "coordinator_unassigned")
        for notification in by_recipient.values():
            self.assertIn("Harbour Lights Festival", notification.message)

        self.assertEqual(self.email.call_count, 2)
        sent = {call.args[0]: call.args for call in self.email.call_args_list}
        self.assertEqual(set(sent), {self.users["chloe"].email, self.users["alice"].email})
        for _, subject, body in sent.values():
            self.assertIn("Harbour Lights Festival", subject + body)

    # TC-82-07 · AC4 (A5) — an email queue failure does not undo the reassignment.
    def test_email_queue_failure_keeps_the_reassignment_and_notifications(self):
        self.email.side_effect = ConnectionError("broker down")

        response = self.reassign()

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": False})
        self.assertEqual(self.state("E1")[0], self.users["chloe"].id)
        self.assertEqual(len(self.notifications("E1")), 2)


# ---------- AC5: the coordinator the event already has ----------


class SameCoordinatorTests(ReassignTestCase):
    # TC-82-08 · AC5 (A6) — choosing the current coordinator is refused.
    def test_choosing_the_current_coordinator_is_refused(self):
        before = self.state("E1")

        body = self.assert_refused(self.reassign(to="alice"), 409)

        self.assertIn("already", body["error"].lower())
        self.assertEqual(before[:3], (self.users["alice"].id, self.users["lena"].id, ASSIGNED_AT))
        self.assert_unchanged("E1", before)


# ---------- AC6: only the Lead ----------


class AccessTests(ReassignTestCase):
    # TC-82-09 · AC6 (A1/Q2) — everyone else is denied, admins and the coordinator included.
    def test_only_leads_can_reassign(self):
        before = self.state("E1")

        for user in NON_LEADS:
            for action, send in (("load", lambda: self.eligible(as_user=user)),
                                 ("reassign", lambda: self.reassign(as_user=user))):
                with self.subTest(user=user, action=action):
                    response = send()
                    self.assert_refused(response, 403)
                    text = response.get_data(as_text=True)
                    self.assertNotIn("Harbour Lights Festival", text)
                    self.assertNotIn(self.users["alice"].email, text)
        self.assert_unchanged("E1", before)

    # TC-82-10 · AC6 — a valid session is required, and role changes apply at once.
    def test_a_valid_session_and_the_lead_role_are_required(self):
        before = self.state("E1")
        ghost = self.make_user(role="coordinator_lead")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["lena"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                response = self.client.put(f"/api/events/{self.events['E1'].id}/coordinator",
                                           headers=headers,
                                           json={"coordinator_id": self.users["chloe"].id})
                self.assertEqual(response.status_code, 401)

        lena_headers = self.headers("lena")
        self.users["lena"].role = "coordinator"
        self.db.session.commit()
        self.assert_refused(self.reassign(headers=lena_headers), 403)
        self.assert_unchanged("E1", before)


# ---------- AC7: nobody else eligible, or the save fails ----------


class FailureTests(ReassignTestCase):
    # TC-82-11 · AC7 (A6) — no other eligible coordinator exists.
    def test_no_other_eligible_coordinator_is_reported_and_nothing_changes(self):
        before = self.state("E1")
        # Every coordinator but alice, real ones included; rolled back after the test.
        User.query.filter(User.role == "coordinator",
                          User.id != self.users["alice"].id).update(
            {"role": "organiser"}, synchronize_session="fetch")
        self.db.session.commit()

        response = self.eligible()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["coordinators"], [])
        self.assertTrue(response.get_json()["message"].strip())

        refused = self.assert_refused(self.reassign(to="ben"), 422)
        self.assertRegex(refused["error"].lower(), r"no other eligible coordinator")
        self.assert_unchanged("E1", before)

    # TC-82-12 · AC7 (A6) — the save fails, nothing changes, and retry works.
    def test_save_failure_changes_nothing_and_retry_works(self):
        before = self.state("E1")
        session = self.db.session()
        with mock.patch.object(session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.reassign()

        body = self.assert_refused(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"could not be saved")
        self.assertRegex(body["error"].lower(), r"try again")
        self.assert_unchanged("E1", before)

        self.assertEqual(self.reassign().status_code, 200)
        self.assertEqual(self.state("E1")[0], self.users["chloe"].id)


if __name__ == "__main__":
    unittest.main()
