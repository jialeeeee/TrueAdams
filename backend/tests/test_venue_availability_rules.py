"""Tests for SCRUM-64 "Define Availability Rules on the Venue Calendar" (addressing SCRUM-36).

Each test names the case it automates from
docs/test-cases/SCRUM-64-venue-availability-rules.md (TC-64-xx) and the acceptance
criteria it checks. Assumptions A1-A6 and questions Q1-Q4 are defined there.
TC-64-03, 04, 05, 12, 13, 15 and 17 are earlier stories' tests, mostly in
test_scrum36_venue_availability.py, whose expectations SCRUM-64 updated.

Endpoint: GET /api/venues/<id>/availability (SCRUM-36). Each day's slots are
    {"start", "end", "status", "causes"}
    status  "available" | "unavailable" | "hours_not_recorded"
    causes  why an unavailable slot is unavailable, in this order:
            "booking", "block", "outside_operating_hours"; empty otherwise.
Neighbouring slots are merged only when their status and causes are both the same.

The seed data is SCRUM-36's AV-SEED, so these tests build on its AvailabilityTestCase.
"""

import unittest
from datetime import datetime

from tests.test_scrum36_venue_availability import (
    AVAILABLE,
    BLOCK,
    BOOKING,
    HOURS_NOT_RECORDED,
    OUTSIDE,
    UNAVAILABLE,
    AvailabilityTestCase,
    free,
    taken,
)


def not_recorded(start, end):
    """Free time at a venue whose operating hours are not recorded (A5)."""
    return (start, end, HOURS_NOT_RECORDED, ())


# ---------- AC1: a record makes only its own period unavailable ----------


class OwnPeriodTests(AvailabilityTestCase):
    # TC-64-01 · AC1, AC4 — a booking makes only its own period unavailable.
    def test_booking_makes_only_its_own_period_unavailable(self):
        self.seed_bookings([
            {"key": "B8", "venue": "recorded_as_none", "status": "confirmed",
             "start_time": datetime(2026, 10, 14, 12, 0),
             "end_time": datetime(2026, 10, 14, 13, 0)},
        ])

        body = self.availability(venue="recorded_as_none", start="2026-10-14")

        self.assertEqual(self.day_slots(body, "2026-10-14"), [
            taken("00:00", "09:00", OUTSIDE),
            free("09:00", "12:00"),
            taken("12:00", "13:00", BOOKING),
            free("13:00", "18:00"),
            taken("18:00", "24:00", OUTSIDE),
        ])

    # TC-64-02 · AC1, AC4 — a recorded block makes only its own period unavailable.
    def test_block_makes_only_its_own_period_unavailable(self):
        self.seed_blocks([
            {"key": "K9", "venue": "fully_recorded", "reason": "Fire drill",
             "start_time": datetime(2026, 10, 19, 15, 0),
             "end_time": datetime(2026, 10, 19, 16, 0)},
        ])

        body = self.availability(start="2026-10-19")

        self.assertEqual(self.day_slots(body, "2026-10-19"), [
            taken("00:00", "08:00", OUTSIDE),
            free("08:00", "15:00"),
            taken("15:00", "16:00", BLOCK),
            free("16:00", "23:00"),
            taken("23:00", "24:00", OUTSIDE),
        ])


# ---------- AC2: outside operating hours is unavailable ----------


