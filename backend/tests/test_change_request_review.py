"""Tests for SCRUM-70 "Review Change Request to a Submitted Event".

Each test names the case it automates in docs/test-cases/SCRUM-70-review-change-request.md
(TC-70-xx). Seed data CV-SEED: the USERS in tests/seed_data.py, plus the attendees, events,
venue bookings, equipment and registrations below.

Model (db/event_change_request_decisions.sql): EventChangeRequest gains decided_at,
decided_by_id and decision_reason; status "accepted" or "rejected" once decided.

Endpoints (JWT required, else 401; the User row is loaded on every request)
    GET  /api/events/change-requests                 a coordinator: their pending requests
        200 {"requests": [REQ + "event": {"id", "title", "status"}], "message"}
    GET  /api/events/<id>/change-requests/<rid>      the event's current coordinator
        200 {"event": {"id", "title", "status", "organiser"}, "request": REQ,
             "impact": IMPACT, "can_decide", "blocked_reason": "decided" | "not_approved"
             | null, "message"}
    POST /api/events/<id>/change-requests/<rid>/decision
        {"decision": "accept" | "reject", "reason": text (required to reject)}
        200 {"message", "request": REQ, "notification": {"in_app", "email_queued",
             "attendees_notified"}}
    REQ = SCRUM-46's request + {"decided_at", "decided_by", "decision_reason"}
    IMPACT = {"venue_bookings": [{"id", "venue": {"id", "name"}, "start_time", "end_time",
              "status", "reasons"}], "equipment": [{"id", "equipment_type", "quantity",
              "reserved", "reasons"}], "registrations": {"registered", "capacity",
              "reasons"}, "affected", "message"}
    Checks, first failure wins: 401 -> 404 (event, or request of that event) -> 403 ->
    400 (body, decision, reason) -> 409 {"reason": "decided" | "not_approved"} ->
    503 {"retryable": true}.
"""

from datetime import datetime
from unittest import mock

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app import tasks
from app.models import (
    EquipmentRequirement,
    EquipmentReservation,
    Event,
    Notification,
    Registration,
    VenueBooking,
)
from tests import seed_data
from tests.base import AppTestCase

SESSION_EXPIRED = "Your session is no longer valid. Please log in again."
NOT_SAVED = ("The decision was not saved, so the change request and the event are unchanged. "
             "Please try again.")
LIST_URL = "/api/events/change-requests"

# CV-SEED events. `organiser` and `coordinator` refer to seed_data USERS keys.
EVENTS = [
    {"key": "V1", "title": "Charity Gala", "status": "approved", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 5, 18, 0),
     "end_time": datetime(2026, 12, 5, 23, 0), "expected_attendance": 200,
     "venue_requirements": "Ballroom for 200",
     "equipment_requirements": "2 wireless microphones", "registration_required": True,
     "registration_capacity": 210, "registration_opens_at": datetime(2026, 11, 1, 9, 0),
     "registration_closes_at": datetime(2026, 12, 1, 12, 0)},
    {"key": "V2", "title": "Product Launch", "status": "approved", "organiser": "dana",
     "coordinator": "ben", "start_time": datetime(2026, 12, 20, 14, 0),
     "end_time": datetime(2026, 12, 20, 18, 0), "expected_attendance": 50,
     "venue_requirements": "Auditorium", "equipment_requirements": "Projector"},
    {"key": "V3", "title": "Winter Concert", "status": "cancelled", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 15, 19, 0),
     "end_time": datetime(2026, 12, 15, 22, 0), "expected_attendance": 300,
     "venue_requirements": "Concert hall"},
]
# CV-SEED change requests: key -> (event, changes as stored by SCRUM-46).
REQUESTS = {
    "T1": ("V1", {"start_time": {"from": "2026-12-05T18:00:00", "to": "2026-12-06T18:00:00"},
                  "end_time": {"from": "2026-12-05T23:00:00", "to": "2026-12-06T23:30:00"}}),
    "N1": ("V1", {"expected_attendance": {"from": 200, "to": 250}}),
    "S1": ("V1", {"venue_requirements": {"from": "Ballroom for 200",
                                         "to": "Ballroom and breakout room"},
                  "equipment_requirements": {"from": "2 wireless microphones",
                                             "to": "4 wireless microphones"}}),
    "P1": ("V2", {"expected_attendance": {"from": 50, "to": 60}}),
    "X1": ("V3", {"expected_attendance": {"from": 300, "to": 320}}),
}
EVENT_FIELDS = ("title", "status", "start_time", "end_time", "expected_attendance",
                "venue_requirements", "equipment_requirements", "venue_id", "coordinator_id")
