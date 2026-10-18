"""Tests for SCRUM-68 "Event Withdrawal".

Written test-first: they fail until the feature is built (TDD, red), except
TC-68-13, which also guards the existing registration endpoint.

Each test names the case it automates from
docs/test-cases/SCRUM-68-event-withdrawal.md (TC-68-nn) and the acceptance
criteria it checks. Assumptions A1-A11 and questions Q1-Q6 are there.

Model: Registration.status gains "withdrawn" next to "registered" and "cancelled". The
column is a plain varchar(20), so there is no schema change. Only "registered" takes a
place and is active. (SCRUM-45 removed the waiting list on 18 Oct 2026.)

Endpoints (JWT required, else 401; the caller must be an attendee, else 403)
    GET  /api/registrations/
        200 {"active": [item], "history": [item], "message": str | null}
        item = {"id", "event": {"id", "title", "start_time", "end_time", "status"},
                "status", "registered_at", "can_withdraw": bool}
        active = registered, soonest event first; history = every other
        status (withdrawn, cancelled); message is set only when both lists are empty.
    POST /api/registrations/<id>/withdraw
        200 {"message", "registration": {"id", "event_id", "status", "registered_at"},
             "event": {"id", "registered_count", "slots_remaining"}}
        404 unknown registration   403 it belongs to someone else
        409 {"error", "reason"}   reason: already_withdrawn | event_cancelled | event_started
        503 {"error", "retryable": true} if saving fails

A freed place simply becomes available again: there is no waiting list (SCRUM-45, 18 Oct
2026), so withdrawing promotes, notifies and emails nobody (TC-68-14).

"Now" is app.registrations.routes.singapore_now(), patched here to a fixed time.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app import tasks
from app.models import Event, Notification, Registration
from app.registrations import routes as registration_routes
from tests import seed_data
from tests.base import AppTestCase

# Singapore time, as event times are recorded.
NOW = datetime(2026, 10, 13, 12, 0)
OPENS = datetime(2026, 10, 1, 9, 0)
CLOSES = datetime(2026, 11, 19, 0, 0)

EXTRA_ATTENDEES = [
    {"key": "ivy", "email": "ivy.attendee@connectsphere.test", "role": "attendee"},
    {"key": "jon", "email": "jon.attendee@connectsphere.test", "role": "attendee"},
]

# Every WD-SEED event has these unless its row says otherwise.
EVENT_DEFAULTS = {
    "status": "approved",
    "registration_required": True,
    "registration_opens_at": OPENS,
    "registration_closes_at": CLOSES,
    "registration_capacity": 5,
    "start_time": datetime(2026, 11, 20, 10, 0),
    "end_time": datetime(2026, 11, 20, 12, 0),
}

# WD-SEED. Every event is organised by dana and coordinated by alice.
EVENTS = {
    "E1": {"title": "Chem Open House"},
    "E2": {"title": "Biology Fair", "start_time": datetime(2026, 11, 25, 10, 0),
           "end_time": datetime(2026, 11, 25, 12, 0)},
    # Started today at 09:00 and still running at NOW (12:00).
    "E3": {"title": "Ongoing Workshop", "start_time": datetime(2026, 10, 13, 9, 0),
           "end_time": datetime(2026, 10, 13, 17, 0)},
    "E4": {"title": "Cancelled Concert", "status": "cancelled"},
    "E5": {"title": "Robotics Day"},
    "E6": {"title": "Full Gala", "registration_capacity": 2},
    "E8": {"title": "Past Seminar", "start_time": datetime(2026, 9, 1, 10, 0),
           "end_time": datetime(2026, 9, 1, 12, 0)},
}

# (event, attendee, status), in the order they were made.
REGISTRATIONS = [
    ("E1", "farah", "registered"),
    ("E1", "jon", "registered"),
    ("E2", "ivy", "registered"),
    ("E3", "farah", "registered"),
    ("E4", "farah", "registered"),
    ("E5", "farah", "withdrawn"),
    ("E6", "farah", "registered"),
    ("E6", "jon", "registered"),
    ("E8", "farah", "registered"),
]


class WithdrawalTestCase(AppTestCase):
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
        self.registrations = {}
        for index, (event_key, user_key, status) in enumerate(REGISTRATIONS):
            self.registrations[(event_key, user_key)] = self.add_registration(
                event_key, self.users[user_key], status,
                registered_at=datetime(2026, 10, 1, 8, 0) + timedelta(minutes=index))

        patcher = mock.patch.object(registration_routes, "singapore_now", return_value=NOW)
        self.clock = patcher.start()
        self.addCleanup(patcher.stop)
        # No test sends a real email; the mock also records what would have been sent.
        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.email = patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- Arranging ----------

    def add_registration(self, event_key, attendee, status, registered_at=None):
        registration = Registration(event_id=self.events[event_key].id,
                                    attendee_id=attendee.id, status=status,
                                    registered_at=registered_at or datetime(2026, 10, 1, 7, 0))
        self.db.session.add(registration)
        self.db.session.commit()
        return registration

    def reg(self, event_key, user_key):
        return self.registrations[(event_key, user_key)]

    # ---------- Requests ----------

    def withdraw(self, event_key="E1", owner="farah", as_user=None, headers=None, url=None):
        """Withdraw `owner`'s registration for the event, signed in as `as_user` (default: owner)."""
        if headers is None:
            headers = self.auth_headers(self.users[as_user or owner])
        url = url or f"/api/registrations/{self.reg(event_key, owner).id}/withdraw"
        return self.client.post(url, headers=headers)

    def my_registrations(self, as_user="farah", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get("/api/registrations/", headers=headers)

    def register(self, event_key, as_user):
        return self.client.post(
            "/api/registrations/", headers=self.auth_headers(self.users[as_user]),
            json={"event_id": self.events[event_key].id})

    # ---------- Reading what was saved ----------

    def status_of(self, event_key, user_key):
        self.db.session.expire_all()
        return self.db.session.get(Registration, self.reg(event_key, user_key).id).status

    def registered_count(self, event_key):
        self.db.session.expire_all()
        return Registration.query.filter_by(
            event_id=self.events[event_key].id, status="registered").count()

    def statuses(self, event_key):
        """The statuses of every registration of one seeded event, oldest first, by user key."""
        self.db.session.expire_all()
        user_keys = {user.id: key for key, user in self.users.items()}
        rows = (Registration.query.filter_by(event_id=self.events[event_key].id)
                .order_by(Registration.registered_at, Registration.id).all())
        return {(user_keys.get(r.attendee_id, r.attendee_id)): r.status for r in rows}

    def notifications(self):
        """Recipients of every notification about the seeded events, by user key."""
        self.db.session.expire_all()
        user_keys = {user.id: key for key, user in self.users.items()}
        rows = (Notification.query
                .filter(Notification.event_id.in_([e.id for e in self.events.values()]))
                .order_by(Notification.id).all())
        return [user_keys.get(n.recipient_id, n.recipient_id) for n in rows]

    # ---------- Assertions ----------

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        return body

    def assert_refused(self, response, reason):
        body = self.assert_error(response, 409)
        self.assertEqual(body.get("reason"), reason)
        return body

    def assert_withdrawn(self, response):
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["registration"]["status"], "withdrawn")
        self.assertIsInstance(body.get("message"), str)
        self.assertTrue(body["message"].strip())
        return body


