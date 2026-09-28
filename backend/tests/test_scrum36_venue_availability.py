"""Tests for SCRUM-36 "View Venue Availability by Date and Time".

Each test names the case it automates from
docs/test-cases/SCRUM-36-venue-availability.md (TC-36-xx) and the acceptance
criteria it checks. Assumptions A1-A6 and questions Q1-Q6 are defined there.

Model (new tables, shared with the venue booking stories)
    VenueBooking  venue_bookings
        venue_id    FK venues.id, not null
        status      "pending" | "confirmed" | "rejected" | "cancelled", not null
        start_time  DateTime, not null   (Singapore time, no time zone)
        end_time    DateTime, not null   CHECK (end_time > start_time)
    VenueBlock    venue_blocks
        venue_id    FK venues.id, not null
        reason      Text
        start_time  DateTime, not null
        end_time    DateTime, not null   CHECK (end_time > start_time)

Endpoint (JWT required, else 401; caller's role not coordinator/venue_staff -> 403)
    GET /api/venues/<id>/availability?from=YYYY-MM-DD[&to=YYYY-MM-DD]
        `to` defaults to `from`. Missing or invalid dates, or `to` before `from` -> 400.
        404 unknown venue.
        200 {
            "venue_id": int, "from": "YYYY-MM-DD", "to": "YYYY-MM-DD",
            "periods": [{"type": "booking" | "block", "id": int,
                         "start": ISO datetime, "end": ISO datetime,
                         "reason": str | null}, ...],
            "days": [{"date": "YYYY-MM-DD",
                      "slots": [{"start": ISO, "end": ISO, "status": str}, ...]}, ...],
            "message": str | null,
        }
        `periods` holds every confirmed booking and every block overlapping the range,
        with its full start and end (not cut off at the range edges), sorted by start.
        Each day's `slots` cover 00:00 to the next 00:00 with no gaps. Neighbouring
        slots with the same status are merged. Status is one of:
            "unavailable"              covered by a confirmed booking or block (wins)
            "available"                within operating hours
            "outside_operating_hours"  outside operating hours
            "hours_not_recorded"       the venue has no usable operating hours
        `message` is the empty-state text when no periods overlap the range.
    503 {"error": str, "retryable": true} if the database fails, even partly.

Periods run up to but not including their end (A4), so touching periods do not overlap.
"""

import unittest
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.models import Venue, VenueBlock, VenueBooking
from tests import seed_data
from tests.scheduling import SchedulingTestCase

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
OUTSIDE = "outside_operating_hours"
HOURS_NOT_RECORDED = "hours_not_recorded"

VIEWER_ROLES = ("coordinator", "venue_staff")

# "Expected calendar for Aurora Ballroom on Thu 15 Oct" in the test case document.
AURORA_15_OCT = [
    ("00:00", "08:00", OUTSIDE),
    ("08:00", "10:00", AVAILABLE),
    ("10:00", "13:00", UNAVAILABLE),  # B1 10:00-12:00 + K3 11:00-13:00
    ("13:00", "14:00", AVAILABLE),
    ("14:00", "17:00", UNAVAILABLE),  # B2 14:00-16:00 + K1 16:00-17:00
    ("17:00", "23:00", AVAILABLE),    # pending B3 and cancelled B4 do not block
    ("23:00", "24:00", OUTSIDE),
]


