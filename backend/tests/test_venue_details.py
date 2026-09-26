"""Tests for the "View Venue Details" user story.

Model (all new columns nullable, with no defaults; NULL means "not recorded")
    Venue.description             Text
    Venue.area_sqm                Integer
    Venue.facilities              JSON list of str
    Venue.accessibility_features  JSON list of str
    Venue.room_layouts            JSON list of str
    Venue.operating_hours         Text
    Venue.contact_email           String
    Venue.contact_phone           String
    Venue.parking_spaces          Integer
    Venue.catering_available      Boolean

Endpoints (JWT required, else 401; caller's role not in VIEWER_ROLES -> 403)
    GET /api/venues/
        200 {"venues": [summary, ...], "message": str | null}
            summary = {"id", "name", "location", "capacity", "is_available"}
            Sorted by name. `message` is the empty-state text when there are no venues.
    GET /api/venues/<id>
        200 {"id", "name", "is_available", <every DETAIL_FIELDS key>, "not_recorded": [...]}
            A field that was never recorded (NULL, or a blank string) comes back as
            null and its name is listed in `not_recorded`, in DETAIL_FIELDS order.
            Recorded absences ([], false, 0) are returned as-is and not listed.
        404 unknown venue
    Either endpoint -> 503 {"error": str, "retryable": true} if the database fails.
    Other errors are {"error": "<message shown to the user>"}.
"""

import sqlite3
import unittest
from contextlib import contextmanager

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app.models import Venue
from tests.base import AppTestCase
from tests.fixtures import venue_data
from tests.fixtures.venue_data import DETAIL_FIELDS

VIEWER_ROLES = ("coordinator", "venue_staff")


class VenueTestCase(AppTestCase):
    """Seeds the shared fixture data and wraps the venue endpoints."""

    def setUp(self):
        super().setUp()
        self.users = {
            row["key"]: self.make_user(email=row["email"], role=row["role"])
            for row in venue_data.USERS
        }
        self.venues = {}

    # ---------- Seeding ----------

    def seed_venues(self, rows=venue_data.VENUES):
        for row in rows:
            fields = {k: v for k, v in row.items() if k != "key"}
            venue = Venue(**fields)
            self.db.session.add(venue)
            self.db.session.commit()
            self.venues[row["key"]] = venue
        return self.venues

    # ---------- Requests ----------

    def list_venues(self, as_user=None):
        as_user = as_user or self.users["coordinator"]
        return self.client.get("/api/venues/", headers=self.auth_headers(as_user))

    def get_venue(self, venue_id, as_user=None):
        as_user = as_user or self.users["coordinator"]
        return self.client.get(f"/api/venues/{venue_id}", headers=self.auth_headers(as_user))

    def details(self, key):
        response = self.get_venue(self.venues[key].id)
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    @contextmanager
    def database_unavailable(self):
        """Make every SQL statement fail, as a dropped Supabase connection would."""

        def fail(conn, cursor, statement, parameters, context, executemany):
            raise OperationalError(
                statement, parameters, sqlite3.OperationalError("simulated database outage")
            )

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            yield
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

    def get_during_outage(self, url):
        # Build the token first: reading the user's id is itself a query.
        headers = self.auth_headers(self.users["coordinator"])
        # Tests share the request's session; start the request cold, as in production.
        self.db.session.expire_all()
        with self.database_unavailable():
            return self.client.get(url, headers=headers)

    def venue_url(self, key):
        return f"/api/venues/{self.venues[key].id}"

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


class VenueModelTests(VenueTestCase):
    def test_planning_fields_default_to_not_recorded(self):
        venue = Venue(name="Bare Venue")
        self.db.session.add(venue)
        self.db.session.commit()

        for field in DETAIL_FIELDS:
            with self.subTest(field=field):
                self.assertIsNone(getattr(venue, field))

    def test_planning_columns_are_nullable(self):
        for field in DETAIL_FIELDS:
            with self.subTest(field=field):
                self.assertTrue(Venue.__table__.c[field].nullable)

    def test_list_fields_round_trip_through_the_database(self):
        self.seed_venues([venue_data.AURORA_BALLROOM])
        self.db.session.expire_all()
        venue = self.db.session.get(Venue, self.venues["fully_recorded"].id)

        self.assertEqual(venue.facilities, venue_data.AURORA_BALLROOM["facilities"])
        self.assertEqual(venue.room_layouts, venue_data.AURORA_BALLROOM["room_layouts"])

    def test_recorded_absences_are_stored_distinctly_from_not_recorded(self):
        self.seed_venues([venue_data.CIVIC_HALL])
        self.db.session.expire_all()
        venue = self.db.session.get(Venue, self.venues["recorded_as_none"].id)

        self.assertEqual(venue.facilities, [])
        self.assertIs(venue.catering_available, False)
        self.assertEqual(venue.parking_spaces, 0)


