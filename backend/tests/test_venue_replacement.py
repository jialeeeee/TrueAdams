"""Tests for SCRUM-89 "Coordinator replaces an unavailable venue".

Each test names the case it automates from the "Sprint 4 test cases" sheet
(IS212-US89-TCnn) and docs/test-cases/SCRUM-89-replacement-venue.md.

Model (db/venue_replacement_requests.sql): venue_bookings.replaces_booking_id, the flagged
booking a request replaces (NULL for any other request). Approving the replacement sets the
flagged booking's status, and its flag's status, to "replaced"; nothing else about it changes.

API
    GET  /api/venues/bookings/<id>/replacement   the event's coordinator only
        200 {"booking": {"id", "venue", "start_time", "end_time", "flag"},
             "event": {"id", "title", "expected_attendance", "venue_requirements"}}
    POST /api/venues/bookings/<id>/replacement   body {"venue_id"}
        201 {"message", "booking"}  the pending request, same times and requirements,
            with "replaces": {"id", "venue"}
        401 · 404 booking/venue · 403 not the event's coordinator · 400 {"fields"}
        409 reason "not_flagged" | "event_not_approved" | "already_requested" | "conflict"
        503 {"retryable": true} and nothing created
    GET /api/venues/bookings?event_id=   a flagged booking has "unavailable_flag":
        {"text", "status": "flagged" | "replaced", "replaced_by": id | null}
"""

import unittest
from datetime import datetime
from unittest import mock

from sqlalchemy.exc import SQLAlchemyError

from app.models import Event, Notification, VenueBooking, VenueReplacementFlag
from app.venues import scheduling
from tests.test_venue_unavailable import FLAG, UnavailableTestCase, at

REPLACEMENT_NOTE = "venue_booking_rejected"


class ReplacementTestCase(UnavailableTestCase):
    """E-901 (coordinator alice, 80 attendees) with B-901 at V-101 on 20 Nov 10:00-12:00,
    flagged because V-101 is unavailable 09:00-18:00, and confirmed B-902 elsewhere."""

    def setUp(self):
        super().setUp()
        self.v103 = self.venues["harbour_room"]  # capacity 120, nothing booked
        self.v104 = self.venues["summit_hall"]  # capacity 400, booked 11:00-13:00
        self.v102 = self.venues["blank_values"]  # capacity 50
        self.v106 = self.venues["recorded_as_none"]
        self.events["E1"].expected_attendance = 80
        self.db.session.commit()
        self.set_buffers(self.v101, None, None)
        self.set_buffers(self.v103, None, None)
        self.b901 = self.b801
        self.recorded()  # the unavailable period: B-901 flagged, E-901 back to Planning
        self.b902 = self.book("E1", self.v106, at(14, day=21), at(16, day=21))
        self.b_other = self.book("E2", self.v104, at(11), at(13))

    # ---------- Calls ----------

    def set_buffers(self, venue, setup, turnaround):
        venue.setup_minutes, venue.turnaround_minutes = setup, turnaround
        self.db.session.commit()

    def replace(self, booking=None, venue=None, as_user="alice", headers=None, body=None):
        booking = booking or self.b901
        if body is None:
            body = {"venue_id": (venue or self.v103).id}
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.post(f"/api/venues/bookings/{booking.id}/replacement",
                                json=body, headers=headers)

    def replaced(self, **kwargs):
        response = self.replace(**kwargs)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def context(self, booking=None, as_user="alice"):
        return self.client.get(f"/api/venues/bookings/{(booking or self.b901).id}/replacement",
                               headers=self.auth_headers(self.users[as_user]))

    def event_bookings(self, as_user="alice"):
        response = self.client.get(
            "/api/venues/bookings", query_string={"event_id": self.events["E1"].id},
            headers=self.auth_headers(self.users[as_user]))
        self.assertEqual(response.status_code, 200, response.get_json())
        return {b["id"]: b for b in response.get_json()["bookings"]}

    def replacement_requests(self):
        self.db.session.expire_all()
        return VenueBooking.query.filter(VenueBooking.replaces_booking_id.isnot(None)).all()

    def booking_row(self, booking):
        self.db.session.expire_all()
        b = self.db.session.get(VenueBooking, booking.id)
        return (b.status, b.venue_id, b.event_id, b.start_time, b.end_time, b.venue_requirements)

    def flag_status(self):
        self.db.session.expire_all()
        return VenueReplacementFlag.query.filter_by(booking_id=self.b901.id).one().status

    def decide(self, action, booking_id, body=None):
        return self.client.post(f"/api/venues/bookings/{booking_id}/{action}", json=body or {},
                                headers=self.auth_headers(self.users["gus"]))

    def assert_nothing_created_or_changed(self):
        self.assertEqual(self.replacement_requests(), [])
        self.assertEqual(self.booking_row(self.b901)[0], "confirmed")
        self.assertEqual(self.flag_status(), "flagged")