REASON = "The ballroom can't hold 250."


def _request_model():
    # Imported here, as in SCRUM-46's tests.
    from app.models import EventChangeRequest

    return EventChangeRequest


class ReviewTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS + seed_data.LEADS)
        for key in ("gail", "hugo", "ivy"):
            self.users[key] = self.make_user(role="attendee")
        self.events = self.seed_events(EVENTS, self.users)
        self._seed_arrangements()
        self.requests = {}
        # Emails are asserted on, never sent.
        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.email = patcher.start()
        self.addCleanup(patcher.stop)

    def _seed_arrangements(self):
        v1, v2, alice, hana = (self.events["V1"], self.events["V2"], self.users["alice"],
                               self.users["hana"])
        self.ballroom = self.make_venue(name="Grand Ballroom", capacity=220)
        self.garden = self.make_venue(name="Garden Room", capacity=120)
        self.rooftop = self.make_venue(name="Rooftop", capacity=None)
        v1.venue_id = self.ballroom.id

        def booking(venue, status, start, end, **extra):
            row = VenueBooking(venue_id=venue.id, event_id=v1.id, status=status,
                               start_time=start, end_time=end, requested_by_id=alice.id,
                               created_at=datetime(2026, 10, 20, 2, 0),
                               venue_requirements="Ballroom for 200", **extra)
            self.db.session.add(row)
            return row

        self.bookings = {
            "B1": booking(self.ballroom, "confirmed", datetime(2026, 12, 5, 18, 0),
                          datetime(2026, 12, 5, 23, 0)),
            "B2": booking(self.garden, "tentative", datetime(2026, 12, 5, 17, 0),
                          datetime(2026, 12, 5, 19, 0),
                          hold_expires_at=datetime(2026, 11, 30, 12, 0)),
            "B3": booking(self.rooftop, "pending", datetime(2026, 12, 5, 21, 0),
                          datetime(2026, 12, 5, 23, 0)),
            "B4": booking(self.garden, "rejected", datetime(2026, 12, 5, 9, 0),
                          datetime(2026, 12, 5, 11, 0), rejection_reason="Closed."),
            "B5": booking(self.ballroom, "tentative", datetime(2026, 12, 4, 18, 0),
                          datetime(2026, 12, 4, 23, 0),
                          hold_expires_at=datetime(2026, 10, 1, 12, 0)),
        }
        mics = EquipmentRequirement(event_id=v1.id, equipment_type="Wireless microphone",
                                    quantity=2, recorded_by_id=alice.id)
        projector = EquipmentRequirement(event_id=v1.id, equipment_type="Projector",
                                         quantity=1, recorded_by_id=alice.id)
        self.db.session.add_all([mics, projector])
        self.db.session.flush()
        self.requirements = {"Q1": mics, "Q2": projector}
        resource = self.make_resource(name="Shure SLX-D", category="Wireless microphone")
        lamp = self.make_resource(name="Epson EB", category="Projector")
        self.reservations = {
            "R1": EquipmentReservation(event_id=v1.id, requirement_id=mics.id,
                                       resource_id=resource.id, quantity=2,
                                       start_time=v1.start_time, end_time=v1.end_time,
                                       status="reserved", reserved_by_id=hana.id),
            "R2": EquipmentReservation(event_id=v1.id, requirement_id=projector.id,
                                       resource_id=lamp.id, quantity=1,
                                       start_time=v1.start_time, end_time=v1.end_time,
                                       status="released", reserved_by_id=hana.id,
                                       released_at=datetime(2026, 10, 25, 2, 0),
                                       release_reason="The equipment requirement was changed."),
        }
        self.db.session.add_all(self.reservations.values())
        for key, event, status in (("farah", v1, "registered"), ("gail", v1, "registered"),
                                   ("hugo", v1, "withdrawn"), ("ivy", v2, "registered")):
            self.db.session.add(Registration(event_id=event.id, attendee_id=self.users[key].id,
                                             status=status))
        self.db.session.commit()

    # ---------- Seeding requests ----------

    def seed_request(self, key, changes=None, event=None, status="pending_review", **extra):
        event_key, stored = REQUESTS.get(key, (event, changes))
        row = _request_model()(event_id=self.events[event_key].id,
                               requested_by_id=self.users["dana"].id, status=status,
                               changes=changes or stored,
                               requested_at=extra.pop("requested_at",
                                                      datetime(2026, 10, 26, 2, 0)),
                               **extra)
        self.db.session.add(row)
        self.db.session.commit()
        self.requests[key] = row
        return row

    # ---------- Requests ----------

    def url(self, key, event=None):
        row = self.requests[key]
        event_id = self.events[event].id if event else row.event_id
        return f"/api/events/{event_id}/change-requests/{row.id}"

    def headers(self, user):
        return self.auth_headers(self.users[user])

    def review(self, key, user="alice"):
        response = self.client.get(self.url(key), headers=self.headers(user))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def decide(self, key, decision, reason=None, user="alice"):
        body = {"decision": decision}
        if reason is not None:
            body["reason"] = reason
        return self.client.post(f"{self.url(key)}/decision", json=body,
                                headers=self.headers(user))

    def decided(self, key, decision, reason=None):
        response = self.decide(key, decision, reason)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    # ---------- Reading what was saved ----------

    def stored(self, key):
        self.db.session.expire_all()
        return self.db.session.get(_request_model(), self.requests[key].id)

    def saved_event(self, key="V1"):
        self.db.session.expire_all()
        row = self.db.session.get(Event, self.events[key].id)
        return {name: getattr(row, name) for name in EVENT_FIELDS}

    def notifications(self, user, kind=None):
        self.db.session.expire_all()
        query = Notification.query.filter_by(recipient_id=self.users[user].id)
        return query.filter_by(kind=kind).all() if kind else query.all()

    def reservation_status(self, key):
        self.db.session.expire_all()
        return self.db.session.get(EquipmentReservation, self.reservations[key].id).status

    def emailed(self):
        return [call.args[0] for call in self.email.call_args_list]

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertTrue(body.get("error", "").strip())
        self.assertNotIn("request", body)
        self.assertNotIn("impact", body)
        return body

    def assert_still_pending(self, key):
        self.assertEqual(self.stored(key).status, "pending_review")
        self.assertIsNone(self.stored(key).decided_at)