class BrowseVenuesTests(VenueTestCase):
    def setUp(self):
        super().setUp()
        self.seed_venues()

    def test_authorised_roles_can_browse_venues(self):
        for role in VIEWER_ROLES:
            with self.subTest(role=role):
                response = self.list_venues(self.users[role])

                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.get_json()["venues"]), len(venue_data.VENUES))

    def test_other_roles_cannot_browse_venues(self):
        for key in ("organiser", "attendee", "tech_staff"):
            with self.subTest(role=key):
                self.assert_error(self.list_venues(self.users[key]), 403)

    def test_browsing_requires_authentication(self):
        self.assertEqual(self.client.get("/api/venues/").status_code, 401)

    def test_token_for_a_deleted_user_is_rejected(self):
        ghost = self.make_user(role="coordinator")
        headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()

        for url in ("/api/venues/", f"/api/venues/{self.venues['fully_recorded'].id}"):
            with self.subTest(url=url):
                self.assert_error(self.client.get(url, headers=headers), 401)

    def test_lists_every_recorded_venue_including_unavailable_ones(self):
        body = self.list_venues().get_json()

        self.assertEqual(
            {v["id"] for v in body["venues"]}, {v.id for v in self.venues.values()}
        )
        self.assertIsNone(body["message"])

    def test_venues_are_sorted_by_name(self):
        names = [v["name"] for v in self.list_venues().get_json()["venues"]]

        self.assertEqual(names, sorted(row["name"] for row in venue_data.VENUES))

    def test_summary_contains_the_fields_needed_to_pick_a_venue(self):
        venue = self.venues["fully_recorded"]
        body = self.list_venues().get_json()

        summary = next(v for v in body["venues"] if v["id"] == venue.id)
        self.assertEqual(
            summary,
            {
                "id": venue.id,
                "name": "Aurora Ballroom",
                "location": "Level 3, Marina Tower, 10 Bayfront Ave",
                "capacity": 400,
                "is_available": True,
            },
        )

    def test_summary_reports_availability(self):
        body = self.list_venues().get_json()

        summary = next(v for v in body["venues"] if v["id"] == self.venues["unavailable"].id)
        self.assertIs(summary["is_available"], False)

    def test_summary_leaves_unrecorded_values_empty_rather_than_guessing(self):
        body = self.list_venues().get_json()
        by_id = {v["id"]: v for v in body["venues"]}

        self.assertIsNone(by_id[self.venues["partially_recorded"].id]["capacity"])
        self.assertIsNone(by_id[self.venues["blank_values"].id]["location"])

    def test_every_listed_venue_can_be_opened(self):
        for summary in self.list_venues().get_json()["venues"]:
            with self.subTest(venue=summary["name"]):
                response = self.get_venue(summary["id"])

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["name"], summary["name"])


class EmptyVenueListTests(VenueTestCase):
    def test_shows_an_empty_state_message_when_no_venues_are_recorded(self):
        response = self.list_venues()

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["venues"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())

    def test_empty_state_is_the_same_for_every_authorised_role(self):
        for role in VIEWER_ROLES:
            with self.subTest(role=role):
                body = self.list_venues(self.users[role]).get_json()

                self.assertEqual(body["venues"], [])
                self.assertTrue(body["message"].strip())


class VenueDetailTests(VenueTestCase):
    def setUp(self):
        super().setUp()
        self.seed_venues()

    def test_authorised_roles_can_open_venue_details(self):
        venue = self.venues["fully_recorded"]

        for role in VIEWER_ROLES:
            with self.subTest(role=role):
                response = self.get_venue(venue.id, self.users[role])

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["id"], venue.id)

    def test_other_roles_cannot_open_venue_details(self):
        venue = self.venues["fully_recorded"]

        for key in ("organiser", "attendee", "tech_staff"):
            with self.subTest(role=key):
                self.assert_error(self.get_venue(venue.id, self.users[key]), 403)

    def test_opening_details_requires_authentication(self):
        response = self.client.get(f"/api/venues/{self.venues['fully_recorded'].id}")

        self.assertEqual(response.status_code, 401)

    def test_unknown_venue_returns_not_found(self):
        self.assert_error(self.get_venue(9999), 404)

    def test_fully_recorded_venue_shows_every_planning_characteristic(self):
        body = self.details("fully_recorded")
        expected = {k: v for k, v in venue_data.AURORA_BALLROOM.items() if k != "key"}

        self.assertEqual(
            body,
            {"id": self.venues["fully_recorded"].id, **expected, "not_recorded": []},
        )

    def test_details_always_include_every_planning_field(self):
        for key in self.venues:
            with self.subTest(venue=key):
                body = self.details(key)

                for field in ["id", "name", "is_available", "not_recorded", *DETAIL_FIELDS]:
                    self.assertIn(field, body)

    def test_list_fields_keep_their_recorded_order(self):
        body = self.details("fully_recorded")

        self.assertEqual(body["room_layouts"], ["theatre", "banquet", "cabaret", "cocktail"])
        self.assertEqual(
            body["accessibility_features"],
            ["Wheelchair ramp", "Accessible toilets", "Hearing loop"],
        )

    def test_unavailable_venue_details_can_still_be_opened(self):
        body = self.details("unavailable")

        self.assertIs(body["is_available"], False)
        self.assertEqual(body["room_layouts"], ["classroom", "boardroom"])


