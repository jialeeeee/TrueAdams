"""Tests for SCRUM-37 "Search for Available Venues".

Each test names the case it automates from docs/test-cases/SCRUM-37-venue-search.md
(TC-37-xx) and the acceptance criteria it checks. Assumptions A1-A11 and questions
Q1-Q8 are defined there. Bookings and blocks use the VenueBooking and VenueBlock
models described in tests/test_scrum36_venue_availability.py.

Endpoint (JWT required, else 401; caller's role not coordinator -> 403)
    GET /api/venues/search
        Query parameters, all optional:
            date=YYYY-MM-DD, start=HH:MM, end=HH:MM   all three together, or none
            min_capacity=<whole number >= 1>
            location=<text>                           case-insensitive "contains"
            accessibility=<feature>                   repeatable; venue needs all
            layout=<one of SUPPORTED_LAYOUTS>
            facility=<facility>                       repeatable; venue needs all
        Facilities, accessibility features and layouts match recorded values exactly,
        ignoring case. A field that is not recorded, blank, or recorded as none never
        satisfies a filter on it. Venues that are not currently bookable never appear.
        With a date and time, venues are excluded when the time overlaps a confirmed
        booking or a block, or falls outside their operating hours (unrecorded or
        "By appointment" hours count as outside).
        400 invalid filter values, an incomplete date and time, or end not after start.
        200 {
            "venues": [{"id": int, "name": str, "location": str | null,
                        "capacity": int | null,
                        "matches": {<filtered list field>: [recorded values matched]},
                        "details_url": "/api/venues/<id>"}, ...],
            "message": str | null,
        }
        Sorted by name. `matches` only has keys for the facility, accessibility and
        layout filters used. `message` is the no-matches text when `venues` is empty.
    503 {"error": str, "retryable": true} if the database fails, even partly.

Real venues may be returned alongside the seeded ones, so tests check only the
seeded venues, by id.
"""

import unittest

from app.models import VenueBlock, VenueBooking
from tests import seed_data
from tests.base import RUN_ID
from tests.scheduling import SchedulingTestCase

SEARCH_URL = "/api/venues/search"

# Seed keys, named after the venues they hold.
AURORA = "fully_recorded"
BAYFRONT = "partially_recorded"
CIVIC = "recorded_as_none"
DOCKSIDE = "unavailable"
EVERGREEN = "blank_values"
HARBOUR = "harbour_room"
SUMMIT = "summit_hall"

# The 15 Oct slot used by several date and time searches.
MORNING_15_OCT = {"date": "2026-10-15", "start": "10:00", "end": "12:00"}


class SearchTestCase(SchedulingTestCase):
    """Seeds SV-SEED and wraps the search endpoint."""

    def setUp(self):
        super().setUp()
        self.venues.update(self.seed_venues(seed_data.SEARCH_VENUES))
        self.seed_bookings(seed_data.SEARCH_BOOKINGS)
        self.seed_blocks(seed_data.SEARCH_BLOCKS)
        self.key_for_id = {venue.id: key for key, venue in self.venues.items()}

    def search(self, as_user=None, headers=None, **filters):
        if headers is None:
            headers = self.auth_headers(as_user or self.users["coordinator"])
        return self.client.get(SEARCH_URL, headers=headers, query_string=filters)

    def found(self, **filters):
        """Seed keys of the seeded venues in the results, in result order."""
        response = self.search(**filters)
        self.assertEqual(response.status_code, 200, response.get_json())
        return [self.key_for_id[v["id"]] for v in response.get_json()["venues"]
                if v["id"] in self.key_for_id]

    def result(self, key, **filters):
        response = self.search(**filters)
        self.assertEqual(response.status_code, 200, response.get_json())
        venue_id = self.venues[key].id
        return next(v for v in response.get_json()["venues"] if v["id"] == venue_id)

    def assert_no_matches(self, response):
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["venues"], [])
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"].strip())


# ---------- AC1 & AC2: enter filters, apply them individually or combined ----------


