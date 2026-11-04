"""CF01 (G4 clarification #22, "Can one person hold two roles? Yes, multiple roles
possible."): a user may hold more than one role.

Cases TC-76-08..13 in docs/test-cases/SCRUM-76-authorised-access.md.

    User.role               the main role, which picks the home page
    User.additional_roles   the other roles, as a list of names; NULL means none
    app/roles.py            roles_of / has_role / has_any_role / holding, used by every check
    POST /api/auth/login    200 {"access_token", "role", "roles": [main role, others sorted]}

Holding a role grants what that role may do, and nothing about any event: the
relationship checks (the event's organiser, its coordinator) still apply.
"""

import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from werkzeug.security import generate_password_hash

from app import tasks
from app.local_time import singapore_now
from app.models import (Event, EventClarification, Notification, Registration, User,
                        VenueBooking)
from app.roles import has_any_role, has_role, holding, roles_of
from tests.base import AppTestCase

PASSWORD = "CF01-test-password!"


# ---------- TC-76-08: the rules ----------


class RoleRulesTests(unittest.TestCase):
    def test_a_user_holds_their_main_role_and_their_other_roles(self):
        user = User(role="organiser", additional_roles=["attendee", "venue_staff"])

        self.assertEqual(roles_of(user), {"organiser", "attendee", "venue_staff"})
        self.assertTrue(has_role(user, "attendee"))
        self.assertFalse(has_role(user, "coordinator"))
        self.assertTrue(has_any_role(user, {"coordinator", "venue_staff"}))
        self.assertFalse(has_any_role(user, {"coordinator", "tech_staff"}))

    def test_no_other_roles_means_only_the_main_role(self):
        for user in (User(role="coordinator"), User(role="coordinator", additional_roles=[]),
                     SimpleNamespace(role="coordinator")):
            with self.subTest(user=user):
                self.assertEqual(roles_of(user), {"coordinator"})

    def test_nobody_holds_a_role(self):
        self.assertFalse(has_role(None, "attendee"))
        self.assertFalse(has_any_role(None, {"attendee"}))


# ---------- TC-76-09..13: through the API ----------


class RolesTestCase(AppTestCase):
    def make_published_event(self, **fields):
        """An approved event next week, taking registrations now (SCRUM-45)."""
        now = singapore_now()
        fields = {"title": "Two Roles Night", "status": "approved",
                  "start_time": now + timedelta(days=7), "registration_required": True,
                  "registration_capacity": 10, "registration_opens_at": now - timedelta(days=1),
                  "registration_closes_at": now + timedelta(days=6), **fields}
        return self.make_event(**fields)


