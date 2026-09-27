"""Tests for the "View Event Planning Information" user story.

Endpoint (JWT required, else 401; unknown event -> 404)
    GET /api/events/<id>/planning
        200 {"id", <every PLANNING_FIELDS key>, "not_recorded": [...]}
            organiser, coordinator      {"id", "email"}
            venue                       {"id", "name", "location"} | null
            start_time, end_time,
            coordinator_assigned_at,
            created_at                  ISO 8601, as stored (naive, no conversion)
            A field that was never recorded (NULL, or blank text) comes back as null
            and its name is listed in `not_recorded`, in PLANNING_FIELDS order.
        403 caller is not the event's current coordinator
        503 {"error": str, "retryable": true} if the database fails, including when
            only part of the information (e.g. the venue) cannot be loaded.
    Other errors are {"error": "<message shown to the user>"}.

Authorisation
    Only the event's current coordinator (Event.coordinator_id) may view, and only
    while their role is still "coordinator". This is read from the database on every
    request, so a reassignment or role change applies to tokens already issued.
    Every field is returned whether or not the coordinator may edit it.

Each test inserts the users and events in tests/seed_data.py, plus the events
below, into the public tables and rolls them back afterwards.
"""

import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta

import psycopg2
from flask_jwt_extended import create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app.models import Event
from tests import seed_data
from tests.base import AppTestCase

# Every field on the planning view, in display order.
PLANNING_FIELDS = [
    "title",
    "description",
    "status",
    "start_time",
    "end_time",
    "venue",
    "organiser",
    "coordinator",
    "coordinator_assigned_at",
    "created_at",
]

# Fields a coordinator cannot edit in the current design, which must still be shown.
NOT_EDITABLE_BY_COORDINATOR = [
    "title", "status", "organiser", "coordinator", "coordinator_assigned_at", "created_at",
]

# Roles that are not coordinators, keyed to their seed users.
NON_COORDINATOR_USERS = {
    "admin": "admin",
    "organiser (the event's own)": "dana",
    "organiser (another event's)": "evan",
    "attendee": "farah",
    "venue_staff": "gus",
    "tech_staff": "hana",
}

FESTIVAL_DESCRIPTION = "Waterfront lantern festival with live music and food stalls."


