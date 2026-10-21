"""Tests for SCRUM-84 "Setup and turnaround time in availability and conflict checks".

Each test names the case it automates from the "Sprint 3 test cases" sheet
(IS212-US84-TCnn) and docs/test-cases/SCRUM-84-setup-and-turnaround-time.md.

Model (db/venue_setup_turnaround.sql), new VenueBooking columns
    setup_minutes, turnaround_minutes   whole minutes 0-1440, default 0 (A1, A2)
    occupied_start = start_time - setup_minutes       (generated, stored)
    occupied_end   = end_time + turnaround_minutes    (generated, stored)
and the "no overlapping confirmed bookings" constraint compares occupied periods.

API
    POST /api/venues/bookings   optional "setup_minutes", "turnaround_minutes"
        201 booking now has setup_minutes, turnaround_minutes, occupied_start, occupied_end
        409 {"error", "reason": "conflict", "conflicts": [...], "occupied": {"start", "end"}}
            when the request's occupied period clashes with a booking, block or hold (A5)
    GET /api/venues/<id>/availability   periods/days use the occupied period; a booking or
        hold period also has event_start, event_end, setup, turnaround
    GET /api/venues/search              a venue is taken for any time inside an occupied period
    GET /api/venues/bookings            pending requests carry the same occupied-period fields
    A conflict entry for a booking or hold: start/end = its occupied period, plus
        event_start, event_end, setup {"start","end","minutes"} | null, turnaround (same)
"""

import unittest
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.models import VenueBooking
from tests import seed_data
from tests.test_venue_booking_request import BOOKINGS_URL, BookingRequestTestCase

DAY = "2027-03-12"
B201 = (datetime(2027, 3, 12, 10, 0), datetime(2027, 3, 12, 12, 0))


class SetupTurnaroundTestCase(BookingRequestTestCase):
    def setUp(self):
        super().setUp()
        self.venues.update(self.seed_venues(seed_data.SEARCH_VENUES))
        self.v101 = self.venues["fully_recorded"]
        self.v102 = self.venues["harbour_room"]

    def confirmed(self, venue=None, window=B201, setup=30, turnaround=45, status="confirmed"):
        """B-201: a confirmed booking with setup and turnaround."""
        booking = VenueBooking(
            venue_id=(venue or self.v101).id, status=status, start_time=window[0],
            end_time=window[1], setup_minutes=setup, turnaround_minutes=turnaround)
        self.db.session.add(booking)
        self.db.session.commit()
        return booking

    def calendar(self, venue=None, day=DAY, user="alice"):
        response = self.client.get(
            f"/api/venues/{(venue or self.v101).id}/availability",
            query_string={"from": day}, headers=self.auth_headers(self.users[user]))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def slot_at(self, calendar, text, day=0):
        for slot in calendar["days"][day]["slots"]:
            if slot["start"] <= text < slot["end"]:
                return slot
        self.fail(f"no slot at {text}")

    def request(self, start, end, setup=30, turnaround=45, venue="fully_recorded", **extra):
        body = self.valid(venue=venue, start_time=f"{DAY}T{start}", end_time=f"{DAY}T{end}",
                          setup_minutes=setup, turnaround_minutes=turnaround, **extra)
        return self.submit(body)


