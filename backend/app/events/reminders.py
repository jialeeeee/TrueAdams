"""SCRUM-99: remind coordinators about approved events with incomplete arrangements.

Celery beat runs this every REMINDER_INTERVAL_HOURS (24 by default, AC5). Each run looks at
every approved event that hasn't started and, for each one still missing something it
needs to be confirmed, sends its coordinator one reminder naming the event and listing
what is missing (AC1, AC2). The checks are confirmation's own (SCRUM-93 AC2), so a reminder
lists exactly what confirming would refuse on. An event with nothing missing, or that is
confirmed, cancelled or rejected, gets no reminder (AC3, AC4).
"""

from flask import current_app
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from .. import tasks
from ..extensions import db
from ..local_time import singapore_now
from ..models import Event, Notification, User
from .permissions import is_current_coordinator
from .routes import _missing_for_confirmation

REMINDER_NOTIFICATION = "arrangements_incomplete"
# AC4: reminders stop once the event is confirmed, cancelled or rejected, so only approved
# events are checked.
REMINDED_STATUS = "approved"


def _when(value):
    return f"{value:%Y-%m-%d %H:%M}" if value else "date not recorded"


def _due(now):
    """The approved events with a coordinator that haven't started yet (A2), oldest first."""
    return (Event.query
            .filter(Event.status == REMINDED_STATUS, Event.coordinator_id.isnot(None),
                    or_(Event.start_time.is_(None), Event.start_time > now))
            .order_by(Event.start_time.asc().nulls_last(), Event.id).all())


def _record(now):
    """Save one reminder per event that needs one, in one commit, and return the emails to
    queue afterwards as (to, subject, body, event id)."""
    emails = []
    for event in _due(now):
        coordinator = db.session.get(User, event.coordinator_id)
        # AC6: only the event's coordinator, while they still hold the role (A3).
        if not is_current_coordinator(coordinator, event):
            continue
        missing = _missing_for_confirmation(event)
        if not missing:
            continue  # AC3
        title = event.title
        message = (f'Reminder: "{title}" ({_when(event.start_time)}, Singapore time) is '
                   f"approved but can't be confirmed yet. Still missing: "
                   f"{', '.join(missing)}.")
        db.session.add(Notification(recipient_id=coordinator.id, event_id=event.id,
                                    kind=REMINDER_NOTIFICATION, message=message))
        emails.append((coordinator.email, f"Arrangements still incomplete: {title}", message,
                       event.id))
    db.session.commit()
    return emails


def _queue_email(to_address, subject, message, event_id):
    """Queue one email after the commit. AC7: a queue outage leaves the in-app reminder
    recorded, is logged, and doesn't stop the other emails."""
    try:
        tasks.send_notification_email.delay(
            to_address, subject,
            f"{message}\n\nSign in to ConnectSphere to see the event's planning information.")
    except Exception:
        current_app.logger.exception("Could not queue the reminder email for event %s",
                                     event_id)


def run():
    """One reminder run. If it fails, nothing is saved and the next run tries again."""
    try:
        emails = _record(singapore_now())
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("The incomplete arrangements reminder run failed")
        return
    for email in emails:
        _queue_email(*email)