# ---------- AC1: my registrations, and only mine ----------


class MyRegistrationsTests(WithdrawalTestCase):
    # TC-68-01 · AC1 — the list holds only the signed-in attendee's registrations.
    def test_list_shows_only_the_signed_in_attendees_registrations(self):
        body = self.my_registrations("ivy").get_json()

        shown = {item["id"] for item in body["active"] + body["history"]}
        self.assertEqual(shown, {self.reg("E2", "ivy").id})
        self.assertIsNone(body["message"])
        titles = {item["event"]["title"] for item in body["active"]}
        self.assertEqual(titles, {"Biology Fair"})
        item = body["active"][0]
        self.assertEqual(set(item), {"id", "event", "status", "registered_at", "can_withdraw"})
        self.assertEqual(set(item["event"]), {"id", "title", "start_time", "end_time", "status"})

        farah = self.my_registrations("farah").get_json()
        farah_ids = {item["id"] for item in farah["active"] + farah["history"]}
        expected = {r.id for (event, user), r in self.registrations.items() if user == "farah"}
        self.assertEqual(farah_ids, expected)

    # TC-68-01 · AC1 — active registrations are listed soonest event first.
    def test_active_registrations_are_listed_soonest_first(self):
        body = self.my_registrations("farah").get_json()

        starts = [item["event"]["start_time"] for item in body["active"]]
        self.assertGreater(len(starts), 1)
        self.assertEqual(starts, sorted(starts))

    # TC-68-01 · AC1 — an attendee with nothing registered is told so.
    def test_no_registrations_gives_a_message(self):
        newcomer = self.make_user(role="attendee")

        body = self.my_registrations(headers=self.auth_headers(newcomer)).get_json()

        self.assertEqual(body["active"], [])
        self.assertEqual(body["history"], [])
        self.assertRegex(body["message"].lower(), r"no registrations")

    # TC-68-02 · AC1 — another attendee's registration cannot be withdrawn.
    def test_attendee_cannot_withdraw_another_attendees_registration(self):
        body = self.assert_error(self.withdraw("E2", owner="ivy", as_user="farah"), 403)

        # The refusal says nothing about whose registration it is or what it is for.
        self.assertNotIn("Biology Fair", body["error"])
        self.assertNotIn(self.users["ivy"].email, body["error"])
        self.assertEqual(self.status_of("E2", "ivy"), "registered")
        ivy = self.my_registrations("ivy").get_json()
        self.assertIn(self.reg("E2", "ivy").id, [item["id"] for item in ivy["active"]])

    # TC-68-02 · AC1 — other roles are refused, and an unknown registration is a 404.
    def test_other_roles_and_unknown_registrations(self):
        for name in ("admin", "dana", "alice", "gus"):
            with self.subTest(user=name):
                self.assert_error(self.my_registrations(name), 403)
                self.assert_error(self.withdraw("E1", owner="farah", as_user=name), 403)
        self.assertEqual(self.status_of("E1", "farah"), "registered")

        missing = f"/api/registrations/{self.missing_id(Registration)}/withdraw"
        self.assert_error(self.withdraw(as_user="farah", url=missing), 404)


