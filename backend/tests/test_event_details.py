"""Tests for SCRUM-74 "View event details".

Written test-first: they fail until the feature is built (TDD, red).

Each test names the case it automates from
docs/test-cases/SCRUM-74-view-event-details.md (TC-74-nn) and the acceptance
criteria it checks. Assumptions A1-A12 and questions Q1-Q6 are there.

Endpoints (JWT required, else 401)
    GET /api/events/
        200 {"events": [item], "message": str | null}
        item = {"id", "title", "start_time", "end_time", "registration_state"}
        The public catalogue: only published ("approved") events, soonest first, for
        every role. message is set only when the list is empty.
    GET /api/events/<id>
        200 {"event": {
                 "id", "title", "description" | null, "status",
                 "start_time", "end_time",              naive Singapore time, ISO 8601
                 "venue": {"name", "location" | null} | null,
                 "registration": {"state": "open" | "closed" | "full",
                                  "opens_at" | null, "closes_at" | null,
                                  "capacity" | null, "registered_count",
                                  "slots_remaining" | null},
                 "my_registration": {"id", "status"} | null,   registered only
                 "can_register": bool,
                 "register_blocked_reason": null | "already_registered" | "closed" | "full"
                                            | "not_attendee",
                 "can_request_reassignment": bool}}      (SCRUM-61)
        404 {"error": "Event not found."}   unknown, malformed or not visible to the caller
    A published event (since SCRUM-45 was reopened on 18 Oct 2026, the status that takes
    registrations: "approved") is visible to every signed-in user. Any other status is visible
    only to its organiser, its assigned coordinator and admins; everyone else gets
    exactly the 404 an unknown ID gets, so the two cannot be told apart.

"Now" is app.events.routes.singapore_now(), patched here to a fixed time. The
registration endpoints (SCRUM-45, SCRUM-68) use their own clock, patched to the same time.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token

from app.events import routes as event_routes
from app.models import Event, Registration
from app.registrations import routes as registration_routes
from tests import seed_data
from tests.base import AppTestCase

# Singapore time.
NOW = datetime(2026, 11, 5, 12, 0)
OPENS = datetime(2026, 11, 1, 0, 0)
CLOSES = datetime(2026, 11, 15, 0, 0)

EXTRA_ATTENDEES = [
    {"key": "ivy", "email": "ivy.attendee@connectsphere.test", "role": "attendee"},
    {"key": "jon", "email": "jon.attendee@connectsphere.test", "role": "attendee"},
    {"key": "kim", "email": "kim.attendee@connectsphere.test", "role": "attendee"},
]

# Every DT-SEED event has these unless its row says otherwise.
EVENT_DEFAULTS = {
    "status": "approved",
    "description": "Open house for O-Level chemistry",
    "start_time": datetime(2026, 11, 20, 10, 0),
    "end_time": datetime(2026, 11, 20, 12, 0),
    "registration_required": True,
    "registration_opens_at": OPENS,
    "registration_closes_at": CLOSES,
    "registration_capacity": 5,
}

# DT-SEED. Every event is organised by dana and coordinated by alice.
EVENTS = {
    "E1": {"title": "Chem Open House", "venue": True},
    "E2": {"title": "Closed Fair",
           "registration_opens_at": datetime(2026, 9, 1, 0, 0),
           "registration_closes_at": datetime(2026, 9, 30, 0, 0)},
    "E3": {"title": "Draft Workshop", "status": "draft"},
    "E4": {"title": "Pending Talk", "status": "submitted"},
    "E5": {"title": "Review Panel", "status": "under_review"},
    "E6": {"title": "Rejected Rally", "status": "rejected"},
    "E7": {"title": "Last Place Gala", "registration_capacity": 2},
    "E8": {"title": "Full House", "registration_capacity": 2},
    "E9": {"title": "No Details Yet", "description": None},
    "E10": {"title": "Blank Details", "description": "   "},
    # No story sets "confirmed"; it no longer publishes an event (SCRUM-45, 18 Oct 2026).
    "E11": {"title": "Confirmed Expo", "status": "confirmed"},
}

# (event, attendee, status).
REGISTRATIONS = [
    ("E1", "ivy", "registered"),
    ("E1", "jon", "registered"),
    ("E1", "kim", "withdrawn"),
    ("E2", "jon", "registered"),
    ("E2", "kim", "cancelled"),
    ("E7", "jon", "registered"),
    ("E8", "jon", "registered"),
    ("E8", "kim", "registered"),
]

NOT_PUBLISHED = {"E3": "draft", "E4": "submitted", "E5": "under_review", "E6": "rejected",
                 "E11": "confirmed"}
NOT_FOUND = {"error": "Event not found."}


class DetailsTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS + EXTRA_ATTENDEES)
        self.venue = self.make_venue(name="Seminar Room 2", capacity=40,
                                     location="SMU Library, 70 Stamford Rd")
        self.events = {}
        for key, row in EVENTS.items():
            row = dict(row)
            venue = self.venue if row.pop("venue", False) else None
            self.events[key] = Event(
                organiser_id=self.users["dana"].id,
                coordinator_id=self.users["alice"].id,
                venue_id=venue.id if venue else None,
                **{**EVENT_DEFAULTS, **row})
        self._insert(Event, list(self.events.values()))
        self.registrations = {}
        for index, (event_key, user_key, status) in enumerate(REGISTRATIONS):
            registration = Registration(
                event_id=self.events[event_key].id, attendee_id=self.users[user_key].id,
                status=status, registered_at=datetime(2026, 10, 20, 9, 0) + timedelta(minutes=index))
            self.db.session.add(registration)
            self.db.session.commit()
            self.registrations[(event_key, user_key)] = registration

        for module in (event_routes, registration_routes):
            patcher = mock.patch.object(module, "singapore_now", return_value=NOW)
            patcher.start()
            self.addCleanup(patcher.stop)

    # ---------- Arranging ----------

    def set_now(self, now):
        """Move the clock of every module that reads it."""
        for module in (event_routes, registration_routes):
            module.singapore_now.return_value = now

    def update_event(self, key, **fields):
        event = self.db.session.get(Event, self.events[key].id)
        for name, value in fields.items():
            setattr(event, name, value)
        self.db.session.commit()

    # ---------- Requests ----------

    def details(self, event_key="E1", as_user="farah", headers=None, url=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get(url or f"/api/events/{self.events[event_key].id}", headers=headers)

    def listing(self, as_user="farah", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get("/api/events/", headers=headers)

    def event_of(self, event_key="E1", as_user="farah"):
        response = self.details(event_key, as_user)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["event"]

    def seeded_items(self, as_user="farah"):
        """The list entries that belong to this test's events, by event key."""
        response = self.listing(as_user)
        self.assertEqual(response.status_code, 200, response.get_json())
        keys = {event.id: key for key, event in self.events.items()}
        return {keys[item["id"]]: item for item in response.get_json()["events"]
                if item["id"] in keys}

    # ---------- Assertions ----------

    def assert_not_found(self, response):
        self.assertEqual(response.status_code, 404, response.get_data(as_text=True))
        self.assertEqual(response.get_json(), NOT_FOUND)