# ---------- AC1: search from a flagged booking and request ----------


class RequestingTests(ReplacementTestCase):
    def test_tc1_the_coordinator_requests_a_replacement_and_it_is_linked(self):  # AC1
        body = self.replaced()
        booking = body["booking"]
        self.assertEqual(booking["status"], "pending")
        self.assertEqual(booking["venue"]["id"], self.v103.id)
        self.assertEqual(booking["event"]["id"], self.events["E1"].id)
        self.assertEqual((booking["start_time"], booking["end_time"]),
                         ("2027-11-20T10:00:00", "2027-11-20T12:00:00"))
        self.assertEqual(booking["replaces"]["id"], self.b901.id)
        [saved] = self.replacement_requests()
        self.assertEqual((saved.replaces_booking_id, saved.requested_by_id, saved.status),
                         (self.b901.id, self.users["alice"].id, "pending"))
        self.assertEqual(saved.venue_requirements, "x")  # the flagged booking's requirements

    def test_tc2_the_search_is_for_the_same_event(self):  # AC1
        response = self.context()
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["event"], {
            "id": self.events["E1"].id, "title": "Harbour Lights Festival",
            "expected_attendance": 80,
            "venue_requirements": "Open-air waterfront space for 250"})
        self.assertEqual((body["booking"]["start_time"], body["booking"]["end_time"]),
                         ("2027-11-20T10:00:00", "2027-11-20T12:00:00"))
        self.assertEqual(body["booking"]["venue"]["id"], self.v101.id)
        self.assertEqual(body["booking"]["flag"], FLAG)

    def test_the_request_takes_no_times_or_event_of_its_own(self):  # AC1
        for extra in ({"start_time": "2027-11-21T10:00"}, {"event_id": 1}, {"setup_minutes": 5}):
            with self.subTest(extra=extra):
                response = self.replace(body={"venue_id": self.v103.id, **extra})
                self.assertEqual(response.status_code, 400)
                self.assertIn(next(iter(extra)), response.get_json()["fields"])
        self.assert_nothing_created_or_changed()

    def test_tc3_a_booking_that_is_not_flagged_cannot_be_replaced(self):  # AC1
        for booking in (self.b902,):
            with self.subTest(booking=booking.id):
                response = self.replace(booking=booking)
                body = self.assert_error(response, 409)
                self.assertEqual(body["reason"], "not_flagged")
                self.assertEqual(self.context(booking).status_code, 409)
        self.assert_nothing_created_or_changed()

    def test_tc4_a_venue_must_be_chosen(self):  # AC1
        for body in ({}, {"venue_id": None}, {"venue_id": ""}, {"venue_id": "abc"},
                     {"venue_id": True}):
            with self.subTest(body=body):
                response = self.replace(body=body)
                self.assertEqual(response.status_code, 400)
                self.assertIn("venue_id", response.get_json()["fields"])
        self.assert_nothing_created_or_changed()

    def test_an_unknown_booking_or_venue_is_a_404(self):  # AC1
        response = self.client.post("/api/venues/bookings/999999/replacement",
                                    json={"venue_id": self.v103.id},
                                    headers=self.auth_headers(self.users["alice"]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.replace(body={"venue_id": 999999}).status_code, 404)
        self.assert_nothing_created_or_changed()

    def test_no_session_is_a_401(self):  # AC5
        response = self.client.post(f"/api/venues/bookings/{self.b901.id}/replacement",
                                    json={"venue_id": self.v103.id})
        self.assertEqual(response.status_code, 401)

    def test_a_body_that_is_not_json_is_a_400(self):  # AC1
        response = self.client.post(f"/api/venues/bookings/{self.b901.id}/replacement",
                                    data="x", headers=self.auth_headers(self.users["alice"]))
        self.assertEqual(response.status_code, 400)

    def test_only_one_replacement_can_be_waiting_for_a_flagged_booking(self):  # AC1
        self.replaced()
        body = self.assert_error(self.replace(venue=self.v102), 409)
        self.assertEqual(body["reason"], "already_requested")
        self.assertEqual(len(self.replacement_requests()), 1)

    def test_the_event_cannot_ask_again_for_a_venue_it_already_requested_then(self):  # AC2
        duplicate = self.book("E1", self.v103, at(10), at(12), status="pending")
        body = self.assert_error(self.replace(venue=self.v103), 409)
        self.assertEqual((body["reason"], body["booking_id"]), ("already_requested", duplicate.id))
        self.assertEqual(self.replacement_requests(), [])

    def test_a_replacement_can_be_asked_for_again_after_a_rejection(self):  # AC4
        first = self.replaced()["booking"]["id"]
        self.assertEqual(self.decide("reject", first, {"reason": "No"}).status_code, 200)
        self.replaced(venue=self.v102)
        self.assertEqual(len(self.replacement_requests()), 2)

    def test_an_event_that_is_no_longer_approved_cannot_ask(self):  # AC1
        self.events["E1"].status = "cancelled"
        self.db.session.commit()
        body = self.assert_error(self.replace(), 409)
        self.assertEqual(body["reason"], "event_not_approved")
        self.assertEqual(self.replacement_requests(), [])

    def test_a_cancelled_flagged_booking_cannot_be_replaced(self):  # AC1
        self.db.session.get(VenueBooking, self.b901.id).status = "cancelled"
        self.db.session.commit()
        self.assertEqual(self.assert_error(self.replace(), 409)["reason"], "not_flagged")


# ---------- AC2: the same checks and approval as any new booking ----------


class SameChecksTests(ReplacementTestCase):
    def test_tc5_a_venue_with_a_conflicting_booking_is_blocked(self):  # AC2
        body = self.assert_error(self.replace(venue=self.v104), 409)
        self.assertEqual(body["reason"], "conflict")
        self.assertEqual([c["type"] for c in body["conflicts"]], ["booking"])
        self.assertEqual(body["conflicts"][0]["id"], self.b_other.id)
        self.assert_nothing_created_or_changed()

    def test_tc6_the_search_shows_when_a_venue_does_not_suit_the_event(self):  # AC2
        response = self.client.get(
            f"/api/events/{self.events['E1'].id}/venue-suitability",
            query_string={"venue_id": self.v102.id},
            headers=self.auth_headers(self.users["alice"]))
        self.assertEqual(response.status_code, 200, response.get_json())
        attendance = [c for c in response.get_json()["checks"]
                      if c["requirement"] == "attendance"][0]
        self.assertEqual(attendance["status"], "mismatch")
        self.assertIn("80", attendance["detail"])
        self.assertIn("50", attendance["detail"])

    def test_tc7_the_unavailable_venue_cannot_be_the_replacement(self):  # AC2
        body = self.assert_error(self.replace(venue=self.v101), 409)
        self.assertEqual(body["reason"], "conflict")
        self.assertIn("unavailable", body["error"].lower())
        self.assertIn("block", [c["type"] for c in body["conflicts"]])
        self.assert_nothing_created_or_changed()

    def test_tc8_a_venue_is_blocked_when_only_setup_or_turnaround_conflicts(self):  # AC2
        self.set_buffers(self.v103, 30, 30)
        self.book("E2", self.v103, at(8), at(9, 15))  # occupied until 09:45
        body = self.assert_error(self.replace(venue=self.v103), 409)  # occupied from 09:30
        self.assertEqual(body["reason"], "conflict")
        self.assertEqual(body["occupied"], {"start": "2027-11-20T09:30:00",
                                            "end": "2027-11-20T12:30:00"})
        self.assertEqual(body["conflicts"][0]["turnaround"]["minutes"], 30)
        self.assert_nothing_created_or_changed()

    def test_tc9_the_request_goes_to_venue_staff_like_any_new_booking(self):  # AC2
        created = self.replaced()["booking"]
        response = self.listed()
        self.assertEqual(response.status_code, 200)
        entry = [b for b in response.get_json()["bookings"] if b["id"] == created["id"]][0]
        self.assertEqual(entry["status"], "pending")
        self.assertEqual(entry["venue"]["id"], self.v103.id)
        self.assertEqual(entry["replaces"]["id"], self.b901.id)
        self.assertEqual(entry["conflicts"], [])

    def test_tc10_the_events_other_venue_bookings_are_unchanged(self):  # AC2
        before = self.booking_row(self.b902)
        self.replaced()
        self.assertEqual(self.booking_row(self.b902), before)
        self.assertEqual(self.booking_row(self.b901)[0], "confirmed")

    def test_a_replacement_request_is_not_a_conflict_with_the_flagged_booking(self):  # AC2
        # The flagged booking still holds V-101 at the same time; a replacement at another
        # venue for the same time is the point, and the event's other bookings are not checked.
        self.assertEqual(self.replace().status_code, 201)


# ---------- AC3, AC4: the decision ----------


class DecisionTests(ReplacementTestCase):
    def test_tc11_approving_the_replacement_marks_the_flagged_booking_replaced(self):  # AC3
        before = self.booking_row(self.b901)
        created = self.replaced()["booking"]
        response = self.decide("approve", created["id"])
        self.assertEqual(response.status_code, 200, response.get_json())
        after = self.booking_row(self.b901)
        self.assertEqual(after[0], "replaced")
        self.assertEqual(after[1:], before[1:])  # venue, event, times, requirements kept
        self.assertEqual(self.flag_status(), "replaced")
        self.assertEqual(self.booking_row(VenueBooking(id=created["id"]))[0], "confirmed")

    def test_tc11_the_coordinator_still_sees_the_original_record_and_its_flag(self):  # AC3
        created = self.replaced()["booking"]
        self.decide("approve", created["id"])
        entry = self.event_bookings()[self.b901.id]
        self.assertEqual(entry["status"], "replaced")
        self.assertEqual(entry["venue"]["id"], self.v101.id)
        self.assertEqual((entry["start_time"], entry["end_time"]),
                         ("2027-11-20T10:00:00", "2027-11-20T12:00:00"))
        self.assertEqual(entry["unavailable_flag"],
                         {"text": FLAG, "status": "replaced", "replaced_by": created["id"]})

    def test_approving_the_replacement_moves_the_events_venue(self):  # AC3
        self.db.session.get(Event, self.events["E1"].id).venue_id = self.v101.id
        self.db.session.commit()
        created = self.replaced()["booking"]
        self.decide("approve", created["id"])
        self.db.session.expire_all()
        self.assertEqual(self.db.session.get(Event, self.events["E1"].id).venue_id,
                         self.v103.id)

    def test_a_replaced_booking_leaves_the_replacement_lists_and_cannot_be_replaced_again(self):  # AC3
        created = self.replaced()["booking"]
        self.decide("approve", created["id"])
        self.assertEqual(self.flagged_ids(), [])
        self.assertEqual(self.assert_error(self.replace(venue=self.v102), 409)["reason"],
                         "not_flagged")

    def test_tc12_the_flagged_booking_stays_flagged_while_the_replacement_waits(self):  # AC3
        self.replaced()
        entry = self.event_bookings()[self.b901.id]
        self.assertEqual(entry["status"], "confirmed")
        self.assertEqual(entry["unavailable_flag"],
                         {"text": FLAG, "status": "flagged", "replaced_by": None})
        self.assertEqual(self.flagged_ids(), [self.b901.id])

    def test_tc13_rejecting_the_replacement_keeps_the_booking_flagged_and_tells_the_coordinator(self):  # AC4
        created = self.replaced()["booking"]
        response = self.decide("reject", created["id"], {"reason": "Not suitable"})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.booking_row(self.b901)[0], "confirmed")
        self.assertEqual(self.flag_status(), "flagged")
        self.assertEqual(self.flagged_ids(), [self.b901.id])
        self.db.session.expire_all()
        [note] = Notification.query.filter_by(recipient_id=self.users["alice"].id,
                                              kind=REPLACEMENT_NOTE).all()
        self.assertIn("rejected", note.message)
        self.assertIn("Not suitable", note.message)
        self.assertIn(FLAG, note.message)  # the original is still flagged

    def test_approving_after_the_flagged_booking_was_cancelled_replaces_nothing(self):  # AC3
        created = self.replaced()["booking"]
        self.db.session.get(VenueBooking, self.b901.id).status = "cancelled"
        self.db.session.commit()
        response = self.decide("approve", created["id"])
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.booking_row(self.b901)[0], "cancelled")
        self.assertEqual(self.flag_status(), "flagged")
        self.assertNotIn("Replaced", response.get_json()["message"])

    def test_an_approval_refused_by_the_database_rule_is_a_conflict_not_a_failure(self):  # AC3
        created = self.replaced()["booking"]
        clash = self.book("E2", self.v103, at(10), at(12))  # saved without the venue lock
        check = scheduling.blocking_bookings
        calls = []

        def checked_before_the_competing_save(*args):
            calls.append(args)
            return [] if len(calls) == 1 else check(*args)

        with mock.patch.object(scheduling, "blocking_bookings",
                               side_effect=checked_before_the_competing_save):
            response = self.decide("approve", created["id"])

        body = self.assert_error(response, 409)
        self.assertEqual(body["reason"], "conflict")
        self.assertEqual([c["id"] for c in body["conflicts"]], [clash.id])
        self.assertEqual(self.booking_row(self.b901)[0], "confirmed")
        self.assertEqual(self.flag_status(), "flagged")

    def test_the_other_bookings_of_the_event_are_untouched_by_the_decision(self):  # AC3
        before = self.booking_row(self.b902)
        created = self.replaced()["booking"]
        self.decide("approve", created["id"])
        self.assertEqual(self.booking_row(self.b902), before)