# ---------- AC2: when "Withdraw" is offered ----------


class WithdrawActionTests(WithdrawalTestCase):
    def item(self, event_key, user_key, **kwargs):
        body = self.my_registrations(user_key, **kwargs).get_json()
        wanted = self.reg(event_key, user_key).id
        return next(i for i in body["active"] + body["history"] if i["id"] == wanted)

    # TC-68-03 · AC2 — offered for a future event.
    def test_withdraw_is_offered_before_the_event_starts(self):
        self.assertIs(self.item("E1", "farah")["can_withdraw"], True)

    # TC-68-04 · AC2 — not offered once the event has started, ended or been cancelled.
    def test_withdraw_is_not_offered_once_the_event_has_started(self):
        for event_key in ("E3", "E8", "E4"):
            with self.subTest(event=event_key):
                self.assertIs(self.item(event_key, "farah")["can_withdraw"], False)

    # TC-68-04 · AC2 — boundary: offered up to, but not including, the start time.
    def test_withdraw_cut_off_is_the_start_time(self):
        start = EVENT_DEFAULTS["start_time"]
        for now, offered in ((start - timedelta(minutes=1), True), (start, False)):
            with self.subTest(now=now):
                self.clock.return_value = now

                self.assertIs(self.item("E1", "farah")["can_withdraw"], offered)

    # TC-68-09 · AC6 — a withdrawn registration is never offered Withdraw again.
    def test_withdrawn_registration_has_no_withdraw_action(self):
        self.assertIs(self.item("E5", "farah")["can_withdraw"], False)


# ---------- AC4, AC5: confirming a withdrawal ----------


