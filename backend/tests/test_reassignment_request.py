"""Tests for SCRUM-61 "Request Event Coordinator reassignment".

Written test-first: they fail until the feature is built (TDD, red).

Each test names the case it automates from
docs/test-cases/SCRUM-61-reassignment-request.md (TC-61-nn) and the acceptance
criteria it checks. Assumptions A1-A12 and questions Q1-Q6 are there.

Model (db/reassignment_requests.sql):
    ReassignmentRequest   id, event_id, requester_id, coordinator_id (the coordinator
                          asked to take over), reason, status, requested_at (naive UTC)
    status is "pending" in this story; accepting and declining are a later story.
    At most one pending request per event (partial unique index).

Endpoints (JWT required, else 401)
    GET  /api/events/<id>/reassignment
        200 {"event": {"id", "title", "status"},
             "coordinators": [{"id", "email"}],
             "pending_request": request | null,
             "can_request": bool,
             "blocked_reason": null | "pending" | "cancelled" | "past" | "no_eligible_coordinators",
             "message": str | null}      message explains any blocked_reason
        404 unknown event   403 caller is not the event's current main coordinator
    POST /api/events/<id>/reassignment   body {"coordinator_id": int, "reason": str}
        201 {"message", "request": request, "notification": {"in_app", "email_queued"}}
        404 unknown event   403 not the current main coordinator
        409 {"error", "reason"}   reason: pending | cancelled | past
        400 {"error", "field"}    coordinator_id or reason missing / wrong type / bad length
        422 {"error"}             the selected user is not an eligible coordinator
        503 {"error", "retryable": true} if saving fails
    request = {"id", "event_id", "requester_id", "coordinator_id", "reason", "status",
               "requested_at"}
    GET  /api/events/<id>  (SCRUM-74) also carries "can_request_reassignment": bool.

Eligibility is decided by events.routes._eligible_coordinators(event), for both the
GET list and the POST check, so the two can never disagree. "Now" is
app.events.routes.singapore_now(), patched here to a fixed time.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app import tasks
from app.events import routes as event_routes
from app.models import Event, Notification, ReassignmentRequest, User
from tests import seed_data
from tests.base import AppTestCase

# Singapore time.
NOW = datetime(2026, 10, 13, 12, 0)
REASON = "Overseas on 20/11/2026"
# Must match REASSIGNMENT_NOTIFICATION in app/events/routes.py.
REASSIGNMENT_NOTIFICATION = "reassignment_requested"
# Must match MAX_REASON_LENGTH in app/events/routes.py (and the frontend page).
MAX_REASON_LENGTH = 500

# Every RR-SEED event is organised by dana and coordinated by alice (the main
# coordinator). ben and chloe are the other coordinators; farah is an attendee.
EVENT_DEFAULTS = {
    "status": "confirmed",
    "start_time": datetime(2026, 11, 20, 10, 0),
    "end_time": datetime(2026, 11, 20, 12, 0),
}

# RR-SEED.
EVENTS = {
    "E1": {"title": "Chem Open House"},
    "E2": {"title": "Cancelled Mixer", "status": "cancelled"},
    "E3": {"title": "Past Seminar",
           "start_time": datetime(2026, 9, 1, 10, 0), "end_time": datetime(2026, 9, 1, 12, 0)},
}


class ReassignmentTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.events = {
            key: Event(organiser_id=self.users["dana"].id,
                       coordinator_id=self.users["alice"].id,
                       coordinator_assigned_at=datetime(2026, 9, 1, 10, 0),
                       **{**EVENT_DEFAULTS, **row})
            for key, row in EVENTS.items()
        }
        self._insert(Event, list(self.events.values()))

        patcher = mock.patch.object(event_routes, "singapore_now", return_value=NOW)
        self.clock = patcher.start()
        self.addCleanup(patcher.stop)
        # No test sends a real email; the mock also records what would have been sent.
        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.email = patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- Arranging ----------

    def ad_hoc_event(self, ends_at):
        """A confirmed event coordinated by alice that ends at `ends_at`."""
        return self.make_event(
            organiser=self.users["dana"], status="confirmed",
            start_time=ends_at - timedelta(hours=2), duration=timedelta(hours=2),
            coordinator_id=self.users["alice"].id,
        )

    def add_pending(self, event_key="E1", requester="alice", target="ben"):
        request = ReassignmentRequest(
            event_id=self.events[event_key].id,
            requester_id=self.users[requester].id,
            coordinator_id=self.users[target].id,
            reason=REASON, status="pending",
        )
        self.db.session.add(request)
        self.db.session.commit()
        return request

    # ---------- Requests ----------

    def url(self, event_key="E1"):
        return f"/api/events/{self.events[event_key].id}/reassignment"

    def view(self, event_key="E1", as_user="alice", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get(self.url(event_key), headers=headers)

    def submit(self, event_key="E1", as_user="alice", coordinator="ben", reason=REASON,
               body=None, headers=None, url=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        if body is None:
            body = {"coordinator_id": self.users[coordinator].id, "reason": reason}
        return self.client.post(url or self.url(event_key), headers=headers, json=body)

    def event_details(self, event_key="E1", as_user="alice"):
        headers = self.auth_headers(self.users[as_user])
        return self.client.get(f"/api/events/{self.events[event_key].id}", headers=headers)

    # ---------- Reading what was saved ----------

    def saved(self):
        """Every request for the seeded events, oldest first, as
        (event key, requester key, target key, reason, status)."""
        self.db.session.expire_all()
        event_keys = {event.id: key for key, event in self.events.items()}
        user_keys = {user.id: key for key, user in self.users.items()}
        rows = (ReassignmentRequest.query
                .filter(ReassignmentRequest.event_id.in_(event_keys))
                .order_by(ReassignmentRequest.id).all())
        return [(event_keys[r.event_id], user_keys.get(r.requester_id),
                 user_keys.get(r.coordinator_id), r.reason, r.status) for r in rows]

    def coordinator_of(self, event_key="E1"):
        self.db.session.expire_all()
        return self.db.session.get(Event, self.events[event_key].id).coordinator_id

    def notifications(self):
        """Reassignment notifications about the seeded events, as (recipient key, event key)."""
        self.db.session.expire_all()
        event_keys = {event.id: key for key, event in self.events.items()}
        user_keys = {user.id: key for key, user in self.users.items()}
        rows = (Notification.query
                .filter(Notification.kind == REASSIGNMENT_NOTIFICATION,
                        Notification.event_id.in_(event_keys))
                .order_by(Notification.id).all())
        return [(user_keys.get(n.recipient_id, n.recipient_id), event_keys[n.event_id])
                for n in rows], rows

    # ---------- Assertions ----------

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        return body


# ---------- AC1: only the current main coordinator ----------


class WhoCanRequestTests(ReassignmentTestCase):
    # TC-61-01 · AC1 — the main coordinator can open the request.
    def test_main_coordinator_can_open_the_request(self):
        response = self.view("E1", "alice")

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["event"]["id"], self.events["E1"].id)
        self.assertEqual(body["event"]["title"], "Chem Open House")
        self.assertTrue(body["can_request"])
        self.assertIsNone(body["blocked_reason"])
        self.assertIsNone(body["pending_request"])
        # The event page uses this to decide whether to show "Request reassignment".
        details = self.event_details("E1", "alice").get_json()
        self.assertIs(details["event"]["can_request_reassignment"], True)

    # TC-61-02 · AC1 — a coordinator who is not assigned to the event cannot.
    def test_unassigned_coordinator_cannot_request(self):
        for name in ("ben", "chloe"):
            with self.subTest(coordinator=name):
                self.assert_error(self.view("E1", name), 403)
                self.assert_error(self.submit("E1", name, coordinator="chloe"), 403)

                details = self.event_details("E1", name).get_json()
                self.assertIs(details["event"]["can_request_reassignment"], False)
        self.assertEqual(self.saved(), [])

    # TC-61-03 · AC1 — other roles cannot; an unknown event is 404 before the role check.
    def test_other_roles_cannot_request(self):
        for name in ("farah", "dana", "admin", "gus"):
            with self.subTest(user=name):
                self.assert_error(self.view("E1", name), 403)
                self.assert_error(self.submit("E1", name), 403)

                details = self.event_details("E1", name)
                if details.status_code == 200:
                    self.assertIs(details.get_json()["event"]["can_request_reassignment"], False)
        self.assertEqual(self.saved(), [])

        missing = f"/api/events/{self.missing_id(Event)}/reassignment"
        farah = self.auth_headers(self.users["farah"])
        self.assert_error(self.client.get(missing, headers=farah), 404)
        self.assert_error(self.submit(headers=farah, url=missing), 404)

    # TC-61-03 · AC1 — the role is read from the database, not from the token.
    def test_access_follows_role_changes(self):
        headers = self.auth_headers(self.users["alice"])  # minted while a coordinator
        self.users["alice"].role = "attendee"
        self.db.session.commit()

        self.assert_error(self.view("E1", headers=headers), 403)
        self.assert_error(self.submit("E1", headers=headers), 403)
        self.assertEqual(self.saved(), [])


# ---------- AC2: who can be selected ----------


class SelectionTests(ReassignmentTestCase):
    # TC-61-04 · AC2 — the list shows the other coordinators, not the requester.
    def test_list_shows_only_eligible_coordinators(self):
        body = self.view("E1", "alice").get_json()

        ids = {c["id"] for c in body["coordinators"]}
        self.assertIn(self.users["ben"].id, ids)
        self.assertIn(self.users["chloe"].id, ids)
        self.assertNotIn(self.users["alice"].id, ids)
        # Never an attendee, organiser or staff member.
        for name in ("farah", "dana", "admin", "gus", "hana"):
            self.assertNotIn(self.users[name].id, ids)
        for coordinator in body["coordinators"]:
            self.assertEqual(set(coordinator), {"id", "email"})

    # TC-61-05 · AC2 — tampering: self, a non-coordinator or an unknown user.
    def test_requester_cannot_select_themselves_or_an_ineligible_user(self):
        cases = {
            "themselves": self.users["alice"].id,
            "an attendee": self.users["farah"].id,
            "an organiser": self.users["dana"].id,
            "an unknown user": self.missing_id(User),
        }
        for label, coordinator_id in cases.items():
            with self.subTest(selected=label):
                body = self.assert_error(
                    self.submit(body={"coordinator_id": coordinator_id, "reason": REASON}), 422)

                self.assertNotIn("Traceback", body["error"])
        self.assertEqual(self.saved(), [])
        self.assertEqual(self.notifications()[0], [])

    # TC-61-05 · AC2 — the coordinator must be a whole number.
    def test_coordinator_must_be_an_integer(self):
        for value in (None, "2", True, 1.5, [1], {"id": 1}):
            with self.subTest(coordinator_id=value):
                body = self.assert_error(
                    self.submit(body={"coordinator_id": value, "reason": REASON}), 400)

                self.assertEqual(body.get("field"), "coordinator_id")
        body = self.assert_error(self.submit(body={"reason": REASON}), 400)
        self.assertEqual(body.get("field"), "coordinator_id")
        self.assertEqual(self.saved(), [])


# ---------- AC3: the reason ----------


class ReasonTests(ReassignmentTestCase):
    # TC-61-06 · AC3 — a reason of exactly the maximum length is accepted.
    def test_reason_at_the_maximum_length_is_accepted(self):
        reason = "A" * MAX_REASON_LENGTH

        response = self.submit(reason=reason)

        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(self.saved(), [("E1", "alice", "ben", reason, "pending")])

    # TC-61-07 · AC3 — one character over the maximum is rejected.
    def test_reason_over_the_maximum_length_is_rejected(self):
        body = self.assert_error(self.submit(reason="A" * (MAX_REASON_LENGTH + 1)), 400)

        self.assertEqual(body.get("field"), "reason")
        self.assertIn(str(MAX_REASON_LENGTH), body["error"])
        self.assertEqual(self.saved(), [])
        self.assertEqual(self.notifications()[0], [])

    # TC-61-08 · AC3 — a missing, empty, blank or non-text reason is rejected.
    def test_reason_is_required(self):
        coordinator_id = self.users["ben"].id
        bodies = [
            ("missing", {"coordinator_id": coordinator_id}),
            ("null", {"coordinator_id": coordinator_id, "reason": None}),
            ("empty", {"coordinator_id": coordinator_id, "reason": ""}),
            ("spaces", {"coordinator_id": coordinator_id, "reason": "   \n\t "}),
            ("a number", {"coordinator_id": coordinator_id, "reason": 42}),
        ]
        for label, body in bodies:
            with self.subTest(reason=label):
                result = self.assert_error(self.submit(body=body), 400)

                self.assertEqual(result.get("field"), "reason")
                self.assertRegex(result["error"].lower(), r"reason")
        self.assertEqual(self.saved(), [])

    # TC-61-08 · AC3 — the body must be a JSON object.
    def test_body_must_be_a_json_object(self):
        headers = self.auth_headers(self.users["alice"])
        for label, kwargs in {"not JSON": {"data": "nope"}, "a list": {"json": [1, 2]}}.items():
            with self.subTest(body=label):
                response = self.client.post(self.url("E1"), headers=headers, **kwargs)

                self.assert_error(response, 400)
        self.assertEqual(self.saved(), [])


# ---------- AC4, AC5, AC6: what a request does ----------


class SubmitTests(ReassignmentTestCase):
    # TC-61-09 · AC4 — everything is recorded, status is pending, a confirmation comes back.
    def test_submission_is_recorded_as_pending(self):
        before = datetime.utcnow()

        response = self.submit(coordinator="ben", reason=REASON)

        after = datetime.utcnow()
        self.assertEqual(response.status_code, 201, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())
        request = body["request"]
        self.assertEqual(request["event_id"], self.events["E1"].id)
        self.assertEqual(request["requester_id"], self.users["alice"].id)
        self.assertEqual(request["coordinator_id"], self.users["ben"].id)
        self.assertEqual(request["reason"], REASON)
        self.assertEqual(request["status"], "pending")
        # Naive UTC audit time, like the other audit timestamps.
        requested_at = datetime.fromisoformat(request["requested_at"])
        self.assertIsNone(requested_at.tzinfo)
        self.assertTrue(before - timedelta(seconds=1) <= requested_at <= after + timedelta(seconds=1))
        self.assertEqual(self.saved(), [("E1", "alice", "ben", REASON, "pending")])

    # TC-61-09 · AC4 — the reason is saved without surrounding spaces.
    def test_reason_is_trimmed(self):
        self.assertEqual(self.submit(reason="  Overseas  \n").status_code, 201)

        self.assertEqual(self.saved(), [("E1", "alice", "ben", "Overseas", "pending")])

    # TC-61-10 · AC5 — only the selected coordinator is told, in the app and by email.
    def test_selected_coordinator_is_notified(self):
        response = self.submit(coordinator="ben")

        body = response.get_json()
        self.assertEqual(body["notification"], {"in_app": True, "email_queued": True})
        recipients, rows = self.notifications()
        self.assertEqual(recipients, [("ben", "E1")])
        self.assertIn("Chem Open House", rows[0].message)
        self.assertIn(self.users["alice"].email, rows[0].message)
        self.email.assert_called_once()
        self.assertEqual(self.email.call_args.args[0], self.users["ben"].email)
        self.assertIn("Chem Open House", self.email.call_args.args[1] + self.email.call_args.args[2])

    # TC-61-10 · AC5 — a broken email queue must not undo a saved request.
    def test_email_queue_failure_is_not_fatal(self):
        self.email.side_effect = ConnectionError("broker down")

        response = self.submit(coordinator="ben")

        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["notification"],
                         {"in_app": True, "email_queued": False})
        self.assertEqual(self.saved(), [("E1", "alice", "ben", REASON, "pending")])
        self.assertEqual(self.notifications()[0], [("ben", "E1")])

    # TC-61-11 · AC6 — while pending, nothing about the assignment or event changes.
    def test_assignment_and_status_do_not_change_while_pending(self):
        event = self.db.session.get(Event, self.events["E1"].id)
        assigned_at, status = event.coordinator_assigned_at, event.status

        self.assertEqual(self.submit(coordinator="ben").status_code, 201)

        self.db.session.expire_all()
        event = self.db.session.get(Event, self.events["E1"].id)
        self.assertEqual(event.coordinator_id, self.users["alice"].id)
        self.assertEqual(event.coordinator_assigned_at, assigned_at)
        self.assertEqual(event.status, status)
        headers = self.auth_headers(self.users["alice"])
        assignment = self.client.get(
            f"/api/events/{self.events['E1'].id}/coordinator", headers=headers).get_json()
        self.assertEqual(assignment["coordinator"]["id"], self.users["alice"].id)

    # TC-61-11 · AC6 — the requester sees the request as pending and cannot raise another.
    def test_requester_sees_the_pending_request(self):
        self.submit(coordinator="ben")

        body = self.view("E1", "alice").get_json()

        self.assertEqual(body["pending_request"]["status"], "pending")
        self.assertEqual(body["pending_request"]["coordinator_id"], self.users["ben"].id)
        self.assertFalse(body["can_request"])
        self.assertEqual(body["blocked_reason"], "pending")
        self.assertRegex(body["message"].lower(), r"pending")


# ---------- AC7, AC8, AC9: when a request is refused ----------


class RefusedRequestTests(ReassignmentTestCase):
    # TC-61-12 · AC7 — a second request for the same event, even for another target.
    def test_second_pending_request_is_rejected(self):
        self.add_pending("E1", "alice", "ben")

        body = self.assert_error(self.submit(coordinator="chloe"), 409)

        self.assertEqual(body.get("reason"), "pending")
        self.assertRegex(body["error"].lower(), r"pending")
        self.assertEqual(self.saved(), [("E1", "alice", "ben", REASON, "pending")])
        self.assertEqual(self.notifications()[0], [])

    # TC-61-12 · AC7 — the limit is per event: another event can still have a request.
    def test_pending_request_on_one_event_does_not_block_another(self):
        self.add_pending("E1", "alice", "ben")
        other = self.ad_hoc_event(ends_at=NOW + timedelta(days=30))

        response = self.client.post(
            f"/api/events/{other.id}/reassignment",
            headers=self.auth_headers(self.users["alice"]),
            json={"coordinator_id": self.users["chloe"].id, "reason": REASON})

        self.assertEqual(response.status_code, 201, response.get_json())

    # TC-61-13 · AC8 — a cancelled event.
    def test_cancelled_event_is_blocked(self):
        view = self.view("E2", "alice").get_json()
        self.assertFalse(view["can_request"])
        self.assertEqual(view["blocked_reason"], "cancelled")
        self.assertRegex(view["message"].lower(), r"cancelled")

        body = self.assert_error(self.submit("E2"), 409)

        self.assertEqual(body.get("reason"), "cancelled")
        self.assertEqual(self.saved(), [])

    # TC-61-14 · AC8 — an event that has already ended.
    def test_past_event_is_blocked(self):
        view = self.view("E3", "alice").get_json()
        self.assertFalse(view["can_request"])
        self.assertEqual(view["blocked_reason"], "past")
        self.assertRegex(view["message"].lower(), r"ended|past")

        body = self.assert_error(self.submit("E3"), 409)

        self.assertEqual(body.get("reason"), "past")
        self.assertEqual(self.saved(), [])

    # TC-61-14 · AC8 — boundary: an event is past from its end time onward (half-open).
    def test_event_is_past_from_its_end_time(self):
        still_running = self.ad_hoc_event(ends_at=NOW + timedelta(minutes=1))
        just_ended = self.ad_hoc_event(ends_at=NOW)
        headers = self.auth_headers(self.users["alice"])
        body = {"coordinator_id": self.users["ben"].id, "reason": REASON}

        allowed = self.client.post(
            f"/api/events/{still_running.id}/reassignment", headers=headers, json=body)
        refused = self.client.post(
            f"/api/events/{just_ended.id}/reassignment", headers=headers, json=body)

        self.assertEqual(allowed.status_code, 201, allowed.get_json())
        self.assertEqual(refused.status_code, 409, refused.get_json())
        self.assertEqual(refused.get_json().get("reason"), "past")

    # TC-61-15 · AC9 — nobody else is eligible: say so, and create nothing.
    def test_no_eligible_coordinator(self):
        # Real coordinators may already exist in the database, so the empty case is
        # arranged by making the shared eligibility rule return nobody.
        with mock.patch.object(event_routes, "_eligible_coordinators", return_value=[]):
            view = self.view("E1", "alice").get_json()
            response = self.submit(coordinator="ben")

        self.assertEqual(view["coordinators"], [])
        self.assertFalse(view["can_request"])
        self.assertEqual(view["blocked_reason"], "no_eligible_coordinators")
        self.assertRegex(view["message"].lower(), r"no eligible coordinator")
        self.assert_error(response, 422)
        self.assertEqual(self.saved(), [])
        self.assertEqual(self.notifications()[0], [])


# ---------- AC10: saving fails ----------


class SaveFailureTests(ReassignmentTestCase):
    # TC-61-16 · AC10 — nothing is created or changed, the user is told, a retry works.
    def test_failed_save_changes_nothing(self):
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.submit(coordinator="ben")

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("simulated outage", body["error"])
        self.assertEqual(self.saved(), [])
        self.assertEqual(self.coordinator_of("E1"), self.users["alice"].id)
        self.assertEqual(self.notifications()[0], [])
        self.email.assert_not_called()

        retry = self.submit(coordinator="ben")
        self.assertEqual(retry.status_code, 201, retry.get_json())
        self.assertEqual(self.saved(), [("E1", "alice", "ben", REASON, "pending")])

    # TC-61-16 · AC10 — a failed load is a failure, not an empty or open form.
    def test_failed_load_is_reported_as_a_failure(self):
        with mock.patch.object(self.db.session, "get",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.view("E1", "alice", headers=self.auth_headers(self.users["alice"]))

        self.assertEqual(response.status_code, 503, response.get_json())
        self.assertIs(response.get_json().get("retryable"), True)


# ---------- AC11: signed-out users ----------


class SignedOutTests(ReassignmentTestCase):
    # TC-61-17 · AC11 — no token, an expired token and a deleted user's token.
    def test_signed_out_users_get_401(self):
        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["alice"].id),
                                      expires_delta=timedelta(seconds=-1))
        cases = {
            "no token": {},
            "expired": {"Authorization": f"Bearer {expired}"},
            "deleted user": ghost_headers,
        }
        for label, headers in cases.items():
            with self.subTest(session=label):
                self.assertEqual(self.view("E1", headers=headers).status_code, 401)
                self.assertEqual(self.submit("E1", headers=headers).status_code, 401)
        self.assertEqual(self.saved(), [])
        # Nothing about the event leaks to a signed-out caller.
        body = self.client.get(self.url("E1")).get_data(as_text=True)
        self.assertNotIn("Chem Open House", body)


if __name__ == "__main__":
    unittest.main()