# ---------- AC1: only the event's coordinator, and only for an approved event ----------


class AccessTests(ReviewTestCase):
    # TC-70-01 · AC1, AC2
    def test_tc_70_01_the_coordinator_opens_a_pending_request(self):
        self.seed_request("T1")

        body = self.review("T1")

        self.assertEqual((body["event"]["id"], body["event"]["title"], body["event"]["status"]),
                         (self.events["V1"].id, "Charity Gala", "approved"))
        self.assertEqual(body["event"]["organiser"]["id"], self.users["dana"].id)
        request = body["request"]
        self.assertEqual((request["id"], request["status"], request["status_label"]),
                         (self.requests["T1"].id, "pending_review", "Pending Review"))
        self.assertEqual([(c["field"], c["label"], c["from"], c["to"]) for c in request["changes"]],
                         [("start_time", "Start", "2026-12-05T18:00:00", "2026-12-06T18:00:00"),
                          ("end_time", "End", "2026-12-05T23:00:00", "2026-12-06T23:30:00")])
        self.assertIsNone(request["decided_at"])
        self.assertIn("impact", body)
        self.assertIs(body["can_decide"], True)
        self.assertIsNone(body["blocked_reason"])

    # TC-70-02 · AC1
    def test_tc_70_02_who_may_review_and_in_what_order(self):
        self.seed_request("T1")
        self.seed_request("P1")
        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        before = self.saved_event()
        v1 = self.events["V1"].id
        t1 = self.requests["T1"].id
        decision = {"decision": "accept"}

        for method in ("get", "post"):
            def call(url, headers=None, method=method):
                url = url if method == "get" else f"{url}/decision"
                send = getattr(self.client, method)
                kwargs = {"json": decision} if method == "post" else {}
                return send(url, headers=headers or {}, **kwargs)

            with self.subTest(method=method):
                # With no token at all, flask-jwt-extended answers before the route runs.
                self.assertEqual(call(self.url("T1")).status_code, 401)
                error = self.assert_error(call(self.url("T1"), ghost_headers), 401)
                self.assertEqual(error["error"], SESSION_EXPIRED)
                missing_event = f"/api/events/{self.missing_id(Event)}/change-requests/{t1}"
                self.assert_error(call(missing_event, self.headers("alice")), 404)
                missing = f"/api/events/{v1}/change-requests/{self.missing_id(_request_model())}"
                self.assert_error(call(missing, self.headers("alice")), 404)
                self.assert_error(call(self.url("P1", event="V1"), self.headers("alice")), 404)
                for user in ("ben", "dana", "farah", "admin", "lena"):
                    error = self.assert_error(call(self.url("T1"), self.headers(user)), 403)
                    self.assertNotIn("Charity Gala", error["error"])
                    self.assertNotIn("2026-12-06", error["error"])
        self.assert_still_pending("T1")
        self.assertEqual(self.saved_event(), before)
        self.email.assert_not_called()

    # TC-70-03 · AC1
    def test_tc_70_03_a_request_on_an_event_no_longer_approved_cannot_be_decided(self):
        self.seed_request("X1")
        before = self.saved_event("V3")

        body = self.review("X1")
        self.assertIs(body["can_decide"], False)
        self.assertEqual(body["blocked_reason"], "not_approved")
        self.assertIn("cancelled", body["message"])

        for decision, reason in (("accept", None), ("reject", REASON)):
            with self.subTest(decision=decision):
                error = self.assert_error(self.decide("X1", decision, reason), 409)
                self.assertEqual(error["reason"], "not_approved")
                self.assertIn("cancelled", error["error"])
        self.assert_still_pending("X1")
        self.assertEqual(self.saved_event("V3"), before)
        self.assertEqual(self.notifications("dana"), [])
        self.email.assert_not_called()

    # TC-70-04 · AC1, AC3
    def test_tc_70_04_the_coordinator_lists_their_pending_change_requests(self):
        self.seed_request("X1", requested_at=datetime(2026, 10, 25, 2, 0))
        self.seed_request("T1")
        self.seed_request("P1")
        self.seed_request("OLD", event="V1", changes=REQUESTS["N1"][1], status="accepted",
                          decided_at=datetime(2026, 10, 20, 2, 0),
                          decided_by_id=self.users["alice"].id,
                          requested_at=datetime(2026, 10, 19, 2, 0))

        def listed(user):
            response = self.client.get(LIST_URL, headers=self.headers(user))
            self.assertEqual(response.status_code, 200, response.get_json())
            return response.get_json()

        alices = listed("alice")
        self.assertEqual([r["id"] for r in alices["requests"]],
                         [self.requests["X1"].id, self.requests["T1"].id])
        first = alices["requests"][1]
        self.assertEqual((first["event"]["id"], first["event"]["title"]),
                         (self.events["V1"].id, "Charity Gala"))
        self.assertEqual(first["requested_by"]["id"], self.users["dana"].id)
        self.assertEqual(first["changes"][0]["field"], "start_time")
        self.assertIsNone(alices["message"])
        self.assertEqual([r["id"] for r in listed("ben")["requests"]], [self.requests["P1"].id])

        self.assert_error(self.client.get(LIST_URL, headers=self.headers("dana")), 403)
        self.assertEqual(self.client.get(LIST_URL).status_code, 401)
        chloes = listed("chloe")
        self.assertEqual(chloes["requests"], [])
        self.assertTrue(chloes["message"])


