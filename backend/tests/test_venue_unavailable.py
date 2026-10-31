"""Tests for SCRUM-88 "Venue becomes unavailable after booking".

Each test names the case it automates from the "Sprint 4 test cases" sheet
(IS212-US88-TCnn) and docs/test-cases/SCRUM-88-venue-becomes-unavailable.md.

Model (db/venue_unavailable_periods.sql): new table venue_replacement_flags, one row per
confirmed booking flagged "Venue unavailable: replacement needed" (booking_id unique,
block_id = the unavailable period that raised it). An unavailable period is a VenueBlock.

API
    POST /api/venues/<id>/unavailable   body {"reason", "start_time", "end_time"} ("YYYY-MM-DDTHH:MM")
        201 {"message", "period": {"id", "venue_id", "reason", "start_time", "end_time"},
             "flagged": [replacement entry], "notified": [coordinator user ids]}
        401 session · 404 unknown venue · 403 not Venue Staff · 400 {"fields": {...}}
        503 {"retryable": true} and nothing saved if any part fails to save
    GET  /api/venues/<id>/unavailable   Venue Staff only: {"periods": [period], "message"}
    GET  /api/venues/replacement-needed Venue Staff only: {"bookings": [entry], "message"}
        entry = {"id", "flag": "Venue unavailable: replacement needed", "status", "event":
                 {"id", "title"}, "venue": {"id", "name", "location"}, "start_time", "end_time",
                 "period": {"id", "reason", "start_time", "end_time"}, "flagged_at"}
    GET /api/events/<id>/planning  each venue booking has "flag" (the text or null); the event
        has "change_review": {"needed": bool, "reason"}
    POST /api/venues/bookings      409 reason "conflict" naming the unavailable period
"""

import unittest
from contextlib import contextmanager
from datetime import datetime

import psycopg2
from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app.models import Event, Notification, VenueBlock, VenueBooking
from tests import seed_data
from tests.test_venue_booking_request import BookingRequestTestCase

FLAG = "Venue unavailable: replacement needed"
REASON = "Floor renovation"
START, END = "2027-11-20T09:00", "2027-11-20T18:00"


def at(hour, minute=0, day=20):
    return datetime(2027, 11, day, hour, minute)


class UnavailableTestCase(BookingRequestTestCase):
    def setUp(self):
        super().setUp()
        self.venues.update(self.seed_venues(seed_data.SEARCH_VENUES))
        self.v101 = self.venues["fully_recorded"]
        self.v102 = self.venues["harbour_room"]
        self.events["E1"].status = "confirmed"  # E-801, coordinator alice
        self.db.session.commit()
        self.b801 = self.book("E1", self.v101, at(10), at(12))

    # ---------- Seeding and calls ----------

    def book(self, event, venue, start, end, status="confirmed"):
        booking = VenueBooking(
            event_id=self.events[event].id, venue_id=venue.id, status=status,
            start_time=start, end_time=end, venue_requirements="x",
            requested_by_id=self.users["alice"].id)
        self.db.session.add(booking)
        self.db.session.commit()
        return booking

    def record(self, venue=None, reason=REASON, start=START, end=END, as_user="gus",
               headers=None, **extra):
        body = {"reason": reason, "start_time": start, "end_time": end, **extra}
        body = {k: v for k, v in body.items() if v is not ...}
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.post(f"/api/venues/{(venue or self.v101).id}/unavailable",
                                json=body, headers=headers)

    def recorded(self, expected=201, **kwargs):
        response = self.record(**kwargs)
        self.assertEqual(response.status_code, expected, response.get_json())
        return response.get_json()

    def periods(self, venue=None, user="gus"):
        response = self.client.get(f"/api/venues/{(venue or self.v101).id}/unavailable",
                                   headers=self.auth_headers(self.users[user]))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["periods"]

    def replacement_list(self, user="gus"):
        return self.client.get("/api/venues/replacement-needed",
                               headers=self.auth_headers(self.users[user]))

    def flagged_ids(self):
        response = self.replacement_list()
        self.assertEqual(response.status_code, 200, response.get_json())
        return sorted(b["id"] for b in response.get_json()["bookings"])

    def stored_blocks(self):
        self.db.session.expire_all()
        return VenueBlock.query.filter_by(venue_id=self.v101.id).count()

    def notifications(self, user):
        self.db.session.expire_all()
        return (Notification.query.filter_by(recipient_id=self.users[user].id,
                                             kind="venue_unavailable").all())

    def event_row(self, key="E1"):
        self.db.session.expire_all()
        e = self.db.session.get(Event, self.events[key].id)
        return (e.title, e.start_time, e.end_time, e.expected_attendance, e.venue_requirements,
                e.venue_id, e.coordinator_id)

    def status_of(self, key):
        self.db.session.expire_all()
        return self.db.session.get(Event, self.events[key].id).status

    @contextmanager
    def queries_fail_on(self, table):
        def fail(conn, cursor, statement, parameters, context, executemany):
            if table in statement and not statement.lstrip().upper().startswith(
                    ("SAVEPOINT", "ROLLBACK", "RELEASE")):
                raise OperationalError(
                    statement, parameters, psycopg2.OperationalError("simulated outage"))

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            yield
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)


