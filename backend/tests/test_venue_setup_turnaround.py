"""Tests for SCRUM-84 "Setup and turnaround time in availability and conflict checks".

Each test names the case it automates from the "Sprint 4 test cases" sheet
(IS212-US84-TCnn) and docs/test-cases/SCRUM-84-setup-and-turnaround-time.md.

SCRUM-84 was reopened: setup and turnaround time belong to the venue (SCRUM-63 AC9,
`Venue.setup_minutes`, `turnaround_minutes`, NULL = none set = 0), not to the booking.
    AC1  a booking occupies start - venue setup to end + venue turnaround, worked out when
         it is read, so changing the venue changes its existing bookings
    AC5  changing a venue's setup or turnaround flags the pending, tentative and confirmed
         bookings whose occupied periods now overlap, without changing any booking

API
    POST /api/venues/bookings    no "setup_minutes"/"turnaround_minutes" in the body (400
        "not part of a venue request"); the booking reports the venue's values and its
        occupied_start / occupied_end
        409 {"reason": "conflict", "conflicts": [...], "occupied": {"start", "end"}}
    GET /api/venues/<id>/availability, GET /api/venues/search, GET /api/venues/bookings
        use the venue's values
    PUT /api/venues/<id>         changing setup_minutes or turnaround_minutes refreshes the
        flags of that venue's bookings in the same save (503 and nothing saved if it fails)
    GET /api/venues/flagged-bookings   Venue Staff only (401, 403)
        200 {"bookings": [{"id", "status", "event", "venue", "start_time", "end_time",
             "occupied_start", "occupied_end", "setup", "turnaround",
             "flag": "Setup or turnaround conflict", "overlaps": [booking ids],
             "flagged_at"}], "message"}; optional ?venue_id=
"""

import unittest
from datetime import datetime

from app.models import VenueBooking
from tests import seed_data
from tests.test_venue_booking_request import BOOKINGS_URL, BookingRequestTestCase

DAY = "2027-03-12"
B201 = (datetime(2027, 3, 12, 10, 0), datetime(2027, 3, 12, 12, 0))
FLAGGED_URL = "/api/venues/flagged-bookings"
FLAG = "Setup or turnaround conflict"


class SetupTurnaroundTestCase(BookingRequestTestCase):
    def setUp(self):
        super().setUp()
        self.venues.update(self.seed_venues(seed_data.SEARCH_VENUES))
        self.v101 = self.venues["fully_recorded"]
        self.v102 = self.venues["harbour_room"]
        self.set_buffers(self.v101, 30, 45)  # V-101: setup 30, turnaround 45
        self.set_buffers(self.v102, None, None)  # V-102: none set

    def set_buffers(self, venue, setup, turnaround):
        venue.setup_minutes, venue.turnaround_minutes = setup, turnaround
        self.db.session.commit()

    def confirmed(self, venue=None, window=B201, status="confirmed", event=None):
        """B-201: a confirmed booking; it stores no setup or turnaround of its own."""
        booking = VenueBooking(
            event_id=self.events[event].id if event else None, venue_id=(venue or self.v101).id,
            status=status,
            start_time=window[0], end_time=window[1])
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

    def request(self, start, end, venue="fully_recorded", **extra):
        body = self.valid(venue=venue, start_time=f"{DAY}T{start}", end_time=f"{DAY}T{end}",
                          **extra)
        return self.submit(body)

    def edit_venue(self, venue=None, as_user="gus", **fields):
        response = self.client.put(
            f"/api/venues/{(venue or self.v101).id}", json=fields,
            headers=self.auth_headers(self.users[as_user]))
        return response