class FilterTests(SearchTestCase):
    # TC-37-01 · AC1, AC2, AC3, AC4, AC5 — search using every filter.
    def test_search_using_every_filter(self):
        filters = {
            "date": "2026-10-15", "start": "18:00", "end": "21:00",
            "min_capacity": 100, "location": "Marina Tower",
            "accessibility": ["Wheelchair ramp"], "layout": "theatre",
            "facility": ["Projector", "Wi-Fi"],
        }

        self.assertEqual(self.found(**filters), [AURORA, HARBOUR])
        self.assertIsNone(self.search(**filters).get_json()["message"])
        self.assertEqual(
            self.result(AURORA, **filters),
            {
                "id": self.venues[AURORA].id,
                "name": "Aurora Ballroom",
                "location": "Level 3, Marina Tower, 10 Bayfront Ave",
                "capacity": 400,
                "matches": {
                    "facilities": ["Projector", "Wi-Fi"],
                    "accessibility_features": ["Wheelchair ramp"],
                    "room_layouts": ["theatre"],
                },
                "details_url": f"/api/venues/{self.venues[AURORA].id}",
            },
        )

    # TC-37-02 · AC2 (A8, A9) — no filters returns every bookable venue.
    def test_search_with_no_filters(self):
        self.assertEqual(self.found(), [AURORA, BAYFRONT, CIVIC, EVERGREEN, HARBOUR, SUMMIT])

    # TC-37-03 · AC1, AC2 — minimum capacity only.
    def test_minimum_capacity_only(self):
        self.assertEqual(self.found(min_capacity=100), [AURORA, HARBOUR, SUMMIT])

    # TC-37-04 · AC1, AC2 (A2/Q1) — location only, ignoring case.
    def test_location_only(self):
        self.assertEqual(self.found(location="Marina Tower"), [AURORA, HARBOUR])
        self.assertEqual(self.found(location="marina tower"), [AURORA, HARBOUR])
        self.assertEqual(self.found(location="Bayfront"), [AURORA, BAYFRONT, HARBOUR])

    # TC-37-05 · AC1, AC2, AC3 — accessibility needs only; several must all match.
    def test_accessibility_needs_only(self):
        self.assertEqual(self.found(accessibility=["Wheelchair ramp"]),
                         [AURORA, HARBOUR, SUMMIT])
        self.assertEqual(self.found(accessibility=["Accessible toilets"]), [AURORA, SUMMIT])
        self.assertEqual(self.found(accessibility=["Wheelchair ramp", "Hearing loop"]),
                         [AURORA])

    # TC-37-06 · AC1, AC2 — supported layout only.
    def test_supported_layout_only(self):
        self.assertEqual(self.found(layout="theatre"), [AURORA, CIVIC, HARBOUR, SUMMIT])
        self.assertEqual(self.found(layout="classroom"), [HARBOUR])  # not Dockside

    # TC-37-07 · AC1, AC2, AC3 (boundary) — required facilities only.
    def test_required_facilities_only(self):
        # "Covered stage" (Bayfront Pavilion) is not "Stage".
        self.assertEqual(self.found(facility=["Stage"]), [AURORA, SUMMIT])
        self.assertEqual(self.found(facility=["projector"]), [AURORA, HARBOUR, SUMMIT])
        self.assertEqual(self.found(facility=["Stage", "PA system", "Wi-Fi"]), [AURORA])

    # TC-37-08 · AC1, AC2, AC4 (A7) — date and time only.
    def test_date_and_time_only(self):
        self.assertEqual(self.found(**MORNING_15_OCT), [HARBOUR, SUMMIT])

    # TC-37-09 · AC2, AC3 — combining filters narrows the results step by step.
    def test_combining_filters_narrows_the_results(self):
        self.assertEqual(self.found(min_capacity=100, layout="banquet"), [AURORA, SUMMIT])
        self.assertEqual(self.found(min_capacity=100, layout="banquet", facility=["Wi-Fi"]),
                         [AURORA])

    # TC-37-10 · AC1 (authorisation, A1/Q4) — only coordinators can search.
    def test_only_coordinators_can_search(self):
        for role in ("venue_staff", "organiser", "attendee", "tech_staff"):
            with self.subTest(role=role):
                response = self.search(as_user=self.users[role])

                self.assert_error(response, 403)
                self.assertNotIn("venues", response.get_json())

    # TC-37-11 · AC1 (authentication) — no token, an expired token, or a deleted user.
    def test_searching_requires_a_valid_session(self):
        cases = {
            "no token": {},
            "expired token": self.expired_headers(self.users["coordinator"]),
            "deleted user": self.deleted_user_headers(),
        }
        for name, headers in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.search(headers=headers).status_code, 401)