# ---------- AC1: the list and the way in ----------


class ListTests(DetailsTestCase):
    # TC-74-01 · AC1 — an attendee finds a published event in the list and opens it.
    def test_attendee_opens_an_event_from_the_list(self):
        items = self.seeded_items("farah")

        self.assertIn("E1", items)
        self.assertEqual(items["E1"]["title"], "Chem Open House")
        self.assertEqual(set(items["E1"]), {"id", "title", "start_time", "end_time",
                                            "registration_state"})
        opened = self.details("E1", "farah", url=f"/api/events/{items['E1']['id']}")
        self.assertEqual(opened.status_code, 200, opened.get_json())
        self.assertEqual(opened.get_json()["event"]["title"], "Chem Open House")

    # TC-74-01 · AC1 — every signed-in role can use the list and open an event.
    def test_every_role_can_view_a_published_event(self):
        for name in ("farah", "dana", "alice", "gus", "hana", "admin"):
            with self.subTest(user=name):
                self.assertIn("E1", self.seeded_items(name))
                self.assertEqual(self.details("E1", name).status_code, 200)

    # TC-74-01 · AC1 — the list is soonest first and shows each event's registration state.
    def test_list_is_soonest_first_with_registration_state(self):
        self.update_event("E7", start_time=datetime(2026, 11, 10, 9, 0),
                          end_time=datetime(2026, 11, 10, 11, 0))

        items = self.seeded_items("farah")

        order = [key for key, _ in sorted(items.items(), key=lambda kv: kv[1]["start_time"])]
        self.assertLess(order.index("E7"), order.index("E1"))
        ids = [item["id"] for item in self.listing("farah").get_json()["events"]]
        self.assertLess(ids.index(items["E7"]["id"]), ids.index(items["E1"]["id"]))
        self.assertEqual(items["E1"]["registration_state"], "open")
        self.assertEqual(items["E2"]["registration_state"], "closed")
        self.assertEqual(items["E8"]["registration_state"], "full")


