"""Tests for SCRUM-98 "Coordinator cancels an event".

Each test names the case it automates in docs/test-cases/SCRUM-98-cancel-event.md (TC-98-xx).

Model (db/event_cancellation.sql): Event gains cancelled_by_id, cancelled_at (naive UTC) and
cancellation_reason.

Endpoint (JWT required, else 401; the User row is loaded on every request)
    POST /api/events/<id>/cancel   {"reason": text, at most 500 characters}
        200 {"message", "event": {"id", "status": "cancelled", "cancellation":
             {"cancelled_by", "cancelled_at", "reason"}}, "released": {"venue_bookings",
             "equipment_reservations", "registrations"}, "notification": {"in_app",
             "email_queued"}}
    Checks, first failure wins: 401 -> 404 -> 403 (not the event's current coordinator) ->
    400 (body, reason) -> 409 {"reason": "not_cancellable" | "started"} -> 503.
    GET /api/events/<id>/planning has "cancellation" once the event is cancelled.

"Now" is fixed at NOW (Singapore time).
"""

from datetime import datetime
from unittest import mock

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app import tasks
from app.events import routes as event_routes
from app.models import (
    EquipmentRequirement,
    EquipmentReservation,
    Event,
    Notification,
    Registration,
    VenueBooking,
)
from tests.base import AppTestCase

NOW = datetime(2027, 5, 1, 9, 0)
START, END = datetime(2027, 6, 10, 10, 0), datetime(2027, 6, 10, 12, 0)
REASON = "The organiser asked to cancel: the speaker withdrew."
SESSION_EXPIRED = "Your session is no longer valid. Please log in again."
KIND = "event_cancelled"


class CancelEventTestCase(AppTestCase):
    """CE-SEED: E1 approved, coordinator alice, with bookings B1-B5, equipment and
    registrations."""

    def setUp(self):
        super().setUp()
        role = {"dana": "organiser", "alice": "coordinator", "ben": "coordinator",
                "gus": "venue_staff", "vera": "venue_staff", "hana": "tech_staff",
                "lena": "coordinator_lead", "sam": "safety_officer", "admin": "admin",
                "farah": "attendee", "gail": "attendee", "hugo": "attendee", "ivy": "attendee"}
        self.users = {key: self.make_user(role=value) for key, value in role.items()}
        self.hall = self.make_venue(name="Hall A")
        self.annex = self.make_venue(name="Annex")
        self.e1 = self.event("Harbour Talk")
        self.other = self.event("Other Event", coordinator="ben")
        self.bookings = {
            "B1": self.book(self.hall, "confirmed"),
            "B2": self.book(self.annex, "tentative", hold_expires_at=datetime(2027, 6, 1, 12, 0)),
            "B3": self.book(self.annex, "pending", start=datetime(2027, 6, 10, 9, 0)),
            "B4": self.book(self.hall, "rejected", rejection_reason="Closed."),
            "B5": self.book(self.annex, "cancelled"),
            "OTHER": self.book(self.hall, "confirmed", event=self.other,
                               start=datetime(2027, 7, 1, 10, 0), end=datetime(2027, 7, 1, 12, 0)),
        }
        mics = EquipmentRequirement(event_id=self.e1.id, equipment_type="Microphone",
                                    quantity=2, recorded_by_id=self.users["alice"].id)
        self.db.session.add(mics)
        self.db.session.flush()
        resource = self.make_resource(name="Shure SLX-D", category="Microphone")
        self.reservation = EquipmentReservation(
            event_id=self.e1.id, requirement_id=mics.id, resource_id=resource.id, quantity=2,
            start_time=START, end_time=END, status="reserved",
            reserved_by_id=self.users["hana"].id)
        self.db.session.add(self.reservation)
        self.registrations = {}
        for key, event, status in (("farah", self.e1, "registered"),
                                   ("gail", self.e1, "registered"),
                                   ("hugo", self.e1, "withdrawn"),
                                   ("ivy", self.other, "registered")):
            row = Registration(event_id=event.id, attendee_id=self.users[key].id, status=status)
            self.db.session.add(row)
            self.registrations[key] = row
        self.db.session.commit()
        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.email = patcher.start()
        self.addCleanup(patcher.stop)
        clock = mock.patch.object(event_routes, "singapore_now", return_value=NOW)
        self.clock = clock.start()
        self.addCleanup(clock.stop)

    # ---------- Seeding ----------

    def event(self, title, status="approved", coordinator="alice", start=START, end=END):
        row = Event(title=title, status=status, organiser_id=self.users["dana"].id,
                    coordinator_id=self.users[coordinator].id, start_time=start, end_time=end,
                    expected_attendance=80, venue_requirements="Hall for 80",
                    equipment_requirements="Two microphones")
        self.db.session.add(row)
        self.db.session.commit()
        return row

    def book(self, venue, status, event=None, start=START, end=END, **extra):
        row = VenueBooking(event_id=(event or self.e1).id, venue_id=venue.id, status=status,
                           start_time=start, end_time=end, venue_requirements="x",
                           requested_by_id=self.users["alice"].id, **extra)
        self.db.session.add(row)
        self.db.session.commit()
        return row

    # ---------- Calls ----------

    def cancel(self, event=None, user="alice", body=None, headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[user])
        return self.client.post(f"/api/events/{(event or self.e1).id}/cancel",
                                json={"reason": REASON} if body is None else body,
                                headers=headers)

    def cancelled(self, **kwargs):
        response = self.cancel(**kwargs)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertTrue(body.get("error", "").strip())
        self.assertNotIn("event", body)
        return body

    # ---------- Reading what was saved ----------

    def stored(self, event=None):
        self.db.session.expire_all()
        return self.db.session.get(Event, (event or self.e1).id)

    def booking_statuses(self):
        self.db.session.expire_all()
        return {key: self.db.session.get(VenueBooking, row.id).status
                for key, row in self.bookings.items()}

    def registration_statuses(self):
        self.db.session.expire_all()
        return {key: self.db.session.get(Registration, row.id).status
                for key, row in self.registrations.items()}

    def reservation_status(self):
        self.db.session.expire_all()
        return self.db.session.get(EquipmentReservation, self.reservation.id).status

    def notifications(self, user):
        self.db.session.expire_all()
        return Notification.query.filter_by(recipient_id=self.users[user].id, kind=KIND).all()

    def emailed(self):
        return [call.args[0] for call in self.email.call_args_list]

    def assert_nothing_changed(self):
        event = self.stored()
        self.assertEqual((event.status, event.cancelled_at, event.cancellation_reason),
                         ("approved", None, None))
        self.assertEqual(self.booking_statuses()["B1"], "confirmed")
        self.assertEqual(self.registration_statuses()["farah"], "registered")
        self.assertEqual(self.reservation_status(), "reserved")
        self.assertEqual(self.notifications("dana"), [])
        self.email.assert_not_called()