# ---------- AC2: what the change affects, before deciding ----------


class ImpactTests(ReviewTestCase):
    def impact(self, key):
        return self.review(key)["impact"]

    def listed_bookings(self, impact):
        ids = {row.id: key for key, row in self.bookings.items()}
        return {ids[item["id"]]: item for item in impact["venue_bookings"]}

    def listed_equipment(self, impact):
        ids = {row.id: key for key, row in self.requirements.items()}
        return {ids[item["id"]]: item for item in impact["equipment"]}

    # TC-70-05 · AC2
    def test_tc_70_05_a_time_change_lists_bookings_reserved_equipment_and_registrations(self):
        self.seed_request("T1")

        impact = self.impact("T1")

        bookings = self.listed_bookings(impact)
        self.assertEqual(set(bookings), {"B1", "B2", "B3"})
        b1 = bookings["B1"]
        self.assertEqual((b1["venue"]["name"], b1["status"], b1["start_time"], b1["end_time"]),
                         ("Grand Ballroom", "confirmed", "2026-12-05T18:00:00",
                          "2026-12-05T23:00:00"))
        self.assertTrue(all(item["reasons"] for item in bookings.values()))
        equipment = self.listed_equipment(impact)
        self.assertEqual(set(equipment), {"Q1"})
        self.assertEqual(equipment["Q1"]["reserved"], 2)
        self.assertIn("released", " ".join(equipment["Q1"]["reasons"]))
        registrations = impact["registrations"]
        self.assertEqual(registrations["registered"], 2)
        self.assertEqual(len(registrations["reasons"]), 1)
        self.assertIn("2 registered attendees", registrations["reasons"][0])
        self.assertIs(impact["affected"], True)
        self.assertIsNone(impact["message"])

    # TC-70-06 · AC2
    def test_tc_70_06_an_attendance_change_lists_small_venues_and_registrations_above_it(self):
        self.seed_request("N1")
        impact = self.impact("N1")

        bookings = self.listed_bookings(impact)
        self.assertEqual(set(bookings), {"B1", "B2"})
        self.assertIn("220", bookings["B1"]["reasons"][0])
        self.assertIn("120", bookings["B2"]["reasons"][0])
        self.assertEqual(impact["equipment"], [])
        self.assertEqual(impact["registrations"]["reasons"], [])

        # One request may be pending per event (SCRUM-46 A6), so N1 makes way for this one.
        self.db.session.delete(self.requests["N1"])
        self.db.session.commit()
        self.seed_request("LOW", event="V1", changes={"expected_attendance": {"from": 200, "to": 1}})
        low = self.review("LOW")["impact"]
        self.assertEqual(low["venue_bookings"], [])
        reasons = " ".join(low["registrations"]["reasons"])
        self.assertIn("2 people are already registered", reasons)
        self.assertIn("210 places", reasons)

    # TC-70-07 · AC2
    def test_tc_70_07_requirement_changes_list_bookings_and_equipment(self):
        self.seed_request("S1")

        impact = self.impact("S1")

        bookings = self.listed_bookings(impact)
        self.assertEqual(set(bookings), {"B1", "B2", "B3"})
        self.assertIn("venue requirements", bookings["B1"]["reasons"][0])
        equipment = self.listed_equipment(impact)
        self.assertEqual(set(equipment), {"Q1", "Q2"})
        self.assertIn("equipment requirements", equipment["Q2"]["reasons"][0])
        self.assertEqual((equipment["Q1"]["reserved"], equipment["Q2"]["reserved"]), (2, 0))
        self.assertEqual(impact["registrations"]["reasons"], [])

    # TC-70-08 · AC2
    def test_tc_70_08_only_live_arrangements_of_the_event_are_listed(self):
        self.seed_request("T1")
        self.seed_request("P1")

        impact = self.impact("T1")

        listed = {item["id"] for item in impact["venue_bookings"]}
        self.assertNotIn(self.bookings["B4"].id, listed)
        self.assertNotIn(self.bookings["B5"].id, listed)
        self.assertNotIn(self.requirements["Q2"].id, {item["id"] for item in impact["equipment"]})
        self.assertEqual(impact["registrations"]["registered"], 2)

        nothing = self.review("P1", user="ben")["impact"]
        self.assertEqual((nothing["venue_bookings"], nothing["equipment"]), ([], []))
        self.assertEqual(nothing["registrations"]["reasons"], [])
        self.assertIs(nothing["affected"], False)
        self.assertIn("Nothing", nothing["message"])

    # TC-70-09 · AC2, AC6
    def test_tc_70_09_a_failed_read_is_an_error_not_an_empty_impact(self):
        self.seed_request("T1")

        def fail(conn, cursor, statement, parameters, context, executemany):
            if "FROM venue_bookings" in statement:
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        self.db.session.expire_all()
        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            response = self.client.get(self.url("T1"), headers=self.headers("alice"))
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("simulated outage", body["error"])


