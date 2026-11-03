"""The guards every route shares (AGENTS.md "Order of checks" and "Database access").

Each story's own tests check these on the routes its acceptance criteria name; this file
checks them on every other route, so that each is known to answer as AGENTS.md says:
    401 "Your session is no longer valid..." for a token whose user no longer exists, or
        whose identity is not a user ID
    404 for an unknown event, before any permission check
    400 for a body that is not a JSON object
    503 {"retryable": true} when the database fails while loading, with the error hidden
"""

import unittest
from datetime import datetime
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app.models import Event, EventClarification, User, Venue, VenueBooking
from tests.base import AppTestCase

SESSION_INVALID = "Your session is no longer valid. Please log in again."
OUTAGE = "Private outage detail"


class GuardTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.organiser = self.make_user(role="organiser")
        self.coordinator = self.make_user(role="coordinator")
        self.safety = self.make_user(role="safety_officer")
        self.venue_staff = self.make_user(role="venue_staff")
        self.event = self.make_event(organiser=self.organiser, status="approved",
                                     coordinator_id=self.coordinator.id)
        self.venue = self.make_venue()

    def token(self, identity):
        return {"Authorization": f"Bearer {create_access_token(identity=identity)}"}

    def call(self, method, path, headers, json=None):
        return self.client.open(path.format(event=self.event.id, venue=self.venue.id),
                                method=method, headers=headers, json=json)


# Routes whose 401 for a session without a user no story test reaches.
SESSION_ROUTES = [
    ("GET", "/api/events/safety-checks"),
    ("POST", "/api/events/{event}/safety-checks/approve"),
    ("POST", "/api/events/{event}/safety-checks/reject"),
    ("POST", "/api/events/{event}/confirm"),
    ("GET", "/api/events/{event}/clarifications"),
    ("POST", "/api/events/{event}/resubmit"),
    ("GET", "/api/events/{event}/registrations"),
    ("GET", "/api/events/{event}/registration-overview"),
    ("GET", "/api/events/{event}/venue-suitability"),
    ("GET", "/api/events/change-requests"),
    ("GET", "/api/registrations/"),
]

# Routes that look the event up before checking who may act on it.
EVENT_ROUTES = [
    ("POST", "/api/events/{event}/safety-checks/approve"),
    ("POST", "/api/events/{event}/safety-checks/reject"),
    ("POST", "/api/events/{event}/confirm"),
    ("POST", "/api/events/{event}/resubmit"),
]

# Routes whose load failure no story test reaches.
LOAD_ROUTES = [
    ("GET", "/api/events/"),
    ("GET", "/api/events/{event}"),
    ("GET", "/api/events/{event}/coordinator"),
    ("GET", "/api/events/{event}/eligible-coordinators"),
    ("GET", "/api/events/{event}/clarifications"),
    ("GET", "/api/events/drafts"),
    ("GET", "/api/events/drafts/{event}"),
    ("GET", "/api/events/{event}/review"),
    ("GET", "/api/events/requests"),
    ("GET", "/api/events/{event}/registration-settings"),
    ("GET", "/api/events/change-requests"),
    ("GET", "/api/venues/options"),
    ("GET", "/api/venues/{venue}/unavailable"),
    ("GET", "/api/venues/{venue}/history"),
    ("GET", "/api/venues/bookings/1/replacement"),
]


class SessionTests(GuardTestCase):
    def test_a_session_whose_user_is_gone_is_a_401(self):
        headers = self.token(str(self.missing_id(User)))
        for method, path in SESSION_ROUTES:
            with self.subTest(method=method, path=path):
                response = self.call(method, path, headers, json={})
                self.assertEqual(response.status_code, 401, response.get_json())
                self.assertEqual(response.get_json()["error"], SESSION_INVALID)

    def test_an_identity_that_is_not_a_user_id_is_a_401(self):
        response = self.call("GET", "/api/registrations/", self.token("not-an-id"))
        self.assertEqual(response.status_code, 401)