class OutsideOperatingHoursTests(AvailabilityTestCase):
    # TC-64-06 · AC2, AC4 (boundary) — outside operating hours is unavailable, from the edges.
    def test_time_outside_operating_hours_is_unavailable(self):
        body = self.availability(start="2026-10-19")

        self.assertEqual(self.day_slots(body, "2026-10-19"), [
            taken("00:00", "08:00", OUTSIDE),
            free("08:00", "23:00"),
            taken("23:00", "24:00", OUTSIDE),
        ])
        for when, status in (("07:59", UNAVAILABLE), ("08:00", AVAILABLE),
                             ("22:59", AVAILABLE), ("23:00", UNAVAILABLE)):
            with self.subTest(time=when):
                self.assertEqual(self.status_at(body, f"2026-10-19T{when}"), status)
        self.assertTrue(body["message"].strip())

    # TC-64-07 · AC2 — a day the venue is closed is unavailable all day.
    def test_closed_day_is_unavailable_all_day(self):
        body = self.availability(venue="recorded_as_none", start="2026-10-17")

        self.assertEqual(body["periods"], [])
        self.assertEqual(self.day_slots(body, "2026-10-17"), [taken("00:00", "24:00", OUTSIDE)])

    # TC-64-08 · AC2, AC4 (boundary, Q2) — a record outside operating hours lists both causes.
    def test_record_outside_operating_hours_lists_both_causes(self):
        body = self.availability(start="2026-10-16", end="2026-10-17")

        self.assertEqual(self.day_slots(body, "2026-10-16"), [
            taken("00:00", "08:00", OUTSIDE),
            free("08:00", "20:00"),
            taken("20:00", "23:00", BLOCK),
            taken("23:00", "24:00", BLOCK, OUTSIDE),
        ])
        self.assertEqual(self.day_slots(body, "2026-10-17"), [
            taken("00:00", "08:00", BLOCK, OUTSIDE),
            taken("08:00", "12:00", BLOCK),
            free("12:00", "23:00"),
            taken("23:00", "24:00", OUTSIDE),
        ])

    # TC-64-09 · AC1, AC2 (Q1) — unrecorded hours are neither available nor unavailable.
    def test_unrecorded_hours_are_neither_available_nor_unavailable(self):
        self.seed_bookings([
            {"key": "B9", "venue": "partially_recorded", "status": "confirmed",
             "start_time": datetime(2026, 10, 15, 10, 0),
             "end_time": datetime(2026, 10, 15, 12, 0)},
        ])

        body = self.availability(venue="partially_recorded")

        self.assertEqual(self.day_slots(body, "2026-10-15"), [
            not_recorded("00:00", "10:00"),
            taken("10:00", "12:00", BOOKING),
            not_recorded("12:00", "24:00"),
        ])


# ---------- AC3: touching periods do not overlap ----------


class TouchingPeriodTests(AvailabilityTestCase):
    # TC-64-10 · AC3, AC4 (boundary) — a booking ending as a block begins.
    def test_booking_ending_as_a_block_begins_does_not_overlap(self):
        slots = self.day_slots(self.availability(), "2026-10-15")

        self.assertIn(taken("14:00", "16:00", BOOKING), slots)  # B2
        self.assertIn(taken("16:00", "17:00", BLOCK), slots)    # K1
        self.assertNotIn(BOOKING, [cause for start, _, _, causes in slots
                                   if start == "16:00" for cause in causes])
        self.assertTrue(all(start < end for start, end, *_ in slots), "zero-length slot found")
        self.assertIn(free("13:00", "14:00"), slots)
        self.assertIn(free("17:00", "23:00"), slots)

    # TC-64-11 · AC3 (boundary) — a booking ending as another booking begins.
    def test_booking_ending_as_another_begins_does_not_overlap(self):
        # Saving both shows the SCRUM-41 database rule does not see them as overlapping.
        self.seed_bookings([
            {"key": "B10", "venue": "fully_recorded", "status": "confirmed",
             "start_time": datetime(2026, 10, 19, 10, 0),
             "end_time": datetime(2026, 10, 19, 12, 0)},
            {"key": "B11", "venue": "fully_recorded", "status": "confirmed",
             "start_time": datetime(2026, 10, 19, 12, 0),
             "end_time": datetime(2026, 10, 19, 14, 0)},
        ])

        body = self.availability(start="2026-10-19")

        self.assertEqual(self.listed(body), ["B10", "B11"])
        self.assertEqual(
            [(p["start"], p["end"]) for p in body["periods"]],
            [("2026-10-19T10:00:00", "2026-10-19T12:00:00"),
             ("2026-10-19T12:00:00", "2026-10-19T14:00:00")],
        )
        self.assertEqual(self.day_slots(body, "2026-10-19"), [
            taken("00:00", "08:00", OUTSIDE),
            free("08:00", "10:00"),
            taken("10:00", "14:00", BOOKING),
            free("14:00", "23:00"),
            taken("23:00", "24:00", OUTSIDE),
        ])
        self.assertEqual(self.status_at(body, "2026-10-19T09:59"), AVAILABLE)
        self.assertEqual(self.status_at(body, "2026-10-19T14:00"), AVAILABLE)


# ---------- AC4: each unavailable period says what it is ----------


class CauseTests(AvailabilityTestCase):
    # TC-64-14 · AC4 — each unavailable slot names its cause, split where it changes.
    def test_each_unavailable_slot_names_its_cause(self):
        slots = self.day_slots(self.availability(), "2026-10-15")

        overlap = [slot for slot in slots if "10:00" <= slot[0] < "13:00"]
        self.assertEqual(overlap, [
            taken("10:00", "11:00", BOOKING),         # B1
            taken("11:00", "12:00", BOOKING, BLOCK),  # B1 and K3
            taken("12:00", "13:00", BLOCK),           # K3
        ])
        for start, end, status, causes in slots:
            with self.subTest(slot=f"{start}-{end}"):
                self.assertEqual(bool(causes), status == UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
