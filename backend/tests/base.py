import unittest
from datetime import datetime, timedelta

from flask_jwt_extended import create_access_token

from app import create_app
from app.config import TestConfig
from app.extensions import celery, db
from app.models import Event, Registration, Resource, User, Venue


class AppTestCase(unittest.TestCase):
    """Base class giving each test a Flask app backed by a fresh in-memory database."""

    def setUp(self):
        self.app = create_app(TestConfig)
        celery.conf.task_always_eager = True

        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        self.db = db
        self.client = self.app.test_client()
        self._user_count = 0

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def make_user(self, email=None, role="attendee", password_hash="not-a-real-hash"):
        """Create a persisted User. Emails are unique per call unless given."""
        email = email or f"user{self._user_count}@test.invalid"
        self._user_count += 1
        user = User(email=email, password_hash=password_hash, role=role)
        db.session.add(user)
        db.session.commit()
        return user

    def make_venue(self, name="Hall A", capacity=100, location="Level 1", is_available=True):
        venue = Venue(
            name=name, capacity=capacity, location=location, is_available=is_available
        )
        db.session.add(venue)
        db.session.commit()
        return venue

    def make_resource(self, name="Projector", category="av", quantity_available=5):
        resource = Resource(
            name=name, category=category, quantity_available=quantity_available
        )
        db.session.add(resource)
        db.session.commit()
        return resource

    def make_event(
        self,
        organiser=None,
        title="Annual Conference",
        status="draft",
        venue=None,
        start_time=None,
        duration=timedelta(hours=2),
        **kwargs,
    ):
        organiser = organiser or self.make_user(role="organiser")
        start_time = start_time or datetime(2026, 10, 1, 9, 0)
        event = Event(
            title=title,
            status=status,
            organiser_id=organiser.id,
            venue_id=venue.id if venue else None,
            start_time=start_time,
            end_time=start_time + duration,
            **kwargs,
        )
        db.session.add(event)
        db.session.commit()
        return event

    def make_registration(self, event=None, attendee=None):
        event = event or self.make_event()
        attendee = attendee or self.make_user(role="attendee")
        registration = Registration(event_id=event.id, attendee_id=attendee.id)
        db.session.add(registration)
        db.session.commit()
        return registration

    def auth_headers(self, user):
        """Bearer-token headers for a given user.

        Unused until the auth routes are implemented, but this is how protected
        endpoints should be exercised once they are.
        """
        token = create_access_token(
            identity=str(user.id), additional_claims={"role": user.role}
        )
        return {"Authorization": f"Bearer {token}"}
