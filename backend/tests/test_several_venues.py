"""Tests for SCRUM-85 "Several Venues for One Event".

Each test names the case it automates from
docs/test-cases/SCRUM-85-several-venues-for-one-event.md (TC-85-xx) and the acceptance
criteria it checks. Assumptions A1-A8 and questions Q1-Q6 are defined there. TC-85-24 to
29 are frontend cases, in EventPlanningPage.test.jsx and VenueBookingRequestPage.test.jsx.

Endpoints
    POST /api/venues/bookings                    several requests per event (A1); 409
        {"error", "reason": "already_requested"} for the event's own pending request at
        the same venue and an overlapping time (A2)
    POST /api/venues/bookings/<id>/approve       and /hold: no conflict from the event's
        bookings at other venues (A3)
    POST /api/venues/bookings/<id>/cancel        optional {"also_cancel": [booking id]}
        200 {..., "booking": main booking, "also_cancelled": [booking]}
        400 {"error", "field": "also_cancel"} · 409 {"reason": "not_cancellable"} (A6)
    GET  /api/events/<id>/planning               adds "venue_bookings": [{"id",
        "venue": {"id", "name", "location"}, "start_time", "end_time", "setup_minutes",
        "turnaround_minutes", "status", "hold_expires_at", "hold_expired"}] (A7)

MV-SEED is SCRUM-94's CB-SEED: E1's P1 (pending), C1 (confirmed), T1 (tentative), R1
(rejected) and X1 (cancelled), and E2's P2.
"""

import unittest
from datetime import datetime
from unittest import mock

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.models import VenueBooking
from tests.test_venue_booking_approval import P1_END, P1_START
from tests.test_venue_booking_cancellation import (
    APPROVED_AT,
    CANCEL_URL,
    CancellationTestCase,
)

BOOKINGS_URL = "/api/venues/bookings"
# The bookings of E1 in MV-SEED, all of which the event's other changes must leave alone.
E1_BOOKINGS = ("P1", "C1", "T1", "R1", "X1")


class SeveralVenuesTestCase(CancellationTestCase):
    """MV-SEED, plus helpers for requests, cancelling several bookings and the planning view."""

    def request_venue(self, venue, start, end, event="E1", as_user="alice", **extra):
        body = {"event_id": self.events[event].id, "venue_id": self.venues[venue].id,
                "start_time": start, "end_time": end,
                "venue_requirements": "Breakout space for 40", **extra}
        return self.client.post(BOOKINGS_URL, json=body,
                                headers=self.auth_headers(self.users[as_user]))

    def cancel_with(self, booking, body, as_user="alice"):
        return self.client.post(CANCEL_URL.format(self.bookings[booking].id), json=body,
                                headers=self.auth_headers(self.users[as_user]))

    def add_c2(self):
        """C2: a second confirmed booking of E1, at Aurora Ballroom on the morning of 12 Mar."""
        c2 = self.add_booking("E1", "fully_recorded", "confirmed", datetime(2027, 3, 12, 9, 0),
                              datetime(2027, 3, 12, 12, 0), requested_by="alice")
        c2.decided_at, c2.decided_by_id = APPROVED_AT, self.users["gus"].id
        self.db.session.commit()
        self.bookings["C2"] = c2
        return c2

    def ids(self, *keys):
        return [self.bookings[key].id for key in keys]

    def statuses(self, *keys):
        return {key: self.stored(key)["status"] for key in keys}

    def own_bookings(self, event="E1"):
        self.db.session.expire_all()
        return (VenueBooking.query.filter_by(event_id=self.events[event].id)
                .order_by(VenueBooking.id).all())

    def listed_bookings(self, event="E1"):
        return self.planning(event)["venue_bookings"]


# ---------- AC1: several requests, each with its own venue and period ----------