class OccupiedPeriodTests(SetupTurnaroundTestCase):
    def test_tc13_occupied_period_uses_the_setup_and_turnaround_set_on_the_venue(self):  # AC1
        booking = self.confirmed()
        self.assertFalse(hasattr(booking, "setup_minutes"))  # the booking stores none
        period = self.calendar()["periods"][0]
        self.assertEqual((period["start"], period["end"]),
                         (f"{DAY}T09:30:00", f"{DAY}T12:45:00"))
        self.assertEqual((period["event_start"], period["event_end"]),
                         (f"{DAY}T10:00:00", f"{DAY}T12:00:00"))
        self.assertEqual(period["setup"], {"start": f"{DAY}T09:30:00", "end": f"{DAY}T10:00:00",
                                           "minutes": 30})
        self.assertEqual(period["turnaround"], {"start": f"{DAY}T12:00:00",
                                                "end": f"{DAY}T12:45:00", "minutes": 45})

    def test_tc13_the_booking_itself_reports_the_venues_occupied_period(self):  # AC1
        booking = self.confirmed(status="pending")
        entry = [b for b in self.listed().get_json()["bookings"] if b["id"] == booking.id][0]
        self.assertEqual((entry["setup_minutes"], entry["turnaround_minutes"]), (30, 45))
        self.assertEqual((entry["occupied_start"], entry["occupied_end"]),
                         (f"{DAY}T09:30:00", f"{DAY}T12:45:00"))

    def test_tc14_a_venue_with_none_set_occupies_only_the_event_time(self):  # AC1
        self.confirmed(self.v102)
        period = self.calendar(self.v102)["periods"][0]
        self.assertEqual((period["start"], period["end"]), (f"{DAY}T10:00:00", f"{DAY}T12:00:00"))
        self.assertNotIn("setup", period)  # nothing to label
        self.assertNotIn("turnaround", period)

    def test_tc14_zero_values_behave_like_none_set(self):  # AC1
        self.set_buffers(self.v102, 0, 0)
        self.confirmed(self.v102)
        period = self.calendar(self.v102)["periods"][0]
        self.assertEqual((period["start"], period["end"]), (f"{DAY}T10:00:00", f"{DAY}T12:00:00"))

    def test_tc15_two_venues_give_different_occupied_periods_for_the_same_event_time(self):  # AC1
        self.set_buffers(self.v102, 10, 15)
        self.confirmed()
        self.confirmed(self.v102, event="E2")
        first = self.calendar()["periods"][0]
        second = self.calendar(self.v102)["periods"][0]
        self.assertEqual((first["start"], first["end"]), (f"{DAY}T09:30:00", f"{DAY}T12:45:00"))
        self.assertEqual((second["start"], second["end"]), (f"{DAY}T09:50:00", f"{DAY}T12:15:00"))

    def test_tc16_changing_the_venues_turnaround_changes_an_existing_bookings_period(self):  # AC1
        self.confirmed()
        response = self.edit_venue(turnaround_minutes=60)
        self.assertEqual(response.status_code, 200, response.get_json())
        period = self.calendar()["periods"][0]
        self.assertEqual((period["start"], period["end"]), (f"{DAY}T09:30:00", f"{DAY}T13:00:00"))
        self.assertEqual(self.slot_at(self.calendar(), f"{DAY}T12:50:00")["status"], "unavailable")
        self.assertEqual(self.slot_at(self.calendar(), f"{DAY}T13:00:00")["status"], "available")

    def test_tc3_turnaround_past_midnight_runs_into_the_next_day(self):  # AC1
        self.set_buffers(self.v102, 30, 45)
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

    def test_a_request_reports_the_venues_occupied_period(self):  # AC1, AC4
        response = self.request("10:00", "12:00")
        self.assertEqual(response.status_code, 201, response.get_json())
        booking = response.get_json()["booking"]
        self.assertEqual((booking["setup_minutes"], booking["turnaround_minutes"]), (30, 45))
        self.assertEqual((booking["occupied_start"], booking["occupied_end"]),
                         (f"{DAY}T09:30:00", f"{DAY}T12:45:00"))

    def test_a_request_for_a_venue_with_none_set_has_zero_minutes(self):  # AC1
        response = self.request("10:00", "12:00", venue="harbour_room")
        booking = response.get_json()["booking"]
        self.assertEqual((booking["setup_minutes"], booking["turnaround_minutes"]), (0, 0))
        self.assertEqual(booking["occupied_start"], booking["start_time"])
        self.assertEqual(booking["occupied_end"], booking["end_time"])

    def test_the_coordinator_can_no_longer_send_setup_or_turnaround(self):  # AC1
        for field in ("setup_minutes", "turnaround_minutes"):
            with self.subTest(field=field):
                self.assert_fields(self.submit(self.valid(**{field: 30})), field)
        self.assert_nothing_saved()


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

    def test_a_tentative_hold_occupies_the_venues_setup_and_turnaround_too(self):  # AC2
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
        created = VenueBooking(
            event_id=self.events["E1"].id, venue_id=self.v101.id, status="pending",
            start_time=datetime(2027, 3, 12, 13, 0), end_time=datetime(2027, 3, 12, 15, 0),
            venue_requirements="x", requested_by_id=self.users["alice"].id)
        self.db.session.add(created)
        other = self.confirmed()
        entry = [b for b in self.listed().get_json()["bookings"] if b["id"] == created.id][0]
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
        self.set_buffers(self.v101, 0, 45)
        other = self.confirmed(window=(datetime(2027, 3, 12, 12, 30), datetime(2027, 3, 12, 14, 0)),
                               event="E2")
        response = self.client.post(
            f"{BOOKINGS_URL}/{created['id']}/approve", headers=self.auth_headers(self.users["gus"]))
        body = self.assert_error(response, 409)
        self.assertEqual(body["reason"], "conflict")
        self.assertEqual(body["conflicts"][0]["id"], other.id)


