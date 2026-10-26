"""Tests for SCRUM-46 "Submit Change Request for a Submitted Event".

Each test names the case it automates in docs/test-cases/SCRUM-46-change-request.md
(TC-46-xx). Seed data CR-SEED: the USERS in tests/seed_data.py, plus C1-C5 below.

Model (db/event_change_requests.sql): EventChangeRequest
    event_id, requested_by_id, status ("pending_review"), changes
    ({field: {"from", "to"}}), requested_at

Endpoints (JWT required, else 401; the User row is loaded on every request)
    GET  /api/events/<id>/change-requests   the event's organiser
        200 FORM = {"event": {"id", "title", "status", "coordinator", "current": {FIELD: value}},
                    "fields": [{"name", "label"}], "can_request", "blocked_reason":
                    "not_approved" | "no_coordinator" | "pending" | null, "message",
                    "pending_request": REQ | null}
    POST /api/events/<id>/change-requests   the event's organiser
        {FIELD: proposed value, ...}
        201 {"message", "request": REQ, "notification": {"in_app", "email_queued"}}
        REQ = {"id", "event_id", "status", "status_label", "changes": [{"field", "label",
               "from", "to"}], "requested_by", "requested_at"}
    FIELD is start_time, end_time, expected_attendance, venue_requirements or
    equipment_requirements.
    Checks, first failure wins: 401 -> 404 -> 403 -> 400 (not a JSON object) -> 409
    {"reason": "not_approved" | "no_coordinator" | "pending"} -> 422 {"fields"} ->
    503 {"retryable": true}.
"""

from datetime import datetime
from unittest import mock

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app import tasks
from app.models import Event, Notification
from tests import seed_data
from tests.base import AppTestCase

SESSION_EXPIRED = "Your session is no longer valid. Please log in again."
NOT_SUBMITTED = "Your change request was not submitted, and the event is unchanged. Please try again."

# CR-SEED. `organiser` and `coordinator` refer to seed_data USERS keys.
EVENTS = [
    {"key": "C1", "title": "Charity Gala", "status": "approved", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 5, 18, 0),
     "end_time": datetime(2026, 12, 5, 23, 0), "expected_attendance": 200,
     "venue_requirements": "Ballroom for 200",
     "equipment_requirements": "2 wireless microphones"},
    {"key": "C2", "title": "Book Fair", "status": "submitted", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 10, 9, 0),
     "end_time": datetime(2026, 12, 10, 17, 0), "expected_attendance": 100,
     "venue_requirements": "Hall"},
    {"key": "C3", "title": "Spring Fair", "status": "approved", "organiser": "dana",
     "coordinator": None, "start_time": datetime(2026, 12, 12, 10, 0),
     "end_time": datetime(2026, 12, 12, 16, 0), "expected_attendance": 80,
     "venue_requirements": "Lawn"},
    {"key": "C4", "title": "Product Launch", "status": "approved", "organiser": "evan",
     "coordinator": "ben", "start_time": datetime(2026, 12, 20, 14, 0),
     "end_time": datetime(2026, 12, 20, 18, 0), "expected_attendance": 50,
     "venue_requirements": "Auditorium", "equipment_requirements": "Projector"},
    {"key": "C5", "title": "Winter Concert", "status": "cancelled", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 15, 19, 0),
     "end_time": datetime(2026, 12, 15, 22, 0), "expected_attendance": 300,
     "venue_requirements": "Concert hall"},
]
EVENT_FIELDS = ("start_time", "end_time", "expected_attendance", "venue_requirements",
                "equipment_requirements", "status", "title")
EVERYTHING = {"start_time": "2026-12-06T18:00", "end_time": "2026-12-06T23:30",
              "expected_attendance": 250, "venue_requirements": "Ballroom for 250",
              "equipment_requirements": "4 wireless microphones"}


def _request_model():
    # Imported here so the tests fail on behaviour, not on import, until it exists.
    from app.models import EventChangeRequest

    return EventChangeRequest


class ChangeRequestTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.events = self.seed_events(EVENTS, self.users)
        # Emails are asserted on, never sent.
        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.email = patcher.start()
        self.addCleanup(patcher.stop)

    def url(self, event="C1"):
        event_id = self.events[event].id if isinstance(event, str) else event
        return f"/api/events/{event_id}/change-requests"

    def headers(self, user):
        return self.auth_headers(self.users[user])

    def form(self, event="C1", user="dana"):
        response = self.client.get(self.url(event), headers=self.headers(user))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def submit(self, body, event="C1", user="dana"):
        return self.client.post(self.url(event), json=body, headers=self.headers(user))

    def submitted(self, body, event="C1"):
        response = self.submit(body, event)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def requests(self, event="C1"):
        model = _request_model()
        self.db.session.expire_all()
        return model.query.filter_by(event_id=self.events[event].id).order_by(model.id).all()

    def notifications(self, user):
        self.db.session.expire_all()
        return Notification.query.filter_by(recipient_id=self.users[user].id).all()

    def saved_event(self, event="C1"):
        self.db.session.expire_all()
        row = self.db.session.get(Event, self.events[event].id)
        return {name: getattr(row, name) for name in EVENT_FIELDS}

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertTrue(body.get("error", "").strip())
        self.assertNotIn("request", body)
        return body

    def assert_nothing_requested(self, event="C1"):
        self.assertEqual(self.requests(event), [])
        self.assertEqual(self.notifications("alice"), [])
        self.email.assert_not_called()


# ---------- AC1: only my own approved events ----------


class AccessTests(ChangeRequestTestCase):
    # TC-46-01 · AC1, AC2
    def test_tc_46_01_the_organiser_opens_the_form_for_their_approved_event(self):
        form = self.form()

        self.assertEqual((form["event"]["title"], form["event"]["status"]),
                         ("Charity Gala", "approved"))
        self.assertEqual(form["event"]["coordinator"]["id"], self.users["alice"].id)
        self.assertEqual(form["event"]["current"], {
            "start_time": "2026-12-05T18:00:00", "end_time": "2026-12-05T23:00:00",
            "expected_attendance": 200, "venue_requirements": "Ballroom for 200",
            "equipment_requirements": "2 wireless microphones"})
        self.assertEqual([f["name"] for f in form["fields"]],
                         ["start_time", "end_time", "expected_attendance",
                          "venue_requirements", "equipment_requirements"])
        self.assertEqual(form["fields"][2]["label"], "Expected attendance")
        self.assertIs(form["can_request"], True)
        self.assertIsNone(form["blocked_reason"])
        self.assertIsNone(form["pending_request"])

    # TC-46-02 · AC1
    def test_tc_46_02_events_that_are_not_approved_cannot_take_a_request(self):
        for event in ("C2", "C5"):
            status = self.events[event].status
            with self.subTest(event=event):
                form = self.form(event)
                self.assertIs(form["can_request"], False)
                self.assertEqual(form["blocked_reason"], "not_approved")
                self.assertIn(status, form["message"])

                body = self.assert_error(self.submit({"expected_attendance": 250}, event), 409)
                self.assertEqual(body["reason"], "not_approved")
                self.assertIn(status, body["error"])
                self.assert_nothing_requested(event)

    # TC-46-03 · AC1
    def test_tc_46_03_who_may_request_and_in_what_order(self):
        ghost = self.make_user(role="organiser")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        body = {"expected_attendance": 250}

        self.assertEqual(self.client.post(self.url(), json=body).status_code, 401)
        error = self.assert_error(self.client.post(self.url(), json=body, headers=ghost_headers), 401)
        self.assertEqual(error["error"], SESSION_EXPIRED)
        self.assert_error(self.submit(body, self.missing_id(Event)), 404)
        for user in ("evan", "alice", "hana", "admin"):
            with self.subTest(user=user):
                error = self.assert_error(self.submit(body, user=user), 403)
                self.assertNotIn("Charity Gala", error["error"])
                self.assertNotIn("current", error)
        error = self.assert_error(self.client.get(self.url(), headers=self.headers("evan")), 403)
        self.assertNotIn("event", error)
        self.assert_error(self.client.post(self.url(), data="not json", content_type="text/plain",
                                           headers=self.headers("dana")), 400)
        self.assert_nothing_requested()


