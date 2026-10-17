"""SCRUM-27 TC-27-01..05: pure production rules, no app, credentials or network.

Load the standalone production module without app/__init__.py, which otherwise
imports Flask, SQLAlchemy and environment configuration. No test-only rules.
Run: python -B -m unittest -v tests.test_authorization_unit
Persistence and API workflows remain in tests/test_authorization.py.
"""

import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace

rules = runpy.run_path(Path(__file__).parents[1] / "app" / "events" / "permissions.py")


class EventPermissionTests(unittest.TestCase):
    def setUp(self):
        self.event = SimpleNamespace(organiser_id=1, coordinator_id=2)

    def user(self, role, user_id=3):
        return SimpleNamespace(id=user_id, role=role)

    # SCRUM-82: only Event Coordinator Leads reassign; the event's current coordinator
    # and the former admin override are refused.
    def test_only_leads_can_reassign(self):
        self.assertTrue(rules["is_coordinator_lead"](self.user("coordinator_lead")))
        for role in ("coordinator", "admin", "organiser", "attendee", "venue_staff",
                     "tech_staff", "unknown"):
            with self.subTest(role=role):
                self.assertFalse(rules["is_coordinator_lead"](self.user(role, 2)))
        self.assertFalse(rules["is_coordinator_lead"](None))

    def test_unrelated_coordinator_cannot_reassign_or_self_assign(self):
        self.assertFalse(rules["is_coordinator_lead"](self.user("coordinator")))
        self.assertEqual(self.event.coordinator_id, 2)

    # SCRUM-82: no non-Lead may; a Lead is sent to the SCRUM-81 queue by the route (409).
    def test_unassigned_event_has_no_manual_initial_assignment(self):
        self.event.coordinator_id = None
        for role in ("coordinator", "admin", "organiser", "attendee", "venue_staff", "tech_staff"):
            with self.subTest(role=role):
                self.assertFalse(rules["is_coordinator_lead"](self.user(role)))

    def test_event_access_moves_to_new_coordinator(self):
        previous, replacement = self.user("coordinator", 2), self.user("coordinator", 3)
        self.assertTrue(rules["is_current_coordinator"](previous, self.event))
        self.assertFalse(rules["is_current_coordinator"](replacement, self.event))
        self.event.coordinator_id = replacement.id
        for rule in ("is_current_coordinator", "can_view_clarifications"):
            with self.subTest(rule=rule):
                self.assertFalse(rules[rule](previous, self.event))
                self.assertTrue(rules[rule](replacement, self.event))

    def test_assigned_identity_alone_does_not_grant_coordinator_privileges(self):
        for role in ("admin", "organiser", "attendee", "venue_staff", "tech_staff", "unknown"):
            with self.subTest(role=role):
                self.assertFalse(rules["is_current_coordinator"](self.user(role, 2), self.event))

    def test_owner_must_still_be_an_organiser(self):
        self.assertTrue(rules["is_current_organiser"](self.user("organiser", 1), self.event))
        for role in ("coordinator", "venue_staff", "tech_staff", "attendee", "admin", "unknown"):
            with self.subTest(role=role):
                former_owner = self.user(role, 1)
                self.assertFalse(rules["is_current_organiser"](former_owner, self.event))
                self.assertFalse(rules["can_view_clarifications"](former_owner, self.event))

    def test_new_role_preserves_its_legitimate_coordinator_information_access(self):
        for role in ("coordinator", "venue_staff", "tech_staff", "admin"):
            with self.subTest(role=role):
                self.assertTrue(rules["can_view_coordinator"](self.user(role, 1), self.event))
        self.assertFalse(rules["can_view_coordinator"](self.user("attendee", 1), self.event))

    def test_unrelated_organiser_and_attendee_cannot_read_internal_information(self):
        for role in ("organiser", "attendee", "unknown"):
            for rule in ("is_current_organiser", "can_view_coordinator", "can_view_clarifications"):
                with self.subTest(role=role, rule=rule):
                    self.assertFalse(rules[rule](self.user(role), self.event))

    def test_missing_user_is_denied(self):
        for name, rule in rules.items():
            if name.startswith(("is_current_", "can_")):
                with self.subTest(rule=name):
                    self.assertFalse(rule(None, self.event))


if __name__ == "__main__":
    unittest.main()