class WithdrawTests(WithdrawalTestCase):
    # TC-68-06 · AC4 — the status becomes withdrawn and the record is kept.
    def test_confirmed_withdrawal_sets_status_to_withdrawn(self):
        before = self.reg("E1", "farah").registered_at

        body = self.assert_withdrawn(self.withdraw("E1", "farah"))

        self.assertIn("Chem Open House", body["message"])
        self.assertEqual(body["registration"]["id"], self.reg("E1", "farah").id)
        self.assertEqual(body["registration"]["event_id"], self.events["E1"].id)
        self.assertEqual(self.status_of("E1", "farah"), "withdrawn")
        self.db.session.expire_all()
        rows = Registration.query.filter_by(event_id=self.events["E1"].id,
                                            attendee_id=self.users["farah"].id).all()
        self.assertEqual(len(rows), 1)  # kept, not deleted
        self.assertEqual(rows[0].registered_at, before)  # the history is not rewritten

    # TC-68-07 · AC5 — the count goes down by one and the response says how many places are left.
    def test_registered_count_and_slots_update(self):
        self.assertEqual(self.registered_count("E1"), 2)

        body = self.assert_withdrawn(self.withdraw("E1", "farah"))

        self.assertEqual(body["event"], {"id": self.events["E1"].id,
                                         "registered_count": 1, "slots_remaining": 4})
        self.assertEqual(self.registered_count("E1"), 1)
        self.assertEqual(self.status_of("E1", "jon"), "registered")

    # TC-68-08 · AC5 — a place freed on a full event can be taken by someone else.
    def test_freed_place_on_a_full_event_can_be_taken(self):
        blocked = self.register("E6", "ivy")
        self.assertEqual(blocked.status_code, 409, blocked.get_json())
        self.assertEqual(blocked.get_json().get("reason"), "full")

        self.assert_withdrawn(self.withdraw("E6", "farah"))

        taken = self.register("E6", "ivy")
        self.assertEqual(taken.status_code, 201, taken.get_json())
        self.assertEqual(taken.get_json()["registration"]["status"], "registered")
        self.assertEqual(self.registered_count("E6"), 2)

    # TC-68-09 · AC6 — the withdrawn registration leaves the active list for the history.
    def test_withdrawn_registration_moves_to_the_history(self):
        before = self.my_registrations("farah").get_json()
        self.assertEqual({i["id"] for i in before["history"]}, {self.reg("E5", "farah").id})
        self.assertIn(self.reg("E1", "farah").id, [i["id"] for i in before["active"]])

        self.assert_withdrawn(self.withdraw("E1", "farah"))

        after = self.my_registrations("farah").get_json()
        self.assertNotIn(self.reg("E1", "farah").id, [i["id"] for i in after["active"]])
        history = {i["id"]: i for i in after["history"]}
        self.assertEqual(set(history), {self.reg("E5", "farah").id, self.reg("E1", "farah").id})
        entry = history[self.reg("E1", "farah").id]
        self.assertEqual(entry["status"], "withdrawn")
        self.assertEqual(entry["event"]["title"], "Chem Open House")
        self.assertIs(entry["can_withdraw"], False)


# ---------- AC7, AC8: refused withdrawals ----------


class RefusedWithdrawalTests(WithdrawalTestCase):
    # TC-68-10 · AC7 — an event that has started or ended.
    def test_withdrawal_after_the_event_has_started_is_rejected(self):
        for event_key in ("E3", "E8"):
            with self.subTest(event=event_key):
                body = self.assert_refused(self.withdraw(event_key, "farah"), "event_started")

                self.assertRegex(body["error"].lower(), r"started|ended")
                self.assertEqual(self.status_of(event_key, "farah"), "registered")
        self.assertEqual(self.notifications(), [])

    # TC-68-10 · AC7 — boundary: allowed one minute before the start, refused at the start.
    def test_withdrawal_boundary_is_the_start_time(self):
        start = EVENT_DEFAULTS["start_time"]

        self.clock.return_value = start - timedelta(minutes=1)
        self.assert_withdrawn(self.withdraw("E1", "farah"))

        self.clock.return_value = start
        self.assert_refused(self.withdraw("E1", "jon"), "event_started")
        self.assertEqual(self.status_of("E1", "jon"), "registered")

    # TC-68-11 · AC7 — a cancelled event.
    def test_withdrawal_from_a_cancelled_event_is_rejected(self):
        body = self.assert_refused(self.withdraw("E4", "farah"), "event_cancelled")

        self.assertRegex(body["error"].lower(), r"cancelled")
        self.assertEqual(self.status_of("E4", "farah"), "registered")

    # TC-68-12 · AC8 — withdrawing twice does not take a second place off the count.
    def test_second_withdrawal_is_rejected_without_a_second_decrement(self):
        self.assert_withdrawn(self.withdraw("E1", "farah"))

        body = self.assert_refused(self.withdraw("E1", "farah"), "already_withdrawn")

        self.assertRegex(body["error"].lower(), r"already")
        self.assertEqual(self.status_of("E1", "farah"), "withdrawn")
        self.assertEqual(self.registered_count("E1"), 1)  # jon only: 1, not 0
        self.assertEqual(self.status_of("E1", "jon"), "registered")


