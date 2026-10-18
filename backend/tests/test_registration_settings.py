"""Tests for SCRUM-45 AC7 "The event's coordinator sets up registration".

Added on 19 Oct 2026 after PR review: nothing set an event's capacity or registration
period, so registration could never open. The team decided the event's coordinator
sets them. Each test names the case it automates from
docs/test-cases/SCRUM-45-register-for-event.md (TC-45-nn); assumptions A13-A16 are there.

Endpoints (JWT required, else 401; unknown event 404; the event's coordinator only, else 403)
    GET /api/events/<id>/registration-settings
        200 {"event_id", "capacity", "opens_at", "closes_at", "registered_count",
             "venue_capacity", "can_edit": bool, "message": str | null}
            message explains why the settings can't be changed (can_edit false)
    PUT /api/events/<id>/registration-settings
        body {"capacity": int, "opens_at": "YYYY-MM-DDTHH:MM", "closes_at": "YYYY-MM-DDTHH:MM"}
        200 {"message", <the GET fields>}
        400 {"error", "field"}   a missing or invalid value, or one breaking a rule
        409 {"error", "reason"}  reason: not_approved | registration_not_needed | below_registered
        503 {"error", "retryable": true}
    Times are Singapore time, as recorded.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app.models import Event, Registration
from app.registrations import routes as registration_routes
from tests import seed_data
from tests.base import AppTestCase

START = datetime(2026, 12, 12, 17, 0)
VALID = {"capacity": 50, "opens_at": "2026-11-01T09:00", "closes_at": "2026-12-01T00:00"}

# RS-SEED. Every event is organised by dana and coordinated by alice, and starts at START.
EVENTS = {
    "R1": {"title": "Harbour Lights Festival", "status": "approved", "registration_required": True},
    "R2": {"title": "Winter Networking Night", "status": "approved", "registration_required": True,
           "registration_capacity": 30,
           "registration_opens_at": datetime(2026, 10, 1, 9, 0),
           "registration_closes_at": datetime(2026, 11, 30, 0, 0)},
    "R3": {"title": "Product Launch", "status": "submitted", "registration_required": True},
    "R4": {"title": "Rooftop Cinema", "status": "approved", "registration_required": False},
    "R5": {"title": "Alumni Mixer", "status": "cancelled", "registration_required": True},
}

NOT_COORDINATOR = ["ben", "lena", "dana", "admin", "farah", "gus", "hana"]


class SettingsTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS + seed_data.LEADS)
        # R2's venue holds 40 people.
        self.venue = self.make_venue(name="Seminar Room 2", capacity=40)
        self.events = {
            key: Event(organiser_id=self.users["dana"].id, coordinator_id=self.users["alice"].id,
                       start_time=START, end_time=START + timedelta(hours=5),
                       venue_id=self.venue.id if key == "R2" else None, **row)
            for key, row in EVENTS.items()
        }
        self._insert(Event, list(self.events.values()))
        # Two attendees registered for R2, and one who withdrew (who takes no place).
        for status in ("registered", "registered", "withdrawn"):
            self.db.session.add(Registration(event_id=self.events["R2"].id,
                                             attendee_id=self.make_user(role="attendee").id,
                                             status=status))
        self.db.session.commit()

    # ---------- Requests ----------

    def url(self, key):
        return f"/api/events/{self.events[key].id}/registration-settings"

    def load(self, key="R1", as_user="alice", headers=None):
        return self.client.get(self.url(key), headers=headers or self.auth_headers(self.users[as_user]))

    def save(self, key="R1", body=None, as_user="alice", headers=None, **changes):
        body = {**VALID, **changes} if body is None else body
        return self.client.put(self.url(key), json=body,
                               headers=headers or self.auth_headers(self.users[as_user]))

    # ---------- Reading what was saved ----------

    def stored(self, key):
        self.db.session.expire_all()
        event = self.db.session.get(Event, self.events[key].id)
        return (event.registration_capacity, event.registration_opens_at,
                event.registration_closes_at)

    # ---------- Assertions ----------

    def assert_error(self, response, status_code, **expected):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        for key, value in expected.items():
            self.assertEqual(body.get(key), value, body)
        return body


# ---------- AC7: the coordinator sets up registration ----------


class SettingUpTests(SettingsTestCase):
    # TC-45-24 · AC7 (A13) — the coordinator sets up registration, and attendees can
    # then register (end to end).
    def test_coordinator_sets_up_registration_and_attendees_can_register(self):
        response = self.save()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(self.stored("R1"), (50, datetime(2026, 11, 1, 9, 0),
                                             datetime(2026, 12, 1, 0, 0)))
        self.assertEqual((body["capacity"], body["opens_at"], body["closes_at"]),
                         (50, "2026-11-01T09:00:00", "2026-12-01T00:00:00"))
        self.assertIn("Harbour Lights Festival", body["message"])

        with mock.patch.object(registration_routes, "singapore_now",
                               return_value=datetime(2026, 11, 15, 12, 0)):
            registered = self.client.post("/api/registrations/",
                                          headers=self.auth_headers(self.users["farah"]),
                                          json={"event_id": self.events["R1"].id})
        self.assertEqual(registered.status_code, 201, registered.get_json())

    # TC-45-25 · AC7 — the coordinator sees the current settings.
    def test_coordinator_sees_the_current_settings(self):
        r1 = self.load("R1").get_json()
        r2 = self.load("R2").get_json()

        self.assertEqual(r1, {
            "event_id": self.events["R1"].id, "capacity": None, "opens_at": None,
            "closes_at": None, "registered_count": 0, "venue_capacity": None,
            "can_edit": True, "message": None,
        })
        self.assertEqual(r2, {
            "event_id": self.events["R2"].id, "capacity": 30,
            "opens_at": "2026-10-01T09:00:00", "closes_at": "2026-11-30T00:00:00",
            "registered_count": 2, "venue_capacity": 40, "can_edit": True, "message": None,
        })

    # TC-45-26 · AC7 (A15/Q9) — the settings can be changed later.
    def test_settings_can_be_changed_later(self):
        response = self.save("R2", capacity=35, opens_at="2026-10-15T09:00",
                             closes_at="2026-12-12T17:00")

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.stored("R2"), (35, datetime(2026, 10, 15, 9, 0), START))


# ---------- AC7: the rules for the values ----------


class ValidationTests(SettingsTestCase):
    # TC-45-27 · AC7 (A14) — each value must be present and valid; nothing changes otherwise.
    def test_values_must_be_present_and_valid(self):
        before = self.stored("R1")
        cases = {
            "capacity": [0, -1, "10", True, 1.5, None, 2_147_483_648],
            "opens_at": [None, "", "soon", "2026-02-30T10:00", "2026-11-01", 5],
            "closes_at": [None, "", "2026-12-01T25:00"],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assert_error(self.save(**{field: value}), 400, field=field)
        for field in VALID:
            with self.subTest(missing=field):
                body = {k: v for k, v in VALID.items() if k != field}
                self.assert_error(self.save(body=body), 400, field=field)
        with self.subTest(extra="venue_id"):
            self.assert_error(self.save(body={**VALID, "venue_id": 1}), 400, field="venue_id")
        with self.subTest(body="not JSON"):
            response = self.client.put(self.url("R1"), data="capacity=5",
                                       headers=self.auth_headers(self.users["alice"]))
            self.assert_error(response, 400)
        self.assertEqual(self.stored("R1"), before)

    # TC-45-28 · AC7 (A14) — registration opens before it closes, and closes no later
    # than the event starts.
    def test_period_rules(self):
        before = self.stored("R1")
        for opens, closes in (("2026-11-01T09:00", "2026-11-01T09:00"),
                              ("2026-11-02T09:00", "2026-11-01T09:00"),
                              ("2026-11-01T09:00", "2026-12-12T17:01")):
            with self.subTest(opens=opens, closes=closes):
                self.assert_error(self.save(opens_at=opens, closes_at=closes), 400,
                                  field="closes_at")
        self.assertEqual(self.stored("R1"), before)

        self.assertEqual(self.save(closes_at="2026-12-12T17:00").status_code, 200)

    # TC-45-29 · AC7 (A14) — no more places than the venue holds.
    def test_no_more_places_than_the_venue_holds(self):
        before = self.stored("R2")

        body = self.assert_error(self.save("R2", capacity=41), 400, field="capacity")

        self.assertIn("40", body["error"])
        self.assertEqual(self.stored("R2"), before)
        self.assertEqual(self.save("R2", capacity=40).status_code, 200)

    # TC-45-30 · AC7 (A15) — no fewer places than people already registered.
    def test_no_fewer_places_than_already_registered(self):
        before = self.stored("R2")

        body = self.assert_error(self.save("R2", capacity=1), 409, reason="below_registered")

        self.assertIn("2", body["error"])
        self.assertEqual(self.stored("R2"), before)
        self.assertEqual(self.save("R2", capacity=2).status_code, 200)


# ---------- AC7: which events ----------


class WhichEventsTests(SettingsTestCase):
    # TC-45-31 · AC7 (A16) — only an approved event that needs registration.
    def test_only_approved_events_that_need_registration(self):
        cases = {"R3": "not_approved", "R5": "not_approved", "R4": "registration_not_needed"}
        for key, reason in cases.items():
            before = self.stored(key)
            with self.subTest(event=key, action="save"):
                self.assert_error(self.save(key), 409, reason=reason)
                self.assertEqual(self.stored(key), before)
            with self.subTest(event=key, action="load"):
                body = self.load(key).get_json()
                self.assertIs(body["can_edit"], False)
                self.assertTrue(body["message"].strip())


# ---------- AC7: only the event's coordinator ----------


class AccessTests(SettingsTestCase):
    # TC-45-32 · AC7 (A13) — everyone else is refused and sees no settings.
    def test_only_the_events_coordinator(self):
        before = self.stored("R2")
        for user in NOT_COORDINATOR:
            for action, send in (("load", lambda: self.load("R2", as_user=user)),
                                 ("save", lambda: self.save("R2", as_user=user))):
                with self.subTest(user=user, action=action):
                    body = self.assert_error(send(), 403)
                    self.assertNotIn("capacity", body)
        self.assertEqual(self.stored("R2"), before)

    # TC-45-33 · AC7 — a valid session and an existing event are required, and role
    # changes apply at once.
    def test_session_event_and_current_role_are_required(self):
        before = self.stored("R1")
        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["alice"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                self.assertEqual(self.client.put(self.url("R1"), json=VALID,
                                                 headers=headers).status_code, 401)

        missing = f"/api/events/{self.missing_id(Event)}/registration-settings"
        self.assert_error(self.client.get(missing, headers=self.auth_headers(self.users["alice"])),
                          404)

        alice_headers = self.auth_headers(self.users["alice"])
        self.users["alice"].role = "organiser"
        self.db.session.commit()
        self.assert_error(self.save(headers=alice_headers), 403)
        self.assertEqual(self.stored("R1"), before)


# ---------- AC7: saving fails ----------


class SaveFailureTests(SettingsTestCase):
    # TC-45-34 · AC7 — a failed save changes nothing, and a retry works.
    def test_failed_save_changes_nothing_and_retry_works(self):
        before = self.stored("R1")
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.save()

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not saved")
        self.assertEqual(self.stored("R1"), before)

        self.assertEqual(self.save().status_code, 200)


if __name__ == "__main__":
    unittest.main()