# ---------- AC1: filter validation ----------


class FilterValidationTests(SearchTestCase):
    # TC-37-12 · AC1 (boundary) — invalid minimum capacity.
    def test_invalid_minimum_capacity_is_rejected(self):
        for value in ("0", "-5", "12.5", "abc"):
            with self.subTest(min_capacity=value):
                self.assert_error(self.search(min_capacity=value), 400)

    # TC-37-13 · AC1 (A5) — incomplete date and time filter.
    def test_incomplete_date_and_time_is_rejected(self):
        cases = {
            "date only": {"date": "2026-10-15"},
            "times without date": {"start": "10:00", "end": "12:00"},
            "no end time": {"date": "2026-10-15", "start": "10:00"},
        }
        for name, filters in cases.items():
            with self.subTest(case=name):
                self.assert_error(self.search(**filters), 400)

    # TC-37-14 · AC1 (boundary, A5/Q6) — end time must be after start time.
    def test_end_time_must_be_after_start_time(self):
        for start, end in (("14:00", "14:00"), ("14:00", "13:00")):
            with self.subTest(start=start, end=end):
                self.assert_error(self.search(date="2026-10-15", start=start, end=end), 400)

        with self.subTest(start="14:00", end="14:01"):
            response = self.search(date="2026-10-15", start="14:00", end="14:01")
            self.assertEqual(response.status_code, 200)

    # TC-37-15 · AC1 — invalid date.
    def test_invalid_date_is_rejected(self):
        for value in ("2026-02-30", "15/10/2026", "tomorrow"):
            with self.subTest(date=value):
                self.assert_error(self.search(date=value, start="10:00", end="12:00"), 400)

    # TC-37-15 · AC1 — invalid times are rejected too.
    def test_invalid_time_is_rejected(self):
        for start in ("25:00", "10am", "10:60"):
            with self.subTest(start=start):
                self.assert_error(self.search(date="2026-10-15", start=start, end="23:00"), 400)

    # TC-37-16 · AC1 (boundary) — dates in the past (proposed behaviour).
    @unittest.skip("Blocked: awaiting the customer's answer to Q5 (past dates)")
    def test_date_in_the_past_is_rejected(self):
        # Needs today fixed to 27 Sep 2026 once the implementation reads the date.
        self.assert_error(self.search(date="2026-09-26", start="10:00", end="12:00"), 400)
        self.assertEqual(
            self.search(date="2026-09-27", start="10:00", end="12:00").status_code, 200)
        self.assertEqual(
            self.search(date="2026-09-28", start="10:00", end="12:00").status_code, 200)

    # TC-37-17 · AC1 — unsupported layout value.
    def test_unsupported_layout_is_rejected(self):
        self.assert_error(self.search(layout="igloo"), 400)


# ---------- AC3: results satisfy all selected filters ----------