class NotRecordedInformationTests(VenueTestCase):
    """Missing information must never look like a confirmed capability."""

    def setUp(self):
        super().setUp()
        self.seed_venues()

    def test_unrecorded_fields_are_null_and_listed_as_not_recorded(self):
        body = self.details("partially_recorded")
        missing = [f for f in DETAIL_FIELDS if venue_data.BAYFRONT_PAVILION[f] is None]

        self.assertEqual(body["not_recorded"], missing)
        for field in missing:
            with self.subTest(field=field):
                self.assertIsNone(body[field])

    def test_recorded_fields_on_a_partial_venue_are_still_shown(self):
        body = self.details("partially_recorded")

        self.assertEqual(body["location"], "Bayfront Park, East Lawn")
        self.assertEqual(body["facilities"], ["Covered stage"])
        self.assertNotIn("location", body["not_recorded"])
        self.assertNotIn("facilities", body["not_recorded"])

    def test_unrecorded_values_are_not_presented_as_false_zero_or_empty(self):
        body = self.details("partially_recorded")

        self.assertIsNot(body["catering_available"], False)
        self.assertNotEqual(body["capacity"], 0)
        self.assertNotEqual(body["parking_spaces"], 0)
        self.assertNotEqual(body["accessibility_features"], [])
        self.assertNotEqual(body["room_layouts"], [])

    def test_recorded_absences_are_confirmed_not_missing(self):
        body = self.details("recorded_as_none")

        self.assertEqual(body["facilities"], [])
        self.assertEqual(body["accessibility_features"], [])
        self.assertIs(body["catering_available"], False)
        self.assertEqual(body["parking_spaces"], 0)
        self.assertEqual(body["not_recorded"], [])

    def test_blank_text_is_treated_as_not_recorded(self):
        body = self.details("blank_values")

        for field in ("description", "location", "operating_hours", "contact_email"):
            with self.subTest(field=field):
                self.assertIsNone(body[field])
                self.assertIn(field, body["not_recorded"])

    def test_not_recorded_lists_fields_in_a_stable_order(self):
        body = self.details("blank_values")
        missing = [
            "description", "location", "area_sqm", "accessibility_features",
            "operating_hours", "contact_email", "contact_phone",
            "parking_spaces", "catering_available",
        ]

        self.assertEqual(body["not_recorded"], missing)

    def test_every_field_can_be_reported_as_not_recorded(self):
        venue = Venue(name="Placeholder Venue")
        self.db.session.add(venue)
        self.db.session.commit()

        body = self.get_venue(venue.id).get_json()

        self.assertEqual(body["not_recorded"], DETAIL_FIELDS)
        self.assertEqual(body["name"], "Placeholder Venue")

    def test_not_recorded_is_empty_when_everything_is_recorded(self):
        self.assertEqual(self.details("fully_recorded")["not_recorded"], [])


class VenueLoadFailureTests(VenueTestCase):
    """The user is told what went wrong and can retry once the database is back."""

    def setUp(self):
        super().setUp()
        self.seed_venues()

    def test_list_failure_informs_the_user_and_offers_retry(self):
        response = self.get_during_outage("/api/venues/")

        self.assert_retryable_error(response)

    def test_list_failure_is_not_shown_as_an_empty_venue_list(self):
        body = self.get_during_outage("/api/venues/").get_json()

        self.assertNotIn("venues", body)

    def test_detail_failure_informs_the_user_and_offers_retry(self):
        response = self.get_during_outage(self.venue_url("fully_recorded"))

        self.assert_retryable_error(response)

    def test_detail_failure_is_not_reported_as_venue_not_found(self):
        response = self.get_during_outage(self.venue_url("fully_recorded"))

        self.assertNotEqual(response.status_code, 404)

    def test_retrying_the_list_succeeds_once_the_database_recovers(self):
        self.get_during_outage("/api/venues/")

        response = self.list_venues()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["venues"]), len(venue_data.VENUES))

    def test_retrying_details_succeeds_once_the_database_recovers(self):
        url = self.venue_url("fully_recorded")
        self.get_during_outage(url)

        response = self.client.get(url, headers=self.auth_headers(self.users["coordinator"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["name"], "Aurora Ballroom")


if __name__ == "__main__":
    unittest.main()
