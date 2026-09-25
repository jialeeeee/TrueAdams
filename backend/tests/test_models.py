from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.models import Event, Registration, User
from tests.base import AppTestCase


class ModelTests(AppTestCase):
    def test_user_defaults_to_the_attendee_role(self):
        user = User(email="someone@test.invalid", password_hash="hash")
        self.db.session.add(user)
        self.db.session.commit()

        self.assertEqual(user.role, "attendee")
        self.assertIsInstance(user.created_at, datetime)

    def test_user_email_must_be_unique(self):
        self.make_user(email="duplicate@test.invalid")

        self.db.session.add(User(email="duplicate@test.invalid", password_hash="hash"))
        with self.assertRaises(IntegrityError):
            self.db.session.commit()

        self.db.session.rollback()

    def test_event_defaults_to_draft_status(self):
        event = self.make_event()

        self.assertEqual(event.status, "draft")

    def test_event_requires_an_organiser(self):
        event = Event(
            title="Orphan event",
            start_time=datetime(2026, 10, 1, 9, 0),
            end_time=datetime(2026, 10, 1, 11, 0),
        )
        self.db.session.add(event)

        with self.assertRaises(IntegrityError):
            self.db.session.commit()

        self.db.session.rollback()

    def test_event_can_be_booked_into_a_venue(self):
        venue = self.make_venue(name="Auditorium", capacity=300)
        event = self.make_event(venue=venue)

        self.assertEqual(event.venue_id, venue.id)

    def test_event_end_time_follows_start_time(self):
        event = self.make_event(duration=timedelta(hours=3))

        self.assertEqual(event.end_time - event.start_time, timedelta(hours=3))

    def test_registration_links_an_attendee_to_an_event(self):
        registration = self.make_registration()

        self.assertIsNotNone(registration.event_id)
        self.assertIsNotNone(registration.attendee_id)
        self.assertIsInstance(registration.registered_at, datetime)

    def test_registration_requires_an_existing_event(self):
        attendee = self.make_user()
        self.db.session.add(Registration(event_id=None, attendee_id=attendee.id))

        with self.assertRaises(IntegrityError):
            self.db.session.commit()

        self.db.session.rollback()
