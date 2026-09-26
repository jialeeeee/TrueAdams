"""Tests for the "Assign or Reassign an Event Coordinator" user story.

Model
    Event.coordinator_id           FK -> users.id, nullable. A single column, so an
                                   event can never hold two current main coordinators.
    Event.coordinator_assigned_at  DateTime (naive UTC), set on every (re)assignment.

Endpoints (JWT required, else 401; unknown event -> 404)
    GET /api/events/<id>/coordinator
        200 {"event_id", "coordinator": {"id", "email"} | null, "assigned_at": iso | null}
    GET /api/events/<id>/eligible-coordinators
        200 {"event_id", "coordinators": [{"id", "email"}, ...], "message": str | null}
        `message` tells the user when nobody is eligible.
    PUT /api/events/<id>/coordinator   body {"coordinator_id": int}
        200 {"message", "event_id", "coordinator": {"id", "email"}, "assigned_at"}
        400 malformed body          403 caller may not assign
        409 event not assignable, or selection is already the current coordinator
        422 selected user is not an eligible coordinator
        500 save failed
    Errors are {"error": "<message shown to the user>"}.

Assignment rules
    - Only ASSIGNER_ROLES may assign, reassign or list eligible coordinators.
    - Eligible = users whose role is "coordinator", excluding the event's current
      coordinator. A coordinator may be the main coordinator of several events.
    - Events in NON_ASSIGNABLE_STATUSES cannot be (re)assigned.
    - The current coordinator is visible to ASSIGNER_ROLES, the event's own
      organiser, and venue / tech staff (who arrange things with the coordinator).
"""

import unittest
from datetime import datetime, timezone
from unittest import mock

from sqlalchemy.exc import SQLAlchemyError

from app.models import Event, User
from tests.base import AppTestCase
from tests.fixtures import coordinator_data

ASSIGNER_ROLES = ("admin", "coordinator")
NON_ASSIGNABLE_STATUSES = ("draft", "cancelled")