# ---------- AC2 + AC3: propose new values; the request records them ----------


class ProposalTests(ChangeRequestTestCase):
    # TC-46-04 · AC2, AC3
    def test_tc_46_04_every_permitted_field_can_be_changed_in_one_request(self):
        result = self.submitted(EVERYTHING)

        self.assertEqual(
            [(c["field"], c["from"], c["to"]) for c in result["request"]["changes"]],
            [("start_time", "2026-12-05T18:00:00", "2026-12-06T18:00:00"),
             ("end_time", "2026-12-05T23:00:00", "2026-12-06T23:30:00"),
             ("expected_attendance", 200, 250),
             ("venue_requirements", "Ballroom for 200", "Ballroom for 250"),
             ("equipment_requirements", "2 wireless microphones", "4 wireless microphones")])

    # TC-46-05 · AC2, AC3
    def test_tc_46_05_only_the_fields_that_change_are_recorded(self):
        result = self.submitted({"start_time": "2026-12-05T18:00", "end_time": "2026-12-05T23:00",
                                 "venue_requirements": "Ballroom for 200",
                                 "expected_attendance": 250})

        self.assertEqual([c["field"] for c in result["request"]["changes"]], ["expected_attendance"])
        [row] = self.requests()
        self.assertEqual(row.changes, {"expected_attendance": {"from": 200, "to": 250}})

    # TC-46-06 · AC2, AC4
    def test_tc_46_06_fields_that_are_not_permitted_are_refused(self):
        for name, value in (("title", "Charity Ball"), ("venue_id", 1),
                            ("registration_required", False), ("status", "draft"),
                            ("colour", "red")):
            with self.subTest(field=name):
                body = self.assert_error(self.submit({name: value, "expected_attendance": 250}), 422)
                self.assertIn("can't be changed through a change request", body["fields"][name])
        self.assert_nothing_requested()

    # TC-46-07 · AC3
    def test_tc_46_07_the_request_records_the_event_fields_and_values(self):
        result = self.submitted({"start_time": "2026-12-05T17:00", "expected_attendance": 250})

        [row] = self.requests()
        self.assertEqual((row.event_id, row.requested_by_id, row.status),
                         (self.events["C1"].id, self.users["dana"].id, "pending_review"))
        self.assertIsNotNone(row.requested_at)
        self.assertEqual(row.changes, {
            "start_time": {"from": "2026-12-05T18:00:00", "to": "2026-12-05T17:00:00"},
            "expected_attendance": {"from": 200, "to": 250}})
        request = result["request"]
        self.assertEqual((request["id"], request["event_id"], request["requested_by"]["id"]),
                         (row.id, self.events["C1"].id, self.users["dana"].id))


# ---------- AC4: disallowed or invalid changes are blocked, with the reason ----------


