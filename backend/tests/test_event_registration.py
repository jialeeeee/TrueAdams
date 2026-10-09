"""Tests for SCRUM-45 "Register for an Event".

Each test names the case it automates from
docs/test-cases/SCRUM-45-register-for-event.md (TC-45-nn) and the acceptance
criteria it checks. Assumptions A1-A12 and questions Q1-Q9 are there.

Model (db/event_registration.sql):
    Event.registration_opens_at, registration_closes_at   DateTime, Singapore time
    Event.registration_capacity                           Integer, number of places
    Event.waitlist_enabled                                Boolean
    Registration.status   "registered" | "waitlisted" | "cancelled"
    At most one active ("registered" or "waitlisted") registration per event and attendee.

Endpoint (JWT required, else 401)
    POST /api/registrations/   body {"event_id": int}
        201 {"message", "registration"}                              registered or waitlisted
        200 {"message", "registration", "already_registered": true}  existing active one
        403 not an attendee   400 bad body   404 unknown event
        409 {"error", "reason"}   reason: not_confirmed | disabled | not_open_yet | closed | full
        503 {"error", "retryable": true} if saving fails
    registration = {"id", "event_id", "status", "registered_at"}

"Now" is app.registrations.routes.singapore_now(), patched here to a fixed time.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models import Event, Registration
from app.registrations import routes as registration_routes
from tests import seed_data
from tests.base import AppTestCase

# Singapore time, as registration periods are recorded.
NOW = datetime(2026, 11, 1, 12, 0)
OPENS = datetime(2026, 10, 1, 9, 0)
CLOSES = datetime(2026, 12, 1, 0, 0)

EXTRA_ATTENDEES = [
    {"key": "ivy", "email": "ivy.attendee@connectsphere.test", "role": "attendee"},
    {"key": "jon", "email": "jon.attendee@connectsphere.test", "role": "attendee"},
]

# Every RG-SEED event has these unless its row says otherwise.
EVENT_DEFAULTS = {
    "status": "confirmed",
    "registration_required": True,
    "registration_opens_at": OPENS,
    "registration_closes_at": CLOSES,
    "waitlist_enabled": False,
    "start_time": datetime(2026, 12, 12, 17, 0),
    "end_time": datetime(2026, 12, 12, 22, 0),
}

# RG-SEED. Every event is organised by dana and coordinated by alice.
EVENTS = {
    "E1": {"title": "Harbour Lights Festival", "registration_capacity": 3},
    "E2": {"title": "Winter Networking Night", "registration_capacity": 2,
           "waitlist_enabled": True},
    "E3": {"title": "Product Launch", "registration_capacity": 1},
    "E4": {"title": "Rooftop Cinema", "registration_capacity": 50,
           "registration_required": False},
    "E5": {"title": "Spring Garden Party", "registration_capacity": 50,
           "registration_opens_at": datetime(2026, 11, 15, 9, 0)},
    "E6": {"title": "Alumni Mixer", "registration_capacity": 50,
           "registration_closes_at": datetime(2026, 11, 1, 0, 0)},
    "E7": {"title": "Tech Summit", "registration_capacity": None},
}

# (event, attendee, status) registrations that exist before each test.
REGISTRATIONS = [
    ("E2", "ivy", "registered"),
    ("E2", "jon", "registered"),
    ("E3", "ivy", "registered"),
]

NOT_CONFIRMED = ["draft", "submitted", "under_review", "approved", "rejected", "cancelled"]
NON_ATTENDEES = ["admin", "alice", "dana", "gus", "hana"]


class RegistrationTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS + EXTRA_ATTENDEES)
        self.events = {
            key: Event(organiser_id=self.users["dana"].id,
                       coordinator_id=self.users["alice"].id,
                       **{**EVENT_DEFAULTS, **row})
            for key, row in EVENTS.items()
        }
        self._insert(Event, list(self.events.values()))
        for event_key, user_key, status in REGISTRATIONS:
            self.add_registration(event_key, self.users[user_key], status)

        patcher = mock.patch.object(registration_routes, "singapore_now", return_value=NOW)
        self.clock = patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- Arranging ----------

    def add_registration(self, event_key, attendee, status):
        registration = Registration(event_id=self.events[event_key].id,
                                    attendee_id=attendee.id, status=status)
        self.db.session.add(registration)
        self.db.session.commit()
        return registration

    def update_event(self, key, **fields):
        event = self.db.session.get(Event, self.events[key].id)
        for name, value in fields.items():
            setattr(event, name, value)
        self.db.session.commit()

    # ---------- Requests ----------

    def register(self, event_key="E1", as_user="farah", headers=None, **kwargs):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        if "data" not in kwargs and "json" not in kwargs:
            kwargs["json"] = {"event_id": self.events[event_key].id}
        return self.client.post("/api/registrations/", headers=headers, **kwargs)

    # ---------- Reading what was saved ----------

    def saved(self):
        """Every registration for the seeded events, oldest first, as
        (event key, user key or ID, status)."""
        self.db.session.expire_all()
        event_keys = {event.id: key for key, event in self.events.items()}
        user_keys = {user.id: key for key, user in self.users.items()}
        rows = (Registration.query.filter(Registration.event_id.in_(event_keys))
                .order_by(Registration.id).all())
        return [(event_keys[r.event_id], user_keys.get(r.attendee_id, r.attendee_id), r.status)
                for r in rows]

    def rows_for(self, event_key, user_key):
        self.db.session.expire_all()
        return (Registration.query
                .filter_by(event_id=self.events[event_key].id,
                           attendee_id=self.users[user_key].id)
                .order_by(Registration.id).all())

    # ---------- Assertions ----------

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        return body

    def assert_blocked(self, response, reason):
        body = self.assert_error(response, 409)
        self.assertEqual(body.get("reason"), reason)
        return body

    def assert_registered(self, response, status="registered", code=201):
        self.assertEqual(response.status_code, code, response.get_json())
        body = response.get_json()
        self.assertEqual(body["registration"]["status"], status)
        self.assertIsInstance(body.get("message"), str)
        self.assertTrue(body["message"].strip())
        return body


# ---------- AC1: who can register, and for which events ----------


class EligibilityTests(RegistrationTestCase):
    # TC-45-01 · AC1, AC2 — register for a confirmed, open event with places.
    def test_register_for_a_confirmed_open_event_with_places(self):
        body = self.assert_registered(self.register("E1"))

        self.assertIn("Harbour Lights Festival", body["message"])
        self.assertFalse(body.get("already_registered", False))

    # TC-45-02 · AC1, AC5 (A2/Q2) — only confirmed events accept registrations.
    def test_only_confirmed_events_accept_registrations(self):
        before = self.saved()
        for status in NOT_CONFIRMED:
            with self.subTest(status=status):
                self.update_event("E1", status=status)

                body = self.assert_blocked(self.register("E1"), "not_confirmed")

                self.assertNotIn("Harbour Lights Festival", body["error"])
                self.assertNotIn(status.replace("_", " "), body["error"].lower())
        self.assertEqual(self.saved(), before)

    # TC-45-03 · AC1, AC5 (A3/Q3) — registration disabled.
    def test_registration_disabled(self):
        before = self.saved()
        self.assert_blocked(self.register("E4"), "disabled")

        self.update_event("E4", registration_required=None)
        self.assert_blocked(self.register("E4"), "disabled")

        self.assertEqual(self.saved(), before)

    # TC-45-04 · AC1, AC5 (A4/Q4) — open from the opening time, up to but not
    # including the closing time.
    def test_registration_period_boundaries(self):
        cases = [
            (OPENS - timedelta(minutes=1), "not_open_yet"),
            (OPENS, None),
            (CLOSES - timedelta(minutes=1), None),
            (CLOSES, "closed"),
        ]
        for now, reason in cases:
            with self.subTest(now=now):
                self.clock.return_value = now
                attendee = self.make_user(role="attendee")

                response = self.register("E1", headers=self.auth_headers(attendee))

                if reason:
                    self.assert_blocked(response, reason)
                else:
                    self.assert_registered(response)

    # TC-45-05 · AC1, AC5 (A4/Q4) — not yet open, or already closed.
    def test_not_yet_open_or_already_closed(self):
        before = self.saved()

        body = self.assert_blocked(self.register("E5"), "not_open_yet")
        self.assertRegex(body["error"], r"15 Nov(ember)? 2026")
        self.assert_blocked(self.register("E6"), "closed")

        self.update_event("E1", registration_opens_at=None)
        self.assert_blocked(self.register("E1"), "closed")
        self.update_event("E1", registration_opens_at=OPENS, registration_closes_at=None)
        self.assert_blocked(self.register("E1"), "closed")

        self.assertEqual(self.saved(), before)

    # TC-45-06 · AC1 (A5/Q5) — only registered attendees take places.
    def test_the_last_place_and_what_takes_a_place(self):
        for status in ("registered", "registered", "waitlisted", "cancelled"):
            self.add_registration("E1", self.make_user(role="attendee"), status)

        self.assert_registered(self.register("E1"))

        latecomer = self.make_user(role="attendee")
        self.assert_blocked(self.register("E1", headers=self.auth_headers(latecomer)), "full")

    # TC-45-07 · AC1, AC5 (A5/Q5) — capacity not recorded.
    def test_capacity_not_recorded(self):
        before = self.saved()

        self.assert_blocked(self.register("E7"), "disabled")

        self.assertEqual(self.saved(), before)

    # TC-45-08 · AC1 (A1/Q1, A10) — only attendees can register; the role is
    # checked before the body and the event.
    def test_only_attendees_can_register(self):
        before = self.saved()
        for user in NON_ATTENDEES:
            with self.subTest(user=user):
                self.assert_error(self.register("E1", as_user=user), 403)

        self.assert_error(self.register(as_user="dana", json={"event_id": "x"}), 403)
        self.assert_error(
            self.register(as_user="dana", json={"event_id": self.missing_id(Event)}), 403)
        self.assertEqual(self.saved(), before)

    # TC-45-09 · AC1 (boundary) — access follows role changes.
    def test_access_follows_role_changes(self):
        farah_headers = self.auth_headers(self.users["farah"])
        self.users["farah"].role = "organiser"
        self.db.session.commit()

        self.assert_error(self.register("E1", headers=farah_headers), 403)

        self.assertEqual(self.rows_for("E1", "farah"), [])

    # TC-45-10 · AC1 — a valid session, a valid body and an existing event are required.
    def test_session_body_and_event_are_required(self):
        ghost = self.make_user(role="attendee")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["farah"].id),
                                      expires_delta=timedelta(seconds=-1))
        before = self.saved()

        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                self.assertEqual(self.register("E1", headers=headers).status_code, 401)

        for label, kwargs in {"missing": {"json": {}},
                              "text": {"json": {"event_id": str(self.events["E1"].id)}},
                              "boolean": {"json": {"event_id": True}},
                              "decimal": {"json": {"event_id": 1.5}},
                              "not JSON": {"data": "event_id=1"}}.items():
            with self.subTest(body=label):
                self.assert_error(self.register(**kwargs), 400)

        self.assert_error(self.register(json={"event_id": self.missing_id(Event)}), 404)
        self.assertEqual(self.saved(), before)


# ---------- AC2: exactly one registration, linked to me ----------


class RegistrationRecordTests(RegistrationTestCase):
    # TC-45-11 · AC2 — the registration is saved and linked to the attendee.
    def test_registration_is_saved_and_linked_to_the_attendee(self):
        before = self.saved()

        started = datetime.utcnow()
        body = self.register("E1").get_json()
        finished = datetime.utcnow()

        self.assertEqual(self.saved(), before + [("E1", "farah", "registered")])
        row = self.rows_for("E1", "farah")[0]
        self.assertTrue(started <= row.registered_at <= finished)
        self.assertEqual(body["registration"], {
            "id": row.id,
            "event_id": self.events["E1"].id,
            "status": "registered",
            "registered_at": row.registered_at.isoformat(),
        })


# ---------- AC3: already registered ----------


class AlreadyRegisteredTests(RegistrationTestCase):
    # TC-45-12 · AC3 — registering twice shows the existing registration.
    def test_registering_twice_shows_the_existing_registration(self):
        first = self.register("E1").get_json()["registration"]

        body = self.assert_registered(self.register("E1"), code=200)

        self.assertIs(body.get("already_registered"), True)
        self.assertEqual(body["registration"], first)
        self.assertIn("already", body["message"].lower())
        self.assertIn("Registered", body["message"])
        self.assertEqual(len(self.rows_for("E1", "farah")), 1)

    # TC-45-13 · AC3, AC4 — already on the waiting list.
    def test_already_on_the_waiting_list(self):
        first = self.register("E2").get_json()["registration"]

        body = self.assert_registered(self.register("E2"), status="waitlisted", code=200)

        self.assertIs(body.get("already_registered"), True)
        self.assertEqual(body["registration"], first)
        self.assertIn("Waitlisted", body["message"])
        self.assertEqual(len(self.rows_for("E2", "farah")), 1)

    # TC-45-14 · AC3 (A8) — the existing status is shown even after registration
    # closes or the event fills up.
    def test_existing_status_is_shown_after_registration_closes_or_fills(self):
        ivy_row = self.rows_for("E3", "ivy")[0]
        body = self.assert_registered(self.register("E3", as_user="ivy"), code=200)
        self.assertEqual(body["registration"]["id"], ivy_row.id)

        first = self.register("E1").get_json()["registration"]
        self.update_event("E1", status="cancelled", registration_required=False)
        self.clock.return_value = CLOSES + timedelta(days=1)

        body = self.assert_registered(self.register("E1"), code=200)

        self.assertEqual(body["registration"], first)
        self.assertEqual(len(self.rows_for("E1", "farah")), 1)

    # TC-45-15 · AC3 (A7/Q7) — a cancelled registration does not count.
    def test_a_cancelled_registration_does_not_count(self):
        cancelled = self.add_registration("E1", self.users["farah"], "cancelled")

        body = self.assert_registered(self.register("E1"))

        self.assertNotEqual(body["registration"]["id"], cancelled.id)
        self.assertEqual([r.status for r in self.rows_for("E1", "farah")],
                         ["cancelled", "registered"])

    # TC-45-16 · AC2, AC3 (A7) — the database allows only one active registration.
    def test_database_allows_only_one_active_registration(self):
        for first, second in (("registered", "registered"), ("registered", "waitlisted"),
                              ("waitlisted", "waitlisted")):
            with self.subTest(first=first, second=second):
                attendee = self.make_user(role="attendee")
                self.add_registration("E1", attendee, first)
                self.db.session.add(Registration(event_id=self.events["E1"].id,
                                                 attendee_id=attendee.id, status=second))

                with self.assertRaises(IntegrityError):
                    self.db.session.commit()
                self.db.session.rollback()

        attendee = self.make_user(role="attendee")
        self.add_registration("E1", attendee, "cancelled")
        self.add_registration("E1", attendee, "cancelled")
        self.add_registration("E1", attendee, "registered")


# ---------- AC4: waiting list ----------


class WaitingListTests(RegistrationTestCase):
    # TC-45-17 · AC4 (A6/Q6) — full with a waiting list: added as Waitlisted.
    def test_full_with_a_waiting_list_adds_to_the_waiting_list(self):
        body = self.assert_registered(self.register("E2"), status="waitlisted")

        self.assertIn("Waitlisted", body["message"])
        self.assertIn("full", body["message"].lower())
        registered = [s for event, _, s in self.saved() if event == "E2" and s == "registered"]
        self.assertEqual(len(registered), 2)
        self.assertEqual([r.status for r in self.rows_for("E2", "farah")], ["waitlisted"])

    # TC-45-18 · AC4, AC5 (A6/Q6) — a waiting list does not get around other rules.
    def test_a_waiting_list_does_not_get_around_other_rules(self):
        before = self.saved()

        self.clock.return_value = CLOSES
        self.assert_blocked(self.register("E2"), "closed")

        self.clock.return_value = NOW
        self.update_event("E2", registration_required=False)
        self.assert_blocked(self.register("E2"), "disabled")

        self.update_event("E2", registration_required=True, status="approved")
        self.assert_blocked(self.register("E2"), "not_confirmed")

        self.assertEqual(self.saved(), before)


# ---------- AC5: blocked registrations explain why ----------


class BlockedTests(RegistrationTestCase):
    # TC-45-19 · AC5 — full without a waiting list.
    def test_full_without_a_waiting_list(self):
        before = self.saved()

        body = self.assert_blocked(self.register("E3"), "full")

        self.assertIn("full", body["error"].lower())
        self.assertEqual(self.saved(), before)

    # TC-45-20 · AC5 (A9) — each reason has its own clear message.
    def test_each_reason_has_its_own_message(self):
        self.update_event("E1", status="approved")
        before = self.saved()

        messages = {
            reason: self.assert_blocked(self.register(key), reason)["error"]
            for key, reason in (("E1", "not_confirmed"), ("E4", "disabled"),
                                ("E5", "not_open_yet"), ("E6", "closed"), ("E3", "full"))
        }

        self.assertEqual(len(set(messages.values())), 5, messages)
        self.assertEqual(self.saved(), before)


# ---------- AC6: saving fails ----------


class SaveFailureTests(RegistrationTestCase):
    # TC-45-21 · AC6 (A11) — nothing is created, and a retry works.
    def test_failed_save_creates_nothing_and_retry_works(self):
        before = self.saved()
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.register("E1")

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not saved")
        self.assertRegex(body["error"].lower(), r"try again")
        self.assertEqual(self.saved(), before)

        self.assert_registered(self.register("E1"))
        self.assertEqual(len(self.rows_for("E1", "farah")), 1)


if __name__ == "__main__":
    unittest.main()
