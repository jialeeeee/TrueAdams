"""SCRUM-70 AC11 and SCRUM-88 A11: clearing an event's safety decision, on plain values.

The rule in app/events/safety.py, without Flask or the database. The routes that use it
are tested in test_change_request_review.py (TC-70-33..36) and test_safety_cleared.py.
"""

import unittest
from datetime import datetime
from types import SimpleNamespace

from app.events import safety


def event(status="approved", decision="approved", **extra):
    return SimpleNamespace(
        status=status, safety_decision=decision,
        safety_decided_by_id=7 if decision else None,
        safety_comment="Exits checked." if decision else None,
        safety_decided_at=datetime(2026, 11, 1, 2, 0) if decision else None,
        confirmed_by_id=3 if status == "confirmed" else None,
        confirmed_at=datetime(2026, 11, 2, 2, 0) if status == "confirmed" else None, **extra)


class ClearSafetyDecisionTests(unittest.TestCase):
    def test_every_part_of_the_decision_is_cleared(self):
        for decision in ("approved", "rejected", "changes_requested"):
            with self.subTest(decision=decision):
                row = event(decision=decision)

                self.assertIs(safety.clear_safety_decision(row), True)

                for name in safety.SAFETY_DECISION_FIELDS:
                    self.assertIsNone(getattr(row, name), name)
                self.assertEqual(row.status, "approved")

    def test_a_confirmed_event_returns_to_planning_and_keeps_its_confirmation_record(self):
        row = event(status="confirmed")

        safety.clear_safety_decision(row)

        self.assertEqual(row.status, "approved")
        self.assertEqual((row.confirmed_by_id, row.confirmed_at),
                         (3, datetime(2026, 11, 2, 2, 0)))

    def test_with_no_decision_there_is_nothing_to_clear(self):
        row = event(decision=None)

        self.assertIs(safety.clear_safety_decision(row), False)
        self.assertEqual(row.status, "approved")

    def test_a_confirmed_event_with_no_decision_still_returns_to_planning(self):
        # Not reachable today (SCRUM-93 needs an approval), but a confirmed event is never
        # left confirmed once its arrangements have changed.
        row = event(status="confirmed", decision=None)

        self.assertIs(safety.clear_safety_decision(row), False)
        self.assertEqual(row.status, "approved")

    def test_other_statuses_are_left_alone(self):
        for status in ("submitted", "under_review", "rejected", "cancelled"):
            with self.subTest(status=status):
                row = event(status=status)
                safety.clear_safety_decision(row)
                self.assertEqual(row.status, status)