class OccupiedPeriodTests(SetupTurnaroundTestCase):
    def test_tc1_occupied_period_includes_setup_and_turnaround(self):  # AC1
        self.confirmed()
        periods = self.calendar()["periods"]
        self.assertEqual(len(periods), 1)
        period = periods[0]
        self.assertEqual((period["start"], period["end"]),
                         (f"{DAY}T09:30:00", f"{DAY}T12:45:00"))
        self.assertEqual((period["event_start"], period["event_end"]),
                         (f"{DAY}T10:00:00", f"{DAY}T12:00:00"))
        self.assertEqual(period["setup"], {"start": f"{DAY}T09:30:00", "end": f"{DAY}T10:00:00",
                                           "minutes": 30})
        self.assertEqual(period["turnaround"], {"start": f"{DAY}T12:00:00",
                                                "end": f"{DAY}T12:45:00", "minutes": 45})

    def test_tc2_without_setup_or_turnaround_it_equals_the_event_time(self):  # AC1
        self.confirmed(self.v102, setup=0, turnaround=0)
        period = self.calendar(self.v102)["periods"][0]
        self.assertEqual((period["start"], period["end"]), (f"{DAY}T10:00:00", f"{DAY}T12:00:00"))
        self.assertNotIn("setup", period)  # nothing to label
        self.assertNotIn("turnaround", period)

    def test_tc2_minutes_default_to_zero_when_not_sent(self):  # AC1
        response = self.submit(self.valid())
        self.assertEqual(response.status_code, 201, response.get_json())
        booking = response.get_json()["booking"]
        self.assertEqual((booking["setup_minutes"], booking["turnaround_minutes"]), (0, 0))
        self.assertEqual(booking["occupied_start"], booking["start_time"])
        self.assertEqual(booking["occupied_end"], booking["end_time"])

    def test_tc3_turnaround_past_midnight_runs_into_the_next_day(self):  # AC1
        window = (datetime(2027, 3, 21, 22, 30), datetime(2027, 3, 21, 23, 30))
        self.confirmed(self.v102, window)
        calendar = self.calendar(self.v102, "2027-03-21")
        period = calendar["periods"][0]
        self.assertEqual((period["start"], period["end"]),
                         ("2027-03-21T22:00:00", "2027-03-22T00:15:00"))

        next_day = self.calendar(self.v102, "2027-03-22")
        early = next_day["days"][0]["slots"][0]
        self.assertEqual((early["start"], early["end"], early["status"]),
                         ("2027-03-22T00:00:00", "2027-03-22T00:15:00", "unavailable"))
        self.assertIn("booking", early["causes"])
        self.assertNotEqual(self.slot_at(next_day, "2027-03-22T00:15:00")["causes"], ["booking"])

    def test_created_request_reports_its_occupied_period(self):  # AC1, AC4
        response = self.request("10:00", "12:00")
        self.assertEqual(response.status_code, 201, response.get_json())
        booking = response.get_json()["booking"]
        self.assertEqual((booking["setup_minutes"], booking["turnaround_minutes"]), (30, 45))
        self.assertEqual((booking["occupied_start"], booking["occupied_end"]),
                         (f"{DAY}T09:30:00", f"{DAY}T12:45:00"))


class MinutesValidationTests(SetupTurnaroundTestCase):
    def test_setup_and_turnaround_must_be_whole_minutes_from_0_to_1440(self):  # AC1
        for field in ("setup_minutes", "turnaround_minutes"):
            for bad in (-1, 1441, 2.5, "ten", True, [5]):
                with self.subTest(field=field, value=bad):
                    body = self.valid(**{field: bad})
                    response = self.submit(body)
                    self.assert_fields(response, field)
        self.assert_nothing_saved()

    def test_edge_values_and_text_numbers_are_accepted(self):  # AC1
        self.assertEqual(self.submit(self.valid(setup_minutes=0, turnaround_minutes=1440)
                                     ).status_code, 201)

    def test_blank_means_zero(self):  # AC1
        response = self.submit(self.valid(setup_minutes="", turnaround_minutes=None))
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["booking"]["setup_minutes"], 0)