class SeveralRequestsTests(SeveralVenuesTestCase):
    # TC-85-01 · AC1 (A1) — another venue alongside pending, held and confirmed bookings.
    def test_tc_85_01_another_venue_can_be_requested_alongside_existing_bookings(self):
        before = {key: self.stored(key) for key in E1_BOOKINGS}

        response = self.request_venue("partially_recorded", "2027-03-12T16:00",
                                      "2027-03-12T22:30")

        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["booking"]["status"], "pending")
        pending = [b for b in self.own_bookings() if b.status == "pending"]
        self.assertEqual(len(pending), 2)
        self.assertEqual({key: self.stored(key) for key in E1_BOOKINGS}, before)

    # TC-85-02 · AC1 (A1) — each request keeps its own venue, period and details.
    def test_tc_85_02_each_request_keeps_its_own_details(self):
        sent = [
            ("partially_recorded", "2027-03-12T09:00", "2027-03-12T12:00", 30, 15,
             "Breakout room A"),
            ("unavailable", "2027-03-12T13:00", "2027-03-12T15:00", 0, 0, "Breakout room B"),
        ]
        made = []
        for venue, start, end, setup, turnaround, requirements in sent:
            response = self.request_venue(venue, start, end, setup_minutes=setup,
                                          turnaround_minutes=turnaround,
                                          venue_requirements=requirements)
            self.assertEqual(response.status_code, 201, response.get_json())
            made.append(response.get_json()["booking"]["id"])

        for booking_id, (venue, start, end, setup, turnaround, requirements) in zip(made, sent):
            row = self.stored(self.db.session.get(VenueBooking, booking_id))
            self.assertEqual(
                (row["venue_id"], row["start_time"], row["end_time"], row["setup_minutes"],
                 row["turnaround_minutes"], row["venue_requirements"], row["status"]),
                (self.venues[venue].id, datetime.fromisoformat(start),
                 datetime.fromisoformat(end), setup, turnaround, requirements, "pending"))

    # TC-85-03 · AC1 (A2, Q2) — the same venue at an overlapping time is a duplicate.
    def test_tc_85_03_the_same_venue_at_an_overlapping_time_is_refused(self):
        count = len(self.own_bookings())
        for start, end, setup in (("2027-03-12T20:00", "2027-03-12T23:00", 0),
                                  ("2027-03-12T22:45", "2027-03-12T23:30", 30)):
            with self.subTest(start=start, setup=setup):
                body = self.assert_error(
                    self.request_venue("fully_recorded", start, end, setup_minutes=setup),
                    409, reason="already_requested")
                self.assertIn("Aurora Ballroom", body["error"])
                self.assertEqual(len(self.own_bookings()), count)

        touching = self.request_venue("fully_recorded", "2027-03-12T22:30", "2027-03-12T23:30")
        self.assertEqual(touching.status_code, 201, touching.get_json())

    # TC-85-04 · AC1 (A2) — decided requests and other events' requests don't block.
    def test_tc_85_04_decided_or_other_events_requests_do_not_block(self):
        other_event = self.request_venue("fully_recorded", "2027-03-12T16:00",
                                         "2027-03-12T22:30", event="E3")
        self.assertEqual(other_event.status_code, 201, other_event.get_json())

        rejected = self.client.post(f"{BOOKINGS_URL}/{self.bookings['P1'].id}/reject",
                                    json={"reason": "No stage power."},
                                    headers=self.auth_headers(self.users["gus"]))
        self.assertEqual(rejected.status_code, 200, rejected.get_json())
        again = self.request_venue("fully_recorded", "2027-03-12T16:00", "2027-03-12T22:30")
        self.assertEqual(again.status_code, 201, again.get_json())

    # TC-85-05 · AC1 (A1) — the database allows several pending requests for one event.
    def test_tc_85_05_the_database_allows_several_pending_requests(self):
        for venue in ("fully_recorded", "partially_recorded"):
            self.db.session.add(VenueBooking(
                event_id=self.events["E3"].id, venue_id=self.venues[venue].id,
                status="pending", start_time=datetime(2027, 3, 20, 10, 0),
                end_time=datetime(2027, 3, 20, 12, 0)))

        self.db.session.commit()

        self.assertEqual([b.status for b in self.own_bookings("E3")], ["pending", "pending"])

    # TC-85-06 · AC1 (A2) — the event is locked before its requests are checked.
    def test_tc_85_06_the_event_is_locked_before_its_requests_are_checked(self):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(" ".join(statement.split()))

        sa_event.listen(self.db.engine, "before_cursor_execute", record)
        try:
            response = self.request_venue("partially_recorded", "2027-03-12T16:00",
                                          "2027-03-12T22:30")
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", record)

        self.assertEqual(response.status_code, 201, response.get_json())
        lock = next(i for i, s in enumerate(statements)
                    if "FROM events" in s and "FOR UPDATE" in s)
        look = next(i for i, s in enumerate(statements)
                    if s.startswith("SELECT") and "FROM venue_bookings" in s)
        self.assertLess(lock, look)