# ---------- AC1: only the event's coordinator, and only before it starts ----------


class AccessTests(CancelEventTestCase):
    # TC-98-01 · AC1
    def test_tc_98_01_who_may_cancel_and_in_what_order(self):
        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()

        self.assertEqual(self.cancel(headers={}).status_code, 401)
        self.assertEqual(self.assert_error(self.cancel(headers=ghost_headers), 401)["error"],
                         SESSION_EXPIRED)
        missing = self.client.post(f"/api/events/{self.missing_id(Event)}/cancel",
                                   json={"reason": REASON},
                                   headers=self.auth_headers(self.users["alice"]))
        self.assert_error(missing, 404)
        for user in ("ben", "dana", "gus", "hana", "lena", "sam", "admin", "farah"):
            with self.subTest(user=user):
                error = self.assert_error(self.cancel(user=user), 403)
                self.assertNotIn("Harbour Talk", error["error"])
        # 403 comes before the body is checked.
        self.assert_error(self.cancel(user="ben", body={}), 403)
        self.assert_nothing_changed()

    # TC-98-02 · AC1
    def test_tc_98_02_an_event_that_has_started_cannot_be_cancelled(self):
        for now in (START, datetime(2027, 6, 10, 11, 0)):
            self.clock.return_value = now
            with self.subTest(now=now):
                body = self.assert_error(self.cancel(), 409)
                self.assertEqual(body["reason"], "started")
                self.assertIn("already started", body["error"])
        self.assert_nothing_changed()

    # TC-98-02 · AC1
    def test_tc_98_02_one_minute_before_the_start_it_can_be(self):
        self.clock.return_value = datetime(2027, 6, 10, 9, 59)

        self.cancelled()


# ---------- AC2: which events can be cancelled ----------


class StatusTests(CancelEventTestCase):
    # TC-98-03 · AC2
    def test_tc_98_03_drafts_rejected_and_cancelled_events_cannot_be_cancelled(self):
        for status in ("draft", "rejected", "cancelled"):
            event = self.event(status, status=status)
            with self.subTest(status=status):
                body = self.assert_error(self.cancel(event=event), 409)
                self.assertEqual(body["reason"], "not_cancellable")
                self.assertIn(f"This event is {status}, so it can't be cancelled.",
                              body["error"])
                self.assertEqual(self.stored(event).status, status)
                self.assertEqual("reinstated" in body["error"], status == "cancelled")

    # TC-98-03 · AC2
    def test_tc_98_03_submitted_reviewed_approved_and_confirmed_events_can_be(self):
        for status in ("submitted", "under_review", "approved", "confirmed"):
            event = self.event(status, status=status)
            with self.subTest(status=status):
                body = self.cancelled(event=event)
                self.assertEqual(body["event"]["status"], "cancelled")


