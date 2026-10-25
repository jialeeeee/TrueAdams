"""Tests for SCRUM-72 "Event Coordinator views registration information".

Each test names the case it automates from
docs/test-cases/SCRUM-72-coordinator-view-registration-information.md (TC-72-nn) and the
acceptance criteria it checks. Assumptions A1-A8 and questions Q1-Q3 are there.

Endpoints (JWT required, else 401)
    GET /api/events/managed/registrations          coordinators only, else 403
        200 {"events": [event], "message": str | null}
        event = {"id", "title", "start_time", "status",
                 "registration": {"capacity", "registered_count", "slots_remaining"}}
    GET /api/events/<id>/registration-overview     404 unknown; the event's coordinator only, else 403
        200 {"event": {"id", "title", "start_time", "end_time", "status",
                       "expected_attendance", "venue": {"name", "capacity"} | null},
             "registration": {"capacity", "registered_count", "slots_remaining",
                              "withdrawn_count", "cancelled_count", "opens_at", "closes_at"},
             "message": str | null}
    both: 503 {"error", "retryable": true} if loading fails, with no partial data
"""

import re
import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app.models import Event, Registration
from tests import seed_data
from tests.base import AppTestCase

# CR-SEED. Event times are Singapore time. `coordinator` refers to a seed_data.USERS key;
# every event is organised by dana. Only C1 is at the venue (Harbour Hall, 120 people).
EVENTS = {
    "C1": {"title": "Alumni Mixer", "coordinator": "alice", "status": "approved",
           "start_time": datetime(2026, 11, 20, 18, 30), "end_time": datetime(2026, 11, 20, 21, 0),
           "expected_attendance": 60, "registration_required": True, "registration_capacity": 50,
           "registration_opens_at": datetime(2026, 10, 1, 9, 0),
           "registration_closes_at": datetime(2026, 11, 15, 18, 0)},
    "C2": {"title": "Harbour Lights Festival", "coordinator": "alice", "status": "approved",
           "start_time": datetime(2026, 12, 12, 17, 0), "end_time": datetime(2026, 12, 12, 22, 0),
           "expected_attendance": 2, "registration_required": True, "registration_capacity": 2,
           "registration_opens_at": datetime(2026, 10, 1, 9, 0),
           "registration_closes_at": datetime(2026, 12, 10, 18, 0)},
    "C3": {"title": "Winter Networking Night", "coordinator": "alice", "status": "submitted",
           "start_time": datetime(2026, 11, 1, 9, 0), "end_time": datetime(2026, 11, 1, 11, 0),
           "expected_attendance": None, "registration_required": True,
           "registration_capacity": None},
    "C4": {"title": "Product Launch", "coordinator": "ben", "status": "approved",
           "start_time": datetime(2026, 11, 20, 14, 0), "end_time": datetime(2026, 11, 20, 16, 0),
           "expected_attendance": 30, "registration_required": True, "registration_capacity": 30,
           "registration_opens_at": datetime(2026, 10, 1, 9, 0),
           "registration_closes_at": datetime(2026, 11, 18, 18, 0)},
    "C5": {"title": "Tech Summit 2026", "coordinator": None, "status": "submitted",
           "start_time": datetime(2026, 11, 10, 9, 0), "end_time": datetime(2026, 11, 10, 17, 0),
           "expected_attendance": 100, "registration_required": True,
           "registration_capacity": None},
}

# Registrations: (event, attendee, status). Attendees are the test's own att1-att3, or
# farah from seed_data.USERS.
REGISTRATIONS = {
    "G1": ("C1", "att1", "registered"),
    "G2": ("C1", "farah", "registered"),
    "G3": ("C1", "att2", "withdrawn"),
    "G4": ("C1", "att3", "cancelled"),
    "G5": ("C2", "att1", "registered"),
    "G6": ("C2", "att3", "registered"),
    "G7": ("C4", "att2", "registered"),
}

# Every role but coordinator, including the events' organiser (dana) and a Lead (lena).
NON_COORDINATORS = ["admin", "dana", "farah", "gus", "hana", "lena"]


class CoordinatorRegistrationsTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS + seed_data.LEADS)
        for key in ("att1", "att2", "att3"):
            self.users[key] = self.make_user(role="attendee")
        self.venue = self.make_venue(name="Harbour Hall", capacity=120)

        self.events = {}
        for key, row in EVENTS.items():
            coordinator = self.users[row["coordinator"]] if row["coordinator"] else None
            self.events[key] = Event(
                organiser_id=self.users["dana"].id,
                coordinator_id=coordinator.id if coordinator else None,
                coordinator_assigned_at=datetime(2026, 9, 1, 10, 0) if coordinator else None,
                venue_id=self.venue.id if key == "C1" else None,
                **{k: v for k, v in row.items() if k != "coordinator"},
            )
        self._insert(Event, list(self.events.values()))

        self.registrations = {
            key: Registration(event_id=self.events[event].id,
                              attendee_id=self.users[attendee].id, status=status)
            for key, (event, attendee, status) in REGISTRATIONS.items()
        }
        self._insert(Registration, list(self.registrations.values()))

    # ---------- Requests ----------

    def load_list(self, as_user="alice", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get("/api/events/managed/registrations", headers=headers)

    def listed(self, as_user="alice", headers=None):
        response = self.load_list(as_user, headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def load_overview(self, event_id, as_user="alice", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get(f"/api/events/{event_id}/registration-overview", headers=headers)

    def overview(self, event_key, as_user="alice"):
        response = self.load_overview(self.events[event_key].id, as_user)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def event_keys(self, items):
        """Seed keys of the listed events, in order; rows from real data are skipped."""
        by_id = {event.id: key for key, event in self.events.items()}
        return [by_id[item["id"]] for item in items if item["id"] in by_id]

    def by_key(self, items):
        by_id = {event.id: key for key, event in self.events.items()}
        return {by_id[item["id"]]: item for item in items if item["id"] in by_id}

    def failing_registration_queries(self):
        """Make every query that reads the registrations table fail, and nothing else."""
        session = self.db.session()
        original = session.execute
        reads_registrations = re.compile(r"\bregistrations\b")

        def execute(statement, *args, **kwargs):
            if reads_registrations.search(str(statement)):
                raise SQLAlchemyError("simulated outage")
            return original(statement, *args, **kwargs)

        return mock.patch.object(session, "execute", side_effect=execute)

    # ---------- Assertions ----------

    def assert_refused(self, response, status_code):
        """An error with a message and nothing about any seeded event."""
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        for key in ("events", "event", "registration"):
            self.assertNotIn(key, body)
        text = response.get_data(as_text=True)
        for row in EVENTS.values():
            self.assertNotIn(row["title"], text)
        return body


# ---------- AC1: the coordinator's events with their registration summary ----------


class ManagedRegistrationsListTests(CoordinatorRegistrationsTestCase):
    # TC-72-01 · AC1, AC3 (A1/Q1, A2/Q2) — the coordinator's assigned events only.
    def test_coordinator_sees_only_the_events_assigned_to_them(self):
        body = self.listed()

        self.assertEqual(set(self.event_keys(body["events"])), {"C1", "C2", "C3"})
        self.assertIsNone(body["message"])

    # TC-72-02 · AC1 (A3) — each event shows its registration summary.
    def test_each_event_shows_its_registration_summary(self):
        by_key = self.by_key(self.listed()["events"])

        self.assertEqual(by_key["C1"], {
            "id": self.events["C1"].id, "title": "Alumni Mixer",
            "start_time": "2026-11-20T18:30:00", "status": "approved",
            "registration": {"capacity": 50, "registered_count": 2, "slots_remaining": 48},
        })
        self.assertEqual(by_key["C2"]["registration"],
                         {"capacity": 2, "registered_count": 2, "slots_remaining": 0})
        self.assertEqual(by_key["C3"]["registration"],
                         {"capacity": None, "registered_count": 0, "slots_remaining": None})

    # TC-72-03 · AC1 (A6) — soonest proposed date first.
    def test_events_are_listed_soonest_first(self):
        self.assertEqual(self.event_keys(self.listed()["events"]), ["C3", "C1", "C2"])


# ---------- AC2: the registration details needed for coordination ----------


class OverviewTests(CoordinatorRegistrationsTestCase):
    # TC-72-04 · AC2 (A4/Q3) — opening an event shows its coordination figures.
    def test_opening_an_event_shows_its_coordination_figures(self):
        c1_id = next(e["id"] for e in self.listed()["events"] if e["title"] == "Alumni Mixer")

        response = self.load_overview(c1_id)

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json(), {
            "event": {
                "id": c1_id, "title": "Alumni Mixer",
                "start_time": "2026-11-20T18:30:00", "end_time": "2026-11-20T21:00:00",
                "status": "approved", "expected_attendance": 60,
                "venue": {"name": "Harbour Hall", "capacity": 120},
            },
            "registration": {
                "capacity": 50, "registered_count": 2, "slots_remaining": 48,
                "withdrawn_count": 1, "cancelled_count": 1,
                "opens_at": "2026-10-01T09:00:00", "closes_at": "2026-11-15T18:00:00",
            },
            "message": None,
        })

    # TC-72-05 · AC2 (A4/Q3) — attendees' identities are not shown to the coordinator.
    def test_attendee_identities_are_not_shown(self):
        response = self.load_overview(self.events["C1"].id)

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertNotIn("registrations", response.get_json())
        text = response.get_data(as_text=True)
        self.assertNotIn("attendee", text)
        for key in ("att1", "att2", "att3", "farah"):
            self.assertNotIn(self.users[key].email, text)


# ---------- AC3: only the coordinator's assigned events ----------


class AssignedEventsOnlyTests(CoordinatorRegistrationsTestCase):
    # TC-72-06 · AC3, AC4 (A1) — reassignment moves the information immediately. Since
    # SCRUM-82 only a Lead reassigns.
    def test_reassignment_moves_the_registration_information_immediately(self):
        alice_headers = self.auth_headers(self.users["alice"])
        ben_headers = self.auth_headers(self.users["ben"])
        c1_id = self.events["C1"].id

        response = self.client.put(
            f"/api/events/{c1_id}/coordinator",
            headers=self.auth_headers(self.users["lena"]),
            json={"coordinator_id": self.users["ben"].id},
        )
        self.assertEqual(response.status_code, 200, response.get_json())

        self.assertNotIn("C1", self.event_keys(self.listed(headers=alice_headers)["events"]))
        self.assert_refused(self.load_overview(c1_id, headers=alice_headers), 403)
        self.assertIn("C1", self.event_keys(self.listed(headers=ben_headers)["events"]))
        self.assertEqual(self.load_overview(c1_id, headers=ben_headers).status_code, 200)

    # TC-72-07 · AC3 (A1/Q1) — only coordinators, with a valid session, on every request.
    def test_only_coordinators_with_a_valid_session_have_the_list(self):
        for user in NON_COORDINATORS:
            with self.subTest(user=user):
                self.assert_refused(self.load_list(as_user=user), 403)

        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["alice"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                self.assertEqual(self.load_list(headers=headers).status_code, 401)

        alice_headers = self.auth_headers(self.users["alice"])
        self.users["alice"].role = "organiser"
        self.db.session.commit()
        self.assert_refused(self.load_list(headers=alice_headers), 403)


# ---------- AC4: access denied for events not assigned to the coordinator ----------


class AccessDeniedTests(CoordinatorRegistrationsTestCase):
    # TC-72-08 · AC4 (A7) — another coordinator's or an unassigned event is refused.
    def test_an_event_not_assigned_to_the_coordinator_is_refused_with_a_message(self):
        for key in ("C4", "C5"):
            with self.subTest(event=key):
                body = self.assert_refused(self.load_overview(self.events[key].id), 403)
                self.assertRegex(body["error"],
                                 r"only view registration information for events assigned to you")

    # TC-72-09 · AC4 (A1/Q1) — other roles are refused, the organiser and a Lead too.
    def test_other_roles_are_refused_an_events_overview(self):
        for user in NON_COORDINATORS:
            with self.subTest(user=user):
                self.assert_refused(self.load_overview(self.events["C1"].id, as_user=user), 403)

    # TC-72-10 · AC4 (A7) — unknown event is 404; a session is required.
    def test_unknown_event_is_not_found_and_a_session_is_required(self):
        body = self.assert_refused(self.load_overview(self.missing_id(Event)), 404)
        self.assertEqual(body["error"], "Event not found.")

        response = self.load_overview(self.events["C1"].id, headers={})
        self.assertEqual(response.status_code, 401)


# ---------- AC5: no registrations ----------


class EmptyStateTests(CoordinatorRegistrationsTestCase):
    # TC-72-11 · AC5 (A5) — an event with no registrations says so.
    def test_event_with_no_registrations_says_there_are_none(self):
        body = self.overview("C3")

        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())
        self.assertEqual(body["event"]["title"], "Winter Networking Night")
        self.assertEqual(body["registration"], {
            "capacity": None, "registered_count": 0, "slots_remaining": None,
            "withdrawn_count": 0, "cancelled_count": 0, "opens_at": None, "closes_at": None,
        })

    # TC-72-12 · AC5 — a coordinator with no events.
    def test_coordinator_with_no_events_gets_an_empty_state_message(self):
        body = self.listed("chloe")

        self.assertEqual(body["events"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())


# ---------- AC6: loading fails ----------


class LoadFailureTests(CoordinatorRegistrationsTestCase):
    def assert_retryable_failure(self, response):
        body = self.assert_refused(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"could not be loaded")
        self.assertRegex(body["error"].lower(), r"try again")

    # TC-72-13 · AC6 (A8) — the list fails as a whole and can be retried.
    def test_list_load_failure_returns_no_partial_data_and_retry_works(self):
        headers = self.auth_headers(self.users["alice"])
        session = self.db.session()
        with mock.patch.object(session, "execute",
                               side_effect=SQLAlchemyError("simulated outage")):
            everything_failed = self.load_list(headers=headers)
        self.assert_retryable_failure(everything_failed)

        # The events load, but their registration counts do not.
        with self.failing_registration_queries():
            counts_failed = self.load_list(headers=headers)
        self.assert_retryable_failure(counts_failed)

        self.assertEqual(set(self.event_keys(self.listed()["events"])), {"C1", "C2", "C3"})

    # TC-72-14 · AC6 (A8) — the overview fails as a whole and can be retried.
    def test_overview_load_failure_returns_no_partial_data_and_retry_works(self):
        headers = self.auth_headers(self.users["alice"])
        c1_id = self.events["C1"].id
        # The event loads, but its registration counts do not.
        with self.failing_registration_queries():
            response = self.load_overview(c1_id, headers=headers)
        self.assert_retryable_failure(response)

        self.assertEqual(self.overview("C1")["registration"]["registered_count"], 2)


if __name__ == "__main__":
    unittest.main()
