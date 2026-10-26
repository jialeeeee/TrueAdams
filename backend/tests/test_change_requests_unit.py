"""SCRUM-46: the change request rules on plain objects (no app, no database).

See docs/test-cases/SCRUM-46-change-request.md, A2-A4 and A7. The event is a plain
object with the five fields an organiser can ask to change.
"""

import unittest
from datetime import datetime
from types import SimpleNamespace


def _rules():
    # Imported here so the tests fail on behaviour, not on import, until it exists.
    from app.events import change_requests

    return change_requests


def gala(**overrides):
    fields = {"start_time": datetime(2026, 12, 5, 18, 0), "end_time": datetime(2026, 12, 5, 23, 0),
              "expected_attendance": 200, "venue_requirements": "Ballroom for 200",
              "equipment_requirements": "2 wireless microphones"}
    return SimpleNamespace(**{**fields, **overrides})


class ProposalRuleTests(unittest.TestCase):
    def parse(self, body, event=None):
        return _rules().parse_proposal(event or gala(), body)

    def test_every_permitted_field_can_change_in_field_order(self):  # A2, A7
        changes, problems = self.parse({
            "equipment_requirements": "4 wireless microphones", "expected_attendance": 250,
            "venue_requirements": "Ballroom for 250", "end_time": "2026-12-06T23:30",
            "start_time": "2026-12-06T18:00"})

        self.assertEqual(problems, {})
        self.assertEqual(list(changes), ["start_time", "end_time", "expected_attendance",
                                         "venue_requirements", "equipment_requirements"])
        self.assertEqual(changes["start_time"], {"from": datetime(2026, 12, 5, 18, 0),
                                                 "to": datetime(2026, 12, 6, 18, 0)})
        self.assertEqual(changes["expected_attendance"], {"from": 200, "to": 250})

    def test_unchanged_values_are_ignored(self):  # A3
        changes, problems = self.parse({"start_time": "2026-12-05T18:00:00",
                                        "venue_requirements": " Ballroom for 200 ",
                                        "expected_attendance": 250})

        self.assertEqual(problems, {})
        self.assertEqual(list(changes), ["expected_attendance"])

    def test_nothing_to_change_gives_no_changes_and_no_problems(self):  # A3
        self.assertEqual(self.parse({}), ({}, {}))
        self.assertEqual(self.parse({"expected_attendance": 200}), ({}, {}))

    def test_other_fields_are_disallowed(self):  # A2
        _, problems = self.parse({"title": "New name", "venue_id": 3,
                                  "registration_required": False, "expected_attendance": 250})

        self.assertEqual(set(problems), {"title", "venue_id", "registration_required"})
        self.assertIn("can't be changed through a change request", problems["venue_id"])

    def test_attendance_must_be_a_whole_number_of_at_least_one(self):  # A4
        for value in (-5, 0, 1.5, "250", True, None):
            with self.subTest(value=value):
                _, problems = self.parse({"expected_attendance": value})
                self.assertIn("whole number of at least 1", problems["expected_attendance"])
        self.assertEqual(self.parse({"expected_attendance": 1})[1], {})

    def test_times_must_be_valid_dates_and_times(self):  # A4
        for value in ("next Friday", "2026-02-30T10:00", "2026-12-06", 20261206, None, ""):
            with self.subTest(value=value):
                _, problems = self.parse({"start_time": value})
                self.assertIn("valid date and time", problems["start_time"])

    def test_the_end_must_be_after_the_start(self):  # A4
        for body in ({"start_time": "2026-12-06T18:00", "end_time": "2026-12-06T17:00"},
                     {"start_time": "2026-12-06T18:00", "end_time": "2026-12-06T18:00"},
                     {"end_time": "2026-12-05T17:00"}):
            with self.subTest(body=body):
                changes, problems = self.parse(body)
                self.assertEqual(problems, {"end_time": "The end must be after the start."})

    def test_a_new_start_must_be_before_the_current_end(self):  # A4
        _, problems = self.parse({"start_time": "2026-12-06T09:00"})

        self.assertIn("before the end", problems["start_time"])
        self.assertIn("2026-12-05 23:00", problems["start_time"])

    def test_venue_requirements_cannot_be_blank_but_equipment_can(self):  # A4
        _, problems = self.parse({"venue_requirements": "   "})
        self.assertIn("can't be blank", problems["venue_requirements"])

        changes, problems = self.parse({"equipment_requirements": ""})
        self.assertEqual(problems, {})
        self.assertEqual(changes["equipment_requirements"],
                         {"from": "2 wireless microphones", "to": None})

    def test_text_must_be_text_and_not_too_long(self):  # A4
        limit = _rules().TEXT_MAX_LENGTH
        _, problems = self.parse({"venue_requirements": "x" * (limit + 1),
                                  "equipment_requirements": ["Projector"]})

        self.assertIn(f"{limit} characters", problems["venue_requirements"])
        self.assertIn("must be text", problems["equipment_requirements"])
        self.assertEqual(self.parse({"venue_requirements": "x" * limit})[1], {})

    def test_every_problem_is_named_at_once(self):  # A4
        _, problems = self.parse({"expected_attendance": -5, "venue_requirements": "",
                                  "title": "New name"})

        self.assertEqual(set(problems), {"expected_attendance", "venue_requirements", "title"})

    def test_changes_are_stored_as_json(self):  # A7
        changes, _ = self.parse({"start_time": "2026-12-06T18:00", "expected_attendance": 250})

        self.assertEqual(_rules().as_json(changes), {
            "start_time": {"from": "2026-12-05T18:00:00", "to": "2026-12-06T18:00:00"},
            "expected_attendance": {"from": 200, "to": 250}})


class DescriptionRuleTests(unittest.TestCase):
    def test_the_changes_are_described_with_labels_and_both_values(self):  # A8
        rules = _rules()
        changes, _ = rules.parse_proposal(gala(), {"start_time": "2026-12-06T18:00",
                                                   "expected_attendance": 250,
                                                   "equipment_requirements": ""})

        self.assertEqual(rules.describe(changes),
                         "Start: 2026-12-05 18:00 → 2026-12-06 18:00; "
                         "Expected attendance: 200 → 250; "
                         "Equipment requirements: 2 wireless microphones → none")

    def test_the_status_is_shown_as_pending_review(self):  # AC6
        rules = _rules()
        self.assertEqual(rules.STATUS_LABELS[rules.PENDING_REVIEW], "Pending Review")


if __name__ == "__main__":
    unittest.main()