# ---------- AC3 by way of a tentative hold (SCRUM-86 meets SCRUM-89) ----------

HOLD_EXPIRY = "2027-11-19T12:00"


class HeldReplacementTests(ReplacementTestCase):
    """Venue Staff may hold a replacement request instead of approving it. Confirming that
    hold must have the same effect as an approval (AC3), and while it is held the
    replacement is still the one waiting (AC1)."""

    def held(self, venue=None):
        created = self.replaced(venue=venue)["booking"]
        response = self.decide("hold", created["id"], {"expires_at": HOLD_EXPIRY})
        self.assertEqual(response.status_code, 200, response.get_json())
        return created

    def confirm(self, booking_id):
        return self.client.post(f"/api/venues/bookings/{booking_id}/confirm",
                                headers=self.auth_headers(self.users["alice"]))

    def test_confirming_a_held_replacement_marks_the_flagged_booking_replaced(self):  # AC3
        before = self.booking_row(self.b901)
        created = self.held()
        response = self.confirm(created["id"])
        self.assertEqual(response.status_code, 200, response.get_json())
        after = self.booking_row(self.b901)
        self.assertEqual(after[0], "replaced")
        self.assertEqual(after[1:], before[1:])
        self.assertEqual(self.flag_status(), "replaced")
        self.assertEqual(self.booking_row(VenueBooking(id=created["id"]))[0], "confirmed")
        self.assertIn("replaces your booking at", response.get_json()["message"])
        entry = self.event_bookings()[self.b901.id]
        self.assertEqual(entry["unavailable_flag"],
                         {"text": FLAG, "status": "replaced", "replaced_by": created["id"]})

    def test_confirming_a_held_replacement_moves_the_events_venue(self):  # AC3
        self.db.session.get(Event, self.events["E1"].id).venue_id = self.v101.id
        self.db.session.commit()
        created = self.held()
        self.assertEqual(self.confirm(created["id"]).status_code, 200)
        self.db.session.expire_all()
        self.assertEqual(self.db.session.get(Event, self.events["E1"].id).venue_id,
                         self.v103.id)

    def test_a_held_replacement_is_still_the_one_waiting(self):  # AC1
        created = self.held()
        body = self.assert_error(self.replace(venue=self.v102), 409)
        self.assertEqual(body["reason"], "already_requested")
        self.assertEqual(body["booking_id"], created["id"])
        self.assertIn("on hold", body["error"])
        self.assertEqual(len(self.replacement_requests()), 1)

    def test_a_confirmation_refused_by_the_database_rule_replaces_nothing(self):  # AC3
        created = self.held()
        clash = self.book("E2", self.v103, at(10), at(12))  # saved without the venue lock
        check = scheduling.blocking_bookings
        calls = []

        def checked_before_the_competing_save(*args):
            calls.append(args)
            return [] if len(calls) == 1 else check(*args)

        with mock.patch.object(scheduling, "blocking_bookings",
                               side_effect=checked_before_the_competing_save):
            response = self.confirm(created["id"])

        body = self.assert_error(response, 409)
        self.assertEqual(body["reason"], "conflict")
        self.assertEqual([c["id"] for c in body["conflicts"]], [clash.id])
        self.assertEqual(self.booking_row(self.b901)[0], "confirmed")
        self.assertEqual(self.flag_status(), "flagged")
        self.assertEqual(self.booking_row(VenueBooking(id=created["id"]))[0], "tentative")

    def test_a_replacement_can_be_asked_for_again_once_its_hold_has_expired(self):  # AC1
        self.held()
        after_expiry = datetime(2027, 11, 19, 12, 0)
        with mock.patch("app.venues.routes.singapore_now", return_value=after_expiry):
            self.replaced(venue=self.v102)
        self.assertEqual(len(self.replacement_requests()), 2)