# ---------- AC3: a reason of at most 500 characters ----------


class ReasonTests(CancelEventTestCase):
    # TC-98-04 · AC3
    def test_tc_98_04_a_reason_is_required(self):
        for body in ({}, {"reason": None}, {"reason": ""}, {"reason": "   "},
                     {"reason": " ​"}):
            with self.subTest(body=body):
                error = self.assert_error(self.cancel(body=body), 400)
                self.assertEqual((error["error"], error["field"]),
                                 ("Give a reason for cancelling the event.", "reason"))
        self.assert_nothing_changed()

    # TC-98-04 · AC3
    def test_tc_98_04_the_reason_must_be_text_of_at_most_500_characters(self):
        self.assertEqual(self.assert_error(self.cancel(body={"reason": 5}), 400)["field"],
                         "reason")
        self.assert_error(self.cancel(body=["not", "an", "object"]), 400)
        too_long = self.assert_error(self.cancel(body={"reason": "x" * 501}), 400)
        self.assertIn("501 characters long. The limit is 500", too_long["error"])
        self.assert_nothing_changed()

        body = self.cancelled(body={"reason": f"  {'x' * 500}  "})
        self.assertEqual(body["event"]["cancellation"]["reason"], "x" * 500)


# ---------- AC4: the cancellation is recorded ----------


class RecordTests(CancelEventTestCase):
    # TC-98-05 · AC4
    def test_tc_98_05_who_when_and_why_are_recorded_and_shown(self):
        before = datetime.utcnow()

        body = self.cancelled(body={"reason": f"  {REASON} "})

        event = self.stored()
        self.assertEqual((event.status, event.cancelled_by_id, event.cancellation_reason),
                         ("cancelled", self.users["alice"].id, REASON))
        self.assertTrue(before <= event.cancelled_at <= datetime.utcnow())
        cancellation = body["event"]["cancellation"]
        self.assertEqual((cancellation["cancelled_by"]["id"], cancellation["reason"]),
                         (self.users["alice"].id, REASON))
        self.assertIn('You cancelled "Harbour Talk"', body["message"])
        planning = self.client.get(f"/api/events/{self.e1.id}/planning",
                                   headers=self.auth_headers(self.users["alice"])).get_json()
        self.assertEqual(planning["status"], "cancelled")
        self.assertEqual(planning["cancellation"], cancellation)

    # TC-98-05 · AC4
    def test_tc_98_05_an_event_not_cancelled_shows_no_cancellation(self):
        planning = self.client.get(f"/api/events/{self.e1.id}/planning",
                                   headers=self.auth_headers(self.users["alice"])).get_json()
        self.assertNotIn("cancellation", planning)


# ---------- AC5, AC6: arrangements and registrations are released ----------


class ReleaseTests(CancelEventTestCase):
    # TC-98-06 · AC5
    def test_tc_98_06_live_bookings_are_cancelled_and_equipment_released(self):
        body = self.cancelled()

        self.assertEqual(self.booking_statuses(), {
            "B1": "cancelled", "B2": "cancelled", "B3": "cancelled", "B4": "rejected",
            "B5": "cancelled", "OTHER": "confirmed"})
        self.db.session.expire_all()
        reservation = self.db.session.get(EquipmentReservation, self.reservation.id)
        self.assertEqual((reservation.status, reservation.release_reason),
                         ("released", "The event was cancelled."))
        self.assertEqual(body["released"], {"venue_bookings": 3, "equipment_reservations": 1,
                                            "registrations": 2})
        # The records are kept, with their other details.
        b1 = self.db.session.get(VenueBooking, self.bookings["B1"].id)
        self.assertEqual((b1.venue_id, b1.start_time), (self.hall.id, START))

    # TC-98-06 · AC5
    def test_tc_98_06_the_venue_is_free_again(self):
        self.cancelled()
        e2 = self.event("New Event", start=START, end=END)

        response = self.client.post("/api/venues/bookings", json={
            "event_id": e2.id, "venue_id": self.hall.id, "start_time": "2027-06-10T10:00",
            "end_time": "2027-06-10T12:00", "venue_requirements": "Hall for 80"},
            headers=self.auth_headers(self.users["alice"]))
        self.assertEqual(response.status_code, 201, response.get_json())

    # TC-98-07 · AC6
    def test_tc_98_07_active_registrations_are_cancelled(self):
        self.cancelled()

        self.assertEqual(self.registration_statuses(), {
            "farah": "cancelled", "gail": "cancelled", "hugo": "withdrawn",
            "ivy": "registered"})


