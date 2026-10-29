"""SCRUM-93 TC-93-01..04; see docs/test-cases/SCRUM-93-confirm-event.md.

Isolated HTTP tests exercise production authorization/readiness, mocking only
persistence. One optional loopback PostgreSQL test proves real flush/rollback.
No schemas are created and no remote database is permitted.
"""

import copy
import socket
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

# This focused module needs no .env file (especially no shared database URL).
with mock.patch("dotenv.load_dotenv", return_value=False):
    from app.config import Config, TestConfig
    from app.events import routes
    from app.models import EquipmentRequirement, EquipmentReservation, Event, User, Venue, VenueBooking
    from tests.base import AppTestCase


# SCRUM-93 A1: additive confirmation action, separate from request approval.
CONFIRM_PATH = "/api/events/{event_id}/confirm"
START = datetime(2030, 1, 16, 17)
VENUE_MISSING = "Confirmed venue booking"
EQUIPMENT_MISSING = "Reserved equipment"
SAFETY_MISSING = "Approved safety check"


class _ReadQuery:
    """Evaluate the existing readiness query predicates, without executing SQL.

    Supports only the simple column predicates used here; unsupported query
    shapes fail visibly. This checks production rules, not PostgreSQL semantics.
    """

    def __init__(self, rows):
        self.rows = list(rows)

    def filter_by(self, **fields):
        return _ReadQuery(row for row in self.rows
                          if all(getattr(row, key) == value for key, value in fields.items()))

    def filter(self, *expressions):
        def matches(row, expression):
            value = getattr(row, expression.left.key)
            if expression.operator.__name__ == "in_op":
                return value in expression.right.value
            return expression.operator(value, expression.right.value)
        return _ReadQuery(row for row in self.rows
                          if all(matches(row, expression) for expression in expressions))

    def all(self):
        return list(self.rows)


