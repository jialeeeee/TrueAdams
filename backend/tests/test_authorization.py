"""SCRUM-27 authorization evidence for existing protected endpoints only.

Confirmed SCRUM-27 rules supersede unrestricted coordinator reassignment.
These are Supabase-backed integration tests; run the isolated unit modules
instead for fast local authorization checks (see the SCRUM-27 test cases).
JWTs are issued directly here to isolate authorization from tested login code.
"""

from datetime import datetime
from unittest import mock

from app import tasks
from app.models import Event, Notification
from tests.base import AppTestCase


class AuthorizationEvidenceTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.organiser = self.make_user(role="organiser")
        self.coordinator = self.make_user(role="coordinator")
        self.event = self.make_event(
            organiser=self.organiser,
            status="submitted",
            coordinator_id=self.coordinator.id,
            coordinator_assigned_at=datetime(2026, 9, 1, 10, 0),
        )

    def event_state(self):
        event_id = self.event.id
        self.db.session.expire_all()
        event = self.db.session.get(Event, event_id)
        return {column.name: getattr(event, column.name) for column in Event.__table__.columns}

    def assert_denied_without_details(self, response):
        self.assertEqual(response.status_code, 403)
        body = response.get_json()
        self.assertIsInstance(body, dict)
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        self.assertFalse(
            {"event_id", "coordinator", "coordinators", "assigned_at", "venues",
             "id", "email", "title", "description", "name", "contact_email"} & body.keys()
        )
        public_response = response.get_data(as_text=True)
        self.assertNotIn(self.coordinator.email, public_response)
        self.assertNotIn(self.organiser.email, public_response)
        self.assertNotIn(self.event.title, public_response)

    def test_organiser_can_read_own_coordinator_but_not_unrelated_event_details(self):
        unrelated = self.make_user(role="organiser")
        url = f"/api/events/{self.event.id}/coordinator"

        allowed = self.client.get(url, headers=self.auth_headers(self.organiser))

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.get_json()["event_id"], self.event.id)
        self.assertEqual(allowed.get_json()["coordinator"], {
            "id": self.coordinator.id, "email": self.coordinator.email,
        })
        denied = self.client.get(url, headers=self.auth_headers(unrelated))
        self.assert_denied_without_details(denied)

    def test_attendee_direct_reads_do_not_disclose_internal_information(self):
        attendee = self.make_user(role="attendee")
        venue = self.make_venue(name="Private planning venue")
        headers = self.auth_headers(attendee)
        paths = (
            f"/api/events/{self.event.id}/coordinator",
            f"/api/events/{self.event.id}/eligible-coordinators",
            "/api/venues/",
            f"/api/venues/{venue.id}",
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path, headers=headers)
                self.assert_denied_without_details(response)
                self.assertNotIn(venue.name, response.get_data(as_text=True))

    def test_venue_access_uses_current_role_with_an_existing_token(self):
        venue = self.make_venue()
        url = f"/api/venues/{venue.id}"
        headers = self.auth_headers(self.coordinator)
        self.assertEqual(self.client.get(url, headers=headers).status_code, 200)

        self.coordinator.role = "attendee"
        self.db.session.commit()
        self.db.session.expire_all()

        # Reuse the exact JWT that still contains a coordinator role claim.
        self.assert_denied_without_details(self.client.get(url, headers=headers))

    def test_event_access_and_reassignment_use_current_role_with_an_existing_token(self):
        target = self.make_user(role="coordinator")
        target_id = target.id
        url = f"/api/events/{self.event.id}/coordinator"
        eligible_url = f"/api/events/{self.event.id}/eligible-coordinators"
        headers = self.auth_headers(self.coordinator)
        self.assertEqual(self.client.get(url, headers=headers).status_code, 200)
        self.assertEqual(self.client.get(eligible_url, headers=headers).status_code, 200)
        # A no-op reassignment reaches the business-rule 409 while authorised.
        self.assertEqual(self.client.put(
            url, json={"coordinator_id": self.coordinator.id}, headers=headers,
        ).status_code, 409)
        before = self.event_state()

        self.coordinator.role = "attendee"
        self.db.session.commit()
        self.db.session.expire_all()

        self.assert_denied_without_details(self.client.get(url, headers=headers))
        self.assert_denied_without_details(self.client.get(eligible_url, headers=headers))
        response = self.client.put(url, json={"coordinator_id": target_id}, headers=headers)
        self.assert_denied_without_details(response)
        self.assertEqual(self.event_state(), before)

    def test_unauthorized_reassignment_preserves_every_persisted_event_field(self):
        target = self.make_user(role="coordinator")
        target_id = target.id
        url = f"/api/events/{self.event.id}/coordinator"
        before = self.event_state()
        for role in ("organiser", "attendee", "venue_staff", "tech_staff"):
            with self.subTest(role=role):
                caller = self.organiser if role == "organiser" else self.make_user(role=role)
                response = self.client.put(
                    url, json={"coordinator_id": target_id}, headers=self.auth_headers(caller),
                )
                self.assert_denied_without_details(response)
                self.assertEqual(self.event_state(), before)

    # TC-27-01/02: both self-assignment and changing someone else's coordinator.
    def test_unrelated_coordinator_cannot_reassign_or_self_assign(self):
        unrelated = self.make_user(role="coordinator")
        event_id, unrelated_id = self.event.id, unrelated.id
        headers = self.auth_headers(unrelated)
        before = self.event_state()
        for target_id in (unrelated_id, self.coordinator.id):
            with self.subTest(target=target_id):
                response = self.client.put(f"/api/events/{event_id}/coordinator",
                                           json={"coordinator_id": target_id}, headers=headers)
                self.assert_denied_without_details(response)
                self.assertEqual(self.event_state(), before)
        self.assert_denied_without_details(self.client.get(
            f"/api/events/{event_id}/eligible-coordinators", headers=headers))

    # TC-27-03: original tokens are reused across the real persisted reassignment.
    def test_reassignment_moves_event_specific_read_and_write_privileges(self):
        replacement = self.make_user(role="coordinator")
        event_id, replacement_id = self.event.id, replacement.id
        previous_headers, new_headers = self.auth_headers(self.coordinator), self.auth_headers(replacement)
        response = self.client.put(f"/api/events/{event_id}/coordinator",
                                   json={"coordinator_id": replacement_id}, headers=previous_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.event_state()["coordinator_id"], replacement_id)
        for suffix in ("planning", "review", "clarifications", "eligible-coordinators"):
            with self.subTest(read=suffix):
                url = f"/api/events/{event_id}/{suffix}"
                self.assert_denied_without_details(self.client.get(url, headers=previous_headers))
                self.assertEqual(self.client.get(url, headers=new_headers).status_code, 200)
        before = self.event_state()
        with mock.patch.object(tasks.send_notification_email, "delay") as email:
            for method, suffix, body in (("PATCH", "", {"title": "Unauthorized"}),
                                         ("POST", "/decision", {"decision": "approve"}),
                                         ("POST", "/clarifications", {"message": "Unauthorized?"}),
                                         ("PUT", "/coordinator", {"coordinator_id": self.coordinator.id})):
                with self.subTest(write=suffix):
                    response = self.client.open(f"/api/events/{event_id}{suffix}", method=method,
                                                json=body, headers=previous_headers)
                    self.assert_denied_without_details(response)
                    self.assertEqual(self.event_state(), before)
            self.assertEqual(Notification.query.filter_by(event_id=event_id).count(), 0)
            email.assert_not_called()
            self.assertEqual(self.client.patch(f"/api/events/{event_id}",
                json={"description": "Authorized update"}, headers=new_headers).status_code, 200)
            self.assertEqual(self.client.post(f"/api/events/{event_id}/clarifications",
                json={"message": "Authorized question?"}, headers=new_headers).status_code, 201)
            self.assertEqual(self.client.post(f"/api/events/{event_id}/decision",
                json={"decision": "approve"}, headers=new_headers).status_code, 200)
        self.assertEqual(self.event_state()["status"], "approved")

    # TC-27-04: no manual initial assignment, including the retained admin exception.
    def test_unassigned_event_cannot_be_assigned_through_reassignment_api(self):
        self.event.coordinator_id = None
        self.db.session.commit()
        before = self.event_state()
        target_id = self.coordinator.id
        for role in ("coordinator", "admin"):
            caller = self.make_user(role=role)
            response = self.client.put(f"/api/events/{self.event.id}/coordinator",
                json={"coordinator_id": target_id}, headers=self.auth_headers(caller))
            self.assert_denied_without_details(response)
            self.assertEqual(self.event_state(), before)

    # TC-27-05: historical ownership is insufficient; new-role access is retained.
    def test_former_organiser_loses_owner_only_reads_with_original_token(self):
        headers = self.auth_headers(self.organiser)
        for role in ("attendee", "coordinator", "venue_staff", "tech_staff"):
            with self.subTest(role=role):
                self.organiser.role = role
                self.db.session.commit()
                self.db.session.expire_all()
                url = f"/api/events/{self.event.id}"
                response = self.client.get(f"{url}/coordinator", headers=headers)
                self.assertEqual(response.status_code, 403 if role == "attendee" else 200)
                self.assert_denied_without_details(self.client.get(f"{url}/clarifications", headers=headers))
                self.assert_denied_without_details(self.client.get("/api/events/requests", headers=headers))

    # TC-27-06: the read path needs its own negative matrix, separate from sending.
    def test_unrelated_users_cannot_read_clarification_history(self):
        for role in ("organiser", "coordinator", "venue_staff", "tech_staff", "attendee", "admin"):
            with self.subTest(role=role):
                caller = self.make_user(role=role)
                response = self.client.get(f"/api/events/{self.event.id}/clarifications",
                                           headers=self.auth_headers(caller))
                self.assert_denied_without_details(response)

    # TC-27-07: extra identity/relationship fields cannot be smuggled with a valid target.
    def test_forged_reassignment_fields_leave_all_persisted_fields_unchanged(self):
        replacement = self.make_user(role="coordinator")
        replacement_id = replacement.id
        before = self.event_state()
        for field in ("organiser_id", "event_id", "coordinator_assigned_at", "status", "user_id"):
            with self.subTest(field=field):
                response = self.client.put(f"/api/events/{self.event.id}/coordinator",
                    json={"coordinator_id": replacement_id, field: replacement_id},
                    headers=self.auth_headers(self.coordinator))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.event_state(), before)