# ---------- AC2: what the page shows ----------


class FieldTests(DetailsTestCase):
    # TC-74-02 · AC2 — every required field, in the agreed shape.
    def test_all_required_fields_are_shown(self):
        event = self.event_of("E1", "farah")

        self.assertEqual(event, {
            "id": self.events["E1"].id,
            "title": "Chem Open House",
            "description": "Open house for O-Level chemistry",
            "status": "approved",
            "start_time": "2026-11-20T10:00:00",
            "end_time": "2026-11-20T12:00:00",
            "venue": {"name": "Seminar Room 2", "location": "SMU Library, 70 Stamford Rd"},
            "registration": {
                "state": "open",
                "opens_at": "2026-11-01T00:00:00",
                "closes_at": "2026-11-15T00:00:00",
                "capacity": 5,
                "registered_count": 2,
                "slots_remaining": 3,
            },
            "my_registration": None,
            "can_register": True,
            "register_blocked_reason": None,
            "can_request_reassignment": False,
        })

    # TC-74-12 · AC8 — missing optional fields come back as null, never blank text.
    def test_empty_optional_fields_are_null(self):
        for key in ("E9", "E10"):
            with self.subTest(event=key):
                event = self.event_of(key, "farah")

                self.assertIsNone(event["description"])
                self.assertIsNone(event["venue"])

    # TC-74-12 · AC8 — a venue with no recorded location still shows its name.
    def test_venue_without_a_location(self):
        venue = self.make_venue(name="Pop-up Tent", location=None)
        self.update_event("E9", venue_id=venue.id)

        event = self.event_of("E9", "farah")

        self.assertEqual(event["venue"], {"name": "Pop-up Tent", "location": None})

    # TC-74-16 · AC11 — times are Singapore time as recorded: no offset, no conversion.
    def test_times_are_singapore_time_as_recorded(self):
        self.update_event("E1", start_time=datetime(2026, 11, 20, 23, 30),
                          end_time=datetime(2026, 11, 21, 1, 0))

        event = self.event_of("E1", "farah")
        item = self.seeded_items("farah")["E1"]

        for value in (event["start_time"], event["end_time"], item["start_time"],
                      item["end_time"], event["registration"]["opens_at"]):
            self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
        self.assertEqual(event["start_time"], "2026-11-20T23:30:00")
        self.assertEqual(item["start_time"], event["start_time"])
        self.assertEqual(item["end_time"], event["end_time"])


# ---------- AC3, AC4: who may see which event ----------


class VisibilityTests(DetailsTestCase):
    # TC-74-03 · AC3 — a draft is not listed and its link looks like an unknown event.
    def test_attendee_cannot_see_a_draft(self):
        self.assertNotIn("E3", self.seeded_items("farah"))

        response = self.details("E3", "farah")

        self.assert_not_found(response)
        self.assertNotIn("Draft Workshop", response.get_data(as_text=True))
        unknown = self.details(url=f"/api/events/{self.missing_id(Event)}")
        self.assertEqual(response.get_data(), unknown.get_data())
        self.assertEqual(response.status_code, unknown.status_code)

    # TC-74-04 · AC3 — pending, under review and rejected events are hidden too.
    def test_attendee_cannot_see_pending_or_rejected_events(self):
        for key, status in NOT_PUBLISHED.items():
            with self.subTest(status=status):
                self.assertNotIn(key, self.seeded_items("farah"))

                self.assert_not_found(self.details(key, "farah"))

    # TC-74-04 · AC3 — the public list never shows them, whoever asks.
    def test_list_shows_published_events_only(self):
        for name in ("farah", "dana", "alice", "admin"):
            with self.subTest(user=name):
                items = self.seeded_items(name)

                self.assertTrue(set(items).isdisjoint(NOT_PUBLISHED))

    # TC-74-05 · AC4 — the organiser, the assigned coordinator and admins see their own unpublished event.
    def test_creator_and_approvers_can_see_unpublished_events(self):
        for name in ("dana", "alice", "admin"):
            for key, status in NOT_PUBLISHED.items():
                with self.subTest(user=name, status=status):
                    event = self.event_of(key, name)

                    self.assertEqual(event["status"], status)
                    self.assertEqual(event["title"], EVENTS[key]["title"])

    # TC-74-05 · AC4 — but not other organisers, other coordinators or staff.
    def test_other_users_cannot_see_unpublished_events(self):
        for name in ("evan", "ben", "gus", "hana", "farah"):
            with self.subTest(user=name):
                self.assert_not_found(self.details("E3", name))
                self.assert_not_found(self.details("E4", name))