# ---------- AC1: recording an unavailable period ----------


class RecordingTests(UnavailableTestCase):
    def test_tc1_venue_staff_record_a_period_on_a_venue_with_no_bookings(self):  # AC1
        body = self.recorded(venue=self.v102, reason="Fire safety inspection",
                             start="2027-11-25T09:00", end="2027-11-25T17:00")
        self.assertIn("recorded", body["message"].lower())
        self.assertEqual(body["flagged"], [])
        [period] = self.periods(self.v102)
        self.assertEqual((period["reason"], period["start_time"], period["end_time"]),
                         ("Fire safety inspection", "2027-11-25T09:00:00", "2027-11-25T17:00:00"))
        self.assertEqual(period["venue_id"], self.v102.id)

    def test_tc2_a_period_can_be_recorded_over_a_confirmed_booking(self):  # AC1
        body = self.recorded()
        self.assertEqual(body["period"]["reason"], REASON)
        self.assertEqual(len(self.periods()), 1)

    def test_tc3_a_reason_is_required(self):  # AC1
        for reason in ("", "   ", None, ...):
            with self.subTest(reason=reason):
                response = self.record(reason=reason)
                self.assertEqual(response.status_code, 400)
                self.assertIn("reason", response.get_json()["fields"])
        self.assertEqual(self.stored_blocks(), 0)
        self.assertEqual(self.flagged_ids(), [])

    def test_tc4_a_start_is_required(self):  # AC1
        for start in ("", None, ...):
            with self.subTest(start=start):
                response = self.record(start=start)
                self.assertEqual(response.status_code, 400)
                self.assertIn("start_time", response.get_json()["fields"])
        self.assertEqual(self.stored_blocks(), 0)
        self.assertEqual(self.flagged_ids(), [])

    def test_tc5_an_end_is_required(self):  # AC1
        for end in ("", None, ...):
            with self.subTest(end=end):
                response = self.record(end=end)
                self.assertEqual(response.status_code, 400)
                self.assertIn("end_time", response.get_json()["fields"])
        self.assertEqual(self.stored_blocks(), 0)
        self.assertEqual(self.flagged_ids(), [])

    def test_tc6_an_end_before_the_start_is_rejected(self):  # AC1
        response = self.record(start="2027-11-20T18:00", end="2027-11-20T09:00")
        self.assertEqual(response.status_code, 400)
        self.assertIn("after the start", response.get_json()["fields"]["end_time"])
        self.assertEqual(self.stored_blocks(), 0)

    def test_tc7_an_end_equal_to_the_start_is_rejected(self):  # AC1
        response = self.record(start="2027-11-20T09:00", end="2027-11-20T09:00")
        self.assertEqual(response.status_code, 400)
        self.assertIn("after the start", response.get_json()["fields"]["end_time"])
        self.assertEqual(self.stored_blocks(), 0)

    def test_tc8_a_period_one_minute_long_is_accepted(self):  # AC1
        self.recorded(venue=self.v102, reason="Quick inspection",
                      start="2027-11-25T09:00", end="2027-11-25T09:01")
        self.assertEqual(len(self.periods(self.v102)), 1)

    def test_badly_formatted_times_and_non_text_values_are_rejected(self):  # AC1
        for field, value in (("start_time", "20/11/2027 09:00"), ("end_time", "tomorrow"),
                             ("start_time", 5), ("reason", 5), ("reason", ["x"])):
            with self.subTest(field=field, value=value):
                response = self.record(**{{"start_time": "start", "end_time": "end",
                                           "reason": "reason"}[field]: value})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.get_json()["fields"])
        self.assertEqual(self.stored_blocks(), 0)

    def test_every_problem_is_named_at_once(self):  # AC1
        response = self.record(reason="", start=None, end=None)
        self.assertEqual(set(response.get_json()["fields"]), {"reason", "start_time", "end_time"})

    def test_an_unknown_field_is_refused(self):  # AC1
        response = self.record(venue_id=3)
        self.assertEqual(response.status_code, 400)
        self.assertIn("venue_id", response.get_json()["fields"])

    def test_a_reason_over_the_limit_is_rejected(self):  # AC1
        response = self.record(reason="x" * 501)
        self.assertEqual(response.status_code, 400)
        self.assertIn("reason", response.get_json()["fields"])

    def test_the_period_lists_for_the_venue_only_in_time_order(self):  # AC1
        self.recorded(start="2027-12-01T09:00", end="2027-12-01T10:00", reason="Later")
        self.recorded(reason="Earlier")
        self.recorded(venue=self.v102, reason="Elsewhere")
        self.assertEqual([p["reason"] for p in self.periods()], ["Earlier", "Later"])

    def test_the_period_with_no_periods_says_so(self):  # AC1
        response = self.client.get(f"/api/venues/{self.v102.id}/unavailable",
                                   headers=self.auth_headers(self.users["gus"]))
        self.assertEqual(response.get_json()["periods"], [])
        self.assertTrue(response.get_json()["message"])

    def test_an_unknown_venue_is_a_404_before_the_role_check(self):  # AC1
        response = self.client.post("/api/venues/999999/unavailable", json={},
                                    headers=self.auth_headers(self.users["alice"]))
        self.assertEqual(response.status_code, 404)

    def test_no_session_is_a_401(self):  # AC6
        response = self.client.post(f"/api/venues/{self.v101.id}/unavailable", json={})
        self.assertEqual(response.status_code, 401)