# ---------- AC3 + AC4: accept or reject; saved with its time; a reason to reject ----------


class DecisionTests(ReviewTestCase):
    # TC-70-10 · AC3
    def test_tc_70_10_accepting_records_the_decision_and_its_time(self):
        self.seed_request("N1")
        started = datetime.utcnow()

        body = self.decided("N1", "accept")

        row = self.stored("N1")
        self.assertEqual((row.status, row.decided_by_id, row.decision_reason),
                         ("accepted", self.users["alice"].id, None))
        self.assertTrue(started <= row.decided_at <= datetime.utcnow())
        request = body["request"]
        self.assertEqual((request["status"], request["status_label"]), ("accepted", "Accepted"))
        self.assertEqual(request["decided_by"]["id"], self.users["alice"].id)
        self.assertEqual(request["decided_at"], row.decided_at.isoformat())
        self.assertIn("accepted", body["message"])
        self.assertIn("Charity Gala", body["message"])

    # TC-70-11 · AC3, AC4
    def test_tc_70_11_rejecting_records_the_decision_time_and_reason(self):
        self.seed_request("N1")

        body = self.decided("N1", "reject", f"  {REASON}  ")

        row = self.stored("N1")
        self.assertEqual((row.status, row.decided_by_id, row.decision_reason),
                         ("rejected", self.users["alice"].id, REASON))
        self.assertIsNotNone(row.decided_at)
        self.assertEqual((body["request"]["status_label"], body["request"]["decision_reason"]),
                         ("Rejected", REASON))
        self.assertIn("rejected", body["message"])

    # TC-70-12 · AC3
    def test_tc_70_12_a_decided_request_cannot_be_decided_again(self):
        self.seed_request("N1")
        self.decided("N1", "accept")
        first = self.stored("N1").decided_at

        for decision, reason in (("accept", None), ("reject", REASON)):
            with self.subTest(decision=decision):
                error = self.assert_error(self.decide("N1", decision, reason), 409)
                self.assertEqual(error["reason"], "decided")
                self.assertIn("already accepted", error["error"])
        row = self.stored("N1")
        self.assertEqual((row.status, row.decided_at, row.decision_reason),
                         ("accepted", first, None))
        self.assertEqual(len(self.notifications("dana")), 1)
        review = self.review("N1")
        self.assertIs(review["can_decide"], False)
        self.assertEqual(review["blocked_reason"], "decided")
        self.assertEqual(review["request"]["status"], "accepted")
        # What it would affect is only worked out before deciding (AC2, A3).
        self.assertIsNone(review["impact"])

    # TC-70-13 · AC3, AC4
    def test_tc_70_13_the_organiser_sees_the_outcome_and_may_ask_again(self):
        self.seed_request("N1")
        self.decided("N1", "reject", REASON)
        url = f"/api/events/{self.events['V1'].id}/change-requests"

        form = self.client.get(url, headers=self.headers("dana")).get_json()

        latest = form["latest_decision"]
        self.assertEqual((latest["id"], latest["status"], latest["status_label"]),
                         (self.requests["N1"].id, "rejected", "Rejected"))
        self.assertEqual(latest["decision_reason"], REASON)
        self.assertEqual(latest["decided_by"]["id"], self.users["alice"].id)
        self.assertIsNotNone(latest["decided_at"])
        self.assertIs(form["can_request"], True)
        self.assertIsNone(form["pending_request"])
        again = self.client.post(url, json={"expected_attendance": 230},
                                 headers=self.headers("dana"))
        self.assertEqual(again.status_code, 201, again.get_json())

    # TC-70-14 · AC3
    def test_tc_70_14_the_decision_must_be_clear(self):
        self.seed_request("N1")
        decision_url = f"{self.url('N1')}/decision"
        headers = self.headers("alice")

        not_json = self.client.post(decision_url, data="accept", content_type="text/plain",
                                    headers=headers)
        self.assert_error(not_json, 400)
        for body in ({}, {"decision": "approve"}, {"decision": "accept", "reason": 5}):
            with self.subTest(body=body):
                self.assert_error(self.client.post(decision_url, json=body, headers=headers), 400)
        self.assert_still_pending("N1")

    # TC-70-15 · AC4
    def test_tc_70_15_the_rejection_reason_is_required_and_limited(self):
        self.seed_request("N1")
        for reason in (None, "", "   ", "​", "x" * 501):
            with self.subTest(reason=reason if reason is None else len(reason)):
                error = self.assert_error(self.decide("N1", "reject", reason), 400)
                self.assertEqual(error["field"], "reason")
        self.assert_still_pending("N1")
        too_long = self.decide("N1", "reject", "x" * 501).get_json()
        self.assertIn("500 characters", too_long["error"])

        longest = "y" * 500
        self.decided("N1", "reject", f"  {longest}  ")
        self.assertEqual(self.stored("N1").decision_reason, longest)


