"""Tests for the "Update Event Planning Information (Normal Fields)" user story.

Endpoint (JWT required, else 401; unknown event -> 404)
    PATCH /api/events/<id>   body: a JSON object of the fields to change
        200 {"message", <the same body as GET /api/events/<id>/planning>}
        400 body is not a JSON object
        403 caller is not the event's current coordinator (checked before the body)
        409 the event is cancelled
        422 {"error", "fields": {<field>: <what to correct>}} for invalid values,
            fields that can't be changed here, or an empty body. Nothing is saved.
        503 {"error", "retryable": true} if the database fails. Nothing is saved.

Editing rules
    Normal fields: title (required, 1-255 characters) and description (optional,
    up to 5,000 characters; null or blank clears it). Surrounding spaces are removed.
    Important fields (venue_id, start_time, end_time) are never saved here; SCRUM-52
    decides what the coordinator is told. Every other field can't be changed here.

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

FESTIVAL_DESCRIPTION = "Waterfront lantern festival with live music and food stalls."
NEW_DESCRIPTION = "Now with a drone light show."

IMPORTANT_CHANGES = {
    "venue_id": None,  # Set in setUp to the id of a different venue.
    "start_time": "2026-12-12T18:00:00",
    "end_time": "2026-12-12T23:00:00",
}

SYSTEM_FIELD_CHANGES = {
    "colour": "blue",
    "status": "approved",
    "organiser_id": 1,
    "coordinator_id": 1,
    "coordinator_assigned_at": "2026-09-20T10:00:00",
    "created_at": "2026-01-01T00:00:00",
    "id": 1,
}

NON_COORDINATOR_USERS = {
    "admin": "admin",
    "organiser (the event's own)": "dana",
    "organiser (another event's)": "evan",
    "attendee": "farah",
    "venue_staff": "gus",
    "tech_staff": "hana",
}


class UpdatePlanningTestCase(AppTestCase):
    """Inserts this test's users, venues and events, and wraps the edit endpoint.

    Alice coordinates the festival, the Charity Gala and the cancelled winter night.
    Ben coordinates the Product Launch. Chloe coordinates nothing. The Tech Summit
    has no coordinator.
    """

    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.events = self.seed_events(seed_data.EVENTS, self.users)
        venue_rows = [v for v in seed_data.VENUES
                      if v["key"] in ("fully_recorded", "partially_recorded")]
        self.venues = self.seed_venues(venue_rows)

        alice = self.users["alice"]
        self.events["festival"] = self.make_event(
            organiser=self.users["dana"],
            title="Harbour Lights Festival",
            status="submitted",
            venue=self.venues["fully_recorded"],
            start_time=datetime(2026, 12, 12, 17, 0),
            duration=timedelta(hours=5),
            description=FESTIVAL_DESCRIPTION,
            coordinator_id=alice.id,
            coordinator_assigned_at=datetime(2026, 9, 10, 9, 30),
            created_at=datetime(2026, 9, 5, 14, 0),
        )
        self.events["winter_cancelled"] = self.make_event(
            organiser=self.users["dana"],
            title="Winter Networking Night",
            status="cancelled",
            coordinator_id=alice.id,
            coordinator_assigned_at=datetime(2026, 9, 3, 16, 0),
        )

    # ---------- Requests ----------

    def url(self, key):
        return f"/api/events/{self.events[key].id}"

    def patch(self, key, body, as_user=None, headers=None):
        headers = headers or self.auth_headers(as_user or self.users["alice"])
        return self.client.patch(self.url(key), json=body, headers=headers)

    def save(self, key, body, as_user=None):
        response = self.patch(key, body, as_user)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def view(self, key):
        response = self.client.get(
            f"{self.url(key)}/planning", headers=self.auth_headers(self.users["alice"])
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def reload(self, key):
        self.db.session.expire_all()
        return self.db.session.get(Event, self.events[key].id)

    def event_state(self, key):
        event = self.reload(key)
        return {column.name: getattr(event, column.name) for column in Event.__table__.columns}

    @contextmanager
    def database_failing(self, only=None):
        """Make queries fail, as a dropped Supabase connection would.

        With `only` (e.g. "UPDATE"), only statements starting with it fail. Savepoint
        statements still run so the test's own transaction survives.
        """

        def fail(conn, cursor, statement, parameters, context, executemany):
            sql = statement.lstrip().upper()
            if sql.startswith(("SAVEPOINT", "ROLLBACK", "RELEASE")):
                return
            if only and not sql.startswith(only):
                return
            raise OperationalError(
                statement, parameters, psycopg2.OperationalError("simulated database outage")
            )

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            yield
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

    def patch_during_outage(self, key, body, only=None):
        # Build the token and URL first: reading an expired row's id is itself a query.
        headers = self.auth_headers(self.users["alice"])
        url = self.url(key)
        self.db.session.expire_all()
        with self.database_failing(only):
            return self.client.patch(url, json=body, headers=headers)

    # ---------- Assertions ----------

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_data(as_text=True))
        body = response.get_json()
        self.assertIsInstance(body, dict)
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip(), "error message should not be blank")
        return body

    def assert_needs_correction(self, response, *fields):
        body = self.assert_error(response, 422)
        self.assertIsInstance(body.get("fields"), dict)
        for field in fields:
            self.assertIsInstance(body["fields"].get(field), str, f"{field} not identified")
            self.assertTrue(body["fields"][field].strip())
        return body

    def assert_no_event_details(self, response, key):
        body = response.get_json()
        self.assertIsInstance(body, dict)
        self.assertFalse({"id", "title", "description", "venue", "not_recorded"} & body.keys())
        text = response.get_data(as_text=True)
        event = self.events[key]
        for secret in (event.title, event.description, self.users["dana"].email):
            if secret and secret.strip():
                self.assertNotIn(secret, text)

    def assert_denied(self, response, key):
        self.assert_error(response, 403)
        self.assert_no_event_details(response, key)

    @contextmanager
    def assert_unchanged(self, key):
        before = self.event_state(key)
        yield
        self.assertEqual(self.event_state(key), before)


# ---------- AC1: The coordinator can edit normal fields ----------


class EditNormalFieldsTests(UpdatePlanningTestCase):
    def test_coordinator_can_update_the_description(self):
        body = self.save("festival", {"description": NEW_DESCRIPTION})

        self.assertEqual(body["description"], NEW_DESCRIPTION)
        self.assertIsInstance(body.get("message"), str)
        self.assertEqual(self.reload("festival").description, NEW_DESCRIPTION)

    def test_coordinator_can_update_the_title(self):
        body = self.save("festival", {"title": "Harbour Lights Festival 2026"})

        self.assertEqual(body["title"], "Harbour Lights Festival 2026")
        self.assertEqual(self.reload("festival").title, "Harbour Lights Festival 2026")

    def test_title_and_description_can_be_updated_together(self):
        self.save("festival", {"title": "Harbour Lights", "description": NEW_DESCRIPTION})

        event = self.reload("festival")
        self.assertEqual(event.title, "Harbour Lights")
        self.assertEqual(event.description, NEW_DESCRIPTION)

    def test_only_the_submitted_fields_change(self):
        before = self.event_state("festival")

        self.save("festival", {"description": NEW_DESCRIPTION})

        after = self.event_state("festival")
        changed = {name for name in before if before[name] != after[name]}
        self.assertEqual(changed, {"description"})

    def test_a_description_that_was_not_recorded_can_be_added(self):
        body = self.save("assigned", {"description": "Black-tie dinner and auction."})

        self.assertEqual(body["description"], "Black-tie dinner and auction.")
        self.assertNotIn("description", body["not_recorded"])

    def test_description_can_be_cleared(self):
        for cleared in (None, "", "   "):
            with self.subTest(description=cleared):
                body = self.save("festival", {"description": cleared})

                self.assertIsNone(body["description"])
                self.assertIn("description", body["not_recorded"])
                self.assertIsNone(self.reload("festival").description)
                self.save("festival", {"description": FESTIVAL_DESCRIPTION})

    def test_surrounding_spaces_are_removed(self):
        self.save("festival", {"title": "  Harbour Lights  ", "description": "  Lanterns.  "})

        event = self.reload("festival")
        self.assertEqual(event.title, "Harbour Lights")
        self.assertEqual(event.description, "Lanterns.")

    def test_saving_an_unchanged_value_is_allowed(self):
        with self.assert_unchanged("festival"):
            self.save("festival", {"title": "Harbour Lights Festival"})


# ---------- AC2: Saved changes update the event and remain visible ----------


class SavedChangesTests(UpdatePlanningTestCase):
    def test_response_shows_the_event_as_saved(self):
        body = self.save("festival", {"description": NEW_DESCRIPTION})

        self.assertEqual({k: v for k, v in body.items() if k != "message"}, self.view("festival"))

    def test_changes_remain_visible_when_the_event_is_reopened(self):
        self.save("festival", {"title": "Harbour Lights", "description": NEW_DESCRIPTION})
        self.db.session.expire_all()

        body = self.view("festival")

        self.assertEqual(body["title"], "Harbour Lights")
        self.assertEqual(body["description"], NEW_DESCRIPTION)

    def test_other_events_are_not_changed(self):
        with self.assert_unchanged("assigned"):
            self.save("festival", {"description": NEW_DESCRIPTION})


# ---------- AC3: Invalid entries prevent saving and identify corrections ----------


class ValidationTests(UpdatePlanningTestCase):
    def test_blank_title_is_rejected(self):
        for title in ("", "   ", None):
            with self.subTest(title=title), self.assert_unchanged("festival"):
                self.assert_needs_correction(self.patch("festival", {"title": title}), "title")

    def test_title_length_limit(self):
        with self.assert_unchanged("festival"):
            self.assert_needs_correction(self.patch("festival", {"title": "T" * 256}), "title")

        self.save("festival", {"title": "T" * 255})
        self.assertEqual(self.reload("festival").title, "T" * 255)

    def test_description_length_limit(self):
        with self.assert_unchanged("festival"):
            response = self.patch("festival", {"description": "D" * 5001})
            self.assert_needs_correction(response, "description")

        self.save("festival", {"description": "D" * 5000})
        self.assertEqual(self.reload("festival").description, "D" * 5000)

    def test_values_that_are_not_text_are_rejected(self):
        cases = [("title", 123), ("title", True), ("title", ["a"]),
                 ("description", 42), ("description", {"a": 1})]
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assert_unchanged("festival"):
                self.assert_needs_correction(self.patch("festival", {field: value}), field)

    def test_one_invalid_field_prevents_saving_the_others(self):
        with self.assert_unchanged("festival"):
            response = self.patch("festival", {"title": "", "description": NEW_DESCRIPTION})

            body = self.assert_needs_correction(response, "title")
            self.assertNotIn("description", body["fields"])

    def test_every_invalid_field_is_identified(self):
        with self.assert_unchanged("festival"):
            response = self.patch("festival", {"title": " ", "description": "D" * 5001})

            self.assert_needs_correction(response, "title", "description")

    def test_empty_save_is_rejected(self):
        with self.assert_unchanged("festival"):
            self.assert_error(self.patch("festival", {}), 422)

    def test_body_that_is_not_a_json_object_is_rejected(self):
        headers = self.auth_headers(self.users["alice"])
        requests = [
            {"json": ["description", NEW_DESCRIPTION]},
            {"json": NEW_DESCRIPTION},
            {"data": "description=hello", "content_type": "application/x-www-form-urlencoded"},
            {"data": "{not json", "content_type": "application/json"},
        ]
        for kwargs in requests:
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}), \
                    self.assert_unchanged("festival"):
                response = self.client.patch(self.url("festival"), headers=headers, **kwargs)

                self.assert_error(response, 400)

    def test_unknown_and_system_fields_are_rejected(self):
        for field, value in SYSTEM_FIELD_CHANGES.items():
            with self.subTest(field=field), self.assert_unchanged("festival"):
                response = self.patch("festival", {field: value})

                self.assert_needs_correction(response, field)


# ---------- AC4: Save failures are reported and can be retried ----------


class SaveFailureTests(UpdatePlanningTestCase):
    def assert_retryable(self, response):
        self.assert_error(response, 503)
        self.assertIs(response.get_json().get("retryable"), True)

    def test_save_failure_informs_the_coordinator_and_offers_retry(self):
        response = self.patch_during_outage(
            "festival", {"description": NEW_DESCRIPTION}, only="UPDATE"
        )

        self.assert_retryable(response)
        self.assert_no_event_details(response, "festival")

    def test_save_failure_leaves_the_event_unchanged(self):
        with self.assert_unchanged("festival"):
            self.patch_during_outage("festival", {"description": NEW_DESCRIPTION}, only="UPDATE")

    def test_load_failure_is_reported_as_retryable(self):
        response = self.patch_during_outage("festival", {"description": NEW_DESCRIPTION})

        self.assert_retryable(response)
        self.assertNotIn(response.status_code, (401, 403, 404))

    def test_retrying_the_same_edits_succeeds_once_the_database_recovers(self):
        edits = {"title": "Harbour Lights", "description": NEW_DESCRIPTION}
        self.patch_during_outage("festival", edits, only="UPDATE")

        body = self.save("festival", edits)

        self.assertEqual(body["title"], "Harbour Lights")
        self.assertEqual(body["description"], NEW_DESCRIPTION)


# ---------- AC5: Important fields are not editable here ----------


class ImportantFieldsTests(UpdatePlanningTestCase):
    def test_important_fields_are_not_saved(self):
        changes = {**IMPORTANT_CHANGES, "venue_id": self.venues["partially_recorded"].id}
        for field, value in changes.items():
            with self.subTest(field=field), self.assert_unchanged("festival"):
                self.patch("festival", {field: value})


# ---------- Authorisation ----------


class EditAuthorisationTests(UpdatePlanningTestCase):
    def test_editing_requires_authentication(self):
        with self.assert_unchanged("festival"):
            response = self.client.patch(self.url("festival"), json={"description": "x"})

            self.assertEqual(response.status_code, 401)

    def test_expired_token_is_rejected(self):
        token = create_access_token(
            identity=str(self.users["alice"].id), expires_delta=timedelta(seconds=-1)
        )
        headers = {"Authorization": f"Bearer {token}"}

        with self.assert_unchanged("festival"):
            response = self.patch("festival", {"description": "x"}, headers=headers)

            self.assertEqual(response.status_code, 401)

    def test_token_for_a_deleted_user_is_rejected(self):
        ghost = self.make_user(role="coordinator")
        headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()

        self.assert_error(self.patch("festival", {"description": "x"}, headers=headers), 401)

    def test_unknown_event_returns_not_found(self):
        response = self.client.patch(
            f"/api/events/{self.missing_id(Event)}",
            json={"description": "x"},
            headers=self.auth_headers(self.users["alice"]),
        )

        self.assert_error(response, 404)

    def test_coordinator_of_another_event_is_refused(self):
        for key in ("ben", "chloe"):
            with self.subTest(coordinator=key), self.assert_unchanged("festival"):
                response = self.patch("festival", {"description": "x"}, as_user=self.users[key])

                self.assert_denied(response, "festival")

    def test_no_one_can_edit_an_unassigned_event(self):
        with self.assert_unchanged("unassigned"):
            response = self.patch("unassigned", {"description": "x"})

            self.assert_denied(response, "unassigned")

    def test_users_who_are_not_coordinators_are_refused(self):
        for label, key in NON_COORDINATOR_USERS.items():
            with self.subTest(user=label), self.assert_unchanged("festival"):
                response = self.patch("festival", {"description": "x"}, as_user=self.users[key])

                self.assert_denied(response, "festival")

    def test_reassigned_coordinator_can_no_longer_edit(self):
        headers = self.auth_headers(self.users["alice"])
        event = self.reload("festival")
        event.coordinator_id = self.users["ben"].id
        self.db.session.commit()
        self.db.session.expire_all()

        with self.assert_unchanged("festival"):
            response = self.patch("festival", {"description": "x"}, headers=headers)

            self.assert_denied(response, "festival")

    def test_coordinator_who_changes_role_can_no_longer_edit(self):
        headers = self.auth_headers(self.users["alice"])
        self.users["alice"].role = "organiser"
        self.db.session.commit()
        self.db.session.expire_all()

        with self.assert_unchanged("festival"):
            response = self.patch("festival", {"description": "x"}, headers=headers)

            self.assert_denied(response, "festival")

    def test_refusal_comes_before_validation(self):
        response = self.patch("festival", {"title": ""}, as_user=self.users["ben"])

        self.assert_denied(response, "festival")

    def test_cancelled_event_cannot_be_edited(self):
        with self.assert_unchanged("winter_cancelled"):
            response = self.patch("winter_cancelled", {"description": "x"})

            self.assert_error(response, 409)


if __name__ == "__main__":
    unittest.main()
