"""SCRUM-88 A11 (team assumption): a venue becoming unavailable undoes the safety check.

Each test names the case it automates in docs/test-cases/SCRUM-88-venue-becomes-unavailable.md
(TC-88-A11-xx). When Venue Staff record an unavailable period over an event's confirmed
booking:

- the event's safety decision is cleared and a Confirmed event returns to Planning, so it
  needs a new safety check and a new confirmation (app/events/safety.py);
- the flagged booking no longer counts towards covering the event, so the event is off the
  Safety Officer's list and can't be confirmed until another confirmed booking covers it.

Endpoints: POST /api/venues/<id>/unavailable (Venue Staff), GET /api/events/safety-checks
(Safety Officers), POST /api/events/<id>/confirm (the event's coordinator).
"""

from datetime import datetime
from unittest import mock

from app import tasks
from app.models import Event, Notification, VenueBooking
from tests.base import AppTestCase

START, END = datetime(2027, 6, 10, 10, 0), datetime(2027, 6, 10, 12, 0)
SAFETY_CHECK_CLEARED = ("Its safety check was cleared, so it needs a new safety check once a "
                        "replacement venue is confirmed.")
REPLACEMENT_MISSING = "Replacement for an unavailable venue"


class UnavailableSafetyTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.organiser = self.make_user(role="organiser")
        self.coordinator = self.make_user(role="coordinator")
        self.venue_staff = self.make_user(role="venue_staff")
        self.officer = self.make_user(role="safety_officer")
        self.hall = self.make_venue(name="Hall A", capacity=200)
        self.annex = self.make_venue(name="Annex", capacity=200)
        self.event = Event(
            title="Harbour Talk", status="confirmed", organiser_id=self.organiser.id,
            coordinator_id=self.coordinator.id, venue_id=self.hall.id, start_time=START,
            end_time=END, expected_attendance=80, venue_requirements="Hall for 80",
            # SCRUM-90 A1: "None" means no equipment is needed.
            equipment_requirements="None", safety_decision="approved",
            safety_decided_by_id=self.officer.id, safety_comment="Exits checked.",
            safety_decided_at=datetime(2026, 11, 1, 2, 0),
            confirmed_by_id=self.coordinator.id, confirmed_at=datetime(2026, 11, 2, 2, 0))
        self.db.session.add(self.event)
        self.db.session.commit()
        self.booking = self.book(self.hall)
        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        patcher.start()
        self.addCleanup(patcher.stop)

    def book(self, venue, start=START, end=END):
        booking = VenueBooking(event_id=self.event.id, venue_id=venue.id, status="confirmed",
                               start_time=start, end_time=end, venue_requirements="Hall for 80",
                               requested_by_id=self.coordinator.id)
        self.db.session.add(booking)
        self.db.session.commit()
        return booking

    def make_unavailable(self, venue=None):
        response = self.client.post(
            f"/api/venues/{(venue or self.hall).id}/unavailable",
            json={"reason": "Burst pipe", "start_time": "2027-06-10T08:00",
                  "end_time": "2027-06-10T18:00"},
            headers=self.auth_headers(self.venue_staff))
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def stored(self):
        self.db.session.expire_all()
        return self.db.session.get(Event, self.event.id)

    def safety_list_ids(self):
        response = self.client.get("/api/events/safety-checks",
                                   headers=self.auth_headers(self.officer))
        self.assertEqual(response.status_code, 200, response.get_json())
        return [item["id"] for item in response.get_json()["events"]]

    def confirm(self):
        return self.client.post(f"/api/events/{self.event.id}/confirm",
                                headers=self.auth_headers(self.coordinator))

    def coordinator_notice(self):
        self.db.session.expire_all()
        [note] = Notification.query.filter_by(recipient_id=self.coordinator.id,
                                              kind="venue_unavailable").all()
        return note.message


