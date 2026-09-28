"""SCRUM-27 authorization evidence for existing protected endpoints only.

Assignment/reassignment keeps its established authority. No implemented
assigned-coordinator-only planning operation exists yet, so none is invented.
JWTs are issued directly here to isolate authorization from tested login code.
"""

from datetime import datetime

from app.models import Event
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