class MultipleRolesTests(RolesTestCase):
    # TC-76-09 · login names every role, main role first.
    def test_login_lists_every_role_the_user_holds(self):
        both = self.make_user(role="organiser", additional_roles=["venue_staff", "attendee"],
                              password_hash=generate_password_hash(PASSWORD))
        single = self.make_user(role="coordinator",
                                password_hash=generate_password_hash(PASSWORD))

        for user, roles in ((both, ["organiser", "attendee", "venue_staff"]),
                            (single, ["coordinator"])):
            with self.subTest(role=user.role):
                response = self.client.post("/api/auth/login",
                                            json={"email": user.email, "password": PASSWORD})

                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(response.get_json()["role"], user.role)
                self.assertEqual(response.get_json()["roles"], roles)

    # TC-76-10 · each role held works: an organiser who is also an attendee drafts a
    # request and registers for an event; a coordinator who is also Venue Staff opens
    # both of their lists.
    def test_each_role_held_gives_that_roles_functions(self):
        organiser = self.make_user(role="organiser", additional_roles=["attendee"])
        event = self.make_published_event()
        coordinator = self.make_user(role="coordinator", additional_roles=["venue_staff"])

        drafted = self.client.post("/api/events/drafts", json={"title": "My own event"},
                                   headers=self.auth_headers(organiser))
        registered = self.client.post("/api/registrations/", json={"event_id": event.id},
                                      headers=self.auth_headers(organiser))
        managed = self.client.get("/api/events/managed", headers=self.auth_headers(coordinator))
        requests = self.client.get("/api/venues/bookings", headers=self.auth_headers(coordinator))

        self.assertEqual(drafted.status_code, 201, drafted.get_json())
        self.assertEqual(registered.status_code, 201, registered.get_json())
        self.assertEqual(Registration.query.filter_by(event_id=event.id,
                                                      attendee_id=organiser.id).count(), 1)
        self.assertEqual(managed.status_code, 200, managed.get_json())
        self.assertEqual(requests.status_code, 200, requests.get_json())

    # TC-76-10 (negative) · a role not held is still refused.
    def test_a_role_not_held_is_still_refused(self):
        user = self.make_user(role="organiser", additional_roles=["attendee"])

        for method, url in (("get", "/api/events/managed"), ("get", "/api/venues/bookings"),
                            ("get", "/api/events/safety-checks")):
            with self.subTest(url=url):
                response = getattr(self.client, method)(url, headers=self.auth_headers(user))
                self.assertEqual(response.status_code, 403, response.get_json())

    # TC-76-11 · an extra role grants no relationship to an event: a coordinator who is
    # also an organiser cannot decide or confirm an event they don't coordinate, nor
    # open another organiser's draft.
    def test_an_extra_role_grants_no_access_to_other_peoples_events(self):
        user = self.make_user(role="organiser", additional_roles=["coordinator"])
        someone_elses = self.make_event(status="submitted",
                                        coordinator_id=self.make_user(role="coordinator").id)
        draft = self.make_event(status="draft")

        for method, url in (("post", f"/api/events/{someone_elses.id}/review"),
                            ("post", f"/api/events/{someone_elses.id}/confirm"),
                            ("get", f"/api/events/drafts/{draft.id}")):
            with self.subTest(url=url):
                response = getattr(self.client, method)(url, headers=self.auth_headers(user))
                self.assertEqual(response.status_code, 403, response.get_json())
        self.db.session.expire_all()
        self.assertEqual(self.db.session.get(Event, someone_elses.id).status, "submitted")

    # TC-76-12 · lists of people with a role include those holding it as another role: the
    # Lead's eligible coordinators, and the Venue Staff told of a cancelled booking.
    def test_people_with_a_role_include_those_holding_it_as_another_role(self):
        lead = self.make_user(role="coordinator_lead")
        main = self.make_user(role="coordinator")
        other = self.make_user(role="venue_staff", additional_roles=["coordinator"])
        neither = self.make_user(role="venue_staff", additional_roles=["attendee"])
        waiting = self.make_event(status="submitted")

        response = self.client.get(f"/api/events/{waiting.id}/assignment",
                                   headers=self.auth_headers(lead))

        self.assertEqual(response.status_code, 200, response.get_json())
        listed = {coordinator["id"] for coordinator in response.get_json()["coordinators"]}
        self.assertLessEqual({main.id, other.id}, listed)
        self.assertNotIn(neither.id, listed)
        mine = {main.id, other.id, neither.id}
        staff = {user.id for user in User.query.filter(holding({"venue_staff"}))} & mine
        self.assertEqual(staff, {other.id, neither.id})

    # TC-76-13 · roles are read from the database on every request, so adding or removing
    # one applies to a token issued before the change.
    def test_a_changed_role_applies_to_an_existing_token(self):
        user = self.make_user(role="organiser")
        headers = self.auth_headers(user)
        self.assertEqual(self.client.get("/api/venues/bookings", headers=headers).status_code, 403)

        user.additional_roles = ["venue_staff"]
        self.db.session.commit()
        self.assertEqual(self.client.get("/api/venues/bookings", headers=headers).status_code, 200)

        user.additional_roles = None
        self.db.session.commit()
        self.assertEqual(self.client.get("/api/venues/bookings", headers=headers).status_code, 403)



# ---------- TC-76-14: every role check ----------


def _status(code):
    return lambda response: response.status_code == code


def _not_refused(response):
    return response.status_code != 403