class UnknownEventTests(GuardTestCase):
    def test_an_unknown_event_is_a_404_whoever_asks(self):
        missing = self.missing_id(Event)
        for method, path in EVENT_ROUTES:
            for user in (self.organiser, self.safety, self.venue_staff):
                with self.subTest(method=method, path=path, role=user.role):
                    response = self.client.open(path.format(event=missing), method=method,
                                                headers=self.auth_headers(user), json={})
                    self.assertEqual(response.status_code, 404, response.get_json())
                    self.assertEqual(response.get_json()["error"], "Event not found.")


class BodyTests(GuardTestCase):
    def test_a_body_that_is_not_a_json_object_is_a_400(self):
        cases = [
            (self.safety, "POST", "/api/events/{event}/safety-checks/approve"),
            (self.safety, "POST", "/api/events/{event}/safety-checks/reject"),
            (self.venue_staff, "POST", "/api/venues/"),
            (self.venue_staff, "POST", "/api/venues/{venue}/unavailable"),
        ]
        for user, method, path in cases:
            with self.subTest(method=method, path=path):
                response = self.call(method, path, self.auth_headers(user), json=["not", "an object"])
                self.assertEqual(response.status_code, 400, response.get_json())

    def test_request_changes_that_are_not_an_object_are_a_400(self):
        self.event.status = "under_review"
        self.db.session.commit()
        response = self.call("POST", "/api/events/{event}/resubmit",
                             self.auth_headers(self.organiser),
                             json={"message": "Here you go", "changes": ["title"]})
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(response.get_json()["error"], "Send the request changes as a JSON object.")


class LoadFailureTests(GuardTestCase):
    def test_a_database_failure_while_loading_is_a_retryable_503(self):
        users = {"/api/venues/": self.venue_staff, "/api/events/drafts": self.organiser,
                 "/api/events/requests": self.organiser}
        for method, path in LOAD_ROUTES:
            with self.subTest(method=method, path=path):
                user = next((u for prefix, u in users.items() if path.startswith(prefix)),
                            self.coordinator)
                headers = self.auth_headers(user)
                with mock.patch.object(self.db.session, "get",
                                       side_effect=SQLAlchemyError(OUTAGE)):
                    response = self.call(method, path, headers)
                self.assertEqual(response.status_code, 503, response.get_json())
                self.assertIs(response.get_json()["retryable"], True)
                self.assertNotIn(OUTAGE, response.get_data(as_text=True))


class StateRefusalTests(GuardTestCase):
    """Refusals that come after the shared guards, which the stories' own tests don't reach."""

    def post(self, path, user, body):
        return self.call("POST", path, self.auth_headers(user), json=body)

    def test_scrum91_a_comment_must_be_text(self):
        response = self.post("/api/events/{event}/safety-checks/approve", self.safety,
                             {"comment": 5})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["field"], "comment")

    def test_scrum91_an_approved_safety_check_cannot_be_approved_again(self):
        self.event.safety_decision = "approved"
        self.db.session.commit()
        response = self.post("/api/events/{event}/safety-checks/approve", self.safety, {})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "This safety check is already approved.")

    def test_scrum92_an_event_not_awaiting_a_check_cannot_be_rejected(self):
        # Approved, but with no confirmed venue it was never in the safety queue.
        response = self.post("/api/events/{event}/safety-checks/reject", self.safety,
                             {"comment": "Fire exits blocked"})
        self.assertEqual(response.status_code, 409)
        self.db.session.expire_all()
        self.assertIsNone(self.db.session.get(Event, self.event.id).safety_decision)

    def test_scrum93_only_an_approved_event_can_be_confirmed(self):
        self.event.status = "submitted"
        self.db.session.commit()
        response = self.post("/api/events/{event}/confirm", self.coordinator, {})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"],
                         "This event is submitted, so it cannot be confirmed.")

    def test_scrum95_invalid_changes_with_a_reply_are_refused_with_every_field(self):
        self.event.status = "under_review"
        self.db.session.add(EventClarification(event_id=self.event.id,
                                               sender_id=self.coordinator.id,
                                               message="How many guests?"))
        self.db.session.commit()
        response = self.post("/api/events/{event}/resubmit", self.organiser,
                             {"message": "Here you go", "changes": {"title": 5}})
        self.assertEqual(response.status_code, 422, response.get_json())
        self.assertIn("title", response.get_json()["fields"])
        self.db.session.expire_all()
        self.assertEqual(self.db.session.get(Event, self.event.id).status, "under_review")