class ValidationTests(ChangeRequestTestCase):
    # TC-46-08 · AC4
    def test_tc_46_08_invalid_values_are_refused_with_the_reason(self):
        cases = {
            "negative attendance": ({"expected_attendance": -5}, "expected_attendance",
                                    "whole number of at least 1"),
            "no attendance": ({"expected_attendance": 0}, "expected_attendance", "at least 1"),
            "fraction": ({"expected_attendance": 1.5}, "expected_attendance", "whole number"),
            "text attendance": ({"expected_attendance": "250"}, "expected_attendance", "whole number"),
            "true": ({"expected_attendance": True}, "expected_attendance", "whole number"),
            "end before start": ({"start_time": "2026-12-06T18:00", "end_time": "2026-12-06T17:00"},
                                 "end_time", "The end must be after the start."),
            "end at start": ({"start_time": "2026-12-06T18:00", "end_time": "2026-12-06T18:00"},
                             "end_time", "The end must be after the start."),
            "end before current start": ({"end_time": "2026-12-05T17:00"}, "end_time",
                                         "The end must be after the start."),
            "words": ({"start_time": "next Friday"}, "start_time", "valid date and time"),
            "no such day": ({"start_time": "2026-02-30T10:00"}, "start_time", "valid date and time"),
            "blank venue requirements": ({"venue_requirements": "  "}, "venue_requirements",
                                         "can't be blank"),
            "long venue requirements": ({"venue_requirements": "x" * 5001}, "venue_requirements",
                                        "5000 characters"),
            "equipment not text": ({"equipment_requirements": ["Projector"]},
                                   "equipment_requirements", "must be text"),
        }
        for case, (body, field, reason) in cases.items():
            with self.subTest(case=case):
                error = self.assert_error(self.submit(body), 422)
                self.assertIn(reason, error["fields"][field])
        self.assert_nothing_requested()

    # TC-46-09 · AC4
    def test_tc_46_09_every_problem_is_named_at_once(self):
        error = self.assert_error(self.submit({"expected_attendance": -5, "venue_requirements": "",
                                               "title": "Charity Ball"}), 422)

        self.assertEqual(set(error["fields"]), {"expected_attendance", "venue_requirements", "title"})

    # TC-46-10 · AC4
    def test_tc_46_10_a_request_must_change_something(self):
        for body in ({}, {"start_time": "2026-12-05T18:00", "expected_attendance": 200,
                          "equipment_requirements": "2 wireless microphones"}):
            with self.subTest(body=body):
                error = self.assert_error(self.submit(body), 422)
                self.assertIn("no changes", error["error"].lower())
        self.assert_nothing_requested()

    # TC-46-11 · AC2, AC4
    def test_tc_46_11_clearing_equipment_is_a_change_and_text_is_tidied(self):
        result = self.submitted({"equipment_requirements": ""})
        self.assertEqual(result["request"]["changes"][0]["to"], None)

        # Only one request may be pending (A6), so the second is checked on C4.
        evans = self.client.post(self.url("C4"), json={"venue_requirements": "  Main hall  "},
                                 headers=self.headers("evan"))
        self.assertEqual(evans.status_code, 201, evans.get_json())
        self.assertEqual(evans.get_json()["request"]["changes"][0]["to"], "Main hall")


# ---------- AC5: no coordinator ----------


class NoCoordinatorTests(ChangeRequestTestCase):
    # TC-46-12 · AC5
    def test_tc_46_12_an_event_without_a_coordinator_cannot_take_a_request(self):
        form = self.form("C3")
        self.assertIs(form["can_request"], False)
        self.assertEqual(form["blocked_reason"], "no_coordinator")
        self.assertIn("no coordinator", form["message"])

        body = self.assert_error(self.submit({"expected_attendance": 100}, "C3"), 409)

        self.assertEqual(body["reason"], "no_coordinator")
        self.assertEqual(body["error"], form["message"])
        self.assertEqual(self.requests("C3"), [])


# ---------- AC6: saved as Pending Review, with a confirmation ----------


class PendingReviewTests(ChangeRequestTestCase):
    # TC-46-13 · AC6
    def test_tc_46_13_a_successful_request_is_pending_review_and_confirmed(self):
        result = self.submitted({"expected_attendance": 250})

        self.assertEqual((result["request"]["status"], result["request"]["status_label"]),
                         ("pending_review", "Pending Review"))
        for text in ("Charity Gala", "Expected attendance", "Pending Review", "coordinator"):
            self.assertIn(text, result["message"])

    # TC-46-14 · AC6
    def test_tc_46_14_only_one_request_can_be_pending_at_a_time(self):
        self.submitted({"expected_attendance": 250})

        body = self.assert_error(self.submit({"expected_attendance": 300}), 409)

        self.assertEqual(body["reason"], "pending")
        form = self.form()
        self.assertIs(form["can_request"], False)
        self.assertEqual(form["blocked_reason"], "pending")
        self.assertEqual(form["pending_request"]["changes"][0]["to"], 250)
        self.assertEqual(len(self.requests()), 1)

    # TC-46-15 · AC6
    def test_tc_46_15_the_event_is_locked_before_the_pending_check(self):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        sa_event.listen(self.db.engine, "before_cursor_execute", record)
        try:
            self.submitted({"expected_attendance": 250})
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", record)

        lock = next(i for i, s in enumerate(statements)
                    if "FROM events" in s and "FOR UPDATE" in s)
        look = next(i for i, s in enumerate(statements) if "FROM event_change_requests" in s)
        self.assertLess(lock, look)