def as_naive_utc(value):
    """Normalise a datetime or ISO string to naive UTC, as SQLite stores it."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class CoordinatorTestCase(AppTestCase):
    """Seeds the shared fixture data and wraps the coordinator endpoints."""

    def setUp(self):
        super().setUp()
        self.users = self.seed_users(coordinator_data.USERS)
        self.events = self.seed_events(coordinator_data.EVENTS)

    # ---------- Seeding ----------

    def seed_users(self, rows):
        users = {}
        for row in rows:
            users[row["key"]] = self.make_user(email=row["email"], role=row["role"])
        return users

    def seed_events(self, rows):
        events = {}
        for row in rows:
            coordinator = self.users[row["coordinator"]] if row["coordinator"] else None
            events[row["key"]] = self.make_event(
                organiser=self.users[row["organiser"]],
                title=row["title"],
                status=row["status"],
                start_time=row["start_time"],
                duration=row["end_time"] - row["start_time"],
                coordinator_id=coordinator.id if coordinator else None,
                coordinator_assigned_at=row["coordinator_assigned_at"],
            )
        return events

    # ---------- Requests ----------

    def get_coordinator(self, event_id, as_user):
        return self.client.get(
            f"/api/events/{event_id}/coordinator", headers=self.auth_headers(as_user)
        )

    def get_eligible(self, event_id, as_user):
        return self.client.get(
            f"/api/events/{event_id}/eligible-coordinators",
            headers=self.auth_headers(as_user),
        )

    def assign(self, event_id, coordinator_id, as_user=None):
        as_user = as_user or self.users["admin"]
        return self.client.put(
            f"/api/events/{event_id}/coordinator",
            json={"coordinator_id": coordinator_id},
            headers=self.auth_headers(as_user),
        )

    # ---------- Assertions ----------

    def reload(self, event):
        self.db.session.expire_all()
        return self.db.session.get(Event, event.id)

    def snapshot(self, event):
        event = self.reload(event)
        return (event.coordinator_id, event.coordinator_assigned_at, event.status)

    def assert_unchanged(self, event, before):
        self.assertEqual(self.snapshot(event), before)

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code)
        body = response.get_json()
        self.assertIsInstance(body, dict)
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip(), "error message should not be blank")

    def assert_coordinator_payload(self, payload, user):
        self.assertEqual(payload, {"id": user.id, "email": user.email})

    def eligible_ids(self, response):
        self.assertEqual(response.status_code, 200)
        return {c["id"] for c in response.get_json()["coordinators"]}

    def demote_other_coordinators(self, *keep):
        """Leave only the given coordinators in the system."""
        for key in ("alice", "ben", "chloe"):
            if key not in keep:
                self.users[key].role = "organiser"
        self.db.session.commit()


class CoordinatorModelTests(CoordinatorTestCase):
    def test_new_event_has_no_coordinator(self):
        event = self.events["unassigned"]

        self.assertIsNone(event.coordinator_id)
        self.assertIsNone(event.coordinator_assigned_at)

    def test_coordinator_column_is_a_nullable_reference_to_users(self):
        column = Event.__table__.c.coordinator_id

        self.assertTrue(column.nullable)
        self.assertEqual(
            {fk.target_fullname for fk in column.foreign_keys}, {"users.id"}
        )

    def test_coordinator_assigned_at_is_a_nullable_datetime(self):
        column = Event.__table__.c.coordinator_assigned_at

        self.assertTrue(column.nullable)
        self.assertEqual(column.type.python_type, datetime)

    def test_event_stores_exactly_one_coordinator_and_assignment_time(self):
        event = self.reload(self.events["assigned"])

        self.assertEqual(event.coordinator_id, self.users["alice"].id)
        self.assertEqual(event.coordinator_assigned_at, datetime(2026, 9, 1, 10, 0))


class ViewCurrentCoordinatorTests(CoordinatorTestCase):
    def test_unassigned_event_reports_no_coordinator(self):
        event = self.events["unassigned"]

        response = self.get_coordinator(event.id, self.users["admin"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"event_id": event.id, "coordinator": None, "assigned_at": None},
        )

    def test_assigned_event_reports_current_coordinator_and_assignment_time(self):
        event = self.events["assigned"]

        response = self.get_coordinator(event.id, self.users["admin"])

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["event_id"], event.id)
        self.assert_coordinator_payload(body["coordinator"], self.users["alice"])
        self.assertEqual(as_naive_utc(body["assigned_at"]), datetime(2026, 9, 1, 10, 0))

    def test_relevant_users_can_view_the_current_coordinator(self):
        event = self.events["assigned"]

        for key in ("admin", "alice", "ben", "dana", "gus", "hana"):
            with self.subTest(viewer=key):
                response = self.get_coordinator(event.id, self.users[key])

                self.assertEqual(response.status_code, 200)
                self.assert_coordinator_payload(
                    response.get_json()["coordinator"], self.users["alice"]
                )

    def test_unrelated_users_cannot_view_the_current_coordinator(self):
        event = self.events["assigned"]

        for key in ("farah", "evan"):
            with self.subTest(viewer=key):
                self.assert_error(self.get_coordinator(event.id, self.users[key]), 403)

    def test_viewing_requires_authentication(self):
        response = self.client.get(f"/api/events/{self.events['assigned'].id}/coordinator")

        self.assertEqual(response.status_code, 401)

    def test_token_for_a_deleted_user_is_rejected(self):
        ghost = self.make_user(role="admin")
        headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        event = self.events["assigned"]
        before = self.snapshot(event)

        requests = {
            "view": ("GET", f"/api/events/{event.id}/coordinator", None),
            "list eligible": ("GET", f"/api/events/{event.id}/eligible-coordinators", None),
            "assign": ("PUT", f"/api/events/{event.id}/coordinator", {"coordinator_id": self.users["ben"].id}),
        }
        for label, (method, url, body) in requests.items():
            with self.subTest(request=label):
                response = self.client.open(url, method=method, json=body, headers=headers)

                self.assert_error(response, 401)
                self.assert_unchanged(event, before)

    def test_viewing_an_unknown_event_returns_not_found(self):
        self.assert_error(self.get_coordinator(9999, self.users["admin"]), 404)


class EligibleCoordinatorTests(CoordinatorTestCase):
    def test_lists_every_user_with_the_coordinator_role(self):
        response = self.get_eligible(self.events["unassigned"].id, self.users["admin"])

        self.assertEqual(
            self.eligible_ids(response),
            {self.users[k].id for k in ("alice", "ben", "chloe")},
        )

    def test_listing_includes_contact_details_for_selection(self):
        response = self.get_eligible(self.events["unassigned"].id, self.users["admin"])

        by_id = {c["id"]: c for c in response.get_json()["coordinators"]}
        self.assert_coordinator_payload(by_id[self.users["alice"].id], self.users["alice"])

    def test_never_lists_users_without_the_coordinator_role(self):
        response = self.get_eligible(self.events["unassigned"].id, self.users["admin"])

        ids = self.eligible_ids(response)
        for key in ("admin", "dana", "evan", "farah", "gus", "hana"):
            with self.subTest(user=key):
                self.assertNotIn(self.users[key].id, ids)

    def test_excludes_the_events_current_coordinator(self):
        response = self.get_eligible(self.events["assigned"].id, self.users["admin"])

        self.assertEqual(
            self.eligible_ids(response), {self.users["ben"].id, self.users["chloe"].id}
        )

    def test_coordinator_of_another_event_is_still_eligible(self):
        # Ben already coordinates Evan's event.
        response = self.get_eligible(self.events["unassigned"].id, self.users["admin"])

        self.assertIn(self.users["ben"].id, self.eligible_ids(response))

    def test_informs_the_user_when_no_coordinator_is_eligible(self):
        self.demote_other_coordinators("alice")
        event = self.events["assigned"]
        before = self.snapshot(event)

        response = self.get_eligible(event.id, self.users["admin"])

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["coordinators"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())
        self.assert_unchanged(event, before)

    def test_informs_the_user_when_there_are_no_coordinators_at_all(self):
        self.demote_other_coordinators()

        response = self.get_eligible(self.events["unassigned"].id, self.users["admin"])

        body = response.get_json()
        self.assertEqual(body["coordinators"], [])
        self.assertTrue(body["message"].strip())

    def test_message_is_null_when_coordinators_are_available(self):
        response = self.get_eligible(self.events["unassigned"].id, self.users["admin"])

        self.assertIsNone(response.get_json()["message"])

    def test_only_assigners_can_list_eligible_coordinators(self):
        event = self.events["unassigned"]

        for key in ("dana", "farah", "gus", "hana"):
            with self.subTest(user=key):
                self.assert_error(self.get_eligible(event.id, self.users[key]), 403)

    def test_listing_requires_authentication(self):
        response = self.client.get(
            f"/api/events/{self.events['unassigned'].id}/eligible-coordinators"
        )

        self.assertEqual(response.status_code, 401)

    def test_listing_for_an_unknown_event_returns_not_found(self):
        self.assert_error(self.get_eligible(9999, self.users["admin"]), 404)


class AssignCoordinatorTests(CoordinatorTestCase):
    def test_assignment_records_coordinator_and_time_and_confirms(self):
        event = self.events["unassigned"]
        alice = self.users["alice"]

        before_request = datetime.utcnow()
        response = self.assign(event.id, alice.id)
        after_request = datetime.utcnow()

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["message"].strip(), "confirmation message should be shown")
        self.assertEqual(body["event_id"], event.id)
        self.assert_coordinator_payload(body["coordinator"], alice)

        stored = self.reload(event)
        self.assertEqual(stored.coordinator_id, alice.id)
        self.assertLessEqual(before_request, stored.coordinator_assigned_at)
        self.assertLessEqual(stored.coordinator_assigned_at, after_request)
        self.assertEqual(as_naive_utc(body["assigned_at"]), stored.coordinator_assigned_at)

    def test_new_assignment_is_visible_to_relevant_users(self):
        event = self.events["unassigned"]
        self.assign(event.id, self.users["chloe"].id)

        response = self.get_coordinator(event.id, self.users["dana"])

        self.assert_coordinator_payload(response.get_json()["coordinator"], self.users["chloe"])

    def test_assignment_does_not_change_event_status(self):
        event = self.events["unassigned"]

        self.assign(event.id, self.users["alice"].id)

        self.assertEqual(self.reload(event).status, "submitted")

    def test_every_assigner_role_can_assign(self):
        for key, event_key in (("admin", "unassigned"), ("chloe", "evans_event")):
            with self.subTest(assigner=key):
                event = self.events[event_key]
                target = self.users["alice"]

                response = self.assign(event.id, target.id, as_user=self.users[key])

                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.reload(event).coordinator_id, target.id)

    def test_coordinator_can_coordinate_several_events(self):
        # Ben already coordinates Evan's event.
        response = self.assign(self.events["unassigned"].id, self.users["ben"].id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.reload(self.events["evans_event"]).coordinator_id, self.users["ben"].id)
        self.assertEqual(self.reload(self.events["unassigned"]).coordinator_id, self.users["ben"].id)

    def test_assignment_leaves_other_events_untouched(self):
        others = {k: self.snapshot(self.events[k]) for k in ("assigned", "evans_event")}

        self.assign(self.events["unassigned"].id, self.users["chloe"].id)

        for key, before in others.items():
            with self.subTest(event=key):
                self.assert_unchanged(self.events[key], before)

    def test_rejects_users_who_are_not_coordinators(self):
        event = self.events["unassigned"]
        before = self.snapshot(event)

        for key in ("admin", "dana", "farah", "gus", "hana"):
            with self.subTest(selected=key):
                self.assert_error(self.assign(event.id, self.users[key].id), 422)
                self.assert_unchanged(event, before)

    def test_rejects_a_user_that_does_not_exist(self):
        event = self.events["unassigned"]
        before = self.snapshot(event)

        self.assert_error(self.assign(event.id, 9999), 422)
        self.assert_unchanged(event, before)

    def test_rejects_events_that_cannot_be_assigned(self):
        for status in NON_ASSIGNABLE_STATUSES:
            with self.subTest(status=status):
                event = self.events[status]
                before = self.snapshot(event)

                self.assert_error(self.assign(event.id, self.users["alice"].id), 409)
                self.assert_unchanged(event, before)

    def test_rejects_malformed_requests(self):
        event = self.events["unassigned"]
        before = self.snapshot(event)
        url = f"/api/events/{event.id}/coordinator"
        headers = self.auth_headers(self.users["admin"])

        bodies = {
            "missing coordinator_id": {"json": {}},
            "null coordinator_id": {"json": {"coordinator_id": None}},
            "non-numeric coordinator_id": {"json": {"coordinator_id": "alice"}},
            "no JSON body": {"data": "coordinator_id=1"},
        }
        for label, kwargs in bodies.items():
            with self.subTest(body=label):
                response = self.client.put(url, headers=headers, **kwargs)

                self.assert_error(response, 400)
                self.assert_unchanged(event, before)

    def test_non_assigners_cannot_assign(self):
        event = self.events["unassigned"]
        before = self.snapshot(event)

        # Includes Dana, the event's own organiser.
        for key in ("dana", "evan", "farah", "gus", "hana"):
            with self.subTest(user=key):
                response = self.assign(event.id, self.users["alice"].id, as_user=self.users[key])

                self.assert_error(response, 403)
                self.assert_unchanged(event, before)

    def test_assigning_requires_authentication(self):
        event = self.events["unassigned"]
        before = self.snapshot(event)

        response = self.client.put(
            f"/api/events/{event.id}/coordinator",
            json={"coordinator_id": self.users["alice"].id},
        )

        self.assertEqual(response.status_code, 401)
        self.assert_unchanged(event, before)

    def test_assigning_to_an_unknown_event_returns_not_found(self):
        self.assert_error(self.assign(9999, self.users["alice"].id), 404)


class ReassignCoordinatorTests(CoordinatorTestCase):
    def test_reassignment_replaces_the_previous_coordinator(self):
        event = self.events["assigned"]
        ben = self.users["ben"]

        before_request = datetime.utcnow()
        response = self.assign(event.id, ben.id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["message"].strip())
        self.assert_coordinator_payload(response.get_json()["coordinator"], ben)

        stored = self.reload(event)
        self.assertEqual(stored.coordinator_id, ben.id)
        self.assertGreaterEqual(stored.coordinator_assigned_at, before_request)

    def test_reassignment_leaves_a_single_current_coordinator(self):
        event = self.events["assigned"]

        self.assign(event.id, self.users["ben"].id)

        response = self.get_coordinator(event.id, self.users["admin"])
        self.assert_coordinator_payload(response.get_json()["coordinator"], self.users["ben"])
        self.assertEqual(
            Event.query.filter_by(id=event.id, coordinator_id=self.users["alice"].id).count(), 0
        )

    def test_repeated_reassignments_keep_only_the_latest_coordinator(self):
        event = self.events["assigned"]
        timestamps = []

        for key in ("ben", "chloe", "alice"):
            with self.subTest(reassign_to=key):
                response = self.assign(event.id, self.users[key].id)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.reload(event).coordinator_id, self.users[key].id)
                timestamps.append(self.reload(event).coordinator_assigned_at)

        self.assertEqual(timestamps, sorted(timestamps))
        current = self.get_coordinator(event.id, self.users["admin"]).get_json()
        self.assert_coordinator_payload(current["coordinator"], self.users["alice"])

    def test_previous_coordinator_becomes_eligible_again(self):
        event = self.events["assigned"]

        self.assign(event.id, self.users["ben"].id)

        response = self.get_eligible(event.id, self.users["admin"])
        self.assertEqual(
            self.eligible_ids(response), {self.users["alice"].id, self.users["chloe"].id}
        )

    def test_reassigning_to_the_current_coordinator_is_rejected(self):
        event = self.events["assigned"]
        before = self.snapshot(event)

        self.assert_error(self.assign(event.id, self.users["alice"].id), 409)
        self.assert_unchanged(event, before)

    def test_reassignment_with_no_eligible_coordinator_keeps_existing_assignment(self):
        self.demote_other_coordinators("alice")
        event = self.events["assigned"]
        before = self.snapshot(event)

        cases = {
            "current coordinator": (self.users["alice"].id, 409),
            "demoted coordinator": (self.users["ben"].id, 422),
        }
        for label, (coordinator_id, status_code) in cases.items():
            with self.subTest(selected=label):
                self.assert_error(self.assign(event.id, coordinator_id), status_code)
                self.assert_unchanged(event, before)

    def test_rejected_reassignment_keeps_existing_assignment_visible(self):
        event = self.events["assigned"]

        self.assign(event.id, self.users["dana"].id)

        response = self.get_coordinator(event.id, self.users["dana"])
        self.assert_coordinator_payload(response.get_json()["coordinator"], self.users["alice"])

    def test_reassigning_a_cancelled_event_is_rejected(self):
        event = self.events["assigned"]
        event.status = "cancelled"
        self.db.session.commit()
        before = self.snapshot(event)

        self.assert_error(self.assign(event.id, self.users["ben"].id), 409)
        self.assert_unchanged(event, before)


class SaveFailureTests(CoordinatorTestCase):
    """If the database write fails, nothing about the assignment may change."""

    def assign_with_failing_commit(self, event_id, coordinator_id):
        with mock.patch.object(
            self.db.session, "commit", side_effect=SQLAlchemyError("simulated outage")
        ):
            return self.assign(event_id, coordinator_id)

    def test_failed_first_assignment_leaves_event_unassigned(self):
        event = self.events["unassigned"]
        before = self.snapshot(event)

        response = self.assign_with_failing_commit(event.id, self.users["alice"].id)

        self.assert_error(response, 500)
        self.assert_unchanged(event, before)

    def test_failed_reassignment_keeps_previous_coordinator(self):
        event = self.events["assigned"]
        before = self.snapshot(event)

        response = self.assign_with_failing_commit(event.id, self.users["ben"].id)

        self.assert_error(response, 500)
        self.assert_unchanged(event, before)

    def test_failed_save_is_rolled_back_before_the_next_request(self):
        """A dirty session would leak the unsaved coordinator into later reads."""
        event = self.events["assigned"]

        self.assign_with_failing_commit(event.id, self.users["ben"].id)

        response = self.get_coordinator(event.id, self.users["admin"])
        body = response.get_json()
        self.assert_coordinator_payload(body["coordinator"], self.users["alice"])
        self.assertEqual(as_naive_utc(body["assigned_at"]), datetime(2026, 9, 1, 10, 0))

    def test_failed_save_does_not_report_success(self):
        response = self.assign_with_failing_commit(
            self.events["unassigned"].id, self.users["alice"].id
        )

        self.assertNotIn("coordinator", response.get_json())


if __name__ == "__main__":
    unittest.main()
