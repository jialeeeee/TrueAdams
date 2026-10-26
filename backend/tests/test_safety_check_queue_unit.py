"""SCRUM-90 TC-90-01..04: isolated HTTP RED tests; no database or app factory.

See docs/test-cases/SCRUM-90-safety-check-queue.md for the proposed API contract.
Reuse SCRUM-55's small query fixture to evaluate production predicates over mixed
records, rather than mocking a ready-made eligible list. It does not execute SQL.
"""

import socket
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

# Importing app otherwise loads backend/.env; these tests need no configuration file.
with mock.patch("dotenv.load_dotenv", return_value=False):
    from app.events import routes
    from app.models import EquipmentRequirement, EquipmentReservation, Event, User, Venue, VenueBooking
    from tests.test_review_requests_unit import _ReadQuery


class SafetyCheckQueueUnitTests(unittest.TestCase):
    def setUp(self):
        for target, name in ((Engine, "connect"), (Engine, "raw_connection"),
                             (socket.socket, "connect")):
            guard = mock.patch.object(target, name,
                                      side_effect=AssertionError("Database/network access in unit test"))
            guard.start()
            self.addCleanup(guard.stop)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="scrum-90-isolated-unit-secret-32-bytes")
        JWTManager(self.app)
        self.app.register_blueprint(routes.events_bp, url_prefix="/api/events")
        self.client = self.app.test_client()
        self.user = SimpleNamespace(id=90, role="safety_officer")
        self.start = datetime(2026, 12, 12, 17)
        self.end = datetime(2026, 12, 12, 20)
        clock = mock.patch.object(routes, "singapore_now", return_value=self.start - timedelta(hours=1))
        clock.start()
        self.addCleanup(clock.stop)
        self.rows = {
            Event: [self.event(1, "Reserved workshop", "Microphones and projector"),
                    self.event(2, "No equipment meeting"),
                    self.event(3, "Pending venue"),
                    self.event(4, "One requirement still missing", "Microphones and projector"),
                    self.event(5, "Unprocessed equipment note", "Speakers needed"),
                    self.event(6, "Partly reserved microphones", "Two microphones"),
                    self.event(7, "No venue booking")],
            Venue: [SimpleNamespace(id=10, name="Aurora Hall"),
                    SimpleNamespace(id=11, name="Meeting Room")],
            VenueBooking: [self.booking(1, 1), self.booking(2, 1, venue_id=11),
                           self.booking(3, 2), self.booking(4, 3, status="pending"),
                           self.booking(5, 4), self.booking(6, 5), self.booking(7, 6)],
            EquipmentRequirement: [self.requirement(101, 1, "Microphone", 2),
                                   self.requirement(102, 1, "Projector", 1),
                                   self.requirement(104, 4, "Microphone", 2),
                                   self.requirement(105, 4, "Projector", 1),
                                   self.requirement(106, 6, "Microphone", 2)],
            EquipmentReservation: [self.reservation(1, 1, 101, 1),
                                   self.reservation(2, 1, 101, 1),
                                   self.reservation(3, 1, 102, 1),
                                   self.reservation(4, 4, 104, 2),
                                   self.reservation(5, 4, 105, 1, status="released"),
                                   self.reservation(6, 6, 106, 1)],
        }
        # PR #58: closed/past events and a rescheduled event with its old booking.
        for record_id, status in ((8, "cancelled"), (9, "rejected")):
            self.rows[Event].append(self.event(record_id, status, status=status))
            self.rows[VenueBooking].append(self.booking(record_id, record_id))
        for record_id, end in ((10, self.start - timedelta(days=1)),
                               (11, self.start - timedelta(hours=1))):
            start = end - timedelta(hours=2)
            self.rows[Event].append(self.event(record_id, "Ended event", start_time=start, end_time=end))
            self.rows[VenueBooking].append(self.booking(record_id, record_id, start=start, end=end))
        self.rows[Event].append(self.event(12, "Rescheduled event", start_time=self.start + timedelta(hours=1),
                                          end_time=self.end + timedelta(hours=1)))
        self.rows[VenueBooking].append(self.booking(12, 12))
        # A wider booking and a different venue's shorter booking remain legitimate.
        self.rows[VenueBooking][0].start_time -= timedelta(hours=1)
        self.rows[VenueBooking][0].end_time += timedelta(hours=1)
        self.rows[VenueBooking][1].start_time += timedelta(minutes=30)
        self.rows[VenueBooking][1].end_time -= timedelta(minutes=30)
        # Distinct venue phases can touch; a gap between them is not coverage.
        for record_id, second_start in ((13, self.start + timedelta(hours=1)),
                                        (14, self.start + timedelta(hours=1, minutes=1))):
            self.rows[Event].append(self.event(record_id, "Venue phases"))
            self.rows[VenueBooking].extend([
                self.booking(record_id * 2, record_id, end=self.start + timedelta(hours=1)),
                self.booking(record_id * 2 + 1, record_id, venue_id=11, start=second_start),
            ])
        self.session = mock.MagicMock()
        self.session.get.side_effect = self.load
        self.session.query.side_effect = lambda model: _ReadQuery(self.rows[model])
        patcher = mock.patch.object(routes.db, "session", self.session)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.queries = {}
        for model in self.rows:
            patcher = mock.patch.object(model, "query", new_callable=mock.PropertyMock,
                                        side_effect=lambda model=model: _ReadQuery(self.rows[model]))
            self.queries[model] = patcher.start()
            self.addCleanup(patcher.stop)

    def event(self, record_id, title, note=None, **changes):
        values = {column.name: None for column in Event.__table__.columns}
        values.update(id=record_id, title=title, status="approved", organiser_id=80,
                      venue_id=10, start_time=self.start, end_time=self.end,
                      expected_attendance=60, equipment_requirements=note)
        values.update(changes)
        return SimpleNamespace(**values)

    def booking(self, record_id, event_id, venue_id=10, status="confirmed", start=None, end=None):
        return SimpleNamespace(id=record_id, event_id=event_id, venue_id=venue_id,
                               status=status, start_time=start or self.start, end_time=end or self.end)

    @staticmethod
    def requirement(record_id, event_id, equipment_type, quantity):
        return SimpleNamespace(id=record_id, event_id=event_id, equipment_type=equipment_type,
                               quantity=quantity, technical_requirements=None, status="requested")

    def reservation(self, record_id, event_id, requirement_id, quantity, status="reserved"):
        return SimpleNamespace(id=record_id, event_id=event_id, requirement_id=requirement_id,
                               resource_id=record_id, quantity=quantity, status=status,
                               start_time=self.start, end_time=self.end)

    def load(self, model, record_id, **kwargs):
        if model is User:
            return self.user if record_id == self.user.id else None
        return next((row for row in self.rows[model] if row.id == record_id), None)

    def listing(self, authenticated=True):
        headers = {}
        if authenticated:
            with self.app.app_context():
                token = create_access_token(identity=str(self.user.id))
            headers = {"Authorization": f"Bearer {token}"}
        return self.client.get("/api/events/safety-checks", headers=headers)

    # TC-90-01 / AC1: existence of a requirement or reservation is insufficient.
    def test_eligibility_uses_confirmed_bookings_and_complete_active_quantities(self):
        response = self.listing()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertCountEqual([row["id"] for row in response.get_json()["events"]], [1, 2, 13])
        self.session.commit.assert_not_called()

    # TC-90-02 / AC2: one event row even when two confirmed bookings exist.
    def test_list_contains_the_required_information_without_duplicate_events(self):
        response = self.listing()
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        workshop = [row for row in body["events"] if row["id"] == 1]
        self.assertEqual(len(workshop), 1)
        event = workshop[0]
        self.assertEqual(event["title"], "Reserved workshop")
        self.assertEqual(event["start_time"], "2026-12-12T17:00:00")
        self.assertEqual(event["end_time"], "2026-12-12T20:00:00")
        self.assertEqual(event["expected_attendance"], 60)
        self.assertCountEqual(event["venues"], [{"id": 10, "name": "Aurora Hall"},
                                               {"id": 11, "name": "Meeting Room"}])
        self.assertCountEqual(event["equipment"], [
            {"equipment_type": "Microphone", "quantity": 2, "reserved_quantity": 2},
            {"equipment_type": "Projector", "quantity": 1, "reserved_quantity": 1},
        ])
        self.assertEqual(next(row for row in body["events"] if row["id"] == 2)["equipment"], [])
        self.assertIsNone(body["message"])

    # TC-90-03 / AC3: positive Safety Officer access is exercised by TC-90-01/02.
    def test_unauthenticated_and_other_roles_are_denied_without_event_data(self):
        for role in (None, "admin", "coordinator", "coordinator_lead", "organiser",
                     "venue_staff", "tech_staff", "attendee"):
            with self.subTest(role=role):
                self.user.role = role
                response = self.listing(authenticated=role is not None)
                self.assertEqual(response.status_code, 401 if role is None else 403)
                body = response.get_json()
                # Missing JWTs use Flask-JWT-Extended's existing `msg` response.
                self.assertTrue(body.get("error") or (role is None and body.get("msg")))
                self.assertNotIn("events", body)
                for event in self.rows[Event]:
                    self.assertNotIn(event.title, response.get_data(as_text=True))
                self.queries[Event].assert_not_called()

    # TC-90-04 / AC4: failure after event retrieval must discard the entire list.
    def test_equipment_retrieval_failure_returns_error_without_a_partial_list(self):
        self.queries[EquipmentReservation].side_effect = SQLAlchemyError("Private retrieval detail")
        response = self.listing()
        self.assertEqual(response.status_code, 503, response.get_json())
        body = response.get_json()
        self.assertTrue(body.get("error"))
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("events", body)
        self.assertNotIn("Reserved workshop", response.get_data(as_text=True))
        self.assertNotIn("Private retrieval detail", response.get_data(as_text=True))
        self.queries[EquipmentReservation].assert_called()
        self.session.rollback.assert_called_once()