class AvailabilityTestCase(SchedulingTestCase):
    """Seeds AV-SEED and wraps the availability endpoint."""

    def setUp(self):
        super().setUp()
        self.seed_bookings(seed_data.AVAILABILITY_BOOKINGS)
        self.seed_blocks(seed_data.AVAILABILITY_BLOCKS)

    # ---------- Requests ----------

    def availability_url(self, venue_key):
        return f"/api/venues/{self.venues[venue_key].id}/availability"

    def get_availability(self, venue="fully_recorded", start="2026-10-15", end=None,
                         as_user=None, headers=None):
        query = {"from": start}
        if end is not None:
            query["to"] = end
        if headers is None:
            headers = self.auth_headers(as_user or self.users["coordinator"])
        return self.client.get(self.availability_url(venue), headers=headers,
                               query_string=query)

    def availability(self, *args, **kwargs):
        response = self.get_availability(*args, **kwargs)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    # ---------- Reading the calendar ----------

    def day_slots(self, body, date):
        """A day's slots as (HH:MM, HH:MM, status), with the next midnight as 24:00."""
        day = next(d for d in body["days"] if d["date"] == date)
        day_date = datetime.fromisoformat(date).date()

        def clock(value):
            moment = datetime.fromisoformat(value)
            return "24:00" if moment.date() > day_date else moment.strftime("%H:%M")

        return [(clock(s["start"]), clock(s["end"]), s["status"]) for s in day["slots"]]

    def status_at(self, body, when):
        moment = datetime.fromisoformat(when)
        for day in body["days"]:
            for slot in day["slots"]:
                start = datetime.fromisoformat(slot["start"])
                end = datetime.fromisoformat(slot["end"])
                if start <= moment < end:
                    return slot["status"]
        self.fail(f"no slot covers {when}")

    def listed(self, body):
        """Seed keys of the listed periods, in listed order."""
        keys = {("booking", b.id): k for k, b in self.bookings.items()}
        keys.update({("block", b.id): k for k, b in self.blocks.items()})
        return [keys[(p["type"], p["id"])] for p in body["periods"]]

    def period(self, body, key):
        record = self.bookings.get(key) or self.blocks[key]
        kind = "booking" if key in self.bookings else "block"
        return next(p for p in body["periods"] if p["type"] == kind and p["id"] == record.id)


# ---------- AC1: select a venue and a date or date range ----------


