from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..extensions import db
from ..models import Event, Registration, User

registrations_bp = Blueprint("registrations", __name__)

ATTENDEE_ROLE = "attendee"
# Only confirmed events take registrations (SCRUM-45 assumption A2, open question Q2).
CONFIRMED_STATUS = "confirmed"
REGISTERED = "registered"
WAITLISTED = "waitlisted"
# A cancelled registration is not active, so the attendee may register again (A7).
ACTIVE_STATUSES = (REGISTERED, WAITLISTED)
STATUS_LABELS = {REGISTERED: "Registered", WAITLISTED: "Waitlisted"}
# Singapore has had no daylight saving since 1982, so a fixed offset is exact and
# avoids depending on the host's time zone database.
SINGAPORE = timezone(timedelta(hours=8))

# Why a registration is blocked: the `reason` sent with HTTP 409, and its message.
BLOCKED_MESSAGES = {
    "not_confirmed": "This event is not open for registration.",
    "disabled": "Registration has not been enabled for this event.",
    "closed": "Registration for this event is closed.",
    "full": "This event is full and has no waiting list.",
}


class _Rejected(Exception):
    """A request that cannot be served, with the reply to send instead."""

    def __init__(self, message, status_code, **extra):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra


def _error(message, status_code, **extra):
    return jsonify({"error": message, **extra}), status_code


def singapore_now():
    """The current Singapore time without a time zone, as event times are stored."""
    return datetime.now(SINGAPORE).replace(tzinfo=None)


def _require_attendee():
    """The caller, checked in the database so role changes apply to existing tokens."""
    try:
        user = db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        user = None
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    if user.role != ATTENDEE_ROLE:
        raise _Rejected("Only attendees can register for events.", 403)
    return user


def _parse_event_id(body):
    event_id = body.get("event_id") if isinstance(body, dict) else None
    if isinstance(event_id, bool) or not isinstance(event_id, int):
        raise _Rejected("Choose an event to register for.", 400)
    return event_id


def _active_registration(event_id, attendee_id):
    return Registration.query.filter(
        Registration.event_id == event_id,
        Registration.attendee_id == attendee_id,
        Registration.status.in_(ACTIVE_STATUSES),
    ).first()


def _format_time(value):
    return f"{value.day} {value:%b %Y}, {value:%H:%M}"


def _blocked(event, now):
    """Why registration is not open, as (reason, message), or None if it is open.

    Places are checked separately, because a full event may still have a waiting list.
    """
    if event.status != CONFIRMED_STATUS:
        return "not_confirmed", BLOCKED_MESSAGES["not_confirmed"]
    if event.registration_required is not True or event.registration_capacity is None:
        return "disabled", BLOCKED_MESSAGES["disabled"]
    opens, closes = event.registration_opens_at, event.registration_closes_at
    if opens is None or closes is None:
        return "closed", BLOCKED_MESSAGES["closed"]
    if now < opens:
        return "not_open_yet", f"Registration for this event opens on {_format_time(opens)}."
    # The period runs up to, but not including, the closing time.
    if now >= closes:
        return "closed", BLOCKED_MESSAGES["closed"]
    return None


def _payload(registration):
    return {
        "id": registration.id,
        "event_id": registration.event_id,
        "status": registration.status,
        "registered_at": registration.registered_at.isoformat(),
    }


def _already_registered(event, registration):
    label = STATUS_LABELS[registration.status]
    where = "on the waiting list for" if registration.status == WAITLISTED else "registered for"
    return jsonify({
        "message": f"You're already {where} {event.title}. Your status is {label}.",
        "registration": _payload(registration),
        "already_registered": True,
    })


@registrations_bp.get("/")
def list_registrations():
    return jsonify([])


@registrations_bp.post("/")
@jwt_required()
def register_for_event():
    try:
        user = _require_attendee()
        event_id = _parse_event_id(request.get_json(silent=True))
        # Locked until the request ends, so two attendees can't both take the last place.
        event = (
            Event.query.filter_by(id=event_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if event is None:
            raise _Rejected("Event not found.", 404)

        # Before the other checks, so attendees still see their status once the
        # event fills up or registration closes (A8).
        existing = _active_registration(event.id, user.id)
        if existing:
            return _already_registered(event, existing)

        blocked = _blocked(event, singapore_now())
        if blocked:
            reason, message = blocked
            raise _Rejected(message, 409, reason=reason)

        taken = Registration.query.filter_by(event_id=event.id, status=REGISTERED).count()
        if taken < event.registration_capacity:
            status = REGISTERED
        elif event.waitlist_enabled:
            status = WAITLISTED
        else:
            raise _Rejected(BLOCKED_MESSAGES["full"], 409, reason="full")

        registration = Registration(event_id=event.id, attendee_id=user.id, status=status)
        db.session.add(registration)
        try:
            db.session.commit()
        except IntegrityError:
            # The same attendee registered twice at once and the unique index stopped
            # the second: show the registration that was saved.
            db.session.rollback()
            existing = _active_registration(event.id, user.id)
            if existing is None:
                raise
            return _already_registered(event, existing)
        payload = _payload(registration)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your registration was not saved. Please try again.", 503, retryable=True
        )

    if status == WAITLISTED:
        message = (
            f"{event.title} is full, so you've been added to the waiting list. "
            "Your status is Waitlisted."
        )
    else:
        message = f"You're registered for {event.title}."
    return jsonify({"message": message, "registration": payload}), 201
