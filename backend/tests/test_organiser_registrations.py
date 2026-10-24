"""Tests for SCRUM-54 "Event Organiser views registration information".

Each test names the case it automates from
docs/test-cases/SCRUM-54-view-registration-information.md (TC-54-nn) and the
acceptance criteria it checks. Assumptions A1-A9 and questions Q1-Q5 are there.

Endpoints (JWT required, else 401)
    GET /api/events/organised                  organisers only, else 403
        200 {"events": [event], "message": str | null}
    GET /api/events/<id>/registrations         404 unknown; the event's organiser only, else 403
        200 {"event": event, "registrations": [registration], "message": str | null}
    both: 503 {"error", "retryable": true} if loading fails, with no partial data
    event = {"id", "title", "start_time", "status",
             "registration": {"capacity", "registered_count", "slots_remaining"}}
    registration = {"id", "attendee": {"id", "email"}, "registered_at", "status"}
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

# RI-SEED. Event times are Singapore time. `organiser` refers to a seed_data.USERS key.
EVENTS = {
    "R1": {"title": "Alumni Mixer", "organiser": "dana", "status": "approved",
           "start_time": datetime(2026, 11, 20, 18, 30), "end_time": datetime(2026, 11, 20, 21, 0),
           "registration_required": True, "registration_capacity": 50},
    "R2": {"title": "Harbour Lights Festival", "organiser": "dana", "status": "approved",
           "start_time": datetime(2026, 12, 12, 17, 0), "end_time": datetime(2026, 12, 12, 22, 0),
           "registration_required": True, "registration_capacity": 2},
    "R3": {"title": "Winter Networking Night", "organiser": "dana", "status": "submitted",
           "start_time": datetime(2026, 11, 1, 9, 0), "end_time": datetime(2026, 11, 1, 11, 0),
           "registration_required": True, "registration_capacity": None},
    "R4": {"title": "Spring Gala (draft)", "organiser": "dana", "status": "draft",
           "start_time": datetime(2027, 3, 1, 18, 0), "end_time": datetime(2027, 3, 1, 22, 0),
           "registration_required": None, "registration_capacity": None},
    "R5": {"title": "Product Launch", "organiser": "evan", "status": "approved",
           "start_time": datetime(2026, 11, 20, 14, 0), "end_time": datetime(2026, 11, 20, 16, 0),
           "registration_required": True, "registration_capacity": 30},
}

# Registrations: (event, attendee, registered_at in UTC, status). Attendees are the
# test's own att1-att3, or farah from seed_data.USERS.
REGISTRATIONS = {
    "G1": ("R1", "att1", datetime(2026, 10, 1, 3, 0), "registered"),
    "G2": ("R1", "farah", datetime(2026, 10, 2, 1, 0), "registered"),
    "G3": ("R1", "att2", datetime(2026, 10, 3, 5, 30), "withdrawn"),
    "G4": ("R2", "att1", datetime(2026, 10, 4, 2, 0), "registered"),
    "G5": ("R2", "att3", datetime(2026, 10, 4, 6, 0), "registered"),
    "G6": ("R5", "att2", datetime(2026, 10, 5, 8, 0), "registered"),
}

NON_ORGANISERS = ["admin", "alice", "farah", "gus", "hana"]


class OrganiserRegistrationsTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        for key in ("att1", "att2", "att3"):
            self.users[key] = self.make_user(role="attendee")

        self.events = {
            key: Event(organiser_id=self.users[row["organiser"]].id,
                       **{k: v for k, v in row.items() if k != "organiser"})
            for key, row in EVENTS.items()
        }
        # alice coordinates R1, to show a coordinator is not its organiser (TC-54-09).
        self.events["R1"].coordinator_id = self.users["alice"].id
        self._insert(Event, list(self.events.values()))

        self.registrations = {
            key: Registration(event_id=self.events[event].id,
                              attendee_id=self.users[attendee].id,
                              registered_at=registered_at, status=status)
            for key, (event, attendee, registered_at, status) in REGISTRATIONS.items()
        }
        self._insert(Registration, list(self.registrations.values()))

    # ---------- Requests ----------

    def load_list(self, as_user="dana", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get("/api/events/organised", headers=headers)

    def listed(self, as_user="dana", headers=None):
        response = self.load_list(as_user, headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def load_details(self, event_id, as_user="dana", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get(f"/api/events/{event_id}/registrations", headers=headers)

    def details(self, event_key, as_user="dana"):
        response = self.load_details(self.events[event_key].id, as_user)
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
        """An error with a message and nothing about any seeded event or attendee."""
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        for key in ("events", "event", "registrations"):
            self.assertNotIn(key, body)
        text = response.get_data(as_text=True)
        for event in self.events.values():
            self.assertNotIn(event.title, text)
        for key in ("att1", "att2", "att3", "farah"):
            self.assertNotIn(self.users[key].email, text)
        return body


# ---------- AC1: the organiser's events with their registration summary ----------


class OrganisedListTests(OrganiserRegistrationsTestCase):
    # TC-54-01 · AC1, AC3 (A2/Q1) — the organiser's events, not drafts or others'.
    def test_organiser_sees_their_non_draft_events_only(self):
        body = self.listed()

        self.assertEqual(set(self.event_keys(body["events"])), {"R1", "R2", "R3"})
        self.assertIsNone(body["message"])

    # TC-54-02 · AC1 (A3/Q2) — each event shows its registration summary.
    def test_each_event_shows_its_registration_summary(self):
        by_key = self.by_key(self.listed()["events"])

        self.assertEqual(by_key["R1"], {
            "id": self.events["R1"].id, "title": "Alumni Mixer",
            "start_time": "2026-11-20T18:30:00", "status": "approved",
            "registration": {"capacity": 50, "registered_count": 2, "slots_remaining": 48},
        })
        self.assertEqual(by_key["R2"]["registration"],
                         {"capacity": 2, "registered_count": 2, "slots_remaining": 0})
        self.assertEqual(by_key["R3"]["registration"],
                         {"capacity": None, "registered_count": 0, "slots_remaining": None})

    # TC-54-03 · AC1 (A7) — soonest proposed date first.
    def test_events_are_listed_soonest_first(self):
        self.assertEqual(self.event_keys(self.listed()["events"]), ["R3", "R1", "R2"])


# ---------- AC2: an event's registration details ----------


class RegistrationDetailsTests(OrganiserRegistrationsTestCase):
    # TC-54-04 · AC2 (A4/Q3, A5/Q4) — opening an event lists each registration.
    def test_opening_an_event_lists_each_registration(self):
        r1_id = next(e["id"] for e in self.listed()["events"] if e["title"] == "Alumni Mixer")

        response = self.load_details(r1_id)

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        att1, farah, att2 = self.users["att1"], self.users["farah"], self.users["att2"]
        self.assertEqual(body["registrations"], [
            {"id": self.registrations["G1"].id,
             "attendee": {"id": att1.id, "email": att1.email},
             "registered_at": "2026-10-01T03:00:00", "status": "registered"},
            {"id": self.registrations["G2"].id,
             "attendee": {"id": farah.id, "email": farah.email},
             "registered_at": "2026-10-02T01:00:00", "status": "registered"},
            {"id": self.registrations["G3"].id,
             "attendee": {"id": att2.id, "email": att2.email},
             "registered_at": "2026-10-03T05:30:00", "status": "withdrawn"},
        ])
        self.assertIsNone(body["message"])

    # TC-54-05 · AC2 — the details repeat the event's summary.
    def test_details_show_the_events_summary(self):
        body = self.details("R1")

        self.assertEqual(body["event"], {
            "id": self.events["R1"].id, "title": "Alumni Mixer",
            "start_time": "2026-11-20T18:30:00", "status": "approved",
            "registration": {"capacity": 50, "registered_count": 2, "slots_remaining": 48},
        })


# ---------- AC3: only the organiser's own events ----------


class OwnEventsOnlyTests(OrganiserRegistrationsTestCase):
    # TC-54-06 · AC3 — another organiser's events and attendees never appear.
    def test_other_organisers_events_and_attendees_are_not_visible(self):
        responses = [self.load_list()] + [
            self.load_details(self.events[key].id) for key in ("R1", "R2", "R3")
        ]
        for response in responses:
            with self.subTest(url=response.request.path):
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertNotIn("Product Launch", response.get_data(as_text=True))
        shown_registration_ids = {r["id"] for key in ("R1", "R2", "R3")
                                  for r in self.details(key)["registrations"]}
        self.assertNotIn(self.registrations["G6"].id, shown_registration_ids)

        self.assertEqual(self.event_keys(self.listed("evan")["events"]), ["R5"])

    # TC-54-07 · AC3 (A1/Q5) — only organisers, with a valid session, on every request.
    def test_only_organisers_with_a_valid_session_have_the_list(self):
        for user in NON_ORGANISERS:
            with self.subTest(user=user):
                self.assert_refused(self.load_list(as_user=user), 403)

        ghost = self.make_user(role="organiser")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["dana"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                self.assertEqual(self.load_list(headers=headers).status_code, 401)

        dana_headers = self.auth_headers(self.users["dana"])
        self.users["dana"].role = "attendee"
        self.db.session.commit()
        self.assert_refused(self.load_list(headers=dana_headers), 403)


# ---------- AC4: access denied for events the organiser doesn't manage ----------


class AccessDeniedTests(OrganiserRegistrationsTestCase):
    # TC-54-08 · AC4 (A8) — another organiser's event is refused with a message.
    def test_another_organisers_event_is_refused_with_a_message(self):
        body = self.assert_refused(self.load_details(self.events["R5"].id), 403)

        self.assertRegex(body["error"], r"only view registration information for events you")

    # TC-54-09 · AC4 (A1/Q5) — non-organisers are refused, the event's coordinator too.
    def test_non_organisers_are_refused_an_events_registrations(self):
        for user in NON_ORGANISERS:
            with self.subTest(user=user):
                self.assert_refused(self.load_details(self.events["R1"].id, as_user=user), 403)

    # TC-54-10 · AC4 (A8) — unknown event is 404; a session is required.
    def test_unknown_event_is_not_found_and_a_session_is_required(self):
        body = self.assert_refused(self.load_details(self.missing_id(Event)), 404)
        self.assertEqual(body["error"], "Event not found.")

        response = self.load_details(self.events["R1"].id, headers={})
        self.assertEqual(response.status_code, 401)


# ---------- AC5: no registrations ----------


class EmptyStateTests(OrganiserRegistrationsTestCase):
    # TC-54-11 · AC5 — an event with no registrations says so.
    def test_event_with_no_registrations_says_there_are_none(self):
        body = self.details("R3")

        self.assertEqual(body["registrations"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())
        self.assertEqual(body["event"]["title"], "Winter Networking Night")
        self.assertEqual(body["event"]["registration"]["registered_count"], 0)

    # TC-54-12 · AC5 — an organiser with no events.
    def test_organiser_with_no_events_gets_an_empty_state_message(self):
        newcomer = self.make_user(role="organiser")

        response = self.load_list(headers=self.auth_headers(newcomer))

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["events"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())


# ---------- AC6: loading fails ----------


class LoadFailureTests(OrganiserRegistrationsTestCase):
    def assert_retryable_failure(self, response):
        body = self.assert_refused(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"could not be loaded")
        self.assertRegex(body["error"].lower(), r"try again")

    # TC-54-13 · AC6 (A9) — the list fails as a whole and can be retried.
    def test_list_load_failure_returns_no_partial_data_and_retry_works(self):
        headers = self.auth_headers(self.users["dana"])
        session = self.db.session()
        with mock.patch.object(session, "execute",
                               side_effect=SQLAlchemyError("simulated outage")):
            everything_failed = self.load_list(headers=headers)
        self.assert_retryable_failure(everything_failed)

        # The events load, but their registration counts do not.
        with self.failing_registration_queries():
            counts_failed = self.load_list(headers=headers)
        self.assert_retryable_failure(counts_failed)

        self.assertEqual(set(self.event_keys(self.listed()["events"])), {"R1", "R2", "R3"})

    # TC-54-14 · AC6 (A9) — the details fail as a whole and can be retried.
    def test_details_load_failure_returns_no_partial_data_and_retry_works(self):
        headers = self.auth_headers(self.users["dana"])
        r1_id = self.events["R1"].id
        # The event loads, but its registrations do not.
        with self.failing_registration_queries():
            response = self.load_details(r1_id, headers=headers)
        self.assert_retryable_failure(response)

        self.assertEqual(len(self.details("R1")["registrations"]), 3)


if __name__ == "__main__":
    unittest.main()