class ClearedSafetyCheckTests(UnavailableSafetyTestCase):
    # TC-88-A11-01 · AC4, A11
    def test_tc_88_a11_01_a_confirmed_event_loses_its_safety_approval(self):
        self.make_unavailable()

        event = self.stored()
        self.assertEqual(event.status, "approved")
        self.assertEqual((event.safety_decision, event.safety_decided_by_id,
                          event.safety_comment, event.safety_decided_at),
                         (None, None, None, None))
        # The record that it was confirmed once is kept.
        self.assertEqual(event.confirmed_by_id, self.coordinator.id)
        self.assertIn(SAFETY_CHECK_CLEARED, self.coordinator_notice())

    # TC-88-A11-02 · A11
    def test_tc_88_a11_02_an_approved_event_loses_a_negative_decision_too(self):
        self.event.status = "approved"
        self.event.safety_decision = "changes_requested"
        self.db.session.commit()

        self.make_unavailable()

        self.assertIsNone(self.stored().safety_decision)
        self.assertEqual(self.stored().status, "approved")

    # TC-88-A11-03 · A11
    def test_tc_88_a11_03_an_event_with_no_safety_decision_is_not_told_about_one(self):
        self.event.status = "approved"
        self.event.safety_decision = None
        self.db.session.commit()

        self.make_unavailable()

        self.assertNotIn("safety check", self.coordinator_notice())

    # TC-88-A11-04 · A11
    def test_tc_88_a11_04_an_event_at_another_venue_keeps_its_safety_approval(self):
        self.make_unavailable(venue=self.annex)

        event = self.stored()
        self.assertEqual((event.status, event.safety_decision), ("confirmed", "approved"))


class FlaggedBookingTests(UnavailableSafetyTestCase):
    def setUp(self):
        super().setUp()
        # Awaiting its safety check: approved, with no decision yet.
        self.event.status = "approved"
        for name in ("safety_decision", "safety_decided_by_id", "safety_comment",
                     "safety_decided_at"):
            setattr(self.event, name, None)
        self.db.session.commit()

    # TC-88-A11-05 · A11, SCRUM-90 AC1
    def test_tc_88_a11_05_a_flagged_booking_takes_the_event_off_the_safety_list(self):
        self.assertIn(self.event.id, self.safety_list_ids())

        self.make_unavailable()

        self.assertNotIn(self.event.id, self.safety_list_ids())

    # TC-88-A11-06 · A11, SCRUM-90 AC1
    def test_tc_88_a11_06_another_confirmed_booking_puts_it_back_on_the_list(self):
        self.make_unavailable()
        self.book(self.annex)

        self.assertIn(self.event.id, self.safety_list_ids())

    # TC-88-A11-07 · A11, SCRUM-93 AC2
    def test_tc_88_a11_07_confirming_asks_for_a_replacement_venue(self):
        self.make_unavailable()
        # Even if the Safety Officer approved it again on the unavailable venue, the event
        # could not be confirmed until it has a replacement.
        self.event = self.stored()
        self.event.safety_decision = "approved"
        self.event.safety_decided_by_id = self.officer.id
        self.db.session.commit()

        response = self.confirm()

        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(response.get_json()["missing"], [REPLACEMENT_MISSING])
        self.assertEqual(self.stored().status, "approved")

    # TC-88-A11-08 · A11, SCRUM-93 AC2
    def test_tc_88_a11_08_with_a_replacement_and_a_new_safety_check_it_can_be_confirmed(self):
        self.make_unavailable()
        self.book(self.annex)
        self.assertEqual(self.confirm().get_json()["missing"], ["Approved safety check"])
        self.event = self.stored()
        self.event.safety_decision = "approved"
        self.event.safety_decided_by_id = self.officer.id
        self.db.session.commit()

        response = self.confirm()

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.stored().status, "confirmed")

    # TC-88-A11-09 · SCRUM-93 AC2
    def test_tc_88_a11_09_a_gap_not_caused_by_a_flag_still_asks_for_a_booking(self):
        self.booking.end_time = datetime(2027, 6, 10, 11, 0)
        self.db.session.commit()

        response = self.confirm()

        self.assertIn("Confirmed venue booking", response.get_json()["missing"])
        self.assertNotIn(REPLACEMENT_MISSING, response.get_json()["missing"])

    # TC-88-A11-10 · SCRUM-93 AC2
    def test_tc_88_a11_10_an_event_without_times_still_asks_for_a_booking(self):
        self.event.end_time = None
        self.db.session.commit()

        response = self.confirm()

        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertIn("Confirmed venue booking", response.get_json()["missing"])
