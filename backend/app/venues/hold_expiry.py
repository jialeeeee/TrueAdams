"""SCRUM-86: the expiry check for tentative holds, which Celery beat runs on a timer.

Each run records the holds whose expiry has passed as expired and tells their
coordinators, and warns coordinators once about holds that expire within 24 hours. An
expiry is always compared with the current Singapore time (AC7).
"""

from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from . import scheduling
from .. import tasks
from ..extensions import db
from ..local_time import singapore_now
from ..models import Event, Notification, User, Venue, VenueBooking

# How often Celery beat runs the check, so each notice arrives at most this long after
# its moment (A4; scrum lead, 29 Oct 2026; open question Q2).
HOLD_CHECK_INTERVAL_SECONDS = 300
# The coordinator is warned this long before a hold expires (AC3).
WARNING_BEFORE = timedelta(hours=24)
EXPIRING_NOTIFICATION = "venue_hold_expiring"
EXPIRED_NOTIFICATION = "venue_hold_expired"


def warned_at(expires_at, now):
    """hold_warned_at for a hold placed or changed `now`: the coordinator counts as warned
    when the expiry is within 24 hours, because the notice about the hold gives the
    expiry (A4, open question Q3). Otherwise the warning is still due."""
    return datetime.utcnow() if expires_at <= now + WARNING_BEFORE else None


def _when(value):
    return f"{value:%Y-%m-%d %H:%M}"


def _due(now):
    """The tentative holds that have expired, or are due their warning, locked so that a
    confirmation or a change of expiry at the same moment is handled one at a time."""
    return (VenueBooking.query
            .filter(VenueBooking.status == scheduling.TENTATIVE_STATUS,
                    or_(VenueBooking.hold_expires_at <= now,
                        (VenueBooking.hold_expires_at <= now + WARNING_BEFORE)
                        & VenueBooking.hold_warned_at.is_(None)))
            .order_by(VenueBooking.id).with_for_update().all())


def _record(now):
    """Record each due hold and its coordinator's notification in one commit, and return
    the emails to queue afterwards as (to, subject, body, event id)."""
    emails = []
    for hold in _due(now):
        expired = hold.hold_expires_at <= now
        if expired:
            hold.status = scheduling.EXPIRED_STATUS
        else:
            hold.hold_warned_at = datetime.utcnow()
        event = db.session.get(Event, hold.event_id) if hold.event_id else None
        coordinator = (db.session.get(User, event.coordinator_id)
                       if event and event.coordinator_id else None)
        if coordinator is None:
            continue  # Nobody to tell, but it still expires (A4).
        venue = db.session.get(Venue, hold.venue_id)
        held = (f'The tentative hold on {venue.name} for "{event.title}" '
                f"({_when(hold.start_time)} to {_when(hold.end_time)})")
        expiry = f"{_when(hold.hold_expires_at)} (Singapore time)"
        if expired:
            kind = EXPIRED_NOTIFICATION
            subject = f"Tentative hold on {venue.name} for {event.title} has expired"
            message = (f"{held} expired on {expiry}. The venue is no longer held. To use "
                       "it, submit a new venue request.")
        else:
            kind = EXPIRING_NOTIFICATION
            subject = f"Tentative hold on {venue.name} for {event.title} expires soon"
            message = (f"{held} expires on {expiry}, within 24 hours. Confirm it before "
                       "then, or the venue will no longer be held.")
        db.session.add(Notification(recipient_id=coordinator.id, kind=kind, message=message,
                                    event_id=event.id))
        emails.append((coordinator.email, subject, message, event.id))
    db.session.commit()
    return emails


def _queue_email(to_address, subject, message, event_id):
    """Queue one email after the commit. A queue outage must not undo what was recorded,
    nor stop the other emails (A4)."""
    try:
        tasks.send_notification_email.delay(
            to_address, subject,
            f"{message}\n\nSign in to ConnectSphere to see the event's planning information.")
    except Exception:
        current_app.logger.exception("Could not queue hold expiry email for event %s",
                                     event_id)


def run():
    """One expiry check (A4). If it fails, nothing changes and the next run tries again."""
    try:
        emails = _record(singapore_now())
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("The tentative hold expiry check failed")
        return
    for email in emails:
        _queue_email(*email)