# ---------- AC5: changing a venue's setup or turnaround flags overlapping bookings ----------


class FlagTestCase(SetupTurnaroundTestCase):
    """V-101 with setup 15 and turnaround 15; B-501 10:00-12:00 (occupied 09:45-12:15) and
    B-502 13:00-15:00 (occupied 12:45-15:15)."""

    def setUp(self):
        super().setUp()
        self.set_buffers(self.v101, 15, 15)
        self.b501 = self.confirmed(window=(datetime(2027, 11, 20, 10), datetime(2027, 11, 20, 12)),
                                   event="E1")
        self.b502 = self.confirmed(window=(datetime(2027, 11, 20, 13), datetime(2027, 11, 20, 15)),
                                   event="E2")

    def flagged(self, user="gus", **query):
        return self.client.get(FLAGGED_URL, query_string=query,
                               headers=self.auth_headers(self.users[user]))

    def flagged_ids(self, **query):
        response = self.flagged(**query)
        self.assertEqual(response.status_code, 200, response.get_json())
        return sorted(b["id"] for b in response.get_json()["bookings"])

    def change(self, **fields):
        response = self.edit_venue(**fields)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response

    def hold(self, window, event="E3"):
        from tests.test_venue_holds import EXPIRY_AT, HELD_AT
        hold = self.confirmed(window=window, status="tentative", event=event)
        hold.held_at, hold.hold_expires_at = HELD_AT, EXPIRY_AT.replace(year=2099)
        hold.held_by_id = self.users["gus"].id
        self.db.session.commit()
        return hold

    def both(self):
        return sorted([self.b501.id, self.b502.id])


class FlaggingTests(FlagTestCase):
    def test_tc17_raising_the_turnaround_so_two_bookings_overlap_flags_both(self):  # AC5
        self.change(turnaround_minutes=60)  # B-501 occupies to 13:00, B-502 from 12:45
        self.assertEqual(self.flagged_ids(), self.both())

    def test_tc18_flagged_bookings_are_listed_for_venue_staff(self):  # AC5
        self.change(turnaround_minutes=60)
        entries = {b["id"]: b for b in self.flagged().get_json()["bookings"]}
        first = entries[self.b501.id]
        self.assertEqual(first["flag"], FLAG)
        self.assertEqual(first["status"], "confirmed")
        self.assertEqual(first["venue"]["id"], self.v101.id)
        self.assertEqual(first["event"]["id"], self.events["E1"].id)
        self.assertEqual((first["start_time"], first["end_time"]),
                         ("2027-11-20T10:00:00", "2027-11-20T12:00:00"))
        self.assertEqual((first["occupied_start"], first["occupied_end"]),
                         ("2027-11-20T09:45:00", "2027-11-20T13:00:00"))
        self.assertEqual(first["turnaround"]["minutes"], 60)
        self.assertEqual(first["overlaps"], [self.b502.id])
        self.assertEqual(entries[self.b502.id]["overlaps"], [self.b501.id])
        self.assertIsInstance(first["flagged_at"], str)

    def test_tc19_a_change_that_creates_no_overlap_flags_nothing(self):  # AC5
        self.change(turnaround_minutes=30)  # B-501 occupies to 12:30, B-502 from 12:45
        response = self.flagged()
        self.assertEqual(response.get_json()["bookings"], [])
        self.assertTrue(response.get_json()["message"])

    def test_tc20_occupied_periods_that_only_touch_are_not_flagged(self):  # AC5
        self.change(turnaround_minutes=45)  # B-501 occupies to 12:45 exactly
        self.assertEqual(self.flagged_ids(), [])

    def test_tc21_occupied_periods_that_overlap_by_one_minute_are_flagged(self):  # AC5
        self.change(turnaround_minutes=46)
        self.assertEqual(self.flagged_ids(), self.both())

    def test_tc22_raising_the_setup_so_two_bookings_overlap_flags_both(self):  # AC5
        self.change(setup_minutes=61)  # B-502 occupies from 11:59, B-501 to 12:15
        self.assertEqual(self.flagged_ids(), self.both())

    def test_tc23_pending_and_tentative_bookings_are_flagged_as_well(self):  # AC5
        self.b501.status = "pending"
        self.db.session.commit()
        self.db.session.delete(self.b502)
        self.db.session.commit()
        hold = self.hold((datetime(2027, 11, 20, 13), datetime(2027, 11, 20, 15)))
        self.change(turnaround_minutes=60)
        self.assertEqual(self.flagged_ids(), sorted([self.b501.id, hold.id]))
        statuses = {b["status"] for b in self.flagged().get_json()["bookings"]}
        self.assertEqual(statuses, {"pending", "tentative"})

    def test_tc24_a_cancelled_booking_is_not_flagged(self):  # AC5
        self.b502.status = "cancelled"
        self.db.session.commit()
        self.change(turnaround_minutes=60)
        self.assertEqual(self.flagged_ids(), [])

    def test_tc25_no_booking_is_cancelled_or_changed_by_the_flag(self):  # AC5
        before = {b.id: (b.status, b.start_time, b.end_time, b.venue_id, b.event_id,
                         b.decided_at, b.hold_expires_at) for b in (self.b501, self.b502)}
        self.change(turnaround_minutes=60)
        self.db.session.expire_all()
        after = {b.id: (b.status, b.start_time, b.end_time, b.venue_id, b.event_id,
                        b.decided_at, b.hold_expires_at)
                 for b in VenueBooking.query.filter(VenueBooking.id.in_(list(before)))}
        self.assertEqual(after, before)

    def test_tc26_bookings_at_other_venues_are_not_flagged(self):  # AC5
        self.set_buffers(self.v102, 15, 15)
        for start, end, event in ((10, 12, "E1"), (13, 15, "E2")):
            self.confirmed(self.v102, (datetime(2027, 11, 20, start), datetime(2027, 11, 20, end)),
                           event=event)
        self.change(turnaround_minutes=60)
        self.assertEqual(self.flagged_ids(), self.both())
        self.assertEqual(self.flagged_ids(venue_id=self.v102.id), [])
        self.assertEqual(self.flagged_ids(venue_id=self.v101.id), self.both())