# ---------- AC2: overlapping confirmed bookings are flagged ----------


class FlaggingTests(UnavailableTestCase):
    def test_tc9_a_confirmed_booking_that_overlaps_is_flagged_and_listed(self):  # AC2
        body = self.recorded()
        self.assertEqual([b["id"] for b in body["flagged"]], [self.b801.id])
        entries = self.replacement_list().get_json()["bookings"]
        [entry] = entries
        self.assertEqual(entry["id"], self.b801.id)
        self.assertEqual(entry["flag"], FLAG)
        self.assertEqual(entry["status"], "confirmed")
        self.assertEqual(entry["event"], {"id": self.events["E1"].id,
                                          "title": "Harbour Lights Festival"})
        self.assertEqual(entry["venue"]["id"], self.v101.id)
        self.assertEqual((entry["start_time"], entry["end_time"]),
                         ("2027-11-20T10:00:00", "2027-11-20T12:00:00"))
        self.assertEqual((entry["period"]["reason"], entry["period"]["start_time"],
                          entry["period"]["end_time"]),
                         (REASON, "2027-11-20T09:00:00", "2027-11-20T18:00:00"))

    def test_tc10_the_flagged_booking_is_not_cancelled_and_the_event_is_unchanged(self):  # AC2
        before_event = self.event_row()
        self.recorded()
        self.db.session.expire_all()
        booking = self.db.session.get(VenueBooking, self.b801.id)
        self.assertEqual((booking.status, booking.start_time, booking.end_time, booking.venue_id),
                         ("confirmed", at(10), at(12), self.v101.id))
        self.assertEqual(self.event_row(), before_event)

    def test_tc11_a_booking_that_starts_before_the_period_and_ends_inside_it_is_flagged(self):  # AC2
        b802 = self.book("E2", self.v101, at(8), at(10))
        self.recorded()
        self.assertEqual(self.flagged_ids(), sorted([self.b801.id, b802.id]))

    def test_tc12_a_booking_that_ends_exactly_when_the_period_starts_is_not_flagged(self):  # AC2
        self.book("E2", self.v101, at(7), at(9))
        self.recorded()
        self.assertEqual(self.flagged_ids(), [self.b801.id])

    def test_tc13_a_booking_that_ends_one_minute_after_the_period_starts_is_flagged(self):  # AC2
        b804 = self.book("E2", self.v101, at(7), at(9, 1))
        self.recorded()
        self.assertIn(b804.id, self.flagged_ids())

    def test_tc14_a_booking_at_another_venue_at_the_same_time_is_not_flagged(self):  # AC2
        self.book("E2", self.v102, at(10), at(12))
        self.recorded()
        self.assertEqual(self.flagged_ids(), [self.b801.id])

    def test_tc15_a_booking_on_a_different_day_is_not_flagged(self):  # AC2
        self.book("E2", self.v101, at(10, day=21), at(12, day=21))
        self.recorded()
        self.assertEqual(self.flagged_ids(), [self.b801.id])

    def test_tc16_a_booking_that_is_not_confirmed_is_not_flagged(self):  # AC2
        for status in ("pending", "tentative", "rejected", "cancelled"):
            self.book("E2", self.v101, at(10), at(12), status=status)
        self.recorded()
        self.assertEqual(self.flagged_ids(), [self.b801.id])

    def test_a_booking_that_ended_in_the_past_is_not_flagged(self):  # AC2
        past = self.book("E2", self.v101, datetime(2020, 1, 1, 10), datetime(2020, 1, 1, 12))
        self.recorded(start="2020-01-01T09:00", end="2020-01-01T18:00")
        self.assertNotIn(past.id, self.flagged_ids())

    def test_a_booking_overlapped_by_two_periods_is_listed_once(self):  # AC2
        self.recorded()
        self.recorded(start="2027-11-20T11:00", end="2027-11-20T12:00", reason="Second")
        self.assertEqual(self.flagged_ids(), [self.b801.id])

    def test_a_later_cancelled_booking_leaves_the_list(self):  # AC2
        self.recorded()
        self.db.session.get(VenueBooking, self.b801.id).status = "cancelled"
        self.db.session.commit()
        self.assertEqual(self.flagged_ids(), [])

    def test_nothing_flagged_says_so(self):  # AC2
        response = self.replacement_list()
        self.assertEqual(response.get_json()["bookings"], [])
        self.assertTrue(response.get_json()["message"])

    def test_only_venue_staff_can_list_bookings_needing_a_replacement(self):  # AC6
        self.assertEqual(self.client.get("/api/venues/replacement-needed").status_code, 401)
        self.assertEqual(self.replacement_list("alice").status_code, 403)

    def test_the_list_reports_a_503_when_it_cannot_be_read(self):  # AC2
        self.recorded()
        headers = self.auth_headers(self.users["gus"])
        self.db.session.expire_all()
        with self.queries_fail_on("venue_replacement_flags"):
            response = self.client.get("/api/venues/replacement-needed", headers=headers)
        self.assertEqual(response.status_code, 503)
        self.assertIs(response.get_json().get("retryable"), True)


