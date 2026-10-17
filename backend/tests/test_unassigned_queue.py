"""Tests for SCRUM-81 "Submitted event requests wait in the Lead's unassigned queue".

Each test names the case it automates from
docs/test-cases/SCRUM-81-unassigned-queue.md (TC-81-nn) and the acceptance criteria
it checks. Assumptions A9-A15 and questions Q5-Q9 are there. TC-81-24 is automated in
tests/test_event_submission.py (TC-28-10, updated).

Endpoint (JWT required, else 401; Event Coordinator Leads only, else 403)
    GET /api/events/queue
        200 {"events": [event], "message": str | null}
        503 {"error", "retryable": true} if loading fails
    event = {"id", "title", "start_time", "status", "organiser": {"id", "email"},
             "submitted_at"}   title, start_time and submitted_at are null when not
             recorded; start_time is Singapore time, submitted_at naive UTC

Submitting uses the SCRUM-28 endpoint POST /api/events/drafts/<id>/submit and
assigning the SCRUM-81 endpoints /api/events/<id>/assignment.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app import tasks
from app.models import Event
from tests import seed_data
from tests.base import AppTestCase
from tests.test_event_drafts import COMPLETE

# UQ-SEED. `coordinator` and `organiser` are user keys; submitted_at is naive UTC,
# start_time Singapore time.
EVENTS = {
    "W1": ("Harbour Lights Festival", "submitted", None, "dana",
           datetime(2026, 10, 10, 9, 0), datetime(2026, 12, 12, 17, 0)),
    "W2": ("Alumni Mixer", "submitted", None, "evan",
           datetime(2026, 10, 8, 14, 0), datetime(2026, 11, 20, 18, 30)),
    "W3": ("   ", "submitted", None, "dana", datetime(2026, 10, 12, 8, 0), None),
    "W4": ("Legacy Forum", "submitted", None, "evan", None, datetime(2026, 11, 25, 9, 0)),
    "H1": ("Product Launch", "submitted", "ben", "evan",
           datetime(2026, 10, 1, 10, 0), datetime(2026, 11, 20, 14, 0)),
    "U1": ("Charity Fun Run", "under_review", None, "dana",
           datetime(2026, 10, 2, 10, 0), datetime(2026, 11, 5, 7, 0)),
    "D1": ("Draft Workshop", "draft", None, "dana", None, datetime(2027, 1, 15, 10, 0)),
    "C1": ("Cancelled Meetup", "cancelled", None, "dana",
           datetime(2026, 10, 3, 10, 0), datetime(2026, 10, 30, 19, 0)),
    "R1": ("Startup Expo", "rejected", None, "evan",
           datetime(2026, 10, 4, 10, 0), datetime(2026, 11, 15, 10, 0)),
}

QUEUED = ["W2", "W1", "W3", "W4"]
NOT_QUEUED = ["H1", "U1", "D1", "C1", "R1"]
NON_LEADS = ["admin", "alice", "dana", "farah", "gus", "hana"]


class QueueTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS + seed_data.LEADS)
        self.events = {}
        for key, (title, status, coordinator, organiser, submitted, start) in EVENTS.items():
            self.events[key] = Event(
                title=title,
                status=status,
                organiser_id=self.users[organiser].id,
                coordinator_id=self.users[coordinator].id if coordinator else None,
                submitted_at=submitted,
                start_time=start,
                end_time=start + timedelta(hours=2) if start else None,
            )
        self._insert(Event, list(self.events.values()))

        # Assigning notifies by email; no test sends a real one.
        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- Requests ----------

    def load(self, as_user="lena", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get("/api/events/queue", headers=headers)

    def listed(self, as_user="lena", headers=None):
        response = self.load(as_user, headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def by_key(self, items):
        """The listed items keyed by seed key, in order; rows from real data are skipped."""
        by_id = {event.id: key for key, event in self.events.items()}
        return {by_id[item["id"]]: item for item in items if item["id"] in by_id}

    def keys(self, items):
        return list(self.by_key(items))

    # ---------- Assertions ----------

    def assert_no_event_data(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        self.assertNotIn("events", body)
        text = response.get_data(as_text=True)
        for event in self.events.values():
            if event.title.strip():
                self.assertNotIn(event.title, text)
        return body


# ---------- AC6: submissions enter the queue ----------


class SubmissionTests(QueueTestCase):
    # TC-81-23 · AC6 (A9/Q5) — a submitted request has no coordinator and is in the queue.
    def test_a_submitted_request_waits_in_the_queue_without_a_coordinator(self):
        draft = Event(organiser_id=self.users["dana"].id, status="draft", **COMPLETE)
        self.db.session.add(draft)
        self.db.session.commit()

        response = self.client.post(f"/api/events/drafts/{draft.id}/submit",
                                    headers=self.auth_headers(self.users["dana"]))

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["status"], "submitted")
        self.db.session.expire_all()
        stored = self.db.session.get(Event, draft.id)
        self.assertEqual(
            (stored.coordinator_id, stored.coordinator_assigned_at,
             stored.coordinator_assigned_by_id),
            (None, None, None),
        )
        queued = [item["id"] for item in self.listed()["events"]]
        self.assertIn(draft.id, queued)


# ---------- AC7: viewing the queue ----------


class QueueListTests(QueueTestCase):
    # TC-81-25 · AC7 (A11, A12/Q7, Q8) — each waiting event's basic information.
    def test_lead_sees_each_waiting_event_with_basic_information(self):
        body = self.listed()
        dana = self.users["dana"]

        self.assertEqual(set(self.keys(body["events"])), set(QUEUED))
        self.assertIsNone(body["message"])
        self.assertEqual(self.by_key(body["events"])["W1"], {
            "id": self.events["W1"].id, "title": "Harbour Lights Festival",
            "start_time": "2026-12-12T17:00:00", "status": "submitted",
            "organiser": {"id": dana.id, "email": dana.email},
            "submitted_at": "2026-10-10T09:00:00",
        })
        self.assertEqual(set(self.keys(self.listed("liam")["events"])), set(QUEUED))

    # TC-81-26 · AC7 (A10/Q6) — only events waiting for a coordinator are listed.
    def test_only_events_waiting_for_a_coordinator_are_listed(self):
        listed = set(self.keys(self.listed()["events"]))

        for key in NOT_QUEUED:
            with self.subTest(event=key, status=self.events[key].status):
                self.assertNotIn(key, listed)

    # TC-81-27 · AC7 (A13/Q9) — oldest submission first, unknown last.
    def test_oldest_submission_is_listed_first(self):
        self.assertEqual(self.keys(self.listed()["events"]), QUEUED)

    # TC-81-28 · AC7 (A12) — missing name, date and submission time are null.
    def test_missing_values_are_null(self):
        by_key = self.by_key(self.listed()["events"])

        self.assertIsNone(by_key["W3"]["title"])
        self.assertIsNone(by_key["W3"]["start_time"])
        self.assertIsNone(by_key["W4"]["submitted_at"])

    # TC-81-29 · AC7 (A14) — every listed event can be opened for assignment.
    def test_every_listed_event_can_be_opened_for_assignment(self):
        headers = self.auth_headers(self.users["lena"])

        for key in self.keys(self.listed()["events"]):
            with self.subTest(event=key):
                response = self.client.get(f"/api/events/{self.events[key].id}/assignment",
                                           headers=headers)
                self.assertEqual(response.status_code, 200, response.get_json())


# ---------- AC8: only the Lead ----------


class AccessTests(QueueTestCase):
    # TC-81-30 · AC8 — every other role is denied and sees no event data.
    def test_only_leads_can_view_the_queue(self):
        for user in NON_LEADS:
            with self.subTest(user=user):
                self.assert_no_event_data(self.load(as_user=user), 403)

    # TC-81-31 · AC8 — a valid session is required, and role changes apply at once.
    def test_a_valid_session_and_the_lead_role_are_required(self):
        ghost = self.make_user(role="coordinator_lead")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["lena"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                response = self.load(headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("events", response.get_json())

        lena_headers = self.auth_headers(self.users["lena"])
        self.users["lena"].role = "coordinator"
        self.db.session.commit()
        self.assert_no_event_data(self.load(headers=lena_headers), 403)


# ---------- AC9: empty and failed loads ----------


class EmptyAndFailureTests(QueueTestCase):
    # TC-81-32 · AC9 — an empty queue says so.
    def test_empty_queue_gets_a_message(self):
        # Every waiting event, real ones included; rolled back after the test.
        Event.query.filter(Event.status == "submitted", Event.coordinator_id.is_(None)).update(
            {"status": "under_review"}, synchronize_session="fetch"
        )
        self.db.session.commit()

        body = self.listed()

        self.assertEqual(body["events"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())

    # TC-81-33 · AC9 (A15) — loading fails, no list is sent, and retry works.
    def test_load_failure_is_reported_without_a_list_and_retry_works(self):
        headers = self.auth_headers(self.users["lena"])
        session = self.db.session()
        with mock.patch.object(session, "execute",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.load(headers=headers)

        body = self.assert_no_event_data(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"could not be loaded")
        self.assertRegex(body["error"].lower(), r"try again")

        self.assertEqual(self.keys(self.listed(headers=headers)["events"]), QUEUED)


# ---------- AC10: leaving the queue ----------


class LeavingTests(QueueTestCase):
    # TC-81-34 · AC10 — an assigned event leaves the queue.
    def test_an_assigned_event_leaves_the_queue(self):
        response = self.client.post(
            f"/api/events/{self.events['W1'].id}/assignment",
            headers=self.auth_headers(self.users["lena"]),
            json={"coordinator_id": self.users["alice"].id},
        )
        self.assertEqual(response.status_code, 200, response.get_json())

        self.assertEqual(self.keys(self.listed()["events"]), ["W2", "W3", "W4"])


if __name__ == "__main__":
    unittest.main()
