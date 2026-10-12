"""Tests for SCRUM-78 "Reject Event Request" (addressing SCRUM-32).

Each test names the case it automates from
docs/test-cases/SCRUM-78-reject-event-request.md (TC-78-nn). Most of SCRUM-78's
acceptance criteria are already covered by tests/test_event_decisions.py (TC-32-nn)
and tests/test_decision_accountability.py (TC-60-nn); the cases here close the gaps
that document lists.

Endpoints are SCRUM-32's: POST /api/events/<id>/decision, GET /api/events/<id>/review,
GET /api/events/requests, and SCRUM-59's GET /api/events/mine. The DC-SEED rows and
helpers come from DecisionTestCase; R8 (under review) is added here.
"""

import unittest
from datetime import datetime

from app.models import Event
from tests.test_event_decisions import REASON, DecisionTestCase

# Every role other than coordinator, keyed to its seed user, plus coordinators who are
# not assigned to R1.
NOT_ALLOWED = {"admin": "admin", "organiser": "dana", "attendee": "farah",
               "venue_staff": "gus", "tech_staff": "hana",
               "another coordinator": "ben", "coordinator with no events": "chloe"}


class RejectTestCase(DecisionTestCase):
    def setUp(self):
        super().setUp()
        # R8: assigned to alice but under review, not submitted (SCRUM-78 AC1).
        self.requests["R8"] = Event(
            title="Spring Fair", status="under_review",
            organiser_id=self.users["dana"].id, coordinator_id=self.users["alice"].id,
            submitted_at=datetime(2026, 9, 24, 9, 0),
        )
        self.db.session.add(self.requests["R8"])
        self.db.session.commit()

    def listed(self, path, group, key, as_user="dana"):
        """The organiser's list item for `key` from GET `path`, inside `group`."""
        response = self.client.get(path, headers=self.auth_headers(self.users[as_user]))
        self.assertEqual(response.status_code, 200, response.get_json())
        return next((r for r in response.get_json()[group]
                     if r["id"] == self.requests[key].id), None)


# ---------- AC1: only a submitted request can be rejected ----------


class OnlySubmittedTests(RejectTestCase):
    # TC-78-01 · AC1 (A1) — a request under review cannot be rejected.
    def test_a_request_under_review_cannot_be_rejected(self):
        before = self.stored("R8")

        body = self.assert_error(self.decide("R8", "reject", reason=REASON), 409)

        self.assertIn("under_review", body["error"])
        self.assert_nothing_decided("R8", before)

    # TC-78-02 · AC1, AC4 — of all the statuses, only submitted becomes rejected.
    def test_only_a_submitted_request_becomes_rejected(self):
        results = {key: self.decide(key, "reject", reason=REASON).status_code
                   for key in ("R1", "R4", "R5", "R6", "R7", "R8")}

        self.assertEqual(results, {"R1": 200, "R4": 409, "R5": 409, "R6": 409,
                                   "R7": 409, "R8": 409})
        self.assertEqual({key: self.stored(key)["status"] for key in results}, {
            "R1": "rejected", "R4": "draft", "R5": "approved", "R6": "rejected",
            "R7": "cancelled", "R8": "under_review",
        })
        # The earlier rejection of R6 keeps its own reason.
        self.assertEqual(self.stored("R6")["decision_note"], "No licensed venue is available")


# ---------- AC2: only an Event Coordinator can reject ----------


class OnlyCoordinatorTests(RejectTestCase):
    # TC-78-03 · AC2 (A2) — no other role, and no other coordinator, can reject.
    def test_no_one_else_can_reject(self):
        before = self.stored("R1")
        for who, user in NOT_ALLOWED.items():
            with self.subTest(user=who):
                body = self.assert_error(self.decide("R1", "reject", reason=REASON, as_user=user),
                                         403)
                self.assertNotIn("Harbour Lights Festival", body["error"])
        self.assert_nothing_decided("R1", before)

    # TC-78-04 · AC2, AC3 — a refused user is told they may not reject, even with no reason.
    def test_permission_is_checked_before_the_reason(self):
        before = self.stored("R1")

        self.assert_error(self.decide("R1", "reject", reason="", as_user="dana"), 403)

        self.assert_nothing_decided("R1", before)


# ---------- AC5: the rejection reason is saved with the request ----------


class ReasonSavedTests(RejectTestCase):
    # TC-78-05 · AC4, AC5 — the reason is read back with the request, trimmed.
    def test_the_reason_is_saved_with_the_request(self):
        self.assertEqual(self.decide("R1", "reject", reason=f"  {REASON}\n").status_code, 200)

        response = self.review("R1")

        self.assertEqual(response.status_code, 200)
        saved = response.get_json()["request"]
        self.assertEqual((saved["status"], saved["decision_note"]), ("rejected", REASON))
        self.assertEqual(self.stored("R1")["decision_note"], REASON)

    # TC-78-06 · AC3, AC5 — a refused rejection saves no reason.
    def test_a_refused_rejection_saves_no_reason(self):
        self.assert_error(self.decide("R1", "reject", reason="   "), 400)

        stored = self.stored("R1")
        self.assertEqual((stored["status"], stored["decision_note"]), ("submitted", None))


# ---------- AC6: the organiser can view the rejected status and reason ----------


class OrganiserSeesRejectionTests(RejectTestCase):
    # TC-78-07 · AC4, AC6 — after rejection, both of the organiser's lists show it.
    def test_organiser_sees_the_rejection_on_both_lists(self):
        self.assertEqual(self.decide("R1", "reject", reason=REASON).status_code, 200)
        decided_at = self.stored("R1")["decided_at"].isoformat()
        alice = {"id": self.users["alice"].id, "email": self.users["alice"].email}

        for path, group in (("/api/events/requests", "requests"),
                            ("/api/events/mine", "submitted")):
            with self.subTest(list=path):
                r1 = self.listed(path, group, "R1")
                self.assertEqual(
                    (r1["status"], r1["decision_note"], r1["decided_at"], r1["decided_by"]),
                    ("rejected", REASON, decided_at, alice))

    # TC-78-08 · AC6 — another organiser sees neither the rejection nor its reason.
    def test_another_organiser_does_not_see_the_rejection(self):
        self.decide("R1", "reject", reason=REASON)

        for path, group in (("/api/events/requests", "requests"),
                            ("/api/events/mine", "submitted")):
            with self.subTest(list=path):
                response = self.client.get(path, headers=self.auth_headers(self.users["evan"]))
                self.assertNotIn(REASON, response.get_data(as_text=True))
                self.assertIsNone(self.listed(path, group, "R1", as_user="evan"))


if __name__ == "__main__":
    unittest.main()