# ---------- AC3: the coordinators are notified ----------


class NotificationTests(UnavailableTestCase):
    def test_tc17_the_coordinator_is_notified_with_the_event_venue_and_period(self):  # AC3
        self.recorded()
        [note] = self.notifications("alice")
        self.assertEqual(note.event_id, self.events["E1"].id)
        for text in ("Harbour Lights Festival", self.v101.name, "2027-11-20 09:00 to 2027-11-20 18:00",
                     REASON):
            self.assertIn(text, note.message)

    def test_tc18_each_coordinator_is_notified_about_their_own_event_only(self):  # AC3
        self.events["E2"].status = "confirmed"
        self.db.session.commit()
        self.book("E2", self.v101, at(14), at(16))
        self.recorded()
        [alice_note] = self.notifications("alice")
        [ben_note] = self.notifications("ben")
        self.assertIn("Harbour Lights Festival", alice_note.message)
        self.assertNotIn("Winter Networking Night", alice_note.message)
        self.assertIn("Winter Networking Night", ben_note.message)
        self.assertNotIn("Harbour Lights Festival", ben_note.message)

    def test_tc19_the_coordinator_of_an_unaffected_event_is_not_notified(self):  # AC3
        self.book("E2", self.v102, at(10), at(12))
        self.recorded()
        self.assertEqual(self.notifications("ben"), [])

    def test_a_coordinator_with_two_affected_events_is_told_about_each(self):  # AC3
        self.book("E3", self.v101, at(14), at(16))
        body = self.recorded()
        self.assertEqual(len(self.notifications("alice")), 2)
        self.assertEqual(body["notified"], [self.users["alice"].id])

    def test_nothing_is_notified_when_the_period_affects_no_booking(self):  # AC3
        self.recorded(venue=self.v102)
        self.assertEqual(self.notifications("alice"), [])

    def test_the_period_is_still_recorded_when_the_email_cannot_be_queued(self):  # AC3
        from unittest import mock
        with mock.patch("app.venues.routes.tasks.send_notification_email.delay",
                        side_effect=ConnectionError("broker down")):
            self.recorded()
        self.assertEqual(self.stored_blocks(), 1)
        self.assertEqual(len(self.notifications("alice")), 1)