class AllFiltersSatisfiedTests(SearchTestCase):
    # TC-37-18 · AC3 — a venue meeting most but not all filters is excluded.
    def test_venue_meeting_most_filters_is_excluded(self):
        found = self.found(min_capacity=100, layout="banquet", accessibility=["Hearing loop"])

        self.assertEqual(found, [AURORA])  # Summit Hall has no hearing loop

    # TC-37-19 · AC3 (A4/Q2) — information never recorded does not satisfy a filter.
    def test_unrecorded_information_does_not_satisfy_a_filter(self):
        with self.subTest(filter="capacity not recorded"):
            self.assertEqual(self.found(min_capacity=1),
                             [AURORA, CIVIC, EVERGREEN, HARBOUR, SUMMIT])
        with self.subTest(filter="accessibility not recorded"):
            found = self.found(accessibility=["Wheelchair ramp"])
            self.assertNotIn(BAYFRONT, found)
            self.assertNotIn(EVERGREEN, found)
        with self.subTest(filter="blank location"):
            self.assertEqual(self.found(location="a"),
                             [AURORA, BAYFRONT, CIVIC, HARBOUR, SUMMIT])

    # TC-37-20 · AC3 (boundary) — recorded "none" is excluded only when that filter is used.
    def test_recorded_none_is_excluded_only_when_filtered(self):
        self.assertIn(CIVIC, self.found(layout="theatre"))
        self.assertEqual(self.found(layout="theatre", facility=["Projector"]),
                         [AURORA, HARBOUR, SUMMIT])

    # TC-37-21 · AC3 (boundary, A10) — minimum capacity boundaries.
    def test_minimum_capacity_boundaries(self):
        expected = {
            399: [AURORA, SUMMIT],
            400: [AURORA, SUMMIT],
            401: [],
            80: [AURORA, CIVIC, HARBOUR, SUMMIT],
            81: [AURORA, HARBOUR, SUMMIT],
        }
        for minimum, venues in expected.items():
            with self.subTest(min_capacity=minimum):
                self.assertEqual(self.found(min_capacity=minimum), venues)

    # TC-37-22 · AC3 (A8/Q7) — venues that are not currently bookable never appear.
    def test_unbookable_venues_never_appear(self):
        for filters in ({"accessibility": ["Step-free entrance"]},
                        {"facility": ["Lighting rig"]},
                        {"location": "Pier 4"}):
            with self.subTest(**filters):
                self.assertNotIn(DOCKSIDE, self.found(**filters))


# ---------- AC4: venues with incompatible bookings or blocks are excluded ----------


class AvailabilityFilterTests(SearchTestCase):
    # TC-37-23 · AC4 (boundary, A6) — overlap boundaries against B1 (Aurora 10:00-12:00).
    def test_overlap_boundaries_against_a_confirmed_booking(self):
        expected = {
            ("08:00", "10:00"): True,   # ends exactly when B1 starts
            ("12:00", "14:00"): True,   # starts exactly when B1 ends
            ("09:00", "10:01"): False,  # overlaps B1's first minute
            ("11:59", "13:00"): False,  # overlaps B1's last minute
            ("10:30", "11:30"): False,  # inside B1
            ("09:00", "13:00"): False,  # contains B1
        }
        for (start, end), listed in expected.items():
            with self.subTest(start=start, end=end):
                found = self.found(date="2026-10-15", start=start, end=end)
                self.assertEqual(AURORA in found, listed)

    # TC-37-24 · AC4 — a recorded block excludes the venue.
    def test_recorded_block_excludes_the_venue(self):
        found = self.found(date="2026-10-15", start="14:00", end="16:00")

        self.assertEqual(found, [AURORA, SUMMIT])  # Harbour: K1; Civic: B4

    # TC-37-25 · AC4 (A6/Q8) — pending and cancelled bookings do not exclude a venue.
    def test_pending_and_cancelled_bookings_do_not_exclude(self):
        with self.subTest(booking="pending B2"):
            self.assertIn(SUMMIT, self.found(**MORNING_15_OCT))
        with self.subTest(booking="cancelled B3"):
            self.assertIn(SUMMIT, self.found(date="2026-10-15", start="14:00", end="16:00"))

    # TC-37-26 · AC4 — a booking on another date does not exclude the venue.
    def test_booking_on_another_date_does_not_exclude(self):
        found = self.found(date="2026-10-16", start="10:00", end="12:00")

        self.assertEqual(found, [AURORA, CIVIC, HARBOUR, SUMMIT])

    # TC-37-27 · AC4 (boundary, A7/Q3) — requested time outside operating hours.
    def test_requested_time_outside_operating_hours(self):
        cases = [
            ("2026-10-15", "20:00", "22:00", HARBOUR, True),   # closes 22:00
            ("2026-10-15", "21:00", "23:00", HARBOUR, False),
            ("2026-10-15", "07:00", "09:00", AURORA, False),   # opens 08:00
            ("2026-10-17", "10:00", "12:00", CIVIC, False),    # Mon-Fri only
            ("2026-10-18", "10:00", "12:00", SUMMIT, False),   # Mon-Sat only
            ("2026-10-19", "10:00", "12:00", SUMMIT, True),
        ]
        for date, start, end, venue, listed in cases:
            with self.subTest(date=date, start=start, end=end, venue=venue):
                found = self.found(date=date, start=start, end=end)
                self.assertEqual(venue in found, listed)


