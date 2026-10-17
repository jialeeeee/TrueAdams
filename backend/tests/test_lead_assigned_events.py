"""Tests for SCRUM-83 "Event Coordinator Lead views the events they assigned".

Each test names the case it automates from
docs/test-cases/SCRUM-83-lead-assigned-events.md (TC-83-nn) and the acceptance
criteria it checks. Assumptions A1-A8 and questions Q1-Q6 are there.

Endpoint (JWT required, else 401; Event Coordinator Leads only, else 403)
    GET /api/events/supervised[?coordinator_id=<user id>]
        200 {"events": [event], "coordinators": [user], "message": str | null}
        400 {"error", "field": "coordinator_id"} if the filter is not a user ID
        503 {"error", "retryable": true} if loading fails
    event = {"id", "title", "start_time", "status", "coordinator": user}
            title and start_time are null when not recorded; start_time is
            Singapore time, as stored
    user  = {"id", "email"}; `coordinators` is always the unfiltered set, by email
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app.models import Event
from tests import seed_data
from tests.base import AppTestCase

# LS-SEED. Times are Singapore time. `coordinator` and `assigned_by` are user keys.
EVENTS = {
    "S1": ("Harbour Lights Festival", "submitted", "alice", "lena", datetime(2026, 12, 12, 17, 0)),
    "S2": ("Alumni Mixer", "approved", "ben", "lena", datetime(2026, 11, 20, 18, 30)),
    "S3": ("Charity Fun Run", "under_review", "alice", "lena", datetime(2026, 11, 5, 7, 0)),
    "S4": ("Year-End Showcase", "confirmed", "ben", "lena", datetime(2026, 11, 30, 19, 0)),
    "S5": ("   ", "submitted", "alice", "lena", None),
    "S6": ("Winter Networking Night", "cancelled", "alice", "lena", datetime(2026, 10, 1, 9, 0)),
    "S7": ("Startup Expo", "rejected", "ben", "lena", datetime(2026, 11, 15, 10, 0)),
    "S8": ("Spring Workshop", "completed", "chloe", "lena", datetime(2026, 9, 10, 14, 0)),
    "S9": ("Draft Workshop", "draft", "alice", "lena", datetime(2027, 1, 15, 10, 0)),
    "S10": ("Product Launch", "submitted", "ben", "liam", datetime(2026, 11, 20, 14, 0)),
    "S11": ("Tech Summit 2026", "submitted", "chloe", "admin", datetime(2026, 11, 10, 9, 0)),
    "S12": ("Legacy Forum", "submitted", "alice", None, datetime(2026, 11, 25, 9, 0)),
}

LENAS_ACTIVE_EVENTS = ["S3", "S2", "S4", "S1", "S5"]
NON_LEADS = ["admin", "alice", "dana", "farah", "gus", "hana"]
# "²" passes str.isdigit() but is not a number int() accepts.
INVALID_FILTERS = ["abc", "1.5", "-3", "true", "²"]


class LeadAssignedEventsTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS + seed_data.LEADS)
        self.events = {}
        for key, (title, status, coordinator, assigned_by, start) in EVENTS.items():
            self.events[key] = Event(
                title=title,
                status=status,
                organiser_id=self.users["dana"].id,
                coordinator_id=self.users[coordinator].id,
                coordinator_assigned_at=datetime(2026, 9, 1, 10, 0),
                coordinator_assigned_by_id=self.users[assigned_by].id if assigned_by else None,
                start_time=start,
                end_time=start + timedelta(hours=2) if start else None,
            )
        self._insert(Event, list(self.events.values()))

    # ---------- Requests ----------

    def load(self, as_user="lena", headers=None, **query):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get("/api/events/supervised", headers=headers, query_string=query)

    def listed(self, as_user="lena", headers=None, **query):
        response = self.load(as_user, headers, **query)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def keys(self, items):
        """Seed keys of the listed events, in order. Every listed row must be a seed row:
        the Leads are new in each run, so no real event can have been assigned by them."""
        by_id = {event.id: key for key, event in self.events.items()}
        return [by_id[item["id"]] for item in items]

    def by_key(self, items):
        return dict(zip(self.keys(items), items))

    def summary(self, user_key):
        user = self.users[user_key]
        return {"id": user.id, "email": user.email}

    # ---------- Assertions ----------

    def assert_no_event_data(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        self.assertNotIn("events", body)
        self.assertNotIn("coordinators", body)
        text = response.get_data(as_text=True)
        for event in self.events.values():
            if event.title.strip():
                self.assertNotIn(event.title, text)
        return body


# ---------- AC1: the Lead's list and filter ----------


class AssignedListTests(LeadAssignedEventsTestCase):
    # TC-83-01 · AC1 — the Lead sees the active events they assigned.
    def test_lead_sees_the_active_events_they_assigned(self):
        body = self.listed()

        self.assertCountEqual(self.keys(body["events"]), LENAS_ACTIVE_EVENTS)
        self.assertIsNone(body["message"])

    # TC-83-02 · AC1 — each event shows its coordinator, status and date.
    def test_each_event_shows_its_coordinator_status_and_date(self):
        by_key = self.by_key(self.listed()["events"])

        self.assertEqual(by_key["S1"], {
            "id": self.events["S1"].id, "title": "Harbour Lights Festival",
            "start_time": "2026-12-12T17:00:00", "status": "submitted",
            "coordinator": self.summary("alice"),
        })
        self.assertEqual(
            {key: (item["status"], item["coordinator"]) for key, item in by_key.items()},
            {
                "S1": ("submitted", self.summary("alice")),
                "S2": ("approved", self.summary("ben")),
                "S3": ("under_review", self.summary("alice")),
                "S4": ("confirmed", self.summary("ben")),
                "S5": ("submitted", self.summary("alice")),
            },
        )
        self.assertEqual(by_key["S2"]["start_time"], "2026-11-20T18:30:00")

    # TC-83-03 · AC1 (A3/Q2) — inactive events are not listed.
    def test_inactive_events_are_not_listed(self):
        listed = set(self.keys(self.listed()["events"]))

        for key in ["S6", "S7", "S8", "S9"]:
            with self.subTest(event=key, status=self.events[key].status):
                self.assertNotIn(key, listed)

    # TC-83-04 · AC1 (A5/Q4) — soonest date first, undated last.
    def test_events_are_listed_soonest_first_with_undated_last(self):
        self.assertEqual(self.keys(self.listed()["events"]), LENAS_ACTIVE_EVENTS)

    # TC-83-05 · AC1 (A5) — missing name and date are sent as not recorded.
    def test_blank_name_and_missing_date_are_null(self):
        s5 = self.by_key(self.listed()["events"])["S5"]

        self.assertIsNone(s5["title"])
        self.assertIsNone(s5["start_time"])
        self.assertEqual(s5["status"], "submitted")

    # TC-83-06 · AC1 (A6) — filtering by coordinator.
    def test_filter_by_coordinator(self):
        alice = self.listed(coordinator_id=self.users["alice"].id)
        ben = self.listed(coordinator_id=self.users["ben"].id)
        everyone = self.listed(coordinator_id="")

        self.assertEqual(self.keys(alice["events"]), ["S3", "S1", "S5"])
        self.assertIsNone(alice["message"])
        self.assertEqual(self.keys(ben["events"]), ["S2", "S4"])
        self.assertEqual(self.keys(everyone["events"]), LENAS_ACTIVE_EVENTS)

    # TC-83-07 · AC1 (A6) — the filter offers the coordinators of the Lead's events.
    def test_coordinator_options_are_the_coordinators_of_the_listed_events(self):
        expected = [self.summary("alice"), self.summary("ben")]

        self.assertEqual(self.listed()["coordinators"], expected)
        self.assertEqual(
            self.listed(coordinator_id=self.users["ben"].id)["coordinators"], expected
        )

    # TC-83-08 · AC1 (A6) — a coordinator with none of the Lead's active events.
    def test_filter_by_a_coordinator_with_none_of_the_leads_events_is_empty(self):
        body = self.listed(coordinator_id=self.users["chloe"].id)

        self.assertEqual(body["events"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())

    # TC-83-09 · AC1 (A6) — a filter that is not a user ID is refused.
    def test_invalid_coordinator_filter_is_refused(self):
        for value in INVALID_FILTERS:
            with self.subTest(coordinator_id=value):
                body = self.assert_no_event_data(self.load(coordinator_id=value), 400)
                self.assertEqual(body.get("field"), "coordinator_id")

    # TC-83-10 · AC1 — a Lead who has assigned nothing.
    def test_lead_with_no_assigned_events_gets_an_empty_state_message(self):
        body = self.listed("lucy")

        self.assertEqual(body["events"], [])
        self.assertEqual(body["coordinators"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())


# ---------- AC2: other Leads' events ----------


class OtherAssignersTests(LeadAssignedEventsTestCase):
    # TC-83-11 · AC2 (A1/Q1) — events assigned by anyone else are not listed.
    def test_events_assigned_by_other_leads_or_admins_are_not_listed(self):
        lenas = set(self.keys(self.listed()["events"]))

        for key in ["S10", "S11", "S12"]:
            with self.subTest(event=key):
                self.assertNotIn(key, lenas)
        self.assertEqual(self.keys(self.listed("liam")["events"]), ["S10"])

    # TC-83-12 · AC2 — filtering never reveals another Lead's events.
    def test_filtering_never_reveals_another_leads_events(self):
        lena_ben = self.listed(coordinator_id=self.users["ben"].id)
        liam_alice = self.listed("liam", coordinator_id=self.users["alice"].id)

        self.assertEqual(self.keys(lena_ben["events"]), ["S2", "S4"])
        self.assertEqual(liam_alice["events"], [])
        self.assertEqual(liam_alice["coordinators"], [self.summary("ben")])

    # TC-83-13 · AC2 (A1/Q1) — reassignment by someone else (since SCRUM-82, another
    # Lead) moves the event out.
    def test_reassignment_by_someone_else_removes_the_event_from_the_leads_list(self):
        lena_headers = self.auth_headers(self.users["lena"])

        response = self.client.put(
            f"/api/events/{self.events['S1'].id}/coordinator",
            headers=self.auth_headers(self.users["liam"]),
            json={"coordinator_id": self.users["chloe"].id},
        )
        self.assertEqual(response.status_code, 200, response.get_json())

        self.assertEqual(
            self.keys(self.listed(headers=lena_headers)["events"]), ["S3", "S2", "S4", "S5"]
        )


# ---------- AC3: only the Lead ----------


class AccessTests(LeadAssignedEventsTestCase):
    # TC-83-14 · AC3 (A4/Q3) — every other role is denied and sees no event data.
    def test_only_leads_can_open_the_view(self):
        for user in NON_LEADS:
            with self.subTest(user=user):
                self.assert_no_event_data(self.load(as_user=user), 403)
            with self.subTest(user=user, filter="invalid"):
                self.assert_no_event_data(self.load(as_user=user, coordinator_id="abc"), 403)

    # TC-83-15 · AC3 — a valid session is required.
    def test_a_valid_session_is_required(self):
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

    # TC-83-16 · AC3 — a Lead whose role changes is denied at once.
    def test_lead_whose_role_changes_is_denied_at_once(self):
        lena_headers = self.auth_headers(self.users["lena"])
        self.users["lena"].role = "coordinator"
        self.db.session.commit()

        self.assert_no_event_data(self.load(headers=lena_headers), 403)


# ---------- AC4: loading fails ----------


class LoadFailureTests(LeadAssignedEventsTestCase):
    # TC-83-17 · AC4 (A7) — the Lead is told, no partial list is sent, and retry works.
    def test_load_failure_is_reported_without_a_partial_list_and_retry_works(self):
        headers = self.auth_headers(self.users["lena"])
        session = self.db.session()
        with mock.patch.object(session, "execute",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.load(headers=headers)

        body = self.assert_no_event_data(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"could not be loaded")
        self.assertRegex(body["error"].lower(), r"try again")

        self.assertEqual(self.keys(self.listed(headers=headers)["events"]), LENAS_ACTIVE_EVENTS)


if __name__ == "__main__":
    unittest.main()