class EveryRoleCheckTests(RolesTestCase):
    """Every place that checks a role accepts it held as another role: refused while the
    user does not hold it, allowed once it is added to their other roles."""

    def assert_checked(self, role, request, allowed):
        """`request(user)` sets up any rows the user needs and returns a call taking headers."""
        user = self.make_user(role="organiser" if role == "attendee" else "attendee")
        call = request(user)
        headers = self.auth_headers(user)
        refused = call(headers)
        self.assertFalse(allowed(refused), refused.get_json())
        user.additional_roles = [role]
        self.db.session.commit()
        granted = call(headers)
        self.assertTrue(allowed(granted), granted.get_json())

    def get(self, url):
        return lambda user: lambda headers: self.client.get(url, headers=headers)

    def post(self, url, body=None):
        return lambda user: lambda headers: self.client.post(url, json=body or {},
                                                             headers=headers)

    def own(self, user, link):
        """An approved event next week whose coordinator or organiser is `user`."""
        return self.make_published_event(
            status="submitted" if link == "coordinator_id" else "approved",
            **({"coordinator_id": user.id} if link == "coordinator_id" else {"organiser": user}))

    def test_every_role_check_accepts_a_role_held_as_another_role(self):
        published = self.make_published_event()
        draft = self.make_event(status="draft")
        venue = self.make_venue()
        booking = VenueBooking(venue_id=venue.id, event_id=published.id, status="pending",
                               start_time=published.start_time, end_time=published.end_time)
        self.db.session.add(booking)
        self.db.session.commit()

        def start_review(user):
            url = f"/api/events/{self.own(user, 'coordinator_id').id}/review"
            return lambda headers: self.client.post(url, headers=headers)

        def change_form(user):
            url = f"/api/events/{self.own(user, 'organiser_id').id}/change-requests"
            return lambda headers: self.client.get(url, headers=headers)

        cases = [
            ("safety_officer", self.get("/api/events/safety-checks"), _status(200)),
            ("safety_officer", self.post(f"/api/events/{published.id}/safety-checks/approve"),
             _not_refused),
            ("safety_officer", self.post(f"/api/events/{published.id}/safety-checks/reject",
                                         {"comment": "The exits are blocked."}), _not_refused),
            ("organiser", self.post("/api/events/drafts", {"title": "Mine"}), _status(201)),
            ("coordinator", self.get("/api/events/review-requests"), _status(200)),
            ("coordinator", self.get("/api/events/managed"), _status(200)),
            ("organiser", self.get("/api/events/organised"), _status(200)),
            ("coordinator", self.get("/api/events/managed/registrations"), _status(200)),
            ("admin", self.get(f"/api/events/{draft.id}"), _status(200)),
            ("attendee", self.get(f"/api/events/{published.id}"),
             lambda response: response.get_json()["event"]["register_blocked_reason"]
             != "not_attendee"),
            ("coordinator", self.get("/api/events/change-requests"), _status(200)),
            ("coordinator", start_review, _status(200)),
            ("coordinator_lead", self.get("/api/events/queue"), _status(200)),
            ("organiser", change_form, _status(200)),
            ("venue_staff", self.get(f"/api/events/{published.id}/coordinator"), _status(200)),
            ("tech_staff", self.get("/api/events/equipment-requests"), _status(200)),
            ("venue_staff", self.get("/api/venues/"), _status(200)),
            ("venue_staff", self.get(f"/api/venues/{venue.id}/unavailable"), _status(200)),
            ("venue_staff", self.post(f"/api/venues/{venue.id}/unavailable"), _not_refused),
            ("venue_staff", self.get("/api/venues/replacement-needed"), _status(200)),
            ("venue_staff", self.post(f"/api/venues/bookings/{booking.id}/reject"), _not_refused),
            ("attendee", self.post("/api/registrations/", {"event_id": published.id}),
             _status(201)),
        ]
        for index, (role, request, allowed) in enumerate(cases):
            with self.subTest(case=index, role=role):
                self.assert_checked(role, request, allowed)

    # The event's coordinator holding the role as another role still counts: the organiser
    # can answer their question and resubmit (SCRUM-95).
    def test_a_coordinator_holding_the_role_as_another_role_can_be_answered(self):
        organiser = self.make_user(role="organiser")
        coordinator = self.make_user(role="venue_staff")
        event = self.make_published_event(status="under_review", organiser=organiser,
                                          coordinator_id=coordinator.id)
        self.db.session.add(EventClarification(event_id=event.id, sender_id=coordinator.id,
                                               message="Who staffs the accessible entrance?"))
        self.db.session.commit()
        url = f"/api/events/{event.id}/resubmit"
        body = {"message": "Our own staff, all day."}

        with mock.patch.object(tasks.send_notification_email, "delay"):
            refused = self.client.post(url, json=body, headers=self.auth_headers(organiser))
            coordinator.additional_roles = ["coordinator"]
            self.db.session.commit()
            allowed = self.client.post(url, json=body, headers=self.auth_headers(organiser))

        self.assertEqual(refused.status_code, 409, refused.get_json())
        self.assertEqual(allowed.status_code, 200, allowed.get_json())

    # Venue Staff holding the role as another role are told of a cancelled booking (SCRUM-94).
    def test_venue_staff_holding_the_role_as_another_role_are_notified(self):
        coordinator = self.make_user(role="coordinator")
        staff = self.make_user(role="tech_staff", additional_roles=["venue_staff"])
        event = self.make_published_event(coordinator_id=coordinator.id)
        venue = self.make_venue()
        booking = VenueBooking(venue_id=venue.id, event_id=event.id, status="pending",
                               start_time=event.start_time, end_time=event.end_time)
        self.db.session.add(booking)
        self.db.session.commit()

        with mock.patch.object(tasks.send_notification_email, "delay"):
            response = self.client.post(f"/api/venues/bookings/{booking.id}/cancel", json={},
                                        headers=self.auth_headers(coordinator))

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(Notification.query.filter_by(recipient_id=staff.id,
                                                      event_id=event.id).count(), 1)


if __name__ == "__main__":
    unittest.main()