# ---------- AC5: an event waiting for a coordinator can't take a request ----------


class WaitingForCoordinatorTests(ReviewTestCase):
    # TC-70-16 · AC5
    def test_tc_70_16_an_event_waiting_for_a_coordinator_cannot_take_a_request(self):
        waiting = self.make_event(organiser=self.users["dana"], title="Spring Fair",
                                  status="approved", expected_attendance=80,
                                  venue_requirements="Lawn")
        url = f"/api/events/{waiting.id}/change-requests"

        form = self.client.get(url, headers=self.headers("dana")).get_json()
        response = self.client.post(url, json={"expected_attendance": 90},
                                    headers=self.headers("dana"))

        self.assertEqual(form["blocked_reason"], "no_coordinator")
        self.assertIn("waiting for a coordinator", form["message"])
        body = self.assert_error(response, 409)
        self.assertEqual(body["reason"], "no_coordinator")
        self.assertIn("waiting for a coordinator", body["error"])
        self.assertEqual(_request_model().query.filter_by(event_id=waiting.id).all(), [])


# ---------- AC6: a failed save changes nothing ----------


class FailureTests(ReviewTestCase):
    def failing(self, condition):
        def fail(conn, cursor, statement, parameters, context, executemany):
            if condition(statement, str(parameters)):
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        return fail

    def decide_while_failing(self, condition, key, decision, reason=None):
        fail = self.failing(condition)
        self.db.session.expire_all()
        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            return self.decide(key, decision, reason)
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

    # TC-70-17 · AC6
    def test_tc_70_17_a_failed_save_leaves_the_request_and_event_unchanged(self):
        self.seed_request("T1")
        before = self.saved_event()
        cases = [
            ("the decision", lambda s, p: s.startswith("UPDATE event_change_requests"), "accept"),
            ("the event", lambda s, p: s.startswith("UPDATE events"), "accept"),
            ("the organiser's notification",
             lambda s, p: s.startswith("INSERT INTO notifications")
             and "change_request_accepted" in p, "accept"),
            ("an attendee's notification",
             lambda s, p: s.startswith("INSERT INTO notifications")
             and "event_details_changed" in p, "accept"),
            ("a rejection", lambda s, p: s.startswith("UPDATE event_change_requests"), "reject"),
        ]
        for name, condition, decision in cases:
            response = self.decide_while_failing(condition, "T1", decision,
                                                 REASON if decision == "reject" else None)
            with self.subTest(failing=name):
                body = self.assert_error(response, 503)
                self.assertIs(body.get("retryable"), True)
                self.assertEqual(body["error"], NOT_SAVED)
                self.assert_still_pending("T1")
                self.assertEqual(self.saved_event(), before)
                self.assertEqual(self.reservation_status("R1"), "reserved")
                for user in ("dana", "farah", "gail"):
                    self.assertEqual(self.notifications(user), [])
                self.email.assert_not_called()

    # TC-70-18 · AC6
    def test_tc_70_18_the_event_and_request_are_locked_before_deciding(self):
        self.seed_request("N1")
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        sa_event.listen(self.db.engine, "before_cursor_execute", record)
        try:
            self.decided("N1", "accept")
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", record)

        event_lock = next(i for i, s in enumerate(statements)
                          if "FROM events" in s and "FOR UPDATE" in s)
        request_lock = next(i for i, s in enumerate(statements)
                            if "FROM event_change_requests" in s and "FOR UPDATE" in s)
        first_write = next(i for i, s in enumerate(statements)
                           if s.startswith(("UPDATE", "INSERT")))
        self.assertLess(event_lock, request_lock)
        self.assertLess(request_lock, first_write)


