"""Tests for SCRUM-77 "Approve Event Request" (addressing SCRUM-32).

Each test names the case it automates from
docs/test-cases/SCRUM-77-approve-event-request.md (TC-77-nn). Most of SCRUM-77's
acceptance criteria are already covered by tests/test_event_decisions.py (TC-32-nn);
the cases here close the gaps that document lists.

Endpoints are SCRUM-32's: POST /api/events/<id>/decision, GET /api/events/requests,
and SCRUM-59's GET /api/events/mine. The DC-SEED rows and helpers come from
DecisionTestCase; R8 (under review) is added here.
"""

import unittest
from datetime import datetime

from app.models import Event
from tests.test_event_decisions import DecisionTestCase

# Every role other than coordinator, keyed to its seed user.
NON_COORDINATORS = {"admin": "admin", "organiser": "dana", "attendee": "farah",
                    "venue_staff": "gus", "tech_staff": "hana"}


class ApproveTestCase(DecisionTestCase):
    def setUp(self):
        super().setUp()
        # R8: assigned to alice but under review, not submitted (SCRUM-77 AC1).
        self.requests["R8"] = Event(
            title="Spring Fair", status="under_review",
            organiser_id=self.users["dana"].id, coordinator_id=self.users["alice"].id,
            submitted_at=datetime(2026, 9, 24, 9, 0),
        )
        self.db.session.add(self.requests["R8"])
        self.db.session.commit()

    def listed(self, path, group, key):
        """The organiser's list item for `key` from GET `path`, inside `group`."""
        response = self.client.get(path, headers=self.auth_headers(self.users["dana"]))
        self.assertEqual(response.status_code, 200, response.get_json())
        return next(r for r in response.get_json()[group] if r["id"] == self.requests[key].id)


# ---------- AC1: only a submitted request can be approved ----------


class OnlySubmittedTests(ApproveTestCase):
    # TC-77-01 · AC1 (A1) — a request under review cannot be approved.
    def test_a_request_under_review_cannot_be_approved(self):
        before = self.stored("R8")

        body = self.assert_error(self.decide("R8", "approve"), 409)

        self.assertIn("under_review", body["error"])
        self.assert_nothing_decided("R8", before)

    # TC-77-02 · AC1, AC3 — of all the statuses, only submitted becomes approved.
    def test_only_a_submitted_request_becomes_approved(self):
        results = {key: self.decide(key, "approve").status_code
                   for key in ("R1", "R4", "R5", "R6", "R7", "R8")}

        self.assertEqual(results, {"R1": 200, "R4": 409, "R5": 409, "R6": 409,
                                   "R7": 409, "R8": 409})
        self.assertEqual({key: self.stored(key)["status"] for key in results}, {
            "R1": "approved", "R4": "draft", "R5": "approved", "R6": "rejected",
            "R7": "cancelled", "R8": "under_review",
        })


# ---------- AC2: only an Event Coordinator can approve ----------


class OnlyCoordinatorTests(ApproveTestCase):
    # TC-77-03 · AC2 (A2) — no other role can approve, even with the event's ID.
    def test_no_other_role_can_approve(self):
        before = self.stored("R1")
        for role, user in NON_COORDINATORS.items():
            with self.subTest(role=role):
                body = self.assert_error(self.decide("R1", "approve", as_user=user), 403)
                self.assertNotIn("Harbour Lights Festival", body["error"])
        self.assert_nothing_decided("R1", before)


# ---------- AC4: the organiser can view the approved status ----------


class OrganiserSeesApprovalTests(ApproveTestCase):
    # TC-77-04 · AC3, AC4 — after approval, both of the organiser's lists show Approved.
    def test_organiser_sees_the_approval_on_both_lists(self):
        self.assertEqual(self.decide("R1", "approve").status_code, 200)
        decided_at = self.stored("R1")["decided_at"].isoformat()
        alice = {"id": self.users["alice"].id, "email": self.users["alice"].email}

        for path, group in (("/api/events/requests", "requests"),
                            ("/api/events/mine", "submitted")):
            with self.subTest(list=path):
                r1 = self.listed(path, group, "R1")
                self.assertEqual(
                    (r1["status"], r1["decided_at"], r1["decided_by"], r1["decision_note"]),
                    ("approved", decided_at, alice, None))

    # TC-77-05 · AC4 — an approval note is shown to the organiser with the status.
    def test_organiser_sees_the_approval_note(self):
        self.decide("R1", "approve", reason="Please book the venue by 1 Nov.")

        r1 = self.listed("/api/events/mine", "submitted", "R1")

        self.assertEqual((r1["status"], r1["decision_note"]),
                         ("approved", "Please book the venue by 1 Nov."))

    # TC-77-06 · AC4 — another organiser cannot see the approval.
    def test_another_organiser_does_not_see_the_approval(self):
        self.decide("R1", "approve")

        for path, group in (("/api/events/requests", "requests"),
                            ("/api/events/mine", "submitted")):
            with self.subTest(list=path):
                response = self.client.get(path, headers=self.auth_headers(self.users["evan"]))
                ids = [r["id"] for r in response.get_json()[group]]
                self.assertNotIn(self.requests["R1"].id, ids)


if __name__ == "__main__":
    unittest.main()
