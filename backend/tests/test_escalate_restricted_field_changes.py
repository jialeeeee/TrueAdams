"""Tests for the "Escalate Restricted-Field Changes for Review" user story.

Builds on the SCRUM-53 normal-edit flow, PATCH /api/events/<id>.

Restricted fields: venue_id, start_time, end_time. A request that changes one is
never saved through this flow. Instead the response carries:

    "requires_review": {
        "fields":    [<restricted fields changed, in the order above>],
        "requested": {<field>: <value the coordinator entered>},
        "message":   <what happened and what to do, naming the fields in words>,
        "next_step": {"action": "Submit a change request", "method": "POST",
                      "url": "/api/events/<id>/change-requests"},
    }

    Only restricted changes            409 {"error", "requires_review"}, nothing saved
    Restricted + valid normal edits    200 {"message", <planning info>, "requires_review"},
                                       the normal edits are saved
    Restricted + any invalid field     422 {"error", "fields", "requires_review"}, nothing saved

A restricted field sent with its current value is not a change and is ignored.
Refusals (401, 403, 404, cancelled 409) come first and never mention review.
"""

import unittest

from tests.test_update_event_planning_info import NEW_DESCRIPTION, UpdatePlanningTestCase

NEW_START = "2026-12-12T18:00:00"
NEW_END = "2026-12-12T23:00:00"
RESTRICTED_FIELDS = ["venue_id", "start_time", "end_time"]


class RestrictedFieldTestCase(UpdatePlanningTestCase):
    def setUp(self):
        super().setUp()
        self.old_venue = self.venues["fully_recorded"]
        self.new_venue = self.venues["partially_recorded"]

    def change_url(self, key):
        return f"/api/events/{self.events[key].id}/change-requests"

    def assert_requires_review(self, body, *fields):
        review = body.get("requires_review")
        self.assertIsInstance(review, dict, "requires_review missing")
        self.assertEqual(review["fields"], list(fields))
        self.assertEqual(set(review["requested"]), set(fields))
        self.assertIsInstance(review["message"], str)
        self.assertTrue(review["message"].strip())
        self.assertIsInstance(review["next_step"], dict)
        return review

    def assert_blocked(self, response, *fields):
        """Only restricted changes were sent: nothing saved, review required."""
        body = self.assert_error(response, 409)
        return self.assert_requires_review(body, *fields)


# ---------- AC1: Restricted changes are not saved ----------


class RestrictedChangeBlockedTests(RestrictedFieldTestCase):
    def test_each_restricted_field_is_blocked(self):
        changes = {
            "venue_id": self.new_venue.id,
            "start_time": NEW_START,
            "end_time": NEW_END,
        }
        for field, value in changes.items():
            with self.subTest(field=field), self.assert_unchanged("festival"):
                self.assert_blocked(self.patch("festival", {field: value}), field)

    def test_several_restricted_fields_are_blocked_together(self):
        with self.assert_unchanged("festival"):
            response = self.patch("festival", {
                "end_time": NEW_END,
                "start_time": NEW_START,
                "venue_id": self.new_venue.id,
            })

            self.assert_blocked(response, *RESTRICTED_FIELDS)

    def test_removing_a_restricted_value_is_a_change(self):
        for field in ("venue_id", "start_time"):
            with self.subTest(field=field), self.assert_unchanged("festival"):
                self.assert_blocked(self.patch("festival", {field: None}), field)

    def test_restricted_fields_sent_unchanged_are_not_blocked(self):
        for start, end in (("2026-12-12T17:00:00", "2026-12-12T22:00:00"),
                           ("2026-12-12T17:00", "2026-12-12T22:00")):
            with self.subTest(start=start):
                body = self.save("festival", {
                    "venue_id": self.old_venue.id,
                    "start_time": start,
                    "end_time": end,
                    "description": NEW_DESCRIPTION,
                })

                self.assertNotIn("requires_review", body)
                self.assertEqual(self.reload("festival").description, NEW_DESCRIPTION)

    def test_badly_formed_restricted_values_need_correction(self):
        cases = [("venue_id", "abc"), ("venue_id", True), ("venue_id", 1.5),
                 ("start_time", "next Friday"), ("end_time", 1700)]
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assert_unchanged("festival"):
                self.assert_needs_correction(self.patch("festival", {field: value}), field)


# ---------- AC2: The coordinator is told review is needed and what to do next ----------