# ---------- AC2: each booking is checked, approved and rejected on its own ----------


class CheckedOnItsOwnTests(SeveralVenuesTestCase):
    # TC-85-07 · AC2 (A3) — a second venue is approved alongside a confirmed one.
    def test_tc_85_07_a_second_venue_is_approved_alongside_a_confirmed_one(self):
        response = self.approve("P1")

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.statuses("P1", "C1"), {"P1": "confirmed", "C1": "confirmed"})

    # TC-85-08 · AC2 (A3) — the event's venue elsewhere is not a conflict.
    def test_tc_85_08_the_events_venue_elsewhere_is_not_a_conflict(self):
        listed = self.client.get(BOOKINGS_URL, headers=self.auth_headers(self.users["gus"]))

        self.assertEqual(listed.status_code, 200, listed.get_json())
        p1 = next(b for b in listed.get_json()["bookings"] if b["id"] == self.bookings["P1"].id)
        self.assertEqual(p1["conflicts"], [])

    # TC-85-09 · AC2 (A3) — the event's own booking at the same venue still clashes.
    def test_tc_85_09_the_events_own_booking_at_the_same_venue_still_clashes(self):
        p3 = self.add_booking("E1", "recorded_as_none", "pending", datetime(2027, 3, 12, 20, 0),
                              datetime(2027, 3, 12, 23, 0), requested_by="alice")

        body = self.assert_error(self.approve(p3.id), 409, reason="conflict")

        self.assertEqual([(c["type"], c["id"], c["event"]["title"]) for c in body["conflicts"]],
                         [("booking", self.bookings["C1"].id, "Harbour Lights Festival")])
        self.assertEqual(self.stored(p3)["status"], "pending")

    # TC-85-10 · AC2, AC3 (A3, A5) — a hold on a second venue changes nothing else.
    def test_tc_85_10_a_hold_can_be_placed_on_a_second_venue(self):
        others = ("C1", "T1", "R1", "X1")
        before = {key: self.stored(key) for key in others}
        event_before = self.event_columns()

        response = self.client.post(f"{BOOKINGS_URL}/{self.bookings['P1'].id}/hold",
                                    json={"expires_at": "2027-03-01T12:00"},
                                    headers=self.auth_headers(self.users["gus"]))

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.stored("P1")["status"], "tentative")
        self.assertEqual({key: self.stored(key) for key in others}, before)
        self.assertEqual(self.event_columns(), event_before)

    # TC-85-11 · AC2 (A3) — one venue's clash doesn't stop another venue's approval.
    def test_tc_85_11_one_venues_clash_does_not_stop_another(self):
        self.add_block("fully_recorded", "Electrical works", datetime(2027, 3, 12, 15, 0),
                       datetime(2027, 3, 12, 17, 0))
        p4 = self.add_booking("E1", "partially_recorded", "pending", P1_START, P1_END,
                              requested_by="alice")

        refused = self.assert_error(self.approve("P1"), 409, reason="conflict")
        self.assertEqual([c["type"] for c in refused["conflicts"]], ["block"])
        approved = self.approve(p4.id)
        self.assertEqual(approved.status_code, 200, approved.get_json())

    # TC-85-12 · AC2, AC3 (A5) — rejecting one request leaves the event's other bookings.
    def test_tc_85_12_rejecting_one_request_leaves_the_others(self):
        self.assertEqual(self.approve("P1").status_code, 200)
        p4 = self.add_booking("E1", "partially_recorded", "pending", P1_START, P1_END,
                              requested_by="alice")
        before = {key: self.stored(key) for key in E1_BOOKINGS}
        venue_before = self.event("E1").venue_id

        response = self.client.post(f"{BOOKINGS_URL}/{p4.id}/reject",
                                    json={"reason": "Too small for the breakout."},
                                    headers=self.auth_headers(self.users["gus"]))

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.stored(p4)["status"], "rejected")
        self.assertEqual({key: self.stored(key) for key in E1_BOOKINGS}, before)
        self.assertEqual(self.event("E1").venue_id, venue_before)

    # TC-85-13 · AC2 (A4, Q3) — the first confirmed venue stays the event's venue.
    def test_tc_85_13_the_first_confirmed_venue_stays_the_events_venue(self):
        self.assertEqual(self.approve("P1").status_code, 200)

        civic = self.venues["recorded_as_none"]
        self.assertEqual(self.event("E1").venue_id, civic.id)
        self.assertEqual(self.planning()["venue"]["id"], civic.id)


