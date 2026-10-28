"""SCRUM-70: the review rules on plain values, without Flask or the database.

What a change affects (A3), what a decision must contain (A4, A5) and the values an
accepted request applies (A6), in docs/test-cases/SCRUM-70-review-change-request.md.
"""

import unittest
from datetime import datetime

NOW = datetime(2026, 10, 28, 12, 0)
TIMES = {"start_time": {"from": "2026-12-05T18:00:00", "to": "2026-12-06T18:00:00"},
         "end_time": {"from": "2026-12-05T23:00:00", "to": "2026-12-06T23:30:00"}}


def _review():
    # Imported here so the tests fail on behaviour, not on import, until it exists.
    from app.events import change_review

    return change_review


def booking(booking_id, status="confirmed", capacity=220, name="Grand Ballroom",
            hold_expires_at=None):
    return {"id": booking_id, "venue": {"id": booking_id * 10, "name": name, "capacity": capacity},
            "start_time": datetime(2026, 12, 5, 18, 0), "end_time": datetime(2026, 12, 5, 23, 0),
            "status": status, "hold_expires_at": hold_expires_at}


def requirement(requirement_id, reserved=0, equipment_type="Wireless microphone"):
    return {"id": requirement_id, "equipment_type": equipment_type, "quantity": 2,
            "reserved": reserved}


def registration(registered=0, capacity=None, closes_at=None):
    return {"registered": registered, "capacity": capacity, "closes_at": closes_at}


class ImpactRuleTests(unittest.TestCase):
    def impact(self, changes, bookings=(), equipment=(), registered=None):
        return _review().impact(changes, list(bookings), list(equipment),
                                registered or registration(), NOW)

    def test_new_times_affect_every_live_booking(self):
        bookings = [booking(1), booking(2, "pending"),
                    booking(3, "tentative", hold_expires_at=datetime(2026, 11, 30, 12, 0)),
                    booking(4, "tentative", hold_expires_at=datetime(2026, 10, 1, 12, 0)),
                    booking(5, "rejected"), booking(6, "cancelled")]

        impact = self.impact(TIMES, bookings)

        self.assertEqual([item["id"] for item in impact["venue_bookings"]], [1, 2, 3])
        first = impact["venue_bookings"][0]
        self.assertEqual((first["venue"], first["start_time"], first["status"]),
                         ({"id": 10, "name": "Grand Ballroom"}, "2026-12-05T18:00:00", "confirmed"))
        self.assertIn("isn't moved", first["reasons"][0])

    def test_new_times_release_reserved_equipment_only(self):
        impact = self.impact(TIMES, equipment=[requirement(1, reserved=2), requirement(2)])

        self.assertEqual([(item["id"], item["reserved"]) for item in impact["equipment"]], [(1, 2)])
        self.assertIn("2 reserved", impact["equipment"][0]["reasons"][0])
        self.assertIn("released", impact["equipment"][0]["reasons"][0])

    def test_new_times_tell_registered_attendees(self):
        for registered, text in ((1, "1 registered attendee will"), (3, "3 registered attendees will")):
            with self.subTest(registered=registered):
                impact = self.impact(TIMES, registered=registration(registered))
                self.assertEqual(len(impact["registrations"]["reasons"]), 1)
                self.assertIn(text, impact["registrations"]["reasons"][0])
        self.assertEqual(self.impact(TIMES)["registrations"]["reasons"], [])

    def test_registration_closing_after_the_new_start_is_listed(self):
        changes = {"start_time": {"from": "2026-12-05T18:00:00", "to": "2026-11-30T18:00:00"}}

        late = self.impact(changes, registered=registration(closes_at=datetime(2026, 12, 1, 12, 0)))
        early = self.impact(changes, registered=registration(closes_at=datetime(2026, 11, 30, 18, 0)))

        self.assertEqual(len(late["registrations"]["reasons"]), 1)
        self.assertIn("2026-12-01 12:00", late["registrations"]["reasons"][0])
        self.assertIn("2026-11-30 18:00", late["registrations"]["reasons"][0])
        self.assertEqual(early["registrations"]["reasons"], [])

    def test_more_people_than_a_venue_holds(self):
        changes = {"expected_attendance": {"from": 200, "to": 250}}
        bookings = [booking(1, capacity=250), booking(2, capacity=249), booking(3, capacity=None)]

        impact = self.impact(changes, bookings, [requirement(1, reserved=2)])

        self.assertEqual([item["id"] for item in impact["venue_bookings"]], [2])
        self.assertIn("holds 249 people", impact["venue_bookings"][0]["reasons"][0])
        self.assertEqual(impact["equipment"], [])

    def test_fewer_people_than_registered_or_places_set(self):
        changes = {"expected_attendance": {"from": 200, "to": 100}}

        above = self.impact(changes, registered=registration(101, capacity=150))
        within = self.impact(changes, registered=registration(100, capacity=100))

        reasons = " ".join(above["registrations"]["reasons"])
        self.assertIn("101 people are already registered", reasons)
        self.assertIn("150 places", reasons)
        self.assertEqual(within["registrations"]["reasons"], [])

    def test_new_venue_requirements_affect_live_bookings(self):
        changes = {"venue_requirements": {"from": "Ballroom", "to": "Ballroom and breakout"}}

        impact = self.impact(changes, [booking(1), booking(2, "rejected")], [requirement(1, 2)])

        self.assertEqual([item["id"] for item in impact["venue_bookings"]], [1])
        self.assertIn("venue requirements", impact["venue_bookings"][0]["reasons"][0])
        self.assertEqual(impact["equipment"], [])

    def test_new_equipment_requirements_affect_every_recorded_requirement(self):
        changes = {"equipment_requirements": {"from": "2 microphones", "to": "4 microphones"}}

        impact = self.impact(changes, [booking(1)], [requirement(1, 2), requirement(2)])

        self.assertEqual(impact["venue_bookings"], [])
        self.assertEqual([item["id"] for item in impact["equipment"]], [1, 2])
        self.assertIn("equipment requirements", impact["equipment"][1]["reasons"][0])

    def test_reasons_add_up_when_several_fields_change(self):
        changes = {**TIMES, "expected_attendance": {"from": 200, "to": 250}}

        [item] = self.impact(changes, [booking(1, capacity=220)])["venue_bookings"]

        self.assertEqual(len(item["reasons"]), 2)

    def test_nothing_affected_says_so(self):
        impact = self.impact({"expected_attendance": {"from": 200, "to": 210}}, [booking(1)],
                             [requirement(1)], registration(5, capacity=210))

        self.assertEqual((impact["venue_bookings"], impact["equipment"]), ([], []))
        self.assertEqual(impact["registrations"]["reasons"], [])
        self.assertIs(impact["affected"], False)
        self.assertTrue(impact["message"].startswith("Nothing"))
        self.assertIsNone(self.impact(TIMES, [booking(1)])["message"])


