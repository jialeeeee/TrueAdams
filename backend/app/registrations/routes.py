from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .. import tasks
from ..extensions import db
from ..models import Event, Notification, Registration, User

registrations_bp = Blueprint("registrations", __name__)

ATTENDEE_ROLE = "attendee"
# Only confirmed events take registrations (SCRUM-45 assumption A2, open question Q2).
CONFIRMED_STATUS = "confirmed"
REGISTERED = "registered"
WAITLISTED = "waitlisted"
# The attendee left (SCRUM-68). Not active, so they may register again (A8).
WITHDRAWN = "withdrawn"
PROMOTION_NOTIFICATION = "registration_promoted"
# The largest ID the database column holds; a bigger one cannot exist.
DB_INTEGER_MAX = 2_147_483_647
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


def _isoformat(value):
    return value.isoformat() if value else None


def _withdraw_blocked(registration, event, now):
    """Why this registration cannot be withdrawn now, as (reason, message), or None.

    Allowed until the event starts (half-open: refused from the start time) (SCRUM-68 A4).
    """
    if registration.status == WITHDRAWN:
        return "already_withdrawn", "You have already withdrawn from this event."
    if registration.status not in ACTIVE_STATUSES:
        return "already_withdrawn", "This registration is no longer active."
    if event.status == "cancelled":
        return (
            "event_cancelled",
            "This event has been cancelled, so there is nothing to withdraw from.",
        )
    started = event.start_time is not None and event.start_time <= now
    ended = event.end_time is not None and event.end_time <= now
    if started or ended:
        return (
            "event_started",
            "This event has already started, so you can no longer withdraw.",
        )
    return None


def _entry(registration, event, now):
    return {
        "id": registration.id,
        "event": {
            "id": event.id,
            "title": event.title,
            "start_time": _isoformat(event.start_time),
            "end_time": _isoformat(event.end_time),
            "status": event.status,
        },
        "status": registration.status,
        "registered_at": _isoformat(registration.registered_at),
        "can_withdraw": registration.status in ACTIVE_STATUSES
        and _withdraw_blocked(registration, event, now) is None,
    }


@registrations_bp.get("/")
@jwt_required()
def list_registrations():
    """The caller's own registrations: active ones soonest first, then the history."""
    try:
        user = _require_attendee()
        rows = (
            db.session.query(Registration, Event)
            .join(Event, Event.id == Registration.event_id)
            .filter(Registration.attendee_id == user.id)
            .all()
        )
        now = singapore_now()
        active = sorted(
            (r for r in rows if r[0].status in ACTIVE_STATUSES),
            key=lambda r: (r[1].start_time is None, r[1].start_time or datetime.min, r[0].id),
        )
        history = sorted(
            (r for r in rows if r[0].status not in ACTIVE_STATUSES),
            key=lambda r: (r[0].registered_at or datetime.min, r[0].id),
            reverse=True,
        )
        body = {
            "active": [_entry(r, e, now) for r, e in active],
            "history": [_entry(r, e, now) for r, e in history],
        }
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your registrations could not be loaded. Please try again.", 503, retryable=True
        )

    body["message"] = None if rows else "You have no registrations."
    return jsonify(body)


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


def _queue_promotion_email(to_address, title, event_id):
    """Queue the promoted attendee's email; False if the queue could not be reached.

    The promotion and in-app notification are already saved by then, so a broker outage
    must not undo them. It takes plain values, not models.
    """
    try:
        tasks.send_notification_email.delay(
            to_address,
            f"You're now registered: {title}",
            f"A place opened up, so you're now registered for {title}.\n\n"
            "Sign in to ConnectSphere to see your registrations.",
        )
    except Exception:
        current_app.logger.exception("Could not queue promotion email for event %s", event_id)
        return False
    return True


def _promote_longest_waiting(event):
    """Give a freed place to whoever has waited longest. Returns that attendee, or None.

    Whoever joined the waiting list first (then the lowest ID) goes first (A9, Q5).
    """
    taken = Registration.query.filter_by(event_id=event.id, status=REGISTERED).count()
    if event.registration_capacity is None or taken >= event.registration_capacity:
        return None
    next_in_line = (
        Registration.query.filter_by(event_id=event.id, status=WAITLISTED)
        .order_by(Registration.registered_at, Registration.id)
        .first()
    )
    if next_in_line is None:
        return None
    next_in_line.status = REGISTERED
    db.session.add(
        Notification(
            recipient_id=next_in_line.attendee_id,
            kind=PROMOTION_NOTIFICATION,
            message=f"A place opened up, so you're now registered for {event.title}.",
            event_id=event.id,
        )
    )
    return db.session.get(User, next_in_line.attendee_id)


@registrations_bp.post("/<int:registration_id>/withdraw")
@jwt_required()
def withdraw_registration(registration_id: int):
    promoted_email = None
    try:
        user = _require_attendee()
        registration = (
            db.session.get(Registration, registration_id)
            if registration_id <= DB_INTEGER_MAX
            else None
        )
        if registration is None:
            raise _Rejected("Registration not found.", 404)
        if registration.attendee_id != user.id:
            raise _Rejected("You can only withdraw your own registration.", 403)

        # Locked until the request ends, so two withdrawals can't promote the same person,
        # then read again in case the registration changed while we waited.
        event = (
            Event.query.filter_by(id=registration.event_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        registration = (
            Registration.query.filter_by(id=registration.id).populate_existing().first()
        )
        blocked = _withdraw_blocked(registration, event, singapore_now())
        if blocked:
            reason, message = blocked
            raise _Rejected(message, 409, reason=reason)

        frees_a_place = registration.status == REGISTERED
        registration.status = WITHDRAWN
        db.session.flush()
        # Only a registered place frees room; leaving the waiting list does not.
        promoted = _promote_longest_waiting(event) if frees_a_place else None
        db.session.flush()
        taken = Registration.query.filter_by(event_id=event.id, status=REGISTERED).count()
        capacity = event.registration_capacity
        payload = {
            "message": f"You've withdrawn from {event.title}.",
            "registration": _payload(registration),
            "event": {
                "id": event.id,
                "registered_count": taken,
                "slots_remaining": None if capacity is None else max(capacity - taken, 0),
            },
        }
        title, event_id = event.title, event.id
        promoted_email = promoted.email if promoted else None
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your withdrawal was not saved. Please try again.", 503, retryable=True
        )

    if promoted_email:
        _queue_promotion_email(promoted_email, title, event_id)
    return jsonify(payload)
