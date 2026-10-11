"""Tests for SCRUM-62 "Identify My Managed Events".

Each test names the case it automates from
docs/test-cases/SCRUM-62-managed-events-list.md (TC-62-nn) and the acceptance
criteria it checks. Assumptions A1-A7 and questions Q1-Q3 are there.

Endpoint (JWT required, else 401; coordinators only, else 403)
    GET /api/events/managed
        200 {"events": [event], "message": str | null}
        503 {"error", "retryable": true} if loading fails
    event = {"id", "title", "start_time", "status"}   title and start_time are null
            when not recorded; start_time is Singapore time, as stored

Opening a listed event uses the SCRUM-34 endpoint GET /api/events/<id>/planning.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app.models import Event
from tests import seed_data
from tests.base import AppTestCase

# ME-SEED. Times are Singapore time. `coordinator` refers to a seed_data.USERS key.
EVENTS = {
    "M1": {"title": "Harbour Lights Festival", "coordinator": "alice", "status": "submitted",
           "start_time": datetime(2026, 12, 12, 17, 0), "end_time": datetime(2026, 12, 12, 22, 0)},
    "M2": {"title": "Alumni Mixer", "coordinator": "alice", "status": "approved",
           "start_time": datetime(2026, 11, 20, 18, 30), "end_time": datetime(2026, 11, 20, 21, 0)},
    "M3": {"title": "Winter Networking Night", "coordinator": "alice", "status": "cancelled",
           "start_time": datetime(2026, 10, 1, 9, 0), "end_time": datetime(2026, 10, 1, 11, 0)},
    "M4": {"title": "   ", "coordinator": "alice", "status": "under_review",
           "start_time": None, "end_time": None},
    "M5": {"title": "Product Launch", "coordinator": "ben", "status": "submitted",
           "start_time": datetime(2026, 11, 20, 14, 0), "end_time": datetime(2026, 11, 20, 16, 0)},
    "M6": {"title": "Tech Summit 2026", "coordinator": None, "status": "submitted",
           "start_time": datetime(2026, 11, 10, 9, 0), "end_time": datetime(2026, 11, 10, 17, 0)},
}

NON_COORDINATORS = ["admin", "dana", "farah", "gus", "hana"]


class ManagedEventsTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.events = {}
        for key, row in EVENTS.items():
            coordinator = self.users[row["coordinator"]] if row["coordinator"] else None
            self.events[key] = Event(
                organiser_id=self.users["dana"].id,
                coordinator_id=coordinator.id if coordinator else None,
                coordinator_assigned_at=datetime(2026, 9, 1, 10, 0) if coordinator else None,
                **{k: v for k, v in row.items() if k != "coordinator"},
            )
        self._insert(Event, list(self.events.values()))

    # ---------- Requests ----------

    def load(self, as_user="alice", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get("/api/events/managed", headers=headers)

    def listed(self, as_user="alice", headers=None):
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

    def assert_error(self, response, status_code):
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


# ---------- AC1: the coordinator's list ----------


class ManagedListTests(ManagedEventsTestCase):
    # TC-62-01 · AC1 — the coordinator sees the events assigned to them.
    def test_coordinator_sees_only_the_events_assigned_to_them(self):
        body = self.listed()

        self.assertEqual(set(self.keys(body["events"])), {"M1", "M2", "M3", "M4"})
        self.assertIsNone(body["message"])
        self.assertEqual(self.keys(self.listed("ben")["events"]), ["M5"])

    # TC-62-02 · AC1 — each event shows its name, proposed date and status.
    def test_each_event_shows_its_name_proposed_date_and_status(self):
        by_key = self.by_key(self.listed()["events"])

        self.assertEqual(by_key["M1"], {
            "id": self.events["M1"].id, "title": "Harbour Lights Festival",
            "start_time": "2026-12-12T17:00:00", "status": "submitted",
        })
        self.assertEqual({key: item["status"] for key, item in by_key.items()}, {
            "M1": "submitted", "M2": "approved", "M3": "cancelled", "M4": "under_review",
        })
        self.assertEqual(by_key["M2"]["start_time"], "2026-11-20T18:30:00")

    # TC-62-03 · AC1 (A4/Q3) — soonest proposed date first, undated last.
    def test_events_are_listed_soonest_first_with_undated_last(self):
        self.assertEqual(self.keys(self.listed()["events"]), ["M3", "M2", "M1", "M4"])

    # TC-62-04 · AC1 — reassignment moves the event between lists immediately.
    def test_reassignment_moves_the_event_to_the_new_coordinators_list(self):
        alice_headers = self.auth_headers(self.users["alice"])
        ben_headers = self.auth_headers(self.users["ben"])

        response = self.client.put(
            f"/api/events/{self.events['M1'].id}/coordinator",
            headers=self.auth_headers(self.users["admin"]),
            json={"coordinator_id": self.users["ben"].id},
        )
        self.assertEqual(response.status_code, 200, response.get_json())

        self.assertNotIn("M1", self.keys(self.listed(headers=alice_headers)["events"]))
        self.assertIn("M1", self.keys(self.listed(headers=ben_headers)["events"]))

    # TC-62-05 · AC1 (A1/Q1) — only coordinators, with a valid session.
    def test_only_coordinators_with_a_valid_session(self):
        for user in NON_COORDINATORS:
            with self.subTest(user=user):
                self.assert_error(self.load(as_user=user), 403)

        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["alice"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                self.assertEqual(self.load(headers=headers).status_code, 401)

        alice_headers = self.auth_headers(self.users["alice"])
        self.users["alice"].role = "organiser"
        self.db.session.commit()
        self.assert_error(self.load(headers=alice_headers), 403)


# ---------- AC2 and AC3: opening an event from the list ----------


class OpeningTests(ManagedEventsTestCase):
    def planning(self, event_id):
        return self.client.get(f"/api/events/{event_id}/planning",
                               headers=self.auth_headers(self.users["alice"]))

    # TC-62-06 · AC2, AC3 — a listed event opens with its status and coordinator.
    def test_a_listed_event_opens_with_its_status_and_coordinator(self):
        m2_id = next(e["id"] for e in self.listed()["events"] if e["title"] == "Alumni Mixer")

        response = self.planning(m2_id)

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        alice = self.users["alice"]
        self.assertEqual(body["title"], "Alumni Mixer")
        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["coordinator"], {"id": alice.id, "email": alice.email})

    # TC-62-07 · AC2 — every listed event can be opened.
    def test_every_listed_event_can_be_opened(self):
        for item in self.listed()["events"]:
            with self.subTest(event=item["id"]):
                response = self.planning(item["id"])
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(response.get_json()["status"], item["status"])


# ---------- AC4: empty state ----------


class EmptyStateTests(ManagedEventsTestCase):
    # TC-62-08 · AC4 — a coordinator with no events.
    def test_coordinator_with_no_events_gets_an_empty_state_message(self):
        body = self.listed("chloe")

        self.assertEqual(body["events"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())


# ---------- AC5: not recorded ----------


class NotRecordedTests(ManagedEventsTestCase):
    # TC-62-09 · AC5 (A5) — missing name and date are sent as not recorded.
    def test_blank_name_and_missing_date_are_null(self):
        m4 = self.by_key(self.listed()["events"])["M4"]

        self.assertIsNone(m4["title"])
        self.assertIsNone(m4["start_time"])
        self.assertEqual(m4["status"], "under_review")


# ---------- A7: loading fails ----------


class LoadFailureTests(ManagedEventsTestCase):
    # TC-62-10 · A7 — the coordinator is told and can retry.
    def test_load_failure_is_reported_and_retry_works(self):
        headers = self.auth_headers(self.users["alice"])
        session = self.db.session()
        with mock.patch.object(session, "execute",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.load(headers=headers)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"could not be loaded")
        self.assertRegex(body["error"].lower(), r"try again")

        self.assertEqual(set(self.keys(self.listed()["events"])), {"M1", "M2", "M3", "M4"})


if __name__ == "__main__":
    unittest.main()