class SelectVenueAndDatesTests(AvailabilityTestCase):
    # TC-36-01 · AC1, AC2, AC3, AC4 — coordinator views one day with bookings and blocks.
    def test_coordinator_views_one_day_with_bookings_and_blocks(self):
        body = self.availability()

        self.assertEqual(body["venue_id"], self.venues["fully_recorded"].id)
        self.assertEqual((body["from"], body["to"]), ("2026-10-15", "2026-10-15"))
        self.assertEqual(self.day_slots(body, "2026-10-15"), AURORA_15_OCT)
        self.assertEqual(self.listed(body), ["B1", "K3", "B2", "K1"])
        self.assertIsNone(body["message"])

    # TC-36-01 · AC2 — each listed period shows its type and full start and end.
    def test_each_period_shows_its_type_start_and_end(self):
        body = self.availability()

        self.assertEqual(
            self.period(body, "B1"),
            {"type": "booking", "id": self.bookings["B1"].id,
             "start": "2026-10-15T10:00:00", "end": "2026-10-15T12:00:00", "reason": None},
        )
        self.assertEqual(
            self.period(body, "K3"),
            {"type": "block", "id": self.blocks["K3"].id,
             "start": "2026-10-15T11:00:00", "end": "2026-10-15T13:00:00",
             "reason": "AV rigging"},
        )

    # TC-36-02 · AC1 (authorisation) — venue staff see the same calendar as coordinators.
    def test_every_viewer_role_can_view_availability(self):
        for role in VIEWER_ROLES:
            with self.subTest(role=role):
                body = self.availability(as_user=self.users[role])

                self.assertEqual(self.day_slots(body, "2026-10-15"), AURORA_15_OCT)

    # TC-36-03 · AC1, AC2 — a multi-day range lists a spanning block once.
    def test_multi_day_range(self):
        body = self.availability(start="2026-10-15", end="2026-10-17")

        self.assertEqual([d["date"] for d in body["days"]],
                         ["2026-10-15", "2026-10-16", "2026-10-17"])
        self.assertEqual(self.day_slots(body, "2026-10-15"), AURORA_15_OCT)
        self.assertEqual(self.listed(body).count("K2"), 1)
        self.assertEqual(
            (self.period(body, "K2")["start"], self.period(body, "K2")["end"]),
            ("2026-10-16T20:00:00", "2026-10-17T12:00:00"),
        )
        self.assertEqual(self.status_at(body, "2026-10-16T08:00"), AVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-16T19:59"), AVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-16T20:00"), UNAVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-17T08:00"), UNAVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-17T11:59"), UNAVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-17T12:00"), AVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-17T22:59"), AVAILABLE)

    # TC-36-04 · AC1 (authorisation, A1/Q3) — other roles are refused.
    def test_other_roles_cannot_view_availability(self):
        for role in ("organiser", "attendee", "tech_staff"):
            with self.subTest(role=role):
                response = self.get_availability(as_user=self.users[role])

                self.assert_error(response, 403)
                self.assertNotIn("periods", response.get_json())

    # TC-36-05 · AC1 (authentication) — no token, an expired token, or a deleted user.
    def test_viewing_requires_a_valid_session(self):
        cases = {
            "no token": {},
            "expired token": self.expired_headers(self.users["coordinator"]),
            "deleted user": self.deleted_user_headers(),
        }
        for name, headers in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.get_availability(headers=headers).status_code, 401)

    # TC-36-06 · AC1 — "no venue selected" is a frontend check: the API has the
    # venue in its URL, so there is no request without one to test here.

    # TC-36-07 · AC1 — unknown venue.
    def test_unknown_venue_returns_not_found(self):
        response = self.client.get(
            f"/api/venues/{self.missing_id(Venue)}/availability",
            headers=self.auth_headers(self.users["coordinator"]),
            query_string={"from": "2026-10-15"},
        )

        self.assert_error(response, 404)

    # TC-36-08 · AC1 — end date before start date.
    def test_end_date_before_start_date_is_rejected(self):
        self.assert_error(self.get_availability(start="2026-10-17", end="2026-10-15"), 400)

    # TC-36-09 · AC1 — invalid or missing dates.
    def test_invalid_or_missing_dates_are_rejected(self):
        for value in ("2026-02-30", "15/10/2026", "tomorrow", ""):
            with self.subTest(date=value):
                self.assert_error(self.get_availability(start=value), 400)

        with self.subTest(date="missing"):
            response = self.client.get(
                self.availability_url("fully_recorded"),
                headers=self.auth_headers(self.users["coordinator"]),
            )
            self.assert_error(response, 400)

    # TC-36-09 · AC1 — an invalid end date is rejected too.
    def test_invalid_end_date_is_rejected(self):
        self.assert_error(self.get_availability(start="2026-10-15", end="2026-10-32"), 400)

    # TC-36-10 · AC1 (boundary) — longest allowed range. 31 days is a placeholder.
    @unittest.skip("Blocked: awaiting the customer's answer to Q5 (maximum date range)")
    def test_longest_allowed_date_range(self):
        self.assertEqual(self.get_availability(start="2026-10-15", end="2026-10-15")
                         .status_code, 200)
        self.assertEqual(self.get_availability(start="2026-10-01", end="2026-10-31")
                         .status_code, 200)
        self.assert_error(self.get_availability(start="2026-10-01", end="2026-11-01"), 400)


# ---------- AC2: bookings and blocks shown with start and end dates and times ----------