class DecisionRuleTests(unittest.TestCase):
    def parse(self, body):
        return _review().parse_decision(body)

    def refused(self, body):
        with self.assertRaises(_review().Refused) as caught:
            self.parse(body)
        return caught.exception

    def test_accept_and_reject(self):
        self.assertEqual(self.parse({"decision": "accept"}), ("accepted", None))
        self.assertEqual(self.parse({"decision": "reject", "reason": "  Too big.  "}),
                         ("rejected", "Too big."))

    def test_a_reason_sent_with_an_acceptance_is_ignored(self):
        self.assertEqual(self.parse({"decision": "accept", "reason": "Fine."}), ("accepted", None))

    def test_the_decision_must_be_accept_or_reject(self):
        for body in (None, [], {}, {"decision": "approve"}, {"decision": True}):
            with self.subTest(body=body):
                self.assertIsNone(self.refused(body).field)

    def test_a_reason_is_required_to_reject(self):
        for reason in (None, "", "  ", "​ "):
            with self.subTest(reason=reason):
                refused = self.refused({"decision": "reject", "reason": reason})
                self.assertEqual(refused.field, "reason")
                self.assertIn("reason is required", refused.message)

    def test_the_reason_must_be_text_of_at_most_500_characters(self):
        self.assertEqual(self.refused({"decision": "reject", "reason": 5}).field, "reason")
        self.assertEqual(self.refused({"decision": "accept", "reason": 5}).field, "reason")
        long = self.refused({"decision": "reject", "reason": "x" * 501})
        self.assertEqual(long.field, "reason")
        self.assertIn("500 characters", long.message)
        self.assertEqual(self.parse({"decision": "reject", "reason": " " + "x" * 500 + " "}),
                         ("rejected", "x" * 500))
        self.assertEqual(_review().REASON_MAX_LENGTH, 500)


class AppliedValueTests(unittest.TestCase):
    def test_stored_values_become_event_values(self):
        values = _review().applied_values({
            **TIMES, "expected_attendance": {"from": 200, "to": 250},
            "equipment_requirements": {"from": "2 microphones", "to": None}})

        self.assertEqual(values, {"start_time": datetime(2026, 12, 6, 18, 0),
                                  "end_time": datetime(2026, 12, 6, 23, 30),
                                  "expected_attendance": 250, "equipment_requirements": None})

    def test_whether_the_times_change(self):
        review = _review()
        self.assertIs(review.changes_times(TIMES), True)
        self.assertIs(review.changes_times({"end_time": TIMES["end_time"]}), True)
        self.assertIs(review.changes_times({"expected_attendance": {"from": 1, "to": 2}}), False)

    def test_decided_statuses_have_labels(self):
        from app.events import change_requests

        self.assertEqual((change_requests.STATUS_LABELS["accepted"],
                          change_requests.STATUS_LABELS["rejected"]), ("Accepted", "Rejected"))


if __name__ == "__main__":
    unittest.main()