class PlanningTestCase(AppTestCase):
    """Inserts this test's users, venue and events, and wraps the planning endpoint.

    Alice coordinates the festival, the Charity Gala, the staff retreat and the
    cancelled winter night. Ben coordinates the Product Launch. Chloe coordinates
    nothing. The Tech Summit has no coordinator.
    """

    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.events = self.seed_events(seed_data.EVENTS, self.users)
        venue_row = next(v for v in seed_data.VENUES if v["key"] == "fully_recorded")
        self.venue = self.seed_venues([venue_row])["fully_recorded"]

        alice = self.users["alice"]
        self.events["festival"] = self.make_event(  # Every planning field recorded.
            organiser=self.users["dana"],
            title="Harbour Lights Festival",
            status="submitted",
            venue=self.venue,
            start_time=datetime(2026, 12, 12, 17, 0),
            duration=timedelta(hours=5),
            description=FESTIVAL_DESCRIPTION,
            coordinator_id=alice.id,
            coordinator_assigned_at=datetime(2026, 9, 10, 9, 30),
            created_at=datetime(2026, 9, 5, 14, 0),
        )
        self.events["retreat"] = self.make_event(  # Description typed in as blanks.
            organiser=self.users["evan"],
            title="Staff Retreat",
            status="submitted",
            description="   ",
            coordinator_id=alice.id,
            coordinator_assigned_at=datetime(2026, 9, 12, 11, 0),
        )
        self.events["winter_cancelled"] = self.make_event(  # Cancelled after assignment.
            organiser=self.users["dana"],
            title="Winter Networking Night",
            status="cancelled",
            coordinator_id=alice.id,
            coordinator_assigned_at=datetime(2026, 9, 3, 16, 0),
        )

    # ---------- Requests ----------

    def url(self, key):
        return f"/api/events/{self.events[key].id}/planning"

    def get_planning(self, key, as_user=None, headers=None):
        headers = headers or self.auth_headers(as_user or self.users["alice"])
        return self.client.get(self.url(key), headers=headers)

    def planning(self, key, as_user=None):
        response = self.get_planning(key, as_user)
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def reload(self, key):
        self.db.session.expire_all()
        return self.db.session.get(Event, self.events[key].id)

    def event_state(self, key):
        event = self.reload(key)
        return {column.name: getattr(event, column.name) for column in Event.__table__.columns}

    @contextmanager
    def database_unavailable(self, table=None):
        """Make queries fail, as a dropped Supabase connection would.

        With `table`, only queries reading that table fail. Savepoint statements
        still run so the test's own transaction survives.
        """

        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith(("SAVEPOINT", "ROLLBACK", "RELEASE")):
                return
            if table and table not in statement.lower():
                return
            raise OperationalError(
                statement, parameters, psycopg2.OperationalError("simulated database outage")
            )

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            yield
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

    def get_during_outage(self, key, table=None):
        # Build the token and URL first: reading an expired row's id is itself a query.
        headers = self.auth_headers(self.users["alice"])
        url = self.url(key)
        # Tests share the request's session; start the request cold, as in production.
        self.db.session.expire_all()
        with self.database_unavailable(table):
            return self.client.get(url, headers=headers)

    # ---------- Assertions ----------

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code)
        body = response.get_json()
        self.assertIsInstance(body, dict)
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip(), "error message should not be blank")

    def assert_retryable_error(self, response):
        self.assert_error(response, 503)
        self.assertIs(response.get_json().get("retryable"), True)

    def assert_no_event_details(self, response, key):
        """Nothing about the event leaks into an error response."""
        body = response.get_json()
        self.assertIsInstance(body, dict)
        self.assertFalse(set(PLANNING_FIELDS + ["id", "not_recorded"]) & body.keys())
        text = response.get_data(as_text=True)
        event = self.events[key]
        for secret in (event.title, event.description, self.users["alice"].email,
                       self.users["dana"].email, self.venue.name):
            if secret and secret.strip():
                self.assertNotIn(secret, text)

    def assert_denied(self, response, key):
        self.assert_error(response, 403)
        self.assert_no_event_details(response, key)


# ---------- AC1: The coordinator can view events they are authorised to manage ----------


