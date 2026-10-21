"""Tests for SCRUM-38 "Assess a Venue Against Event Requirements".

Each test names the case it automates from the "Sprint 3 test cases" sheet
(IS212-US38-TCnn) and docs/test-cases/SCRUM-38-assess-venue-against-event.md.

Model (db/event_requirements.sql), new nullable Event columns (NULL = not recorded)
    required_facilities, required_accessibility_features, required_layouts   JSON list of str
They can be saved through PATCH /api/events/<id> like the other normal planning fields.

Endpoint (JWT required, else 401)
    GET /api/events/<id>/venue-suitability?venue_id=<n>
        200 {"event": {"id", "title"}, "venue": {"id", "name"},
             "checks": [{"requirement": "attendance" | "facility" | "accessibility" | "layout",
                         "item": str | null, "label", "status", "detail"}, ...],
             "overall": "meets" | "does_not_meet" | "unable_to_assess", "summary": str}
            status: "match" | "mismatch" | "unable_to_assess" | "not_required"
        400 {"error", "fields": {"venue_id"}}   venue not chosen / not a number
        403 not the event's coordinator   404 unknown event or venue
        503 {"error", "retryable": true}  the check could not be completed
    Read-only: nothing is booked, requested or changed.
"""

import unittest

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app.models import Event, VenueBooking
from tests.base import AppTestCase

FACILITIES = ["Projector", "Microphone"]


class SuitabilityTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.alice = self.make_user("coord_alice@test.example", role="coordinator")
        self.organiser = self.make_user("org@test.example", role="organiser")
        # V-101 Orchard Hall; V-102 Marina Room; V-103 Harbour Room (layouts not recorded).
        self.v101 = self.make_venue("Orchard Hall", 120)
        self.v101.facilities = ["Projector", "Microphone"]
        self.v101.accessibility_features = ["Wheelchair ramp"]
        self.v101.room_layouts = ["theatre", "classroom"]
        self.v102 = self.make_venue("Marina Room", 50)
        self.v102.facilities = ["Microphone"]
        self.v102.accessibility_features = []
        self.v102.room_layouts = ["boardroom"]
        self.v103 = self.make_venue("Harbour Room", 60)
        self.v103.facilities = ["Projector"]
        self.v103.accessibility_features = ["Wheelchair ramp"]
        self.v103.room_layouts = None
        self.db.session.commit()

    def event(self, attendance=80, facilities=("Projector",), accessibility=("Wheelchair ramp",),
              layouts=("theatre",), title="E-401", coordinator=None, status="approved"):
        return self.make_event(
            self.organiser, title=title, status=status, expected_attendance=attendance,
            coordinator_id=(coordinator or self.alice).id,
            required_facilities=None if facilities is None else list(facilities),
            required_accessibility_features=None if accessibility is None else list(accessibility),
            required_layouts=None if layouts is None else list(layouts))

    def check(self, event, venue=None, user=None, **query):
        if venue is not None:
            query["venue_id"] = venue.id
        return self.client.get(
            f"/api/events/{event.id}/venue-suitability", query_string=query,
            headers=self.auth_headers(user or self.alice))

    def result(self, event, venue):
        response = self.check(event, venue)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def lines(self, result):
        return {(c["requirement"], c["item"]): c["status"] for c in result["checks"]}


class RunCheckTests(SuitabilityTestCase):
    def test_tc1_one_line_each_for_attendance_facility_accessibility_and_layout(self):  # AC1
        result = self.result(self.event(), self.v101)
        self.assertEqual(result["event"], {"id": result["event"]["id"], "title": "E-401"})
        self.assertEqual(result["venue"]["name"], "Orchard Hall")
        self.assertEqual(self.lines(result), {
            ("attendance", None): "match", ("facility", "Projector"): "match",
            ("accessibility", "Wheelchair ramp"): "match", ("layout", "theatre"): "match"})
        for check in result["checks"]:
            self.assertTrue(check["label"] and check["detail"])

    def test_tc2_a_venue_must_be_chosen(self):  # AC1
        for query in ({}, {"venue_id": ""}, {"venue_id": "abc"}):
            response = self.check(self.event(), **query)
            self.assertEqual(response.status_code, 400, query)
            self.assertIn("venue_id", response.get_json()["fields"])
        self.assertEqual(self.check(self.event(), venue_id=99999999).status_code, 404)

    def test_tc3_uses_the_latest_saved_event_information(self):  # AC1
        event = self.event(attendance=80)
        self.assertEqual(self.lines(self.result(event, self.v101))[("attendance", None)], "match")
        event.expected_attendance = 130
        self.db.session.commit()
        self.assertEqual(self.lines(self.result(event, self.v101))[("attendance", None)], "mismatch")

    def test_uses_the_latest_saved_venue_information(self):  # AC1
        event = self.event(facilities=("Projector",))
        self.assertEqual(self.lines(self.result(event, self.v101))[("facility", "Projector")], "match")
        self.v101.facilities = ["Microphone"]
        self.db.session.commit()
        self.assertEqual(
            self.lines(self.result(event, self.v101))[("facility", "Projector")], "mismatch")