class VenueRefusalTests(GuardTestCase):
    """Venue refusals the stories' own tests don't reach."""

    def book(self, event, status, start, end, venue=None):
        booking = VenueBooking(event_id=event.id, venue_id=(venue or self.venue).id,
                               status=status, start_time=start, end_time=end,
                               venue_requirements="x", requested_by_id=self.coordinator.id)
        self.db.session.add(booking)
        self.db.session.commit()
        return booking

    def test_scrum63_every_catalogue_problem_is_named(self):
        response = self.call("POST", "/api/venues/", self.auth_headers(self.venue_staff),
                             json={"name": "x" * 256, "location": "Level 1", "capacity": ""})
        self.assertEqual(response.status_code, 400, response.get_json())
        fields = response.get_json()["fields"]
        self.assertEqual(fields["name"], "Name must be at most 255 characters.")
        self.assertEqual(fields["capacity"], "Capacity is required.")

    def test_scrum88_periods_of_an_unknown_venue_are_a_404(self):
        response = self.client.get(f"/api/venues/{self.missing_id(Venue)}/unavailable",
                                   headers=self.auth_headers(self.venue_staff))
        self.assertEqual(response.status_code, 404)

    def test_scrum36_a_range_over_the_maximum_is_refused(self):
        response = self.call("GET", "/api/venues/{venue}/availability?from=2027-01-01&to=2027-02-01",
                             self.auth_headers(self.coordinator))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Choose a range of at most 31 days.")

    def test_scrum69_an_events_venue_requests_need_a_known_event(self):
        headers = self.auth_headers(self.coordinator)
        bad = self.client.get("/api/venues/bookings?event_id=abc", headers=headers)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.get_json()["field"], "event_id")
        unknown = self.client.get(f"/api/venues/bookings?event_id={self.missing_id(Event)}",
                                  headers=headers)
        self.assertEqual(unknown.status_code, 404)

    def test_scrum69_a_request_whose_event_has_no_coordinator_cannot_be_rejected(self):
        event = self.make_event(organiser=self.organiser, status="approved")
        booking = self.book(event, "pending", datetime(2027, 3, 1, 10), datetime(2027, 3, 1, 12))
        response = self.call("POST", f"/api/venues/bookings/{booking.id}/reject",
                             self.auth_headers(self.venue_staff), json={"reason": "No"})
        self.assertEqual(response.status_code, 409, response.get_json())
        self.db.session.expire_all()
        self.assertEqual(self.db.session.get(VenueBooking, booking.id).status, "pending")

    def test_scrum85_a_cancellation_body_must_be_an_object(self):
        booking = self.book(self.event, "confirmed", datetime(2027, 3, 1, 10),
                            datetime(2027, 3, 1, 12))
        response = self.call("POST", f"/api/venues/bookings/{booking.id}/cancel",
                             self.auth_headers(self.coordinator), json=["also"])
        self.assertEqual(response.status_code, 400, response.get_json())

    def test_scrum85_the_event_keeps_a_venue_it_still_has_a_booking_at(self):
        self.event.start_time, self.event.end_time = datetime(2027, 3, 1, 9), datetime(2027, 3, 2, 18)
        self.event.venue_id = self.venue.id
        self.db.session.commit()
        first = self.book(self.event, "confirmed", datetime(2027, 3, 1, 10), datetime(2027, 3, 1, 12))
        self.book(self.event, "confirmed", datetime(2027, 3, 2, 10), datetime(2027, 3, 2, 12))
        response = self.call("POST", f"/api/venues/bookings/{first.id}/cancel",
                             self.auth_headers(self.coordinator))
        self.assertEqual(response.status_code, 200, response.get_json())
        self.db.session.expire_all()
        self.assertEqual(self.db.session.get(Event, self.event.id).venue_id, self.venue.id)


if __name__ == "__main__":
    unittest.main()