class CalendarAndSearchTests(SetupTurnaroundTestCase):
    def test_tc4_calendar_shows_the_venue_occupied_for_the_whole_period(self):  # AC2
        self.confirmed()
        calendar = self.calendar()
        for text, status in (("09:29", "available"), ("09:30", "unavailable"),
                             ("10:30", "unavailable"), ("12:44", "unavailable"),
                             ("12:45", "available")):
            with self.subTest(at=text):
                self.assertEqual(self.slot_at(calendar, f"{DAY}T{text}:00")["status"], status)

    def test_tc5_search_treats_the_turnaround_as_unavailable(self):  # AC2
        self.confirmed()
        response = self.client.get(
            "/api/venues/search", headers=self.auth_headers(self.users["alice"]),
            query_string={"date": DAY, "start": "12:15", "end": "14:00"})
        self.assertEqual(response.status_code, 200)
        ids = [v["id"] for v in response.get_json()["venues"]]
        self.assertNotIn(self.v101.id, ids)
        self.assertIn(self.v102.id, ids)

    def test_search_after_the_occupied_period_offers_the_venue(self):  # AC2
        self.confirmed()
        response = self.client.get(
            "/api/venues/search", headers=self.auth_headers(self.users["alice"]),
            query_string={"date": DAY, "start": "12:45", "end": "14:00"})
        self.assertIn(self.v101.id, [v["id"] for v in response.get_json()["venues"]])

    def test_a_tentative_hold_occupies_its_setup_and_turnaround_too(self):  # AC2
        from tests.test_venue_holds import EXPIRY_AT, HELD_AT
        hold = self.confirmed(status="tentative")
        hold.held_at, hold.hold_expires_at = HELD_AT, EXPIRY_AT.replace(year=2099)
        hold.held_by_id = self.users["gus"].id
        self.db.session.commit()
        calendar = self.calendar()
        period = [p for p in calendar["periods"] if p["type"] == "hold"][0]
        self.assertEqual((period["start"], period["end"]), (f"{DAY}T09:30:00", f"{DAY}T12:45:00"))
        self.assertEqual(self.slot_at(calendar, f"{DAY}T12:30:00")["status"], "tentative")


class RequestConflictTests(SetupTurnaroundTestCase):
    def test_tc6_conflict_when_only_setup_and_turnaround_overlap(self):  # AC2
        self.confirmed()
        response = self.request("13:00", "15:00")
        body = self.assert_error(response, 409)
        self.assertEqual(body["reason"], "conflict")
        self.assertEqual(body["occupied"], {"start": f"{DAY}T12:30:00", "end": f"{DAY}T15:45:00"})
        self.assertEqual([c["type"] for c in body["conflicts"]], ["booking"])
        self.assert_nothing_saved()

    def test_tc7_starting_exactly_when_another_ends_is_allowed(self):  # AC2
        self.confirmed()
        response = self.request("13:15", "15:00")
        self.assertEqual(response.status_code, 201, response.get_json())
        booking = response.get_json()["booking"]
        self.assertEqual((booking["occupied_start"], booking["occupied_end"]),
                         (f"{DAY}T12:45:00", f"{DAY}T15:45:00"))

    def test_tc8_one_minute_earlier_is_a_conflict(self):  # AC2
        self.confirmed()
        response = self.request("13:14", "15:00")
        body = self.assert_error(response, 409)
        self.assertEqual(body["conflicts"][0]["end"], f"{DAY}T12:45:00")
        self.assertEqual(body["occupied"]["start"], f"{DAY}T12:44:00")
        self.assert_nothing_saved()

    def test_tc9_same_time_at_another_venue_is_not_a_conflict(self):  # AC2
        self.confirmed()
        response = self.request("13:00", "15:00", venue="harbour_room")
        self.assertEqual(response.status_code, 201, response.get_json())

    def test_tc10_message_gives_the_occupied_period_and_labels_the_parts(self):  # AC3
        self.confirmed()
        body = self.assert_error(self.request("13:00", "15:00"), 409)
        conflict = body["conflicts"][0]
        self.assertEqual((conflict["start"], conflict["end"]),
                         (f"{DAY}T09:30:00", f"{DAY}T12:45:00"))
        self.assertEqual(conflict["setup"], {"start": f"{DAY}T09:30:00", "end": f"{DAY}T10:00:00",
                                             "minutes": 30})
        self.assertEqual(conflict["turnaround"], {"start": f"{DAY}T12:00:00",
                                                  "end": f"{DAY}T12:45:00", "minutes": 45})
        self.assertEqual((conflict["event_start"], conflict["event_end"]),
                         (f"{DAY}T10:00:00", f"{DAY}T12:00:00"))
        # The new request's own occupied period is given too (open question in the sheet).
        self.assertEqual(body["occupied"], {"start": f"{DAY}T12:30:00", "end": f"{DAY}T15:45:00"})

    def test_pending_unconfirmed_bookings_do_not_block_a_request(self):  # AC2
        self.confirmed(status="pending")
        self.assertEqual(self.request("10:00", "12:00").status_code, 201)