# ---------- AC9: registering again ----------


class RegisterAgainTests(WithdrawalTestCase):
    # TC-68-13 · AC9 (A8/Q4) — a withdrawn registration is not active, so she can register again.
    def test_attendee_can_register_again_after_withdrawing(self):
        response = self.register("E5", "farah")

        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["registration"]["status"], "registered")
        self.db.session.expire_all()
        rows = Registration.query.filter_by(
            event_id=self.events["E5"].id, attendee_id=self.users["farah"].id
        ).order_by(Registration.id).all()
        self.assertEqual([r.status for r in rows], ["withdrawn", "registered"])

    # TC-68-13 · AC9 (A8/Q4) — "if capacity allows": a full event still turns her away.
    def test_registering_again_still_needs_a_free_place(self):
        for _ in range(5):
            self.add_registration("E5", self.make_user(role="attendee"), "registered")

        response = self.register("E5", "farah")

        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(response.get_json().get("reason"), "full")
        self.assertEqual(self.status_of("E5", "farah"), "withdrawn")


# ---------- AC10: no waiting list ----------


class NoWaitingListTests(WithdrawalTestCase):
    # TC-68-14 · AC10 (A9, changed by SCRUM-45 on 18 Oct 2026) — there is no waiting
    # list: the freed place is simply open, and nobody is promoted, notified or emailed.
    def test_withdrawing_promotes_and_notifies_nobody(self):
        body = self.assert_withdrawn(self.withdraw("E6", "farah"))

        self.assertEqual(self.statuses("E6"), {"farah": "withdrawn", "jon": "registered"})
        self.assertEqual(body["event"]["registered_count"], 1)
        self.assertEqual(body["event"]["slots_remaining"], 1)
        self.assertEqual(self.notifications(), [])
        self.email.assert_not_called()


# ---------- AC11: saving fails ----------


class SaveFailureTests(WithdrawalTestCase):
    # TC-68-15 · AC11 — nothing changes, the user is told, a retry works.
    def test_failed_save_leaves_the_registration_unchanged(self):
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.withdraw("E1", "farah")

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"try again")
        self.assertNotIn("simulated outage", body["error"])
        self.assertEqual(self.status_of("E1", "farah"), "registered")
        self.assertEqual(self.registered_count("E1"), 2)

        self.assert_withdrawn(self.withdraw("E1", "farah"))
        self.assertEqual(self.registered_count("E1"), 1)

    # TC-68-15 · AC11 — a failed save changes nothing and sends nothing.
    def test_failed_save_sends_nothing(self):
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            self.assert_error(self.withdraw("E6", "farah"), 503)

        self.assertEqual(self.statuses("E6"), {"farah": "registered", "jon": "registered"})
        self.assertEqual(self.notifications(), [])
        self.email.assert_not_called()

    # TC-68-15 · AC11 — a failed load is a failure, not an empty list.
    def test_failed_load_is_reported_as_a_failure(self):
        with mock.patch.object(self.db.session, "get",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.my_registrations("farah")

        self.assertEqual(response.status_code, 503, response.get_json())
        self.assertIs(response.get_json().get("retryable"), True)


# ---------- AC12: signed-out users ----------


class SignedOutTests(WithdrawalTestCase):
    # TC-68-16 · AC12 — no token, an expired token and a deleted user's token.
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
                self.assertEqual(self.my_registrations(headers=headers).status_code, 401)
                self.assertEqual(self.withdraw("E1", headers=headers).status_code, 401)
        self.assertEqual(self.status_of("E1", "farah"), "registered")
        self.assertNotIn("Chem Open House", self.client.get("/api/registrations/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