class ReviewGuidanceTests(RestrictedFieldTestCase):
    def blocked_venue_and_start(self):
        response = self.patch("festival", {"venue_id": self.new_venue.id, "start_time": NEW_START})
        return self.assert_blocked(response, "venue_id", "start_time")

    def test_message_explains_that_review_is_needed(self):
        message = self.blocked_venue_and_start()["message"].lower()

        self.assertIn("review", message)
        self.assertIn("change request", message)
        self.assertIn("venue", message)
        self.assertIn("start time", message)
        self.assertNotIn("venue_id", message)
        self.assertNotIn("start_time", message)

    def test_next_step_is_submitting_a_change_request_for_this_event(self):
        next_step = self.blocked_venue_and_start()["next_step"]

        self.assertEqual(next_step, {
            "action": "Submit a change request",
            "method": "POST",
            "url": self.change_url("festival"),
        })

    def test_requested_values_are_returned_for_the_change_request(self):
        requested = self.blocked_venue_and_start()["requested"]

        self.assertEqual(requested, {"venue_id": self.new_venue.id, "start_time": NEW_START})

    def test_refused_requests_do_not_mention_review(self):
        other = self.patch("festival", {"venue_id": self.new_venue.id}, as_user=self.users["ben"])
        cancelled = self.patch("winter_cancelled", {"venue_id": self.new_venue.id})

        self.assert_denied(other, "festival")
        self.assertNotIn("requires_review", other.get_json())
        self.assert_error(cancelled, 409)
        self.assertNotIn("requires_review", cancelled.get_json())


# ---------- AC3: Saved information stays unchanged ----------


class SavedInformationUnchangedTests(RestrictedFieldTestCase):
    def test_repeated_attempts_change_nothing(self):
        with self.assert_unchanged("festival"):
            for _ in range(3):
                self.assert_blocked(self.patch("festival", {"venue_id": self.new_venue.id}),
                                    "venue_id")

    def test_a_blocked_change_is_not_applied_by_a_later_save(self):
        self.patch("festival", {"venue_id": self.new_venue.id})

        self.save("festival", {"description": NEW_DESCRIPTION})

        event = self.reload("festival")
        self.assertEqual(event.venue_id, self.old_venue.id)
        self.assertEqual(event.description, NEW_DESCRIPTION)

    def test_view_still_shows_the_saved_values(self):
        self.patch("festival", {"venue_id": self.new_venue.id, "start_time": NEW_START})
        self.db.session.expire_all()

        body = self.view("festival")

        self.assertEqual(body["venue"]["name"], "Aurora Ballroom")
        self.assertEqual(body["start_time"], "2026-12-12T17:00:00")

    def test_save_failure_with_a_restricted_change_saves_nothing(self):
        with self.assert_unchanged("festival"):
            response = self.patch_during_outage(
                "festival",
                {"description": NEW_DESCRIPTION, "venue_id": self.new_venue.id},
                only="UPDATE",
            )

            self.assert_error(response, 503)
            self.assertIs(response.get_json().get("retryable"), True)


# ---------- AC4: Other edits are unaffected ----------


class OtherEditsUnaffectedTests(RestrictedFieldTestCase):
    def test_normal_edits_are_saved_alongside_a_blocked_change(self):
        body = self.save("festival", {"description": NEW_DESCRIPTION, "venue_id": self.new_venue.id})

        self.assert_requires_review(body, "venue_id")
        self.assertIn("review", body["message"].lower())
        event = self.reload("festival")
        self.assertEqual(event.description, NEW_DESCRIPTION)
        self.assertEqual(event.venue_id, self.old_venue.id)

    def test_response_shows_the_saved_edit_and_the_unchanged_venue(self):
        body = self.save("festival", {"description": NEW_DESCRIPTION, "venue_id": self.new_venue.id})

        self.assertEqual(body["description"], NEW_DESCRIPTION)
        self.assertEqual(body["venue"]["id"], self.old_venue.id)
        shown = {k: v for k, v in body.items() if k not in ("message", "requires_review")}
        self.assertEqual(shown, self.view("festival"))

    def test_editing_continues_normally_after_a_block(self):
        self.assert_blocked(self.patch("festival", {"venue_id": self.new_venue.id}), "venue_id")

        title = self.save("festival", {"title": "Harbour Lights"})
        description = self.save("festival", {"description": NEW_DESCRIPTION})

        self.assertNotIn("requires_review", title)
        self.assertNotIn("requires_review", description)
        event = self.reload("festival")
        self.assertEqual((event.title, event.description), ("Harbour Lights", NEW_DESCRIPTION))

    def test_invalid_normal_field_still_stops_the_save(self):
        with self.assert_unchanged("festival"):
            response = self.patch("festival", {
                "title": "",
                "description": NEW_DESCRIPTION,
                "venue_id": self.new_venue.id,
            })

            body = self.assert_needs_correction(response, "title")
            self.assertEqual(set(body["fields"]), {"title"})
            self.assert_requires_review(body, "venue_id")

    def test_non_editable_field_still_stops_the_save(self):
        with self.assert_unchanged("festival"):
            response = self.patch("festival", {
                "status": "approved",
                "description": NEW_DESCRIPTION,
                "venue_id": self.new_venue.id,
            })

            body = self.assert_needs_correction(response, "status")
            self.assert_requires_review(body, "venue_id")


if __name__ == "__main__":
    unittest.main()