class ReviewTests(SetupTurnaroundTestCase):
    def test_tc11_venue_staff_see_the_occupied_period_when_reviewing(self):  # AC4
        created = self.request("10:00", "12:00").get_json()["booking"]
        response = self.listed()
        self.assertEqual(response.status_code, 200)
        entry = [b for b in response.get_json()["bookings"] if b["id"] == created["id"]][0]
        self.assertEqual((entry["start_time"], entry["end_time"]),
                         (f"{DAY}T10:00:00", f"{DAY}T12:00:00"))
        self.assertEqual((entry["setup_minutes"], entry["turnaround_minutes"]), (30, 45))
        self.assertEqual((entry["occupied_start"], entry["occupied_end"]),
                         (f"{DAY}T09:30:00", f"{DAY}T12:45:00"))

    def test_review_list_has_no_conflict_when_occupied_periods_only_touch(self):  # AC2, AC4
        created = self.request("13:15", "15:00").get_json()["booking"]
        self.confirmed()  # occupies 09:30-12:45; the request occupies 12:45-15:45
        entry = [b for b in self.listed().get_json()["bookings"] if b["id"] == created["id"]][0]
        self.assertEqual(entry["conflicts"], [])

    def test_review_list_flags_a_conflict_that_exists_only_in_the_occupied_periods(self):  # AC4
        # A pending request made before the other booking was confirmed.
        created = VenueBooking(
            event_id=self.events["E1"].id, venue_id=self.v101.id, status="pending",
            start_time=datetime(2027, 3, 12, 13, 0), end_time=datetime(2027, 3, 12, 15, 0),
            setup_minutes=30, turnaround_minutes=45, venue_requirements="x",
            requested_by_id=self.users["alice"].id)
        self.db.session.add(created)
        other = self.confirmed()
        entry = [b for b in self.listed().get_json()["bookings"] if b["id"] == created.id][0]
        # Events are 10:00-12:00 and 13:00-15:00; only 12:30-12:45 (setup/turnaround) overlaps.
        self.assertEqual([c["id"] for c in entry["conflicts"]], [other.id])

    def test_tc12_approving_confirms_the_booking_and_the_calendar_shows_it(self):  # AC4
        created = self.request("10:00", "12:00").get_json()["booking"]
        response = self.client.post(
            f"{BOOKINGS_URL}/{created['id']}/approve", headers=self.auth_headers(self.users["gus"]))
        self.assertEqual(response.status_code, 200, response.get_json())
        period = self.calendar()["periods"][0]
        self.assertEqual((period["start"], period["end"]), (f"{DAY}T09:30:00", f"{DAY}T12:45:00"))
        self.assertEqual(self.slot_at(self.calendar(), f"{DAY}T12:30:00")["status"], "unavailable")

    def test_approval_is_refused_when_occupied_periods_overlap(self):  # AC2
        created = self.request("10:00", "12:00").get_json()["booking"]
        other = self.confirmed(window=(datetime(2027, 3, 12, 12, 30), datetime(2027, 3, 12, 14, 0)),
                               setup=0, turnaround=0)
        # 12:30 is inside the request's turnaround (12:00-12:45) though the events do not overlap.
        response = self.client.post(
            f"{BOOKINGS_URL}/{created['id']}/approve", headers=self.auth_headers(self.users["gus"]))
        body = self.assert_error(response, 409)
        self.assertEqual(body["reason"], "conflict")
        self.assertEqual(body["conflicts"][0]["id"], other.id)

    def test_database_refuses_two_confirmed_bookings_with_overlapping_occupied_periods(self):  # AC2
        self.confirmed()
        with self.assertRaises(IntegrityError):
            self.confirmed(window=(datetime(2027, 3, 12, 13, 0), datetime(2027, 3, 12, 14, 0)))
        self.db.session.rollback()


if __name__ == "__main__":
    unittest.main()