# ---------- AC7: everyone affected is told ----------


class NotificationTests(CancelEventTestCase):
    # TC-98-08 · AC7
    def test_tc_98_08_the_organiser_attendees_venue_and_tech_staff_are_told(self):
        body = self.cancelled()

        [organiser] = self.notifications("dana")
        for text in ("Harbour Talk", "2027-06-10 10:00", self.users["alice"].email, REASON):
            self.assertIn(text, organiser.message)
        for user in ("farah", "gail"):
            with self.subTest(attendee=user):
                [note] = self.notifications(user)
                self.assertIn("your registration was cancelled", note.message)
                # The reason is internal planning information (A6).
                self.assertNotIn(REASON, note.message)
        for user in ("gus", "vera"):
            with self.subTest(venue_staff=user):
                [note] = self.notifications(user)
                self.assertIn("Hall A", note.message)
                self.assertIn("Annex", note.message)
        [tech] = self.notifications("hana")
        self.assertIn("reserved equipment was released", tech.message)
        for user in ("hugo", "ivy", "ben", "alice", "lena", "sam"):
            with self.subTest(not_told=user):
                self.assertEqual(self.notifications(user), [])
        notes = Notification.query.filter_by(kind=KIND, event_id=self.e1.id).all()
        self.assertEqual(sorted(self.emailed()),
                         sorted(self.db.session.get(type(self.users["dana"]),
                                                    note.recipient_id).email for note in notes))
        self.assertEqual(body["notification"], {"in_app": True, "email_queued": True})

    # TC-98-08 · AC7
    def test_tc_98_08_staff_with_nothing_to_release_are_not_told(self):
        bare = self.event("Bare Event")
        bare.equipment_requirements = None
        self.db.session.commit()

        self.cancelled(event=bare)

        for user in ("gus", "vera", "hana"):
            self.assertEqual(self.notifications(user), [])
        self.assertEqual(len(self.notifications("dana")), 1)

    # TC-98-08 · AC7
    def test_tc_98_08_requirements_without_reservations_still_tell_tech_staff(self):
        self.db.session.delete(self.reservation)
        self.db.session.commit()

        self.cancelled()

        [tech] = self.notifications("hana")
        self.assertIn("no longer need arranging", tech.message)

    # TC-98-08 · AC7, AC9
    def test_tc_98_08_an_email_queue_outage_does_not_undo_the_cancellation(self):
        self.email.side_effect = ConnectionError("broker down")

        body = self.cancelled()

        self.assertEqual(self.stored().status, "cancelled")
        self.assertIs(body["notification"]["email_queued"], False)
        self.assertEqual(len(self.notifications("dana")), 1)


# ---------- AC8: a cancelled event stays cancelled ----------


class AfterCancellationTests(CancelEventTestCase):
    # TC-98-09 · AC8
    def test_tc_98_09_a_cancelled_event_cannot_be_edited_reinstated_or_confirmed(self):
        self.cancelled()
        headers = self.auth_headers(self.users["alice"])

        edit = self.client.patch(f"/api/events/{self.e1.id}", json={"title": "Back on"},
                                 headers=headers)
        self.assertEqual(edit.status_code, 409, edit.get_json())
        again = self.assert_error(self.cancel(), 409)
        self.assertIn("can't be reinstated", again["error"])
        confirm = self.client.post(f"/api/events/{self.e1.id}/confirm", headers=headers)
        self.assertEqual(confirm.status_code, 409, confirm.get_json())
        self.assertEqual(self.stored().status, "cancelled")


# ---------- AC9: a failed save changes nothing ----------


class FailureTests(CancelEventTestCase):
    # TC-98-10 · AC9
    def test_tc_98_10_a_failed_save_changes_nothing(self):
        for prefix in ("UPDATE events", "UPDATE venue_bookings", "UPDATE registrations",
                       "UPDATE equipment_reservations", "INSERT INTO notifications"):
            def fail(conn, cursor, statement, parameters, context, executemany,
                     prefix=prefix):
                if statement.startswith(prefix):
                    raise OperationalError(statement, parameters, Exception("simulated outage"))

            self.db.session.expire_all()
            sa_event.listen(self.db.engine, "before_cursor_execute", fail)
            try:
                response = self.cancel()
            finally:
                sa_event.remove(self.db.engine, "before_cursor_execute", fail)
            with self.subTest(failing=prefix):
                body = self.assert_error(response, 503)
                self.assertIs(body["retryable"], True)
                self.assertIn("nothing about it changed", body["error"])
                self.assert_nothing_changed()