# ---------- AC7: the approved event is not overwritten ----------


class EventUnchangedTests(ChangeRequestTestCase):
    # TC-46-16 · AC7
    def test_tc_46_16_the_event_keeps_its_approved_values(self):
        before = self.saved_event()

        self.submitted(EVERYTHING)

        self.assertEqual(self.saved_event(), before)
        planning = self.client.get(f"/api/events/{self.events['C1'].id}/planning",
                                   headers=self.headers("alice")).get_json()
        self.assertEqual((planning["start_time"], planning["expected_attendance"]),
                         ("2026-12-05T18:00:00", 200))


# ---------- AC8: a failed save changes nothing ----------


class FailureTests(ChangeRequestTestCase):
    def failing(self, condition):
        def fail(conn, cursor, statement, parameters, context, executemany):
            if condition(statement):
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        return fail

    # TC-46-17 · AC8
    def test_tc_46_17_a_failed_save_leaves_the_event_and_requests_unchanged(self):
        before = self.saved_event()
        for prefix in ("INSERT INTO event_change_requests", "INSERT INTO notifications"):
            fail = self.failing(lambda statement: statement.startswith(prefix))
            self.db.session.expire_all()
            sa_event.listen(self.db.engine, "before_cursor_execute", fail)
            try:
                response = self.submit({"expected_attendance": 250})
            finally:
                sa_event.remove(self.db.engine, "before_cursor_execute", fail)

            with self.subTest(failing=prefix):
                body = self.assert_error(response, 503)
                self.assertIs(body.get("retryable"), True)
                self.assertEqual(body["error"], NOT_SUBMITTED)
                self.assertNotIn("simulated outage", body["error"])
                self.assert_nothing_requested()
                self.assertEqual(self.saved_event(), before)

    # TC-46-18 · AC8
    def test_tc_46_18_a_failed_load_is_an_error_not_an_empty_form(self):
        fail = self.failing(lambda statement: "FROM event_change_requests" in statement)
        self.db.session.expire_all()
        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            response = self.client.get(self.url(), headers=self.headers("dana"))
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("simulated outage", body["error"])
        self.assertNotIn("event", body)


# ---------- AC9: the coordinator is notified ----------


class NotificationTests(ChangeRequestTestCase):
    # TC-46-19 · AC9
    def test_tc_46_19_the_coordinator_is_told_the_proposed_changes(self):
        result = self.submitted({"start_time": "2026-12-05T17:00", "expected_attendance": 250})

        [notification] = self.notifications("alice")
        self.assertEqual((notification.kind, notification.event_id),
                         ("change_requested", self.events["C1"].id))
        for text in ("Charity Gala", "Start: 2026-12-05 18:00 → 2026-12-05 17:00",
                     "Expected attendance: 200 → 250"):
            self.assertIn(text, notification.message)
        self.email.assert_called_once()
        to_address, subject, body = self.email.call_args.args
        self.assertEqual(to_address, self.users["alice"].email)
        self.assertIn("Charity Gala", subject)
        self.assertIn("Expected attendance: 200 → 250", body)
        self.assertEqual(result["notification"], {"in_app": True, "email_queued": True})
        self.assertEqual(self.notifications("dana"), [])

    # TC-46-20 · AC9
    def test_tc_46_20_an_email_queue_failure_does_not_undo_the_request(self):
        self.email.side_effect = ConnectionError("broker down")

        result = self.submitted({"expected_attendance": 250})

        self.assertEqual(result["notification"], {"in_app": True, "email_queued": False})
        self.assertEqual(len(self.requests()), 1)
        self.assertEqual(len(self.notifications("alice")), 1)