class FlaggingEdgeCaseTests(FlagTestCase):
    def test_an_edit_that_leaves_setup_and_turnaround_alone_flags_nothing(self):  # AC5
        self.change(turnaround_minutes=15, capacity=900)
        self.assertEqual(self.flagged_ids(), [])

    def test_a_later_change_that_removes_the_overlap_clears_the_flags(self):  # AC5
        self.change(turnaround_minutes=60)
        self.change(turnaround_minutes=20)
        self.assertEqual(self.flagged_ids(), [])

    def test_bookings_whose_events_themselves_overlap_are_not_a_setup_conflict(self):  # AC5
        self.confirmed(window=(datetime(2027, 11, 20, 11), datetime(2027, 11, 20, 14)),
                       status="pending", event="E3")
        self.change(setup_minutes=20)
        self.assertEqual(self.flagged_ids(), [])  # nothing overlaps because of the setup

    def test_an_expired_hold_is_not_flagged(self):  # AC5
        hold = self.hold((datetime(2027, 11, 20, 15, 30), datetime(2027, 11, 20, 16, 30)))
        hold.hold_expires_at = datetime(2020, 1, 1)
        self.db.session.commit()
        self.change(turnaround_minutes=60)
        self.assertNotIn(hold.id, self.flagged_ids())

    def test_the_venue_save_fails_without_flagging_when_the_flags_cannot_be_saved(self):  # AC5
        with self.queries_fail_on("venue_booking_flags"):
            response = self.edit_venue(turnaround_minutes=60)
        self.assertEqual(response.status_code, 503, response.get_json())
        self.db.session.expire_all()
        self.assertEqual(self.db.session.get(type(self.v101), self.v101.id).turnaround_minutes, 15)

    def test_only_venue_staff_can_list_flagged_bookings(self):  # AC5
        self.assertEqual(self.client.get(FLAGGED_URL).status_code, 401)
        self.assertEqual(self.flagged(user="alice").status_code, 403)
        self.assertEqual(self.flagged(user="gus").status_code, 200)

    def test_the_list_reports_a_503_when_it_cannot_be_read(self):  # AC5
        self.change(turnaround_minutes=60)
        headers = self.auth_headers(self.users["gus"])
        self.db.session.expire_all()
        with self.queries_fail_on("venue_booking_flags"):
            response = self.client.get(FLAGGED_URL, headers=headers)
        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)

    def test_a_bad_venue_filter_is_refused(self):  # AC5
        self.assertEqual(self.flagged(venue_id="abc").status_code, 400)


if __name__ == "__main__":
    unittest.main()