class AttendanceTests(SuitabilityTestCase):
    def test_tc4_one_above_the_capacity_is_a_mismatch(self):  # AC2
        result = self.result(self.event(121), self.v101)
        check = [c for c in result["checks"] if c["requirement"] == "attendance"][0]
        self.assertEqual(check["status"], "mismatch")
        self.assertIn("121", check["detail"])
        self.assertIn("120", check["detail"])

    def test_tc5_equal_to_the_capacity_is_a_match(self):  # AC2
        self.assertEqual(self.lines(self.result(self.event(120), self.v101))[("attendance", None)],
                         "match")

    def test_below_the_capacity_is_a_match(self):  # AC2
        self.assertEqual(self.lines(self.result(self.event(1), self.v101))[("attendance", None)],
                         "match")


class RequirementTests(SuitabilityTestCase):
    def test_tc6_a_facility_the_venue_lacks_is_a_mismatch(self):  # AC3
        event = self.event(facilities=("Video conferencing",))
        self.assertEqual(self.lines(self.result(event, self.v101))[("facility", "Video conferencing")],
                         "mismatch")

    def test_tc7_an_accessibility_feature_the_venue_lacks_is_a_mismatch(self):  # AC3
        event = self.event(accessibility=("Hearing loop",))
        self.assertEqual(self.lines(self.result(event, self.v101))[("accessibility", "Hearing loop")],
                         "mismatch")

    def test_tc8_a_layout_the_venue_does_not_support_is_a_mismatch(self):  # AC3
        event = self.event(layouts=("banquet",))
        self.assertEqual(self.lines(self.result(event, self.v101))[("layout", "banquet")], "mismatch")

    def test_matching_ignores_case_and_spacing(self):  # AC3
        event = self.event(facilities=(" projector ",), layouts=("THEATRE",))
        lines = self.lines(self.result(event, self.v101))
        self.assertEqual(lines[("facility", "projector")], "match")
        self.assertEqual(lines[("layout", "THEATRE")], "match")

    def test_tc9_matches_and_mismatches_are_listed_separately_and_labelled(self):  # AC4
        event = self.event(facilities=("Video conferencing",), accessibility=(), layouts=("theatre",))
        result = self.result(event, self.v101)
        statuses = {c["label"]: c["status"] for c in result["checks"]}
        self.assertEqual(len(statuses), len(result["checks"]), "labels are distinct")
        self.assertEqual(statuses["Attendance"], "match")
        self.assertEqual(statuses["Layout: theatre"], "match")
        self.assertEqual(statuses["Facility: Video conferencing"], "mismatch")
        self.assertEqual(result["overall"], "does_not_meet")

    def test_a_category_with_nothing_required_is_not_required(self):  # AC3
        event = self.event(40, facilities=(), accessibility=(), layouts=())
        result = self.result(event, self.v102)
        self.assertEqual(self.lines(result), {
            ("attendance", None): "match", ("facility", None): "not_required",
            ("accessibility", None): "not_required", ("layout", None): "not_required"})
        self.assertEqual(result["overall"], "meets")


class UnableToAssessTests(SuitabilityTestCase):
    def test_tc10_missing_attendance_is_unable_to_assess(self):  # AC5
        event = self.event(attendance=None, accessibility=(), layouts=())
        line = self.lines(self.result(event, self.v101))[("attendance", None)]
        self.assertEqual(line, "unable_to_assess")

    def test_missing_venue_capacity_is_unable_to_assess(self):  # AC5
        self.v101.capacity = None
        self.db.session.commit()
        self.assertEqual(self.lines(self.result(self.event(), self.v101))[("attendance", None)],
                         "unable_to_assess")

    def test_tc11_layouts_not_recorded_at_the_venue_is_unable_to_assess(self):  # AC5
        event = self.event(attendance=40, layouts=("theatre",))
        self.assertEqual(self.lines(self.result(event, self.v103))[("layout", "theatre")],
                         "unable_to_assess")

    def test_a_recorded_empty_layout_list_is_a_mismatch_not_unrecorded(self):  # AC5 (open question)
        self.v103.room_layouts = []
        self.db.session.commit()
        event = self.event(layouts=("theatre",))
        self.assertEqual(self.lines(self.result(event, self.v103))[("layout", "theatre")],
                         "mismatch")

    def test_venue_facilities_and_accessibility_not_recorded_are_unable_to_assess(self):  # AC5
        self.v101.facilities = None
        self.v101.accessibility_features = None
        self.db.session.commit()
        lines = self.lines(self.result(self.event(), self.v101))
        self.assertEqual(lines[("facility", "Projector")], "unable_to_assess")
        self.assertEqual(lines[("accessibility", "Wheelchair ramp")], "unable_to_assess")

    def test_event_requirements_not_recorded_are_unable_to_assess(self):  # AC5
        event = self.event(facilities=None, accessibility=None, layouts=None)
        lines = self.lines(self.result(event, self.v101))
        self.assertEqual(lines[("facility", None)], "unable_to_assess")
        self.assertEqual(lines[("accessibility", None)], "unable_to_assess")
        self.assertEqual(lines[("layout", None)], "unable_to_assess")

    def test_tc12_an_unassessed_requirement_stops_the_venue_meeting_the_requirements(self):  # AC5
        event = self.event(attendance=None)
        result = self.result(event, self.v101)
        self.assertEqual(result["overall"], "unable_to_assess")
        self.assertNotIn("meets the checked requirements", result["summary"])
        self.assertIn("could not be assessed", result["summary"])

    def test_a_mismatch_outweighs_an_unassessed_requirement(self):  # AC5
        event = self.event(attendance=None, facilities=("Video conferencing",))
        self.assertEqual(self.result(event, self.v101)["overall"], "does_not_meet")