class EventConfirmationUnitTests(unittest.TestCase):
    def setUp(self):
        for target, name in ((Engine, "connect"), (Engine, "raw_connection"),
                             (socket.socket, "connect")):
            guard = mock.patch.object(target, name,
                side_effect=AssertionError("Database/network access in isolated SCRUM-93 test"))
            guard.start()
            self.addCleanup(guard.stop)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, JWT_SECRET_KEY="scrum-93-isolated-secret-at-least-32-bytes")
        JWTManager(self.app)
        self.app.register_blueprint(routes.events_bp, url_prefix="/api/events")
        self.client = self.app.test_client()
        self.coordinator = SimpleNamespace(id=2, role="coordinator", email="current@test.invalid")
        self.other = SimpleNamespace(id=3, role="coordinator", email="other@test.invalid")
        self.organiser = SimpleNamespace(id=4, role="organiser", email="owner@test.invalid")
        self.event = SimpleNamespace(**{column.name: None for column in Event.__table__.columns})
        vars(self.event).update(id=1, title="Confirmation workshop", status="approved",
            organiser_id=4, coordinator_id=2, venue_id=10, start_time=START,
            end_time=START + timedelta(hours=2), expected_attendance=40,
            equipment_requirements="Two microphones and a projector", safety_decision="approved",
            safety_decided_by_id=5, safety_decided_at=START - timedelta(days=1),
            decision_note="Original request approved", decided_by_id=2,
            decided_at=START - timedelta(days=7), confirmed_by_id=None, confirmed_at=None)
        self.rows = {
            User: [self.coordinator, self.other, self.organiser], Event: [self.event],
            Venue: [SimpleNamespace(id=10, name="Hall A"), SimpleNamespace(id=11, name="Hall B")],
            # SCRUM-85/90: different venues cover touching phases, not identical periods.
            VenueBooking: [self.booking(20, 10, START, START + timedelta(hours=1)),
                           self.booking(21, 11, START + timedelta(hours=1), self.event.end_time)],
            EquipmentRequirement: [SimpleNamespace(id=30, event_id=1, equipment_type="Microphone",
                                                   quantity=2, status="requested"),
                                   SimpleNamespace(id=31, event_id=1, equipment_type="Projector",
                                                   quantity=1, status="requested")],
            EquipmentReservation: [self.reservation(40, 30), self.reservation(41, 30),
                                   self.reservation(42, 31)],
        }
        self.session = mock.MagicMock()
        self.session.get.side_effect = lambda model, key, **kwargs: next(
            (row for row in self.rows[model] if row.id == key), None)
        session = mock.patch.object(routes.db, "session", self.session)
        session.start()
        self.addCleanup(session.stop)
        self.session.query.side_effect = lambda model: _ReadQuery(self.rows[model])
        for model in self.rows:
            query = mock.patch.object(model, "query", new_callable=mock.PropertyMock,
                side_effect=lambda model=model: _ReadQuery(self.rows[model]))
            query.start()
            self.addCleanup(query.stop)
        clock = mock.patch.object(routes, "singapore_now", return_value=START - timedelta(hours=1))
        clock.start()
        self.addCleanup(clock.stop)

    @staticmethod
    def booking(key, venue_id, start, end):
        return SimpleNamespace(id=key, event_id=1, venue_id=venue_id, status="confirmed",
            start_time=start, end_time=end, setup_minutes=0, turnaround_minutes=0, hold_expires_at=None)

    @staticmethod
    def reservation(key, requirement_id):
        return SimpleNamespace(id=key, event_id=1, requirement_id=requirement_id,
            resource_id=key, quantity=1, status="reserved", start_time=START,
            end_time=START + timedelta(hours=2))

    def confirm(self, user=None, authenticated=True):
        headers = {}
        if authenticated:
            user = user or self.coordinator
            with self.app.app_context():
                token = create_access_token(identity=str(user.id), additional_claims={"role": "coordinator"})
            headers = {"Authorization": f"Bearer {token}"}
        return self.client.post(CONFIRM_PATH.format(event_id=1), json={}, headers=headers)

    def snapshot(self):
        return copy.deepcopy({model.__name__: [vars(row) for row in rows]
                              for model, rows in self.rows.items()})

    # TC-93-01 / AC1: positive current-coordinator access is also TC-93-03.
    def test_only_the_current_stored_coordinator_can_confirm(self):
        for caller in (None, self.other, self.organiser, self.coordinator):
            with self.subTest(caller=getattr(caller, "id", None)):
                # Same assigned ID and a coordinator token cannot override a changed stored role.
                if caller is self.coordinator:
                    caller.role = "admin"
                before = self.snapshot()
                response = self.confirm(caller, authenticated=caller is not None)
                self.assertEqual(response.status_code, 401 if caller is None else 403)
                body = response.get_json()
                self.assertTrue(body.get("error") or (caller is None and body.get("msg")))
                self.assertNotIn(self.event.title, response.get_data(as_text=True))
                self.assertNotIn("confirmation", body)
                self.assertEqual(self.snapshot(), before)
                self.session.commit.assert_not_called()
                self.session.add.assert_not_called()
                self.session.add_all.assert_not_called()

    # TC-93-02 / AC2: small scenarios, no unrelated lifecycle/readiness rules.
    def test_prerequisites_use_current_bookings_active_quantities_and_persisted_safety(self):
        original = copy.deepcopy(self.rows)
        scenarios = ("ready_phases", "no_equipment", "venue_gap", "equipment_partial",
                     "safety_missing", "all_missing", "unprocessed_note")
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                self.rows = copy.deepcopy(original)
                self.event = self.rows[Event][0]
                self.session.reset_mock()
                missing = []
                if scenario == "no_equipment":
                    self.rows[EquipmentRequirement] = []
                    self.rows[EquipmentReservation] = []
                    self.event.equipment_requirements = None
                if scenario == "venue_gap":
                    self.rows[VenueBooking][1].start_time += timedelta(minutes=1)
                    missing.append(VENUE_MISSING)
                if scenario == "equipment_partial":
                    self.rows[EquipmentReservation][1].status = "released"
                    missing.append(EQUIPMENT_MISSING)
                if scenario in {"safety_missing", "all_missing"}:
                    self.event.safety_decision = None
                    missing.append(SAFETY_MISSING)
                if scenario == "all_missing":
                    self.rows[VenueBooking][0].status = "tentative"
                    self.rows[EquipmentReservation] = []
                    missing.extend([VENUE_MISSING, EQUIPMENT_MISSING])
                if scenario == "unprocessed_note":
                    self.rows[EquipmentRequirement] = []
                    self.rows[EquipmentReservation] = []
                    missing.append(EQUIPMENT_MISSING)
                # Validate fixture readiness with actual SCRUM-90 rules too;
                # a missing confirmation route must not hide a broken seed.
                self.assertEqual(bool(routes._safety_check_items([self.event])),
                    not bool(set(missing) & {VENUE_MISSING, EQUIPMENT_MISSING}))
                before = self.snapshot()
                response = self.confirm()
                self.assertEqual(response.status_code, 409 if missing else 200, response.get_json())
                body = response.get_json()
                if missing:
                    self.assertCountEqual(body["missing"], missing)
                    for label in missing:
                        self.assertIn(label.lower(), body["error"].lower())
                    for label in {VENUE_MISSING, EQUIPMENT_MISSING, SAFETY_MISSING} - set(missing):
                        self.assertNotIn(label.lower(), body["error"].lower())
                    self.assertEqual(self.snapshot(), before)
                    self.session.commit.assert_not_called()
                else:
                    self.assertEqual(self.event.status, "confirmed")
                    self.session.commit.assert_called_once()

    # TC-93-03 / AC3: attribution must be mapped, separate from prior decisions.
    def test_confirmation_sets_status_and_separate_coordinator_and_utc_timestamp(self):
        before = vars(self.event).copy()
        earliest = datetime.utcnow()
        response = self.confirm()
        latest = datetime.utcnow()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue({"confirmed_by_id", "confirmed_at"}.issubset(Event.__table__.columns.keys()))
        self.assertEqual(self.event.status, "confirmed")
        self.assertEqual(self.event.confirmed_by_id, self.coordinator.id)
        self.assertIsNone(self.event.confirmed_at.tzinfo)
        self.assertLessEqual(earliest, self.event.confirmed_at)
        self.assertLessEqual(self.event.confirmed_at, latest)
        for field in before.keys() - {"status", "confirmed_by_id", "confirmed_at"}:
            self.assertEqual(getattr(self.event, field), before[field], field)
        body = response.get_json()
        self.assertEqual(body["status"], "confirmed")
        self.assertEqual(body["confirmation"], {
            "coordinator": {"id": self.coordinator.id, "email": self.coordinator.email},
            "confirmed_at": self.event.confirmed_at.isoformat(),
        })
        self.assertTrue(body.get("message"))
        self.session.commit.assert_called_once()

    # TC-93-04 / AC4: HTTP branch only; actual durability checked below.
    def test_failed_commit_returns_retryable_error_and_rolls_back(self):
        self.session.commit.side_effect = SQLAlchemyError("Private simulated save failure")
        response = self.confirm()
        self.assertEqual(response.status_code, 503, response.get_json())
        body = response.get_json()
        self.assertTrue(body.get("error"))
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("Private simulated save failure", body["error"])
        self.assertNotIn("confirmation", body)
        self.assertNotEqual(body.get("status"), "confirmed")
        self.session.commit.assert_called_once()
        self.session.rollback.assert_called_once()