# ---------- AC7: the organiser is notified ----------


class OrganiserNotificationTests(ReviewTestCase):
    # TC-70-19 · AC7, AC4
    def test_tc_70_19_the_organiser_is_told_the_decision(self):
        self.seed_request("T1")
        accepted = self.decided("T1", "accept")
        self.seed_request("N1")
        self.decided("N1", "reject", REASON)

        [yes] = self.notifications("dana", "change_request_accepted")
        [no] = self.notifications("dana", "change_request_rejected")
        alice = self.users["alice"].email
        for text in ("Charity Gala", "accepted", alice, "Start: 2026-12-05 18:00 → 2026-12-06 18:00"):
            self.assertIn(text, yes.message)
        for text in ("Charity Gala", "rejected", alice, REASON):
            self.assertIn(text, no.message)
        self.assertEqual((yes.event_id, no.event_id), (self.events["V1"].id,) * 2)
        self.assertEqual(self.emailed().count(self.users["dana"].email), 2)
        self.assertEqual((accepted["notification"]["in_app"],
                          accepted["notification"]["email_queued"]), (True, True))

    # TC-70-20 · AC7
    def test_tc_70_20_an_email_queue_failure_does_not_undo_the_decision(self):
        self.seed_request("T1")
        self.email.side_effect = ConnectionError("broker down")

        body = self.decided("T1", "accept")

        self.assertIs(body["notification"]["email_queued"], False)
        self.assertEqual(self.stored("T1").status, "accepted")
        self.assertEqual(self.saved_event()["start_time"], datetime(2026, 12, 6, 18, 0))
        self.assertEqual(len(self.notifications("dana")), 1)
        self.assertEqual(len(self.notifications("farah")), 1)
        self.assertEqual(self.email.call_count, 1)


