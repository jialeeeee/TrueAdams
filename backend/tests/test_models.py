from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Event, Registration, User


def test_user_defaults_to_the_attendee_role(db):
    user = User(email="someone@test.invalid", password_hash="hash")
    db.session.add(user)
    db.session.commit()

    assert user.role == "attendee"
    assert isinstance(user.created_at, datetime)


def test_user_email_must_be_unique(db, make_user):
    make_user(email="duplicate@test.invalid")

    db.session.add(User(email="duplicate@test.invalid", password_hash="hash"))
    with pytest.raises(IntegrityError):
        db.session.commit()

    db.session.rollback()


def test_event_defaults_to_draft_status(make_event):
    event = make_event()

    assert event.status == "draft"


def test_event_requires_an_organiser(db):
    event = Event(
        title="Orphan event",
        start_time=datetime(2026, 10, 1, 9, 0),
        end_time=datetime(2026, 10, 1, 11, 0),
    )
    db.session.add(event)

    with pytest.raises(IntegrityError):
        db.session.commit()

    db.session.rollback()


def test_event_can_be_booked_into_a_venue(make_event, make_venue):
    venue = make_venue(name="Auditorium", capacity=300)
    event = make_event(venue=venue)

    assert event.venue_id == venue.id


def test_event_end_time_follows_start_time(make_event):
    event = make_event(duration=timedelta(hours=3))

    assert event.end_time - event.start_time == timedelta(hours=3)


def test_registration_links_an_attendee_to_an_event(make_registration):
    registration = make_registration()

    assert registration.event_id is not None
    assert registration.attendee_id is not None
    assert isinstance(registration.registered_at, datetime)


def test_registration_requires_an_existing_event(db, make_user):
    attendee = make_user()
    db.session.add(Registration(event_id=None, attendee_id=attendee.id))

    with pytest.raises(IntegrityError):
        db.session.commit()

    db.session.rollback()