class OverallResultTests(SuitabilityTestCase):
    def test_tc13_passing_every_check_meets_the_checked_requirements(self):  # AC6
        result = self.result(self.event(), self.v101)
        self.assertTrue(all(c["status"] == "match" for c in result["checks"]))
        self.assertEqual(result["overall"], "meets")
        self.assertIn("meets the checked requirements", result["summary"])

    def test_tc14_a_passing_result_does_not_claim_or_create_a_booking(self):  # AC6
        event = self.event()
        status = event.status
        result = self.result(event, self.v101)
        text = str(result).lower()
        for word in ("booked", "confirmed", "approved", "reserved"):
            self.assertNotIn(word, text)
        self.db.session.expire_all()
        self.assertEqual(VenueBooking.query.filter_by(event_id=event.id).count(), 0)
        self.assertEqual(self.db.session.get(Event, event.id).status, status)
        self.assertIsNone(self.db.session.get(Event, event.id).venue_id)

    def test_summary_for_a_mismatch(self):  # AC4
        result = self.result(self.event(121), self.v101)
        self.assertEqual(result["overall"], "does_not_meet")
        self.assertIn("does not meet", result["summary"])


class AccessAndFailureTests(SuitabilityTestCase):
    def test_login_is_required(self):
        event = self.event()
        response = self.client.get(f"/api/events/{event.id}/venue-suitability?venue_id={self.v101.id}")
        self.assertEqual(response.status_code, 401)

    def test_unknown_event_is_404(self):
        response = self.client.get(
            f"/api/events/{self.missing_id(Event)}/venue-suitability?venue_id={self.v101.id}",
            headers=self.auth_headers(self.alice))
        self.assertEqual(response.status_code, 404)

    def test_only_the_events_coordinator_can_run_the_check(self):
        event = self.event()
        other = self.make_user("coord_ben@test.example", role="coordinator")
        for user in (other, self.organiser, self.make_user("vs@test.example", role="venue_staff")):
            self.assertEqual(self.check(event, self.v101, user=user).status_code, 403, user.role)

    def test_database_failure_is_a_retryable_error_not_a_result(self):
        event = self.event()
        headers = self.auth_headers(self.alice)
        url = f"/api/events/{event.id}/venue-suitability?venue_id={self.v101.id}"

        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith(("SELECT",)) and "venues" in statement:
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        self.db.session.expire_all()
        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            response = self.client.get(url, headers=headers)
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.get_json()["retryable"])
        self.assertNotIn("checks", response.get_json())


class SavingRequirementsTests(SuitabilityTestCase):
    def patch_event(self, event, body):
        return self.client.patch(f"/api/events/{event.id}", json=body,
                                 headers=self.auth_headers(self.alice))

    def test_requirement_lists_can_be_saved_and_cleared(self):
        event = self.event(facilities=None, accessibility=None, layouts=None)
        response = self.patch_event(event, {
            "required_facilities": ["Projector", " Microphone "],
            "required_accessibility_features": [], "required_layouts": ["theatre"]})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.db.session.expire_all()
        saved = self.db.session.get(Event, event.id)
        self.assertEqual(saved.required_facilities, ["Projector", "Microphone"])
        self.assertEqual(saved.required_accessibility_features, [])
        self.assertEqual(saved.required_layouts, ["theatre"])
        self.assertEqual(self.patch_event(event, {"required_layouts": None}).status_code, 200)
        self.db.session.expire_all()
        self.assertIsNone(self.db.session.get(Event, event.id).required_layouts)

    def test_invalid_requirement_lists_are_refused(self):
        event = self.event()
        for bad in ("Projector", [1], [""], ["x" * 101], ["a"] * 21, {"a": 1}):
            response = self.patch_event(event, {"required_facilities": bad})
            self.assertEqual(response.status_code, 422, bad)
            self.assertIn("required_facilities", response.get_json()["fields"])


if __name__ == "__main__":
    unittest.main()