# ---------- AC4: a confirmed event returns to planning ----------


class EventStatusTests(UnavailableTestCase):
    def test_tc20_a_confirmed_event_returns_to_planning_and_is_not_cancelled(self):  # AC4
        before = self.event_row()
        self.assertEqual(self.status_of("E1"), "confirmed")
        self.recorded()
        self.assertEqual(self.status_of("E1"), "approved")  # Planning (SCRUM-92 A2)
        self.assertEqual(self.event_row(), before)

    def test_tc20_the_planning_view_shows_it_needs_a_change_review(self):  # AC4
        self.recorded()
        response = self.client.get(f"/api/events/{self.events['E1'].id}/planning",
                                   headers=self.auth_headers(self.users["alice"]))
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["change_review"]["needed"], True)
        self.assertIn(FLAG, body["change_review"]["reason"])
        [booking] = body["venue_bookings"]
        self.assertEqual(booking["flag"], FLAG)

    def test_the_planning_view_of_an_unaffected_event_has_no_flag(self):  # AC4
        response = self.client.get(f"/api/events/{self.events['E1'].id}/planning",
                                   headers=self.auth_headers(self.users["alice"]))
        body = response.get_json()
        self.assertEqual(body["change_review"], {"needed": False, "reason": None})
        self.assertIsNone(body["venue_bookings"][0]["flag"])

    def test_tc21_an_affected_event_that_was_not_confirmed_keeps_its_status(self):  # AC4
        self.events["E2"].status = "approved"
        self.db.session.commit()
        e810 = self.book("E2", self.v101, at(15), at(17))
        self.recorded()
        self.assertEqual(self.status_of("E2"), "approved")
        self.assertIn(e810.id, self.flagged_ids())

    def test_other_event_states_are_left_alone(self):  # AC4
        for key, status in (("E3", "submitted"), ("E4", "draft")):
            self.events[key].status = status
        self.db.session.commit()
        self.book("E3", self.v101, at(14), at(16))
        self.recorded()
        self.assertEqual(self.status_of("E3"), "submitted")


# ---------- AC5: the calendar and new bookings ----------


class CalendarAndRequestTests(UnavailableTestCase):
    def calendar(self, venue=None, day="2027-11-20"):
        response = self.client.get(
            f"/api/venues/{(venue or self.v101).id}/availability", query_string={"from": day},
            headers=self.auth_headers(self.users["alice"]))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def slot_status(self, calendar, text):
        for slot in calendar["days"][0]["slots"]:
            if slot["start"] <= text < slot["end"]:
                return slot
        self.fail(f"no slot at {text}")

    def ask(self, start, end, venue="fully_recorded", event="E3"):
        return self.submit(self.valid(event=event, venue=venue, start_time=start, end_time=end))

    def test_tc22_the_calendar_shows_the_period_as_unavailable(self):  # AC5
        self.recorded()
        calendar = self.calendar()
        for text, status in (("2027-11-20T08:59:00", "available"),
                             ("2027-11-20T09:00:00", "unavailable"),
                             ("2027-11-20T17:59:00", "unavailable"),
                             ("2027-11-20T18:00:00", "available")):
            with self.subTest(at=text):
                self.assertEqual(self.slot_status(calendar, text)["status"], status)
        self.assertIn("block", self.slot_status(calendar, "2027-11-20T13:00:00")["causes"])

    def test_tc23_a_new_request_inside_the_period_is_blocked(self):  # AC5
        self.recorded()
        before = VenueBooking.query.count()
        response = self.ask("2027-11-20T14:00", "2027-11-20T16:00")
        body = self.assert_error(response, 409)
        self.assertEqual(body["reason"], "conflict")
        self.assertIn("unavailable", body["error"].lower())
        self.assertEqual([c["type"] for c in body["conflicts"]], ["block"])
        self.assertEqual(body["conflicts"][0]["reason"], REASON)
        self.assertEqual(VenueBooking.query.count(), before)

    def test_tc24_a_request_that_starts_one_minute_before_the_period_ends_is_blocked(self):  # AC5
        self.recorded()
        response = self.ask("2027-11-20T17:59", "2027-11-20T19:00", event="E3")
        self.assertEqual(self.assert_error(response, 409)["reason"], "conflict")

    def test_tc25_a_request_that_starts_exactly_when_the_period_ends_is_allowed(self):  # AC5
        self.recorded()
        response = self.ask("2027-11-20T18:00", "2027-11-20T20:00")
        self.assertEqual(response.status_code, 201, response.get_json())

    def test_tc26_the_same_time_at_another_venue_is_not_blocked(self):  # AC5
        self.recorded()
        response = self.ask("2027-11-20T14:00", "2027-11-20T16:00", venue="harbour_room")
        self.assertEqual(response.status_code, 201, response.get_json())

    def test_a_pending_request_cannot_be_approved_inside_a_new_period(self):  # AC5
        pending = self.book("E3", self.v101, at(14), at(16), status="pending")
        self.recorded()
        response = self.client.post(f"/api/venues/bookings/{pending.id}/approve",
                                    headers=self.auth_headers(self.users["gus"]))
        self.assertEqual(self.assert_error(response, 409)["reason"], "conflict")

    def test_venue_search_does_not_offer_the_venue_inside_the_period(self):  # AC5
        self.recorded()
        response = self.client.get(
            "/api/venues/search", headers=self.auth_headers(self.users["alice"]),
            query_string={"date": "2027-11-20", "start": "14:00", "end": "16:00"})
        ids = [v["id"] for v in response.get_json()["venues"]]
        self.assertNotIn(self.v101.id, ids)
        self.assertIn(self.v102.id, ids)