# ---------- AC3: changing or cancelling one booking leaves the others ----------


class CancellingSeveralTests(SeveralVenuesTestCase):
    # TC-85-14 · AC3 (A4, A5) — cancelling one confirmed booking leaves the others.
    def test_tc_85_14_cancelling_one_confirmed_booking_leaves_the_others(self):
        self.add_c2()
        before = {key: self.stored(key) for key in E1_BOOKINGS}

        self.assert_cancelled(self.cancel("C2"), "C2")

        self.assertEqual({key: self.stored(key) for key in E1_BOOKINGS}, before)
        self.assertEqual(self.event("E1").venue_id, self.venues["recorded_as_none"].id)

    # TC-85-15 · AC3 (A4, Q3) — cancelling the main venue moves the event's venue.
    def test_tc_85_15_cancelling_the_main_venue_moves_the_events_venue(self):
        self.add_c2()

        self.assert_cancelled(self.cancel("C1"), "C1")
        aurora = self.venues["fully_recorded"]
        self.assertEqual(self.event("E1").venue_id, aurora.id)
        self.assertEqual(self.planning()["venue"]["id"], aurora.id)

        self.assert_cancelled(self.cancel("C2"), "C2")
        self.assertIsNone(self.event("E1").venue_id)

    # TC-85-16 · AC3 (A6) — the coordinator chooses to cancel other bookings too.
    def test_tc_85_16_the_coordinator_chooses_to_cancel_others_too(self):
        before = {key: self.stored(key) for key in ("R1", "X1")}

        body = self.assert_cancelled(
            self.cancel_with("P1", {"also_cancel": self.ids("C1", "T1")}), "P1")

        self.assertEqual(self.statuses("C1", "T1"), {"C1": "cancelled", "T1": "cancelled"})
        self.assertEqual({key: self.stored(key) for key in ("R1", "X1")}, before)
        self.assertIsNone(self.event("E1").venue_id)
        self.assertEqual(body["booking"]["id"], self.bookings["P1"].id)
        self.assertEqual([(b["id"], b["status"]) for b in body["also_cancelled"]],
                         [(self.bookings["C1"].id, "cancelled"),
                          (self.bookings["T1"].id, "cancelled")])
        for venue in ("Aurora Ballroom", "Civic Hall"):
            self.assertIn(venue, body["message"])
        self.assertEqual(body["notification"], {"in_app": True, "email_queued": True})

        notices = self.cancellation_notices(self.users["gus"])
        self.assertEqual(len(notices), 1)
        for detail in ("Civic Hall", "Aurora Ballroom", "2027-03-12 16:00", "2027-03-13 09:00",
                       "pending", "confirmed", "tentative"):
            self.assertIn(detail, notices[0].message)
        emailed = [call.args[0] for call in self.queue_email.call_args_list]
        self.assertEqual(emailed.count(self.users["gus"].email), 1)

    # TC-85-17 · AC3 (A6, Q5) — a refused choice cancels nothing.
    def test_tc_85_17_a_refused_choice_cancels_nothing(self):
        everything = (*E1_BOOKINGS, "P2")
        before = {key: self.stored(key) for key in everything}
        event_before = self.event_columns()
        unknown = self.missing_id(VenueBooking)

        answers = {}
        for case, body in (("another event's booking", {"also_cancel": self.ids("P2")}),
                           ("an unknown booking", {"also_cancel": [unknown]}),
                           ("not a list", {"also_cancel": "C1"}),
                           ("not ids", {"also_cancel": [True]}),
                           ("another field", {"reason": "Plans changed"})):
            with self.subTest(case=case):
                response = self.cancel_with("P1", body)
                refused = self.assert_error(response, 400)
                self.assertEqual(refused.get("field"), "also_cancel" if "also_cancel" in body
                                 else "reason")
                answers[case] = refused["error"]
        self.assertEqual(answers["another event's booking"], answers["an unknown booking"])

        with self.subTest(case="a rejected booking"):
            refused = self.assert_error(
                self.cancel_with("P1", {"also_cancel": self.ids("C1", "R1")}), 409,
                reason="not_cancellable")
            self.assertIn("rejected", refused["error"])

        with self.subTest(case="not the event's coordinator"):
            self.assert_error(self.cancel_with("P1", {"also_cancel": "C1"}, as_user="ben"), 403)

        self.assertEqual({key: self.stored(key) for key in everything}, before)
        self.assertEqual(self.event_columns(), event_before)
        self.assert_nothing_announced()

    # TC-85-18 · AC3 (A5) — changing one hold's expiry leaves the other bookings.
    def test_tc_85_18_changing_one_hold_leaves_the_others(self):
        others = ("P1", "C1", "R1", "X1")
        before = {key: self.stored(key) for key in others}
        event_before = self.event_columns()

        response = self.client.patch(f"{BOOKINGS_URL}/{self.bookings['T1'].id}/hold",
                                     json={"expires_at": "2027-03-02T12:00"},
                                     headers=self.auth_headers(self.users["gus"]))

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.stored("T1")["hold_expires_at"], datetime(2027, 3, 2, 12, 0))
        self.assertEqual({key: self.stored(key) for key in others}, before)
        self.assertEqual(self.event_columns(), event_before)

    # TC-85-19 · AC3 (A6) — a failed save cancels none of them.
    def test_tc_85_19_a_failed_save_cancels_none_of_them(self):
        before = {key: self.stored(key) for key in ("P1", "C1")}
        event_before = self.event_columns()

        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.cancel_with("P1", {"also_cancel": self.ids("C1")})

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertEqual({key: self.stored(key) for key in ("P1", "C1")}, before)
        self.assertEqual(self.event_columns(), event_before)
        self.assert_nothing_announced()