# ---------- AC5: result content and access to details ----------


class ResultContentTests(SearchTestCase):
    # TC-37-28 · AC5 — each result shows identity, location, capacity and what matched.
    def test_result_shows_identity_location_capacity_and_matches(self):
        filters = {"min_capacity": 300, "facility": ["Stage"]}

        self.assertEqual(self.found(**filters), [AURORA, SUMMIT])
        self.assertEqual(
            self.result(SUMMIT, **filters),
            {
                "id": self.venues[SUMMIT].id,
                "name": "Summit Hall",
                "location": "5 Orchard Link",
                "capacity": 400,
                "matches": {"facilities": ["Stage"]},
                "details_url": f"/api/venues/{self.venues[SUMMIT].id}",
            },
        )

    # TC-37-28 · AC5 — the details link opens that venue's details (SCRUM-35).
    def test_details_link_opens_the_venues_details(self):
        summit = self.result(SUMMIT, min_capacity=300, facility=["Stage"])

        response = self.client.get(summit["details_url"],
                                   headers=self.auth_headers(self.users["coordinator"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["id"], self.venues[SUMMIT].id)
        self.assertEqual(response.get_json()["name"], "Summit Hall")

    # TC-37-29 · AC5 (boundary) — a blank location comes back as not recorded.
    def test_blank_location_is_returned_as_not_recorded(self):
        evergreen = self.result(EVERGREEN, layout="u_shape")

        self.assertIsNone(evergreen["location"])


# ---------- AC6: no matches ----------


class NoMatchTests(SearchTestCase):
    # TC-37-30 · AC6 — no matches, then revise the filters.
    # (Keeping the filters filled in for editing is checked in the frontend.)
    def test_no_matches_then_revise_the_filters(self):
        self.assert_no_matches(self.search(min_capacity=10_000_000))

        self.assertEqual(self.found(min_capacity=300), [AURORA, SUMMIT])

    # TC-37-31 · AC6 — an unknown facility gives no matches, not an error.
    def test_unknown_facility_gives_no_matches(self):
        self.assert_no_matches(self.search(facility=[f"Helipad {RUN_ID}"]))


# ---------- AC7: failures are shown as errors, not as "no matches" ----------


class SearchFailureTests(SearchTestCase):
    def assert_failed_without_results(self, response):
        self.assert_retryable_error(response)
        self.assertNotIn("venues", response.get_json())

    # TC-37-32 · AC7 — database unavailable during search.
    def test_database_unavailable_during_search(self):
        response = self.get_while_failing(SEARCH_URL, query_string={"min_capacity": 100})

        self.assert_failed_without_results(response)

    # TC-37-33 · AC4, AC7 — the availability check fails during a date and time search.
    def test_availability_check_failing_is_a_full_failure(self):
        for table in (VenueBooking.__tablename__, VenueBlock.__tablename__):
            with self.subTest(failing=table):
                response = self.get_while_failing(SEARCH_URL, table,
                                                  query_string=MORNING_15_OCT)

                self.assert_failed_without_results(response)

    # TC-37-34 · AC7 — retry with the same filters succeeds after recovery.
    def test_retry_succeeds_after_recovery(self):
        failed = self.get_while_failing(SEARCH_URL, query_string={"min_capacity": 100})
        self.assert_retryable_error(failed)

        self.assertEqual(self.found(min_capacity=100), [AURORA, HARBOUR, SUMMIT])


if __name__ == "__main__":
    unittest.main()
