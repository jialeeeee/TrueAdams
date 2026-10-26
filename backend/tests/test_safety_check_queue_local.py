"""SCRUM-90 PR #58: one opt-in PostgreSQL check, restricted to a local test DB."""

import os
import unittest
from datetime import datetime, timedelta
from unittest import mock

from sqlalchemy.engine import make_url

with mock.patch("dotenv.load_dotenv", return_value=False):
    from app.config import TestConfig
    from app.events import routes
    from app.models import EquipmentRequirement, EquipmentReservation, VenueBooking
    from tests import base


@unittest.skipUnless(os.environ.get("SCRUM90_LOCAL_TEST_DATABASE_URL"),
                     "Requires the explicitly selected dedicated local SCRUM-90 database")
class SafetyCheckQueueLocalTests(base.AppTestCase):
    @classmethod
    def setUpClass(cls):
        target = os.environ["SCRUM90_LOCAL_TEST_DATABASE_URL"]
        url = make_url(target)
        expected = ("127.0.0.1", 5433, "trueadams_s90_fresh", "connectsphere_test")
        if (url.host, url.port, url.database, url.username) != expected:
            raise RuntimeError("Refusing any target except the dedicated local SCRUM-90 test database.")
        if base._app is not None and base._app.config["SQLALCHEMY_DATABASE_URI"] != target:
            raise RuntimeError("Refusing a cached app configured for another database.")
        config = mock.patch.object(TestConfig, "SQLALCHEMY_DATABASE_URI", target)
        config.start()
        cls.addClassCleanup(config.stop)
        super().setUpClass()

    # TC-90-01/02: actual SQL filtering plus grouped venues and reservation totals.
    def test_current_schedule_and_equipment_readiness_through_postgresql(self):
        now = datetime(2026, 12, 12, 16)
        officer = self.make_user(role="safety_officer")
        organiser = self.make_user(role="organiser")
        coordinator = self.make_user(role="coordinator")
        technician = self.make_user(role="tech_staff")
        events = {}
        for name, status, start in (
            ("ready", "approved", now + timedelta(hours=1)),
            ("cancelled", "cancelled", now + timedelta(hours=1)),
            ("rejected", "rejected", now + timedelta(hours=1)),
            ("ended", "approved", now - timedelta(hours=3)),
            ("stale", "approved", now + timedelta(hours=2)),
            ("phases", "approved", now + timedelta(hours=1)),
            ("gap", "approved", now + timedelta(hours=1)),
        ):
            venue = self.make_venue(name=name)
            event = self.make_event(organiser=organiser, title=name, status=status,
                                    venue=venue, start_time=start, expected_attendance=60)
            events[name] = event
            booking_start = start - timedelta(hours=1) if name == "stale" else start
            booking_end = booking_start + timedelta(hours=1 if name in {"phases", "gap"} else 2)
            self.db.session.add(VenueBooking(event_id=event.id, venue_id=venue.id,
                status="confirmed", start_time=booking_start, end_time=booking_end))
            if name in {"phases", "gap"}:
                next_venue = self.make_venue(name=f"{name} second phase")
                next_start = booking_end + timedelta(minutes=1 if name == "gap" else 0)
                self.db.session.add(VenueBooking(event_id=event.id, venue_id=next_venue.id,
                    status="confirmed", start_time=next_start, end_time=event.end_time))
        ready = events["ready"]
        extra = self.make_venue(name="Second venue")
        self.db.session.add(VenueBooking(event_id=ready.id, venue_id=extra.id, status="confirmed",
            start_time=ready.start_time + timedelta(minutes=15), end_time=ready.end_time - timedelta(minutes=15)))
        requirement = EquipmentRequirement(event_id=ready.id, equipment_type="Microphone", quantity=2,
                                             recorded_by_id=coordinator.id)
        self.db.session.add(requirement)
        self.db.session.flush()
        resource = self.make_resource(name="Microphones", category="Microphone", quantity_available=2)
        for _ in range(2):
            self.db.session.add(EquipmentReservation(event_id=ready.id, requirement_id=requirement.id,
                resource_id=resource.id, quantity=1, start_time=ready.start_time, end_time=ready.end_time,
                status="reserved", reserved_by_id=technician.id))
        self.db.session.commit()

        with mock.patch.object(routes, "singapore_now", return_value=now):
            response = self.client.get("/api/events/safety-checks", headers=self.auth_headers(officer))
        self.assertEqual(response.status_code, 200, response.get_json())
        own_ids = {event.id for event in events.values()}
        own_rows = [row for row in response.get_json()["events"] if row["id"] in own_ids]
        self.assertCountEqual([row["id"] for row in own_rows], [ready.id, events["phases"].id])
        ready_row = next(row for row in own_rows if row["id"] == ready.id)
        self.assertEqual(len(ready_row["venues"]), 2)
        self.assertEqual(ready_row["equipment"], [
            {"equipment_type": "Microphone", "quantity": 2, "reserved_quantity": 2}])