class PeriodDisplayTests(AvailabilityTestCase):
    # TC-36-11 · AC2 (boundary) — a period extending beyond the range keeps its true times.
    def test_period_beyond_the_range_shows_its_true_start_and_end(self):
        body = self.availability(start="2026-10-17")

        self.assertEqual(self.listed(body), ["K2"])
        self.assertEqual(
            (self.period(body, "K2")["start"], self.period(body, "K2")["end"]),
            ("2026-10-16T20:00:00", "2026-10-17T12:00:00"),
        )
        self.assertEqual(self.status_at(body, "2026-10-17T08:00"), UNAVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-17T12:00"), AVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-17T22:59"), AVAILABLE)

    # TC-36-12 · AC2, AC3 (boundary) — records touching the edges of the range.
    def test_records_touching_the_range_edges(self):
        self.seed_blocks([
            {"key": "K4", "venue": "fully_recorded", "reason": "Ends at midnight",
             "start_time": datetime(2026, 10, 14, 22, 0),
             "end_time": datetime(2026, 10, 15, 0, 0)},
            {"key": "K5", "venue": "fully_recorded", "reason": "One minute into the day",
             "start_time": datetime(2026, 10, 14, 23, 0),
             "end_time": datetime(2026, 10, 15, 0, 1)},
            {"key": "K6", "venue": "fully_recorded", "reason": "Starts at next midnight",
             "start_time": datetime(2026, 10, 16, 0, 0),
             "end_time": datetime(2026, 10, 16, 1, 0)},
            {"key": "K7", "venue": "fully_recorded", "reason": "One minute before midnight",
             "start_time": datetime(2026, 10, 15, 23, 59),
             "end_time": datetime(2026, 10, 16, 0, 30)},
        ])

        body = self.availability()
        listed = self.listed(body)

        self.assertNotIn("K4", listed)
        self.assertNotIn("K6", listed)
        self.assertIn("K5", listed)
        self.assertIn("K7", listed)
        self.assertEqual(self.period(body, "K5")["start"], "2026-10-14T23:00:00")
        self.assertEqual(self.period(body, "K7")["end"], "2026-10-16T00:30:00")
        self.assertEqual(self.status_at(body, "2026-10-15T00:00"), UNAVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-15T00:01"), OUTSIDE)
        self.assertEqual(self.status_at(body, "2026-10-15T23:59"), UNAVAILABLE)


# ---------- AC3: incompatible bookings and blocks are never shown as available ----------


class IncompatiblePeriodTests(AvailabilityTestCase):
    # TC-36-13 · AC2, AC3 (A2/Q2) — pending and cancelled bookings do not block time.
    def test_pending_and_cancelled_bookings_do_not_block_time(self):
        body = self.availability()

        self.assertNotIn("B3", self.listed(body))
        self.assertNotIn("B4", self.listed(body))
        for when in ("18:00", "19:59", "20:00", "20:59"):
            with self.subTest(time=when):
                self.assertEqual(self.status_at(body, f"2026-10-15T{when}"), AVAILABLE)

    # TC-36-14 · AC2, AC3 (boundary) — an overlapping booking and block.
    def test_overlapping_booking_and_block(self):
        body = self.availability()

        self.assertIn("B1", self.listed(body))
        self.assertIn("K3", self.listed(body))
        self.assertIn(("10:00", "13:00", UNAVAILABLE), self.day_slots(body, "2026-10-15"))
        for when in ("10:00", "11:00", "11:59", "12:59"):
            with self.subTest(time=when):
                self.assertEqual(self.status_at(body, f"2026-10-15T{when}"), UNAVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-15T13:00"), AVAILABLE)

    # TC-36-15 · AC3 (boundary) — back-to-back records leave no gap.
    def test_back_to_back_records_leave_no_gap(self):
        slots = self.day_slots(self.availability(), "2026-10-15")

        self.assertIn(("14:00", "17:00", UNAVAILABLE), slots)
        self.assertTrue(all(start < end for start, end, _ in slots), "zero-length slot found")
        self.assertIn(("13:00", "14:00", AVAILABLE), slots)
        self.assertIn(("17:00", "23:00", AVAILABLE), slots)

    # TC-36-15 · AC3 — slots cover the whole day with no gaps or overlaps.
    def test_slots_cover_the_whole_day_without_gaps(self):
        slots = self.day_slots(self.availability(), "2026-10-15")

        self.assertEqual(slots[0][0], "00:00")
        self.assertEqual(slots[-1][1], "24:00")
        for earlier, later in zip(slots, slots[1:]):
            self.assertEqual(earlier[1], later[0])
            self.assertNotEqual(earlier[2], later[2], "neighbouring slots should be merged")

    # TC-36-16 · AC3 — another venue's bookings do not affect this venue.
    def test_other_venues_bookings_do_not_affect_this_venue(self):
        civic = self.availability(venue="recorded_as_none")
        aurora = self.availability(venue="fully_recorded")

        self.assertEqual(self.listed(civic), ["B6"])
        self.assertEqual(
            self.day_slots(civic, "2026-10-15"),
            [("00:00", "09:00", OUTSIDE), ("09:00", "18:00", UNAVAILABLE),
             ("18:00", "24:00", OUTSIDE)],
        )
        self.assertNotIn("B6", self.listed(aurora))
        self.assertEqual(self.day_slots(aurora, "2026-10-15"), AURORA_15_OCT)

    # TC-36-17 · AC3, AC4 — a venue with nothing recorded is available, not an error.
    def test_venue_with_no_bookings_or_blocks(self):
        body = self.availability(start="2026-10-19")

        self.assertEqual(body["periods"], [])
        self.assertEqual(
            self.day_slots(body, "2026-10-19"),
            [("00:00", "08:00", OUTSIDE), ("08:00", "23:00", AVAILABLE),
             ("23:00", "24:00", OUTSIDE)],
        )
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())


# ---------- AC4: time outside bookings and blocks is assessed separately ----------


class SchedulingRuleTests(AvailabilityTestCase):
    # TC-36-18 · AC4 — one booking does not make the whole day unavailable.
    def test_one_booking_does_not_make_the_whole_day_unavailable(self):
        self.seed_bookings([
            {"key": "B8", "venue": "recorded_as_none", "status": "confirmed",
             "start_time": datetime(2026, 10, 14, 12, 0),
             "end_time": datetime(2026, 10, 14, 13, 0)},
        ])

        body = self.availability(venue="recorded_as_none", start="2026-10-14")

        self.assertEqual(
            self.day_slots(body, "2026-10-14"),
            [("00:00", "09:00", OUTSIDE), ("09:00", "12:00", AVAILABLE),
             ("12:00", "13:00", UNAVAILABLE), ("13:00", "18:00", AVAILABLE),
             ("18:00", "24:00", OUTSIDE)],
        )

    # TC-36-19 · AC4 (A3/Q1) — a closed day is outside operating hours, not booked.
    def test_closed_day_is_outside_operating_hours(self):
        body = self.availability(venue="recorded_as_none", start="2026-10-17")

        self.assertEqual(body["periods"], [])
        self.assertEqual(self.day_slots(body, "2026-10-17"), [("00:00", "24:00", OUTSIDE)])

    # TC-36-20 · AC4 (boundary, A3/Q1) — operating-hours edges.
    def test_operating_hours_edges(self):
        body = self.availability(start="2026-10-19")

        self.assertEqual(self.status_at(body, "2026-10-19T07:59"), OUTSIDE)
        self.assertEqual(self.status_at(body, "2026-10-19T08:00"), AVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-19T22:59"), AVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-19T23:00"), OUTSIDE)

    # TC-36-21 · AC4, AC6 — a venue with no recorded operating hours (proposed behaviour).
    @unittest.skip("Blocked: awaiting the customer's answer to Q4 (unrecorded operating hours)")
    def test_venue_with_no_recorded_operating_hours(self):
        body = self.availability(venue="partially_recorded")

        self.assertEqual(self.day_slots(body, "2026-10-15"),
                         [("00:00", "24:00", HOURS_NOT_RECORDED)])