# ---------- AC5: Open, Closed or Full ----------


class RegistrationStateTests(DetailsTestCase):
    # TC-74-06 · AC5 — one place left is still Open.
    def test_one_place_left_is_open(self):
        registration = self.event_of("E7", "farah")["registration"]

        self.assertEqual(registration["state"], "open")
        self.assertEqual(registration["registered_count"], 1)
        self.assertEqual(registration["slots_remaining"], 1)

    # TC-74-07 · AC5 — no places left is Full.
    def test_no_places_left_is_full(self):
        event = self.event_of("E8", "farah")

        self.assertEqual(event["registration"]["state"], "full")
        self.assertEqual(event["registration"]["slots_remaining"], 0)
        self.assertEqual(event["registration"]["registered_count"], 2)
        self.assertIs(event["can_register"], False)

    # TC-74-07 · AC5 — only registered attendees take places, never cancelled or withdrawn ones.
    def test_only_registered_attendees_take_places(self):
        self.assertEqual(self.event_of("E2", "farah")["registration"]["registered_count"], 1)
        self.assertEqual(self.event_of("E1", "farah")["registration"]["registered_count"], 2)

    # TC-74-08 · AC5 — outside the registration period it is Closed, even with places left.
    def test_outside_the_period_is_closed_even_with_places_left(self):
        registration = self.event_of("E2", "farah")["registration"]

        self.assertEqual(registration["state"], "closed")
        self.assertEqual(registration["slots_remaining"], 4)

    # TC-74-08 · AC5 — boundaries: open from the opening time up to, not including, the closing time.
    def test_period_boundaries(self):
        cases = [
            (OPENS - timedelta(minutes=1), "closed"),
            (OPENS, "open"),
            (CLOSES - timedelta(minutes=1), "open"),
            (CLOSES, "closed"),
        ]
        for now, state in cases:
            with self.subTest(now=now):
                self.set_now(now)

                self.assertEqual(self.event_of("E1", "farah")["registration"]["state"], state)

    # TC-74-08 · AC5 — Closed beats Full once the period is over.
    def test_closed_beats_full(self):
        self.set_now(CLOSES)

        self.assertEqual(self.event_of("E8", "farah")["registration"]["state"], "closed")

    # TC-74-08 · AC5 — registration not set up: Closed, with no places shown.
    def test_registration_that_is_not_set_up_is_closed(self):
        self.update_event("E1", registration_capacity=None)

        registration = self.event_of("E1", "farah")["registration"]

        self.assertEqual(registration["state"], "closed")
        self.assertIsNone(registration["capacity"])
        self.assertIsNone(registration["slots_remaining"])
        self.update_event("E1", registration_capacity=5, registration_required=None)
        self.assertEqual(self.event_of("E1", "farah")["registration"]["state"], "closed")
        self.update_event("E1", registration_required=True, registration_closes_at=None)
        self.assertEqual(self.event_of("E1", "farah")["registration"]["state"], "closed")


# ---------- AC6: my registration ----------


class MyRegistrationTests(DetailsTestCase):
    # TC-74-09 · AC6 — a registered attendee sees their own status.
    def test_registered_attendee_sees_their_status(self):
        event = self.event_of("E1", "ivy")

        self.assertEqual(event["my_registration"],
                         {"id": self.registrations[("E1", "ivy")].id, "status": "registered"})

    # TC-74-09 · AC6 — a cancelled registration is not "your registration" (there is no
    # waiting list since SCRUM-45 was reopened on 18 Oct 2026).
    def test_cancelled_registration_is_not_shown(self):
        event = self.event_of("E2", "kim")

        self.assertIsNone(event["my_registration"])

    # TC-74-10 · AC6 — an unregistered attendee sees nothing, and nobody else's details.
    def test_unregistered_attendee_sees_no_registration(self):
        response = self.details("E1", "farah")

        event = response.get_json()["event"]
        self.assertIsNone(event["my_registration"])
        text = response.get_data(as_text=True)
        for name in ("ivy", "jon"):
            self.assertNotIn(self.users[name].email, text)

    # TC-74-10 · AC6 — a withdrawn registration is not "your registration".
    def test_withdrawn_registration_is_not_shown(self):
        self.assertIsNone(self.event_of("E1", "kim")["my_registration"])