class ViewPlanningInformationTests(PlanningTestCase):
    def test_assigned_coordinator_sees_the_events_planning_information(self):
        dana, alice = self.users["dana"], self.users["alice"]

        body = self.planning("festival")

        self.assertEqual(
            body,
            {
                "id": self.events["festival"].id,
                "title": "Harbour Lights Festival",
                "description": FESTIVAL_DESCRIPTION,
                "status": "submitted",
                "start_time": "2026-12-12T17:00:00",
                "end_time": "2026-12-12T22:00:00",
                "venue": {
                    "id": self.venue.id,
                    "name": "Aurora Ballroom",
                    "location": "Level 3, Marina Tower, 10 Bayfront Ave",
                },
                "organiser": {"id": dana.id, "email": dana.email},
                "coordinator": {"id": alice.id, "email": alice.email},
                "coordinator_assigned_at": "2026-09-10T09:30:00",
                "created_at": "2026-09-05T14:00:00",
                "not_recorded": [],
            },
        )

    def test_coordinator_can_view_every_event_they_manage(self):
        for key in ("festival", "assigned", "retreat", "winter_cancelled"):
            with self.subTest(event=key):
                body = self.planning(key)

                self.assertEqual(body["id"], self.events[key].id)
                self.assertEqual(body["title"], self.events[key].title)

    def test_each_coordinator_sees_their_own_event(self):
        body = self.planning("evans_event", as_user=self.users["ben"])

        self.assertEqual(body["title"], "Product Launch")
        self.assertEqual(body["coordinator"]["id"], self.users["ben"].id)

    def test_cancelled_event_remains_viewable_by_its_coordinator(self):
        body = self.planning("winter_cancelled")

        self.assertEqual(body["status"], "cancelled")

    def test_unknown_event_returns_not_found(self):
        response = self.client.get(
            f"/api/events/{self.missing_id(Event)}/planning",
            headers=self.auth_headers(self.users["alice"]),
        )

        self.assert_error(response, 404)

    def test_viewing_requires_authentication(self):
        self.assertEqual(self.client.get(self.url("festival")).status_code, 401)

    def test_expired_token_is_rejected(self):
        token = create_access_token(
            identity=str(self.users["alice"].id), expires_delta=timedelta(seconds=-1)
        )

        response = self.get_planning("festival", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("Harbour Lights Festival", response.get_data(as_text=True))

    def test_token_for_a_deleted_user_is_rejected(self):
        ghost = self.make_user(role="coordinator")
        headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()

        self.assert_error(self.get_planning("festival", headers=headers), 401)

    def test_viewing_does_not_change_the_event(self):
        before = self.event_state("festival")

        self.planning("festival")

        self.assertEqual(self.event_state("festival"), before)


# ---------- AC2: All recorded planning fields are displayed ----------


class PlanningFieldsTests(PlanningTestCase):
    def test_every_planning_field_is_always_present(self):
        for key in ("festival", "assigned", "retreat", "winter_cancelled"):
            with self.subTest(event=key):
                body = self.planning(key)

                for field in ["id", "not_recorded", *PLANNING_FIELDS]:
                    self.assertIn(field, body)

    def test_fields_the_coordinator_cannot_edit_are_still_shown(self):
        body = self.planning("festival")

        for field in NOT_EDITABLE_BY_COORDINATOR:
            with self.subTest(field=field):
                self.assertIsNotNone(body[field])
        self.assertEqual(body["organiser"]["email"], self.users["dana"].email)
        self.assertEqual(body["status"], "submitted")
        self.assertEqual(body["created_at"], "2026-09-05T14:00:00")

    def test_venue_is_shown_by_name_and_location_not_just_an_id(self):
        venue = self.planning("festival")["venue"]

        self.assertEqual(venue["name"], "Aurora Ballroom")
        self.assertEqual(venue["location"], "Level 3, Marina Tower, 10 Bayfront Ave")

    def test_dates_and_times_are_shown_exactly_as_recorded(self):
        body = self.planning("festival")

        self.assertEqual(body["start_time"], "2026-12-12T17:00:00")
        self.assertEqual(body["end_time"], "2026-12-12T22:00:00")

    def test_unrecorded_fields_are_null_and_listed_as_not_recorded(self):
        body = self.planning("assigned")  # Charity Gala: no description, no venue.

        self.assertEqual(body["not_recorded"], ["description", "venue"])
        self.assertIsNone(body["description"])
        self.assertIsNone(body["venue"])

    def test_recorded_fields_on_a_partly_recorded_event_are_still_shown(self):
        body = self.planning("assigned")

        self.assertEqual(body["title"], "Charity Gala")
        self.assertEqual(body["start_time"], "2026-12-05T18:00:00")
        self.assertEqual(body["organiser"]["id"], self.users["dana"].id)
        self.assertNotIn("title", body["not_recorded"])

    def test_blank_text_is_treated_as_not_recorded(self):
        body = self.planning("retreat")

        self.assertIsNone(body["description"])
        self.assertIn("description", body["not_recorded"])

    def test_not_recorded_is_empty_when_everything_is_recorded(self):
        self.assertEqual(self.planning("festival")["not_recorded"], [])

    def test_saved_changes_are_shown_the_next_time_the_event_is_viewed(self):
        self.planning("festival")
        event = self.reload("festival")
        event.description = "Now with a drone light show."
        event.venue_id = None
        event.start_time = datetime(2026, 12, 12, 18, 0)
        self.db.session.commit()
        self.db.session.expire_all()

        body = self.planning("festival")

        self.assertEqual(body["description"], "Now with a drone light show.")
        self.assertIsNone(body["venue"])
        self.assertEqual(body["not_recorded"], ["venue"])
        self.assertEqual(body["start_time"], "2026-12-12T18:00:00")


# ---------- AC3: Load failures are reported, and the coordinator can retry ----------


class PlanningLoadFailureTests(PlanningTestCase):
    def test_failure_informs_the_coordinator_and_offers_retry(self):
        self.assert_retryable_error(self.get_during_outage("festival"))

    def test_failure_does_not_return_any_event_information(self):
        response = self.get_during_outage("festival")

        self.assert_no_event_details(response, "festival")

    def test_failure_is_not_reported_as_not_found_or_not_allowed(self):
        response = self.get_during_outage("festival")

        self.assertNotIn(response.status_code, (401, 403, 404))

    def test_venue_load_failure_is_not_shown_as_venue_not_recorded(self):
        response = self.get_during_outage("festival", table="venues")

        self.assert_retryable_error(response)
        self.assert_no_event_details(response, "festival")

    def test_retrying_succeeds_once_the_database_recovers(self):
        self.get_during_outage("festival")

        body = self.planning("festival")

        self.assertEqual(body["title"], "Harbour Lights Festival")
        self.assertEqual(body["venue"]["name"], "Aurora Ballroom")


# ---------- AC4: Coordinators without authorisation cannot view ----------


class PlanningAuthorisationTests(PlanningTestCase):
    def test_coordinator_of_another_event_is_refused(self):
        response = self.get_planning("festival", as_user=self.users["ben"])

        self.assert_denied(response, "festival")

    def test_coordinator_with_no_events_is_refused(self):
        response = self.get_planning("festival", as_user=self.users["chloe"])

        self.assert_denied(response, "festival")

    def test_no_coordinator_can_view_an_unassigned_event(self):
        for key in ("alice", "ben", "chloe"):
            with self.subTest(coordinator=key):
                response = self.get_planning("unassigned", as_user=self.users[key])

                self.assert_denied(response, "unassigned")

    def test_reassignment_moves_access_to_the_new_coordinator(self):
        alice_headers = self.auth_headers(self.users["alice"])
        ben_headers = self.auth_headers(self.users["ben"])
        self.assertEqual(self.get_planning("festival", headers=alice_headers).status_code, 200)

        event = self.reload("festival")
        event.coordinator_id = self.users["ben"].id
        self.db.session.commit()
        self.db.session.expire_all()

        self.assert_denied(self.get_planning("festival", headers=alice_headers), "festival")
        self.assertEqual(self.get_planning("festival", headers=ben_headers).status_code, 200)

    def test_coordinator_who_changes_role_loses_access_with_an_existing_token(self):
        headers = self.auth_headers(self.users["alice"])
        self.assertEqual(self.get_planning("festival", headers=headers).status_code, 200)

        self.users["alice"].role = "organiser"
        self.db.session.commit()
        self.db.session.expire_all()

        self.assert_denied(self.get_planning("festival", headers=headers), "festival")

    def test_users_who_are_not_coordinators_are_refused(self):
        for label, key in NON_COORDINATOR_USERS.items():
            with self.subTest(user=label):
                response = self.get_planning("festival", as_user=self.users[key])

                self.assert_denied(response, "festival")

    def test_refusal_does_not_change_the_event(self):
        before = self.event_state("festival")

        self.get_planning("festival", as_user=self.users["ben"])

        self.assertEqual(self.event_state("festival"), before)


if __name__ == "__main__":
    unittest.main()