# ---------- AC6: only Venue Staff ----------


class PermissionTests(UnavailableTestCase):
    def assert_denied(self, response):
        self.assertEqual(response.status_code, 403, response.get_json())
        self.assertEqual(self.stored_blocks(), 0)
        self.assertEqual(self.flagged_ids(), [])
        self.assertEqual(self.status_of("E1"), "confirmed")
        self.assertEqual(self.notifications("alice"), [])

    def test_tc27_an_event_coordinator_cannot_record_a_period(self):  # AC6
        self.assert_denied(self.record(as_user="alice"))

    def test_tc28_an_attendee_cannot_record_a_period(self):  # AC6
        self.assert_denied(self.record(as_user="farah"))

    def test_other_roles_cannot_record_a_period(self):  # AC6
        for user in ("dana", "hana", "admin", "ben"):
            with self.subTest(user=user):
                self.assert_denied(self.record(as_user=user))

    def test_tc29_a_second_venue_staff_user_can_record_a_period(self):  # AC6
        second = self.make_user(email="venue.two@connectsphere.test", role="venue_staff")
        body = self.recorded(venue=self.v102, headers=self.auth_headers(second),
                             reason="Fire safety inspection")
        self.assertEqual(body["period"]["reason"], "Fire safety inspection")

    def test_a_coordinator_cannot_list_a_venues_unavailable_periods(self):  # AC6
        response = self.client.get(f"/api/venues/{self.v101.id}/unavailable",
                                   headers=self.auth_headers(self.users["alice"]))
        self.assertEqual(response.status_code, 403)

    def test_a_deleted_user_is_a_401(self):  # AC6
        ghost = self.make_user(email="gone@connectsphere.test", role="venue_staff")
        headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        self.assertEqual(self.record(headers=headers).status_code, 401)


# ---------- Failure: nothing half-saved ----------


class FailureTests(UnavailableTestCase):
    def test_a_failed_save_records_nothing_flags_nothing_and_notifies_no_one(self):  # AC2, AC3, AC4
        for table in ("venue_replacement_flags", "notifications"):
            with self.subTest(table=table):
                with self.queries_fail_on(table):
                    response = self.record()
                self.assertEqual(response.status_code, 503, response.get_json())
                self.assertIs(response.get_json().get("retryable"), True)
                self.assertEqual(self.stored_blocks(), 0)
                self.assertEqual(self.flagged_ids(), [])
                self.assertEqual(self.status_of("E1"), "confirmed")
                self.assertEqual(self.notifications("alice"), [])

    def test_a_retry_after_a_failure_succeeds(self):  # AC1
        with self.queries_fail_on("venue_replacement_flags"):
            self.record()
        self.assertEqual(self.stored_blocks(), 0)
        self.recorded()
        self.assertEqual(self.stored_blocks(), 1)


if __name__ == "__main__":
    unittest.main()