# ---------- AC5: only the event's coordinator ----------


class PermissionTests(ReplacementTestCase):
    def test_tc14_another_coordinator_cannot_request_a_replacement(self):  # AC5
        before = self.booking_row(self.b901)
        response = self.replace(as_user="ben")
        self.assertEqual(response.status_code, 403, response.get_json())
        self.assertEqual(self.context(as_user="ben").status_code, 403)
        self.assert_nothing_created_or_changed()
        self.assertEqual(self.booking_row(self.b901), before)

    def test_tc15_venue_staff_cannot_request_a_replacement(self):  # AC5
        self.assertEqual(self.replace(as_user="gus").status_code, 403)
        self.assertEqual(self.context(as_user="gus").status_code, 403)
        self.assert_nothing_created_or_changed()

    def test_tc16_an_attendee_cannot_request_a_replacement(self):  # AC5
        self.assertEqual(self.replace(as_user="farah").status_code, 403)
        self.assert_nothing_created_or_changed()

    def test_other_roles_cannot_request_a_replacement(self):  # AC5
        for user in ("dana", "hana", "admin"):
            with self.subTest(user=user):
                self.assertEqual(self.replace(as_user=user).status_code, 403)
        self.assert_nothing_created_or_changed()

    def test_after_a_reassignment_only_the_new_coordinator_can_ask(self):  # AC5
        self.db.session.get(Event, self.events["E1"].id).coordinator_id = self.users["ben"].id
        self.db.session.commit()
        self.assertEqual(self.replace(as_user="alice").status_code, 403)
        self.assertEqual(self.replace(as_user="ben").status_code, 201)

    def test_a_refusal_does_not_reveal_whether_the_booking_is_flagged(self):  # AC5
        # 403 comes before the flagged check (401, 404, 403, 400, 409).
        self.assertEqual(self.replace(booking=self.b902, as_user="ben").status_code, 403)


# ---------- AC6: failure ----------


class FailureTests(ReplacementTestCase):
    def test_tc17_a_failed_save_creates_no_request_and_leaves_the_booking_unchanged(self):  # AC6
        before = self.booking_row(self.b901)
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.replace()
        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not (sent|saved)")
        self.assert_nothing_created_or_changed()
        self.assertEqual(self.booking_row(self.b901), before)

    def test_a_failed_approval_leaves_the_flagged_booking_flagged(self):  # AC3
        created = self.replaced()["booking"]
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.decide("approve", created["id"])
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.booking_row(self.b901)[0], "confirmed")
        self.assertEqual(self.flag_status(), "flagged")

    def test_a_retry_after_a_failure_succeeds(self):  # AC1
        with mock.patch.object(self.db.session, "commit",
                               side_effect=SQLAlchemyError("simulated outage")):
            self.replace()
        self.assertEqual(self.replace().status_code, 201)


if __name__ == "__main__":
    unittest.main()