# ---------- AC5: a refreshed calendar reflects saved changes ----------
#
# Changes are saved directly through the models until the booking approval and
# block management endpoints exist.


class RefreshTests(AvailabilityTestCase):
    def save(self):
        self.db.session.commit()
        self.db.session.expire_all()

    # TC-36-22 · AC5 — a newly confirmed booking appears after refresh.
    def test_newly_confirmed_booking_appears_after_refresh(self):
        self.assertEqual(self.status_at(self.availability(), "2026-10-15T18:00"), AVAILABLE)

        self.bookings["B3"].status = "confirmed"
        self.save()
        body = self.availability()

        self.assertIn("B3", self.listed(body))
        self.assertEqual(self.status_at(body, "2026-10-15T17:59"), AVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-15T18:00"), UNAVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-15T19:59"), UNAVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-15T20:00"), AVAILABLE)

    # TC-36-23 · AC5 — a cancelled booking is freed after refresh.
    def test_cancelled_booking_is_freed_after_refresh(self):
        self.bookings["B2"].status = "cancelled"
        self.save()
        body = self.availability()

        self.assertNotIn("B2", self.listed(body))
        self.assertIn(("13:00", "16:00", AVAILABLE), self.day_slots(body, "2026-10-15"))
        self.assertEqual(self.status_at(body, "2026-10-15T16:00"), UNAVAILABLE)  # K1

    # TC-36-24 · AC5 — an edited block moves after refresh.
    def test_edited_block_moves_after_refresh(self):
        self.blocks["K1"].start_time = datetime(2026, 10, 15, 21, 0)
        self.blocks["K1"].end_time = datetime(2026, 10, 15, 22, 0)
        self.save()
        body = self.availability()

        self.assertEqual(
            (self.period(body, "K1")["start"], self.period(body, "K1")["end"]),
            ("2026-10-15T21:00:00", "2026-10-15T22:00:00"),
        )
        self.assertEqual(self.status_at(body, "2026-10-15T16:00"), AVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-15T21:00"), UNAVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-15T22:00"), AVAILABLE)

    # TC-36-25 · AC5 — a new block appears after refresh.
    def test_new_block_appears_after_refresh(self):
        self.seed_blocks([
            {"key": "K8", "venue": "fully_recorded", "reason": "Fire drill",
             "start_time": datetime(2026, 10, 15, 8, 0),
             "end_time": datetime(2026, 10, 15, 9, 0)},
        ])
        body = self.availability()

        self.assertIn("K8", self.listed(body))
        self.assertEqual(self.status_at(body, "2026-10-15T08:00"), UNAVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-15T09:00"), AVAILABLE)

    # TC-36-26 · AC5 — a change that fails to save is not shown.
    def test_change_that_fails_to_save_is_not_shown(self):
        block = self.blocks["K1"]
        block.start_time = datetime(2026, 10, 15, 17, 0)
        block.end_time = datetime(2026, 10, 15, 16, 0)

        with self.assertRaises(IntegrityError):
            self.db.session.commit()
        self.db.session.rollback()

        body = self.availability()
        self.assertEqual(
            (self.period(body, "K1")["start"], self.period(body, "K1")["end"]),
            ("2026-10-15T16:00:00", "2026-10-15T17:00:00"),
        )
        self.assertEqual(self.day_slots(body, "2026-10-15"), AURORA_15_OCT)


# ---------- AC6: load failures are shown as errors, never as availability ----------


class LoadFailureTests(AvailabilityTestCase):
    def url(self):
        return self.availability_url("fully_recorded")

    def assert_nothing_shown_as_available(self, response):
        self.assert_retryable_error(response)
        body = response.get_json()
        self.assertNotIn("days", body)
        self.assertNotIn("periods", body)

    # TC-36-27 · AC6 — database unavailable when loading.
    def test_database_unavailable_when_loading(self):
        response = self.get_while_failing(self.url(), query_string={"from": "2026-10-15"})

        self.assert_nothing_shown_as_available(response)

    # TC-36-28 · AC6 — blocks fail to load while bookings load: still a full failure.
    def test_partial_failure_is_treated_as_a_full_failure(self):
        response = self.get_while_failing(
            self.url(), VenueBlock.__tablename__, query_string={"from": "2026-10-15"}
        )

        self.assert_nothing_shown_as_available(response)

    # TC-36-28 · AC6 — and the other way round: bookings fail while blocks load.
    def test_bookings_failing_is_treated_as_a_full_failure(self):
        response = self.get_while_failing(
            self.url(), VenueBooking.__tablename__, query_string={"from": "2026-10-15"}
        )

        self.assert_nothing_shown_as_available(response)

    # TC-36-29 · AC6 — retry succeeds after recovery.
    def test_retry_succeeds_after_recovery(self):
        failed = self.get_while_failing(self.url(), query_string={"from": "2026-10-15"})
        self.assert_retryable_error(failed)

        body = self.availability()
        self.assertEqual(self.day_slots(body, "2026-10-15"), AURORA_15_OCT)

    # TC-36-30 · AC5, AC6 — a refresh that fails after a successful load is an error.
    # (Not presenting the old calendar as current is checked in the frontend.)
    def test_refresh_fails_after_a_successful_load(self):
        self.assertEqual(self.day_slots(self.availability(), "2026-10-15"), AURORA_15_OCT)

        response = self.get_while_failing(self.url(), query_string={"from": "2026-10-15"})

        self.assert_nothing_shown_as_available(response)


if __name__ == "__main__":
    unittest.main()