# ---------- AC8: accepting applies the proposed values ----------


class AppliedTests(ReviewTestCase):
    # TC-70-21 · AC8
    def test_tc_70_21_accepting_applies_every_proposed_value(self):
        self.seed_request("T1")
        before = self.saved_event()

        self.decided("T1", "accept")

        after = self.saved_event()
        self.assertEqual((after.pop("start_time"), after.pop("end_time")),
                         (datetime(2026, 12, 6, 18, 0), datetime(2026, 12, 6, 23, 30)))
        before.pop("start_time"), before.pop("end_time")
        self.assertEqual(after, before)
        planning = self.client.get(f"/api/events/{self.events['V1'].id}/planning",
                                   headers=self.headers("alice")).get_json()
        self.assertEqual((planning["start_time"], planning["end_time"]),
                         ("2026-12-06T18:00:00", "2026-12-06T23:30:00"))

        self.seed_request("S1")
        self.decided("S1", "accept")
        saved = self.saved_event()
        self.assertEqual((saved["venue_requirements"], saved["equipment_requirements"]),
                         ("Ballroom and breakout room", "4 wireless microphones"))

        self.seed_request("CLEAR", event="V1", changes={
            "equipment_requirements": {"from": "4 wireless microphones", "to": None}})
        self.decided("CLEAR", "accept")
        self.assertIsNone(self.saved_event()["equipment_requirements"])

    # TC-70-22 · AC8
    def test_tc_70_22_rejecting_leaves_the_event_unchanged(self):
        self.seed_request("T1")
        before = self.saved_event()

        self.decided("T1", "reject", REASON)

        self.assertEqual(self.saved_event(), before)
        self.assertEqual(self.reservation_status("R1"), "reserved")

    # TC-70-23 · AC8, AC2
    def test_tc_70_23_new_times_release_reserved_equipment_and_leave_bookings(self):
        def booking_rows():
            self.db.session.expire_all()
            return {key: (row.status, row.start_time, row.end_time)
                    for key, row in ((k, self.db.session.get(VenueBooking, b.id))
                                     for k, b in self.bookings.items())}

        bookings_before = booking_rows()
        self.seed_request("N1")
        self.decided("N1", "accept")
        self.assertEqual(self.reservation_status("R1"), "reserved")

        self.seed_request("T1")
        body = self.decided("T1", "accept")

        self.db.session.expire_all()
        r1 = self.db.session.get(EquipmentReservation, self.reservations["R1"].id)
        self.assertEqual((r1.status, r1.release_reason),
                         ("released", "The event's times were changed."))
        self.assertIn("reserved equipment was released", body["message"])
        self.assertEqual(booking_rows(), bookings_before)


# ---------- AC9: registered attendees are told new details ----------


class AttendeeNotificationTests(ReviewTestCase):
    # TC-70-24 · AC9
    def test_tc_70_24_every_registered_attendee_is_told_the_new_details(self):
        self.seed_request("T1")

        body = self.decided("T1", "accept")

        for user in ("farah", "gail"):
            with self.subTest(attendee=user):
                [note] = self.notifications(user, "event_details_changed")
                self.assertEqual(note.event_id, self.events["V1"].id)
                for text in ("Charity Gala", "2026-12-06 18:00", "2026-12-06 23:30",
                             "Grand Ballroom"):
                    self.assertIn(text, note.message)
                self.assertEqual(self.emailed().count(self.users[user].email), 1)
        for user in ("hugo", "ivy", "dana", "alice"):
            with self.subTest(not_told=user):
                self.assertEqual(self.notifications(user, "event_details_changed"), [])
        for user in ("hugo", "ivy", "alice"):
            self.assertNotIn(self.users[user].email, self.emailed())
        # The organiser's one email is about the decision (AC7), not the new details.
        self.assertEqual(self.emailed().count(self.users["dana"].email), 1)
        self.assertEqual(body["notification"]["attendees_notified"], 2)

    # TC-70-25 · AC9
    def test_tc_70_25_no_attendee_is_told_when_the_times_do_not_change(self):
        self.seed_request("N1")
        accepted = self.decided("N1", "accept")
        self.seed_request("T1")
        self.decided("T1", "reject", REASON)

        for user in ("farah", "gail", "hugo"):
            self.assertEqual(self.notifications(user), [])
            self.assertNotIn(self.users[user].email, self.emailed())
        self.assertEqual(accepted["notification"]["attendees_notified"], 0)