class EventConfirmationLocalTests(AppTestCase):
    @classmethod
    def setUpClass(cls):
        # Guard before the app factory or any connection; never use DATABASE_URL.
        url = make_url(TestConfig.SQLALCHEMY_DATABASE_URI or "postgresql://")
        if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1", "::1"}:
            raise unittest.SkipTest("Requires a separate loopback PostgreSQL TEST_DATABASE_URL; no remote access.")
        development = make_url(Config.SQLALCHEMY_DATABASE_URI or "postgresql://")
        if (url.host, url.port, url.database) == (development.host, development.port, development.database):
            raise unittest.SkipTest("Refusing the development database; use a separate local test database.")
        super().setUpClass()

    # TC-93-03/04: one real transaction test, failure after flush then successful retry.
    def test_flushed_failure_preserves_all_event_fields_and_retry_persists_confirmation(self):
        coordinator = self.make_user(role="coordinator")
        venue = self.make_venue()
        event = self.make_event(status="approved", venue=venue, start_time=START,
            coordinator_id=coordinator.id, safety_decision="approved")
        event_id = event.id
        self.db.session.add(VenueBooking(event_id=event_id, venue_id=venue.id,
            status="confirmed", start_time=event.start_time, end_time=event.end_time))
        self.db.session.commit()
        headers = self.auth_headers(coordinator)

        def stored():
            self.db.session.expire_all()
            row = self.db.session.get(Event, event_id)
            return {column.name: getattr(row, column.name) for column in Event.__table__.columns}

        before = stored()
        flush = self.db.session.flush

        def fail_after_flush():
            self.assertEqual(event.status, "confirmed")
            self.assertEqual(event.confirmed_by_id, coordinator.id)
            self.assertIsNotNone(event.confirmed_at)
            flush()
            raise SQLAlchemyError("Private simulated save failure")

        path = CONFIRM_PATH.format(event_id=event_id)
        with mock.patch.object(self.db.session, "commit", side_effect=fail_after_flush) as commit:
            response = self.client.post(path, json={}, headers=headers)
        self.assertEqual(response.status_code, 503, response.get_json())
        commit.assert_called_once()
        self.assertTrue(response.get_json().get("error"))
        self.assertEqual(stored(), before)
        earliest = datetime.utcnow()
        response = self.client.post(path, json={}, headers=headers)
        latest = datetime.utcnow()
        self.assertEqual(response.status_code, 200, response.get_json())
        saved = stored()
        self.assertEqual(saved["status"], "confirmed")
        self.assertEqual(saved["confirmed_by_id"], coordinator.id)
        self.assertLessEqual(earliest, saved["confirmed_at"])
        self.assertLessEqual(saved["confirmed_at"], latest)
        for field in before.keys() - {"status", "confirmed_by_id", "confirmed_at"}:
            self.assertEqual(saved[field], before[field], field)