# ---------- AC4: the planning view lists every booking with its status ----------


class PlanningViewTests(SeveralVenuesTestCase):
    def expected(self, key, venue, status, hold_expires_at=None, hold_expired=None):
        booking = self.bookings[key]
        venue = self.venues[venue]
        return {
            "id": booking.id,
            "venue": {"id": venue.id, "name": venue.name, "location": venue.location},
            "start_time": booking.start_time.isoformat(),
            "end_time": booking.end_time.isoformat(),
            "setup_minutes": 0,
            "turnaround_minutes": 0,
            "status": status,
            "hold_expires_at": hold_expires_at,
            "hold_expired": hold_expired,
        }

    # TC-85-20 · AC4 (A7) — every booking with its status, in time order.
    def test_tc_85_20_the_planning_view_lists_every_booking_with_its_status(self):
        self.assertEqual(self.listed_bookings(), [
            self.expected("R1", "recorded_as_none", "rejected"),
            self.expected("X1", "partially_recorded", "cancelled"),
            self.expected("P1", "fully_recorded", "pending"),
            self.expected("C1", "recorded_as_none", "confirmed"),
            self.expected("T1", "fully_recorded", "tentative",
                          hold_expires_at="2027-03-01T12:00:00", hold_expired=False),
        ])

    # TC-85-21 · AC4 (A7) — an expired hold is shown as expired.
    def test_tc_85_21_an_expired_hold_is_shown_as_expired(self):
        self.bookings["T1"].hold_expires_at = datetime(2026, 1, 1, 12, 0)
        self.db.session.commit()

        t1 = next(b for b in self.listed_bookings() if b["id"] == self.bookings["T1"].id)

        self.assertEqual((t1["status"], t1["hold_expires_at"], t1["hold_expired"]),
                         ("tentative", "2026-01-01T12:00:00", True))

    # TC-85-22 · AC4 (A7) — only the event's own bookings, and none is not an error.
    def test_tc_85_22_only_the_events_own_bookings_are_listed(self):
        self.assertEqual(self.listed_bookings("E3"), [])
        listed = [b["id"] for b in self.listed_bookings()]
        self.assertNotIn(self.bookings["P2"].id, listed)
        self.assertEqual(sorted(listed), sorted(self.ids(*E1_BOOKINGS)))

    # TC-85-23 · AC4 (A7) — a failed read of the bookings is a failure, not an empty list.
    def test_tc_85_23_a_failed_read_is_a_failure_not_an_empty_list(self):
        headers = self.auth_headers(self.users["alice"])
        self.db.session.expire_all()

        def fail(conn, cursor, statement, parameters, context, executemany):
            if "FROM venue_bookings" in statement:
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            response = self.client.get(f"/api/events/{self.events['E1'].id}/planning",
                                       headers=headers)
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        self.assertEqual(response.status_code, 503, response.get_json())
        body = response.get_json()
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("venue_bookings", body)
        self.assertNotIn("title", body)


if __name__ == "__main__":
    unittest.main()