# ---------- AC9: slots follow registering ----------


class SlotsTests(DetailsTestCase):
    # TC-74-13 · AC9 — registering takes a place. (Withdrawing gives it back: SCRUM-68.)
    def test_slots_remaining_follows_registering(self):
        farah = self.auth_headers(self.users["farah"])
        self.assertEqual(self.event_of("E1", "farah")["registration"]["slots_remaining"], 3)

        registered = self.client.post("/api/registrations/", headers=farah,
                                      json={"event_id": self.events["E1"].id})
        self.assertEqual(registered.status_code, 201, registered.get_json())
        event = self.event_of("E1", "farah")
        self.assertEqual(event["registration"]["slots_remaining"], 2)
        self.assertEqual(event["my_registration"]["status"], "registered")
        self.assertEqual(self.seeded_items("farah")["E1"]["registration_state"], "open")


# ---------- AC10: the Register button ----------


class RegisterButtonTests(DetailsTestCase):
    # TC-74-14 · AC10 — open, with space, not registered: Register is offered.
    def test_register_is_offered_when_registration_is_possible(self):
        event = self.event_of("E1", "farah")

        self.assertIs(event["can_register"], True)
        self.assertIsNone(event["register_blocked_reason"])

    # TC-74-15 · AC10 — each blocking reason has its own message code.
    def test_register_is_replaced_by_the_reason(self):
        cases = [
            ("E1", "ivy", "already_registered"),
            ("E8", "farah", "full"),
            ("E2", "farah", "closed"),
            # Already registered wins over full: they should see their status.
            ("E8", "jon", "already_registered"),
        ]
        for key, user, reason in cases:
            with self.subTest(event=key, user=user):
                event = self.event_of(key, user)

                self.assertIs(event["can_register"], False)
                self.assertEqual(event["register_blocked_reason"], reason)

    # TC-74-15 · AC10 — only attendees register (SCRUM-45 A1).
    def test_only_attendees_are_offered_register(self):
        for name in ("dana", "alice", "admin", "gus"):
            with self.subTest(user=name):
                event = self.event_of("E1", name)

                self.assertIs(event["can_register"], False)
                self.assertEqual(event["register_blocked_reason"], "not_attendee")


# ---------- AC7: unknown and malformed IDs ----------


class NotFoundTests(DetailsTestCase):
    # TC-74-11 · AC7 — an ID no event has.
    def test_unknown_event_is_not_found(self):
        self.assert_not_found(self.details(url=f"/api/events/{self.missing_id(Event)}"))

    # TC-74-11 · AC7 — malformed or out-of-range IDs never show an error trace or database error.
    def test_malformed_ids_do_not_leak_errors(self):
        for label, path in {
            "quote and comment": "/api/events/abc%27--",
            "word": "/api/events/not-an-id",
            "negative": "/api/events/-1",
            "too large for the database": "/api/events/99999999999999999999",
            "just over the database limit": "/api/events/2147483648",
        }.items():
            with self.subTest(id=label):
                response = self.details(url=path)

                self.assertEqual(response.status_code, 404, response.get_data(as_text=True))
                text = response.get_data(as_text=True).lower()
                for leak in ("traceback", "sqlalchemy", "psycopg", "select ", "syntax error"):
                    self.assertNotIn(leak, text)


# ---------- AC12: signed-out users ----------


class SignedOutTests(DetailsTestCase):
    # TC-74-17 · AC12 — no token, an expired token and a deleted user's token.
    def test_signed_out_users_get_401(self):
        ghost = self.make_user(role="attendee")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["farah"].id),
                                      expires_delta=timedelta(seconds=-1))
        cases = {
            "no token": {},
            "expired": {"Authorization": f"Bearer {expired}"},
            "deleted user": ghost_headers,
        }
        for label, headers in cases.items():
            with self.subTest(session=label):
                self.assertEqual(self.details("E1", headers=headers).status_code, 401)
                self.assertEqual(self.listing(headers=headers).status_code, 401)
        text = self.client.get(f"/api/events/{self.events['E1'].id}").get_data(as_text=True)
        self.assertNotIn("Chem Open House", text)


if __name__ == "__main__":
    unittest.main()
