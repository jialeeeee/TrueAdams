from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.config import TestConfig
from app.extensions import celery, db as _db
from app.models import Event, Registration, Resource, User, Venue


@pytest.fixture
def app():
    """A Flask app backed by a fresh in-memory database for each test."""
    app = create_app(TestConfig)
    celery.conf.task_always_eager = True

    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    """The SQLAlchemy session, already inside an app context."""
    return _db


@pytest.fixture
def make_user(db):
    """Create a persisted User. Emails are unique per call unless given."""
    created = []

    def _make_user(email=None, role="attendee", password_hash="not-a-real-hash"):
        email = email or f"user{len(created)}@test.invalid"
        user = User(email=email, password_hash=password_hash, role=role)
        db.session.add(user)
        db.session.commit()
        created.append(user)
        return user

    return _make_user


@pytest.fixture
def make_venue(db):
    def _make_venue(name="Hall A", capacity=100, location="Level 1", is_available=True):
        venue = Venue(
            name=name, capacity=capacity, location=location, is_available=is_available
        )
        db.session.add(venue)
        db.session.commit()
        return venue

    return _make_venue


@pytest.fixture
def make_resource(db):
    def _make_resource(name="Projector", category="av", quantity_available=5):
        resource = Resource(
            name=name, category=category, quantity_available=quantity_available
        )
        db.session.add(resource)
        db.session.commit()
        return resource

    return _make_resource


@pytest.fixture
def make_event(db, make_user):
    def _make_event(
        organiser=None,
        title="Annual Conference",
        status="draft",
        venue=None,
        start_time=None,
        duration=timedelta(hours=2),
        **kwargs,
    ):
        organiser = organiser or make_user(role="organiser")
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

    return _make_event


@pytest.fixture
def make_registration(db, make_user, make_event):
    def _make_registration(event=None, attendee=None):
        event = event or make_event()
        attendee = attendee or make_user(role="attendee")
        registration = Registration(event_id=event.id, attendee_id=attendee.id)
        db.session.add(registration)
        db.session.commit()
        return registration

    return _make_registration


@pytest.fixture
def auth_headers(app):
    """Bearer-token headers for a given user.

    Unused until the auth routes are implemented, but this is how protected
    endpoints should be exercised once they are.
    """

    def _auth_headers(user):
        token = create_access_token(
            identity=str(user.id), additional_claims={"role": user.role}
        )
        return {"Authorization": f"Bearer {token}"}

    return _auth_headers
