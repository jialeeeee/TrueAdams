import re
from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from .. import tasks
from ..extensions import db
from ..models import (
    Event,
    EventClarification,
    Notification,
    ReassignmentRequest,
    Registration,
    User,
    Venue,
)
from ..registrations.routes import singapore_now
from .permissions import (
    COORDINATOR_LEAD_ROLE,
    COORDINATOR_ROLE,
    can_reassign_coordinator,
    can_view_clarifications,
    can_view_coordinator,
    is_current_coordinator as _is_current_coordinator,
    is_current_organiser,
)

events_bp = Blueprint("events", __name__)

NON_ASSIGNABLE_STATUSES = {"draft", "cancelled"}
# Fields on the coordinator's planning view, in display order.
PLANNING_FIELDS = [
    "title",
    "purpose",
    "description",
    "status",
    "start_time",
    "end_time",
    "venue",
    "expected_attendance",
    "venue_requirements",
    "accessibility_needs",
    "equipment_requirements",
    "registration_required",
    "organiser",
    "coordinator",
    "coordinator_assigned_at",
    "created_at",
]
# Limits on the text a coordinator may change directly (the normal editing rules).
# The title's limit is TITLE_MAX_LENGTH, below.
DESCRIPTION_MAX_LENGTH = 5000
# Statuses in which an event's planning information can no longer be edited.
NON_EDITABLE_STATUSES = {"cancelled"}
# Statuses in which a request is under review, so the organiser can be asked questions.
CLARIFIABLE_STATUSES = {"submitted", "under_review"}
MAX_CLARIFICATION_WORDS = 1000
CLARIFICATION_NOTIFICATION = "clarification_requested"

ORGANISER_ROLE = "organiser"
DRAFT_STATUS = "draft"
SUBMITTED_STATUS = "submitted"
# SCRUM-55 confirmed queue eligibility; decision eligibility remains separate.
REVIEW_QUEUE_STATUSES = {"submitted", "under_review"}
# A coordinator's decision on a submitted request, and the status it leads to (SCRUM-32).
DECISION_STATUSES = {"approve": "approved", "reject": "rejected"}
MAX_DECISION_WORDS = 1000
# Shown when a rejection reason has no visible character (SCRUM-60 A3).
REASON_REQUIRED = "A reason is required to reject this request."
# Audit times are naive UTC. Singapore is UTC+8 all year (no daylight saving), so the
# organiser's plain-text notification and email can show the decision time locally
# (SCRUM-60 A2, open question Q2).
SINGAPORE_UTC_OFFSET = timedelta(hours=8)
# Every field an organiser fills in on an event request, in display order, with the
# label used in error messages.
DRAFT_FIELDS = {
    "title": "Event name",
    "purpose": "Purpose",
    "description": "Description",
    "start_time": "Start",
    "end_time": "End",
    "expected_attendance": "Expected attendance",
    "venue_requirements": "Venue requirements",
    "accessibility_needs": "Accessibility needs",
    "equipment_requirements": "Equipment requirements",
    "registration_required": "Attendee registration needed",
}
DRAFT_TEXT_FIELDS = {"title", "purpose", "description", "venue_requirements",
                     "accessibility_needs", "equipment_requirements"}
DRAFT_TIME_FIELDS = {"start_time", "end_time"}
# Accessibility needs and equipment requirements are optional (SCRUM-29 A7).
REQUIRED_FOR_SUBMISSION = [
    "title", "purpose", "description", "start_time", "end_time",
    "expected_attendance", "venue_requirements", "registration_required",
]
TITLE_MAX_LENGTH = 255
_LOCAL_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")

# SCRUM-74. Only published events are visible to everyone; "confirmed" is the status
# SCRUM-45 uses for events that take registrations (open question Q1).
PUBLISHED_STATUSES = {"confirmed"}
# Event IDs live in a 32-bit column; a larger ID cannot exist, and asking the database
# for one raises an error instead of finding nothing.
DB_INTEGER_MAX = 2_147_483_647
EVENT_NOT_FOUND = "Event not found."

# SCRUM-61. Must match MAX_REASON_LENGTH in frontend/src/pages/ReassignmentRequestPage.jsx.
MAX_REASON_LENGTH = 500
REASSIGNMENT_NOTIFICATION = "reassignment_requested"
PENDING = "pending"
# Statuses that end an event's life, mapped to the reason a request is refused (A7, Q5).
# `completed` is not set by any story yet; "past" also covers events whose end time has gone.
REASSIGNMENT_CLOSED_STATUSES = {"cancelled": "cancelled", "completed": "past"}
REASSIGNMENT_MESSAGES = {
    "cancelled": "A reassignment cannot be requested for a cancelled event.",
    "past": "A reassignment cannot be requested for an event that has ended.",
    "pending": "A reassignment request is already pending for this event.",
    "no_eligible_coordinators": "No eligible coordinator is available for this event.",
}


@events_bp.get("/")
@jwt_required()
def list_events():
    """The public catalogue: published events only, soonest first (SCRUM-74 A3)."""
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        events = (
            Event.query.filter(Event.status.in_(PUBLISHED_STATUSES))
            .order_by(Event.start_time.asc().nulls_last(), Event.id)
            .all()
        )
        counts = _registered_counts([event.id for event in events])
        now = singapore_now()
        items = [
            {
                "id": event.id,
                "title": _recorded(event.title),
                "start_time": _isoformat(event.start_time),
                "end_time": _isoformat(event.end_time),
                "registration_state": _registration_info(
                    event, now, counts.get(event.id, 0)
                )["state"],
            }
            for event in events
        ]
    except SQLAlchemyError:
        db.session.rollback()
        return _error("Events could not be loaded. Please try again.", 503, retryable=True)

    return jsonify({"events": items, "message": None if items else "There are no events to show."})


@events_bp.post("/")
def create_event():
    return jsonify({"message": "create event not yet implemented"}), 501


@events_bp.post("/<int:event_id>/change-requests")
def submit_change_request(event_id: int):
    return jsonify({"message": "change request not yet implemented"}), 501


def _error(message, status_code, **extra):
    return jsonify({"error": message, **extra}), status_code


def _current_user():
    """The caller's User row, so role changes apply without re-issuing tokens."""
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def _user_summary(user):
    return {"id": user.id, "email": user.email}


def _eligible_coordinators(event):
    query = User.query.filter_by(role=COORDINATOR_ROLE)
    if event.coordinator_id is not None:
        query = query.filter(User.id != event.coordinator_id)
    return query.order_by(User.email).all()


def _assignment_payload(event):
    coordinator = (
        db.session.get(User, event.coordinator_id) if event.coordinator_id else None
    )
    assigned_at = event.coordinator_assigned_at
    return {
        "event_id": event.id,
        "coordinator": _user_summary(coordinator) if coordinator else None,
        "assigned_at": assigned_at.isoformat() if assigned_at else None,
    }


def _recorded(value):
    """Return the value, or None if it was never recorded (NULL or blank text)."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _planning_payload(event):
    venue = db.session.get(Venue, event.venue_id) if event.venue_id else None
    organiser = db.session.get(User, event.organiser_id)
    coordinator = db.session.get(User, event.coordinator_id)
    fields = {
        "title": _recorded(event.title),
        "purpose": _recorded(event.purpose),
        "description": _recorded(event.description),
        "status": _recorded(event.status),
        "start_time": _isoformat(event.start_time),
        "end_time": _isoformat(event.end_time),
        "venue": {"id": venue.id, "name": venue.name, "location": venue.location}
        if venue
        else None,
        "expected_attendance": event.expected_attendance,
        "venue_requirements": _recorded(event.venue_requirements),
        "accessibility_needs": _recorded(event.accessibility_needs),
        "equipment_requirements": _recorded(event.equipment_requirements),
        "registration_required": event.registration_required,
        "organiser": _user_summary(organiser) if organiser else None,
        "coordinator": _user_summary(coordinator) if coordinator else None,
        "coordinator_assigned_at": _isoformat(event.coordinator_assigned_at),
        "created_at": _isoformat(event.created_at),
    }
    return {
        "id": event.id,
        **fields,
        "not_recorded": [name for name in PLANNING_FIELDS if fields[name] is None],
    }


@events_bp.get("/<int:event_id>/planning")
@jwt_required()
def get_planning(event_id: int):
    # Every read sits inside the try, so a partial failure (e.g. only the venue)
    # is reported as a failure rather than as a field that was never recorded.
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)

        event = db.session.get(Event, event_id)
        if event is None:
            return _error("Event not found.", 404)

        if not _is_current_coordinator(user, event):
            return _error(
                "You are not allowed to view this event's planning information.", 403
            )

        payload = _planning_payload(event)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The event's information could not be loaded. Please try again.",
            503,
            retryable=True,
        )

    return jsonify(payload)


def _validate_title(value):
    if value is not None and not isinstance(value, str):
        return None, "Title must be text."
    title = (value or "").strip()
    if not title:
        return None, "Enter a title."
    if len(title) > TITLE_MAX_LENGTH:
        return None, f"Title must be {TITLE_MAX_LENGTH} characters or fewer."
    return title, None


def _optional_text_validator(label):
    def validate(value):
        if value is not None and not isinstance(value, str):
            return None, f"{label} must be text."
        text = (value or "").strip()
        if len(text) > DESCRIPTION_MAX_LENGTH:
            return None, f"{label} must be {DESCRIPTION_MAX_LENGTH} characters or fewer."
        return text or None, None  # Blank clears it.

    return validate


NORMAL_FIELD_VALIDATORS = {
    "title": _validate_title,
    "purpose": _optional_text_validator("Purpose"),
    "description": _optional_text_validator("Description"),
    "accessibility_needs": _optional_text_validator("Accessibility needs"),
}

# Fields whose changes affect existing arrangements, so they go through the review
# process (a change request) instead of being saved directly. In display order.
RESTRICTED_FIELD_LABELS = {
    "venue_id": "venue",
    "start_time": "start time",
    "end_time": "end time",
    "expected_attendance": "expected attendance",
    "venue_requirements": "venue requirements",
    "registration_required": "registration requirement",
}


def _parse_restricted(name, value):
    """Read a restricted field's value so it can be compared with the saved one."""
    if value is None:
        return None, None
    if name == "venue_id":
        if isinstance(value, bool) or not isinstance(value, int):
            return None, "Choose a venue."
        return value, None
    if name == "expected_attendance":
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return None, "Expected attendance must be a whole number of at least 1."
        return value, None
    if name == "venue_requirements":
        return _optional_text_validator("Venue requirements")(value)
    if name == "registration_required":
        if not isinstance(value, bool):
            return None, "Say whether attendee registration is needed (yes or no)."
        return value, None
    problem = f"Enter the {RESTRICTED_FIELD_LABELS[name]} as a date and time."
    if not isinstance(value, str):
        return None, problem
    try:
        return datetime.fromisoformat(value), None
    except ValueError:
        return None, problem


def _saved_value(event, name):
    """The stored value, with text normalised the way edits are."""
    value = getattr(event, name)
    return (value.strip() or None) if isinstance(value, str) else value


def _validate_planning_edits(event, body):
    """Split the requested edits into values to save, corrections to make, and
    restricted changes that need review."""
    changes, corrections, needs_review = {}, {}, {}
    for name, value in body.items():
        if name in RESTRICTED_FIELD_LABELS:
            parsed, problem = _parse_restricted(name, value)
            if problem:
                corrections[name] = problem
            elif parsed != _saved_value(event, name):  # Unchanged values are ignored.
                needs_review[name] = value
            continue
        validate = NORMAL_FIELD_VALIDATORS.get(name)
        if validate is None:
            corrections[name] = "This field can't be changed here."
            continue
        cleaned, problem = validate(value)
        if problem:
            corrections[name] = problem
        else:
            changes[name] = cleaned
    return changes, corrections, needs_review


def _join_words(words):
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _review_required(event, needs_review):
    fields = [name for name in RESTRICTED_FIELD_LABELS if name in needs_review]
    labels = _join_words([RESTRICTED_FIELD_LABELS[name] for name in fields])
    verb, pronoun = ("affects", "it") if len(fields) == 1 else ("affect", "them")
    return {
        "fields": fields,
        "requested": {name: needs_review[name] for name in fields},
        "message": (
            f"The {labels} {verb} existing arrangements, so {pronoun} can't be changed "
            f"directly. Submit a change request to have {pronoun} reviewed."
        ),
        "next_step": {
            "action": "Submit a change request",
            "method": "POST",
            "url": url_for("events.submit_change_request", event_id=event.id),
        },
    }


@events_bp.patch("/<int:event_id>")
@jwt_required()
def update_planning(event_id: int):
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)

        event = db.session.get(Event, event_id)
        if event is None:
            return _error("Event not found.", 404)

        if not _is_current_coordinator(user, event):
            return _error("You are not allowed to edit this event.", 403)

        if event.status in NON_EDITABLE_STATUSES:
            return _error(f"This event is {event.status} and can no longer be edited.", 409)

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _error("Send the changes as a JSON object.", 400)
        if not body:
            return _error("There are no changes to save.", 422, fields={})

        changes, corrections, needs_review = _validate_planning_edits(event, body)
        review = _review_required(event, needs_review) if needs_review else None
        extra = {"requires_review": review} if review else {}
        if corrections:
            return _error(
                "Some changes could not be saved. Please correct them and try again.",
                422,
                fields=corrections,
                **extra,
            )
        if review and not changes:
            return _error(review["message"], 409, **extra)

        for name, value in changes.items():
            setattr(event, name, value)
        db.session.commit()
        payload = _planning_payload(event)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your changes could not be saved. Please try again.", 503, retryable=True
        )

    message = f"Changes saved. {review['message']}" if review else "Changes saved."
    return jsonify({"message": message, **payload, **extra})


@events_bp.get("/<int:event_id>/coordinator")
@jwt_required()
def get_coordinator(event_id: int):
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        event = db.session.get(Event, event_id)
        if event is None:
            return _error("Event not found.", 404)
        if not can_view_coordinator(user, event):
            return _error("You are not allowed to view this event's coordinator.", 403)
        payload = _assignment_payload(event)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The coordinator could not be loaded. Please try again.", 503, retryable=True)
    return jsonify(payload)


@events_bp.get("/<int:event_id>/eligible-coordinators")
@jwt_required()
def list_eligible_coordinators(event_id: int):
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        event = db.session.get(Event, event_id)
        if event is None:
            return _error("Event not found.", 404)
        if not can_reassign_coordinator(user, event):
            return _error("You are not allowed to reassign this event's coordinator.", 403)
        coordinators = _eligible_coordinators(event)
        payload = {
            "event_id": event.id,
            "coordinators": [_user_summary(c) for c in coordinators],
            "message": None
            if coordinators
            else "No eligible coordinators are available for this event.",
        }
    except SQLAlchemyError:
        db.session.rollback()
        return _error("Eligible coordinators could not be loaded. Please try again.", 503, retryable=True)
    return jsonify(payload)


@events_bp.put("/<int:event_id>/coordinator")
@jwt_required()
def assign_coordinator(event_id: int):
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        # SCRUM-27: re-read and lock before checking the relationship, so a
        # concurrent reassignment cannot authorize the former coordinator.
        event = db.session.get(Event, event_id, with_for_update=True, populate_existing=True)
        if event is None:
            return _error("Event not found.", 404)
        if not can_reassign_coordinator(user, event):
            return _error("You are not allowed to reassign this event's coordinator.", 403)

        body = request.get_json(silent=True)
        coordinator_id = body.get("coordinator_id") if isinstance(body, dict) else None
        if not isinstance(coordinator_id, int) or isinstance(coordinator_id, bool):
            return _error("coordinator_id must be an integer.", 400)
        # Do not accept forged ownership/assignment/audit fields alongside the target.
        if set(body) != {"coordinator_id"}:
            return _error("Only coordinator_id can be changed here.", 400)
        if event.status in NON_ASSIGNABLE_STATUSES:
            return _error(f"A coordinator cannot be assigned to a {event.status} event.", 409)
        if coordinator_id == event.coordinator_id:
            return _error("This user is already the event's coordinator.", 409)
        coordinator = db.session.get(User, coordinator_id)
        if coordinator is None or coordinator.role != COORDINATOR_ROLE:
            return _error("The selected user is not an eligible coordinator.", 422)

        event.coordinator_id = coordinator.id
        event.coordinator_assigned_at = datetime.utcnow()
        event.coordinator_assigned_by_id = user.id
        payload = {
            "message": f"{coordinator.email} is now the coordinator for {event.title}.",
            **_assignment_payload(event),
        }
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The coordinator assignment could not be saved. Please try again.", 503, retryable=True
        )

    return jsonify(payload)


def _clarification_payload(clarification, sender):
    return {
        "id": clarification.id,
        "event_id": clarification.event_id,
        "sender": _user_summary(sender),
        "message": clarification.message,
        "created_at": clarification.created_at.isoformat(),
    }


def _queue_clarification_email(organiser, event, sender, question):
    """Queue the organiser's email; False if the queue could not be reached.

    The question and in-app notification are already saved by then, so a broker
    outage (whatever error it raises) must not turn a sent question into a failure.
    """
    try:
        tasks.send_notification_email.delay(
            organiser.email,
            f"Question about your event request: {event.title}",
            f"{sender.email} has a question about your event request "
            f'"{event.title}":\n\n{question}\n\n'
            "Please sign in to ConnectSphere to reply.",
        )
    except Exception:
        current_app.logger.exception("Could not queue clarification email for event %s", event.id)
        return False
    return True


@events_bp.get("/<int:event_id>/clarifications")
@jwt_required()
def list_clarifications(event_id: int):
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)

        event = db.session.get(Event, event_id)
        if event is None:
            return _error("Event not found.", 404)

        if not can_view_clarifications(user, event):
            return _error(
                "You are not allowed to view this event's clarification questions.", 403
            )

        organiser = db.session.get(User, event.organiser_id)
        rows = (
            db.session.query(EventClarification, User)
            .join(User, User.id == EventClarification.sender_id)
            .filter(EventClarification.event_id == event.id)
            .order_by(EventClarification.created_at, EventClarification.id)
            .all()
        )
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The questions could not be loaded. Please try again.", 503, retryable=True
        )

    return jsonify(
        {
            "event": {
                "id": event.id,
                "title": event.title,
                "status": event.status,
                "organiser": _user_summary(organiser),
            },
            "clarifications": [_clarification_payload(c, sender) for c, sender in rows],
            "can_send": _is_current_coordinator(user, event) and event.status in CLARIFIABLE_STATUSES,
            "message": None if rows else "No questions have been sent for this event yet.",
        }
    )


@events_bp.post("/<int:event_id>/clarifications")
@jwt_required()
def send_clarification(event_id: int):
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)

        event = db.session.get(Event, event_id)
        if event is None:
            return _error("Event not found.", 404)

        if not _is_current_coordinator(user, event):
            return _error(
                "Only the event's assigned coordinator can send clarification questions.",
                403,
            )

        body = request.get_json(silent=True)
        question = body.get("message") if isinstance(body, dict) else None
        if not isinstance(question, str) or not question.strip():
            return _error("Enter a question before sending.", 400)
        question = question.strip()

        word_count = len(question.split())
        if word_count > MAX_CLARIFICATION_WORDS:
            return _error(
                f"Your question is {word_count:,} words long. The limit is "
                f"{MAX_CLARIFICATION_WORDS:,} words, so remove "
                f"{word_count - MAX_CLARIFICATION_WORDS:,} and send it again.",
                400,
            )

        if event.status not in CLARIFIABLE_STATUSES:
            return _error(
                f"Questions cannot be sent for a {event.status} event. They can only "
                "be sent while the request is being reviewed.",
                409,
            )

        organiser = db.session.get(User, event.organiser_id)
        clarification = EventClarification(
            event_id=event.id, sender_id=user.id, message=question
        )
        # Saved in the same commit, so the organiser is never told about a question
        # that was not saved, and a saved question always has its notification.
        db.session.add(clarification)
        db.session.add(
            Notification(
                recipient_id=organiser.id,
                kind=CLARIFICATION_NOTIFICATION,
                message=f'{user.email} asked a question about your event request "{event.title}".',
                event_id=event.id,
            )
        )
        db.session.commit()
        payload = _clarification_payload(clarification, user)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your question was not sent because it could not be saved. Please try again.",
            503,
            retryable=True,
        )

    email_queued = _queue_clarification_email(organiser, event, user, question)
    return (
        jsonify(
            {
                "message": f"Your question was sent to {organiser.email}.",
                "clarification": payload,
                "notification": {"in_app": True, "email_queued": email_queued},
            }
        ),
        201,
    )


# ---------- Draft event requests (SCRUM-29) ----------


class _Rejected(Exception):
    """A request that cannot be served, with the reply to send instead."""

    def __init__(self, message, status_code, **extra):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra


def _require_organiser(denied):
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    if user.role != ORGANISER_ROLE:
        raise _Rejected(denied, 403)
    return user


def _own_draft(event_id, lock=False):
    """The caller's draft, checked in the order 401, 404, 403, 409."""
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    # SCRUM-28: draft writers must see a concurrent submission before editing.
    # As in SCRUM-60, hold the row until commit and refresh the identity map.
    locking = {"with_for_update": True, "populate_existing": True} if lock else {}
    event = db.session.get(Event, event_id, **locking)
    if event is None:
        raise _Rejected("Event request not found.", 404)
    if not is_current_organiser(user, event):
        raise _Rejected("You can only open your own event requests.", 403)
    if event.status != DRAFT_STATUS:
        raise _Rejected(
            "This request has already been submitted and can no longer be edited as a draft.",
            409,
        )
    return event


def _field_error(field, message):
    return _Rejected(message, 400, field=field)


def _parse_draft_value(field, value):
    label = DRAFT_FIELDS[field]
    if field in DRAFT_TEXT_FIELDS:
        if value is None:
            return None
        if not isinstance(value, str):
            raise _field_error(field, f"{label} must be text.")
        return value.strip() or None
    if field in DRAFT_TIME_FIELDS:
        if value is None or value == "":
            return None
        if isinstance(value, str) and _LOCAL_DATETIME.match(value):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
        raise _field_error(field, f"{label} must be a valid date and time (YYYY-MM-DDTHH:MM).")
    if field == "expected_attendance":
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise _field_error(field, f"{label} must be a whole number of at least 1.")
        return value
    # registration_required
    if value is None or isinstance(value, bool):
        return value
    raise _field_error(field, f"{label} must be yes or no.")


def _parse_draft(body, creating):
    """The fields to save, all checked before anything is changed.

    Only the fields sent are returned (A6). Checks that compare fields wait for
    submission, so an unfinished draft can always be saved (A4).
    """
    if not isinstance(body, dict):
        raise _Rejected("Send the event request as JSON.", 400)
    for key in body:
        if key not in DRAFT_FIELDS:
            raise _field_error(key, f"{key} is not a field of an event request.")

    fields = {key: _parse_draft_value(key, value) for key, value in body.items()}
    if (creating or "title" in fields) and not fields.get("title"):
        raise _field_error("title", "Enter an event name to save the draft.")
    if len(fields.get("title") or "") > TITLE_MAX_LENGTH:
        raise _field_error(
            "title", f"The event name must be at most {TITLE_MAX_LENGTH} characters."
        )
    return fields


def _isoformat(value):
    return value.isoformat() if value else None


def _draft_payload(event):
    fields = {}
    for field in DRAFT_FIELDS:
        value = getattr(event, field)
        fields[field] = _isoformat(value) if field in DRAFT_TIME_FIELDS else value
    return {
        "id": event.id,
        "status": event.status,
        **fields,
        "created_at": _isoformat(event.created_at),
        "last_saved_at": _isoformat(event.last_saved_at),
        "submitted_at": _isoformat(event.submitted_at),
        "missing_for_submission": [
            field for field in REQUIRED_FOR_SUBMISSION if getattr(event, field) is None
        ],
    }


def _commit_draft_payload(event, creating=False):
    """Snapshot the response before commit expires ORM fields (SCRUM-28)."""
    if creating:
        db.session.flush()  # Obtain the ID without a post-commit refresh.
    payload = _draft_payload(event)
    try:
        db.session.commit()
    except DBAPIError as failure:
        if not failure.connection_invalidated:
            raise
        # A lost connection during COMMIT cannot establish whether it persisted.
        db.session.rollback()
        raise _Rejected(
            "We could not confirm whether your request was saved. "
            "Check your request's status before trying again.",
            503, retryable=True, outcome_uncertain=True,
        ) from failure
    return payload


def _draft_not_saved():
    db.session.rollback()
    return _error(
        "Your draft was not saved. Your changes have been kept, so please try again.",
        503,
        retryable=True,
    )


@events_bp.get("/drafts")
@jwt_required()
def list_drafts():
    try:
        user = _require_organiser("Only event organisers have draft event requests.")
        drafts = (
            Event.query.filter_by(organiser_id=user.id, status=DRAFT_STATUS)
            .order_by(Event.last_saved_at.desc().nulls_last(), Event.id.desc())
            .all()
        )
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("Your drafts could not be loaded. Please try again.", 503, retryable=True)

    return jsonify(
        {
            "drafts": [
                {"id": d.id, "title": d.title, "status": d.status,
                 "last_saved_at": _isoformat(d.last_saved_at)}
                for d in drafts
            ],
            "message": None if drafts else "You have no draft event requests.",
        }
    )


@events_bp.post("/drafts")
@jwt_required()
def create_draft():
    try:
        user = _require_organiser("Only event organisers can create event requests.")
        fields = _parse_draft(request.get_json(silent=True), creating=True)
        now = datetime.utcnow()
        event = Event(organiser_id=user.id, status=DRAFT_STATUS, created_at=now,
                      last_saved_at=now, **fields)
        db.session.add(event)
        payload = _commit_draft_payload(event, creating=True)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        return _draft_not_saved()

    return jsonify(payload), 201


@events_bp.get("/drafts/<int:event_id>")
@jwt_required()
def get_draft(event_id: int):
    try:
        payload = _draft_payload(_own_draft(event_id))
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("Your draft could not be loaded. Please try again.", 503, retryable=True)

    return jsonify(payload)


@events_bp.put("/drafts/<int:event_id>")
@jwt_required()
def save_draft(event_id: int):
    try:
        event = _own_draft(event_id, lock=True)
        # Every field is checked before any is applied, so a refused save changes nothing.
        fields = _parse_draft(request.get_json(silent=True), creating=False)
        for field, value in fields.items():
            setattr(event, field, value)
        event.last_saved_at = datetime.utcnow()
        payload = _commit_draft_payload(event)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        return _draft_not_saved()

    return jsonify(payload)


@events_bp.post("/drafts/<int:event_id>/submit")
@jwt_required()
def submit_draft(event_id: int):
    try:
        event = _own_draft(event_id, lock=True)
        missing = [f for f in REQUIRED_FOR_SUBMISSION if getattr(event, f) is None]
        if missing:
            labels = ", ".join(DRAFT_FIELDS[f] for f in missing)
            raise _Rejected(
                f"Complete these fields before submitting: {labels}.", 400, missing=missing
            )
        if event.end_time <= event.start_time:
            raise _field_error("end_time", "The end must be after the start.")

        # SCRUM-28 approved initial-assignment policy: current coordinator role,
        # lowest user ID. Manual reassignment remains a separate workflow.
        coordinator = User.query.filter_by(role=COORDINATOR_ROLE).order_by(User.id).first()
        if coordinator is None:
            raise _Rejected(
                "No coordinator is currently available. Your request is still saved "
                "as a draft, so please try again later.",
                503, retryable=True,
            )
        now = datetime.utcnow()
        event.coordinator_id = coordinator.id
        event.coordinator_assigned_at = now
        event.status = SUBMITTED_STATUS
        event.submitted_at = now
        payload = _commit_draft_payload(event)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your request was not submitted. It is still saved as a draft, so please try again.",
            503,
            retryable=True,
        )

    return jsonify(payload)


# ---------- Approving or rejecting a request (SCRUM-32) ----------


def _request_payload(event):
    """The full request with its decision, for the coordinator reviewing it."""
    fields = {}
    for field in DRAFT_FIELDS:
        value = getattr(event, field)
        fields[field] = _isoformat(value) if field in DRAFT_TIME_FIELDS else value
    decided_by = db.session.get(User, event.decided_by_id) if event.decided_by_id else None
    return {
        "id": event.id,
        "status": event.status,
        **fields,
        "submitted_at": _isoformat(event.submitted_at),
        "decided_at": _isoformat(event.decided_at),
        "decided_by": _user_summary(decided_by) if decided_by else None,
        "decision_note": event.decision_note,
    }


def _decider_summaries(events):
    """{user id: summary} for whoever decided any of `events`, loaded in one query, so
    the organiser sees who decided each outcome (SCRUM-60). None = not recorded."""
    ids = {event.decided_by_id for event in events if event.decided_by_id}
    if not ids:
        return {}
    return {user.id: _user_summary(user) for user in User.query.filter(User.id.in_(ids))}


def _assigned_request(event_id, denied, lock=False):
    """The request, for its assigned coordinator only; checked 401, 404, 403.

    With `lock`, the row is read afresh with SELECT ... FOR UPDATE, so a decision
    made meanwhile (another tab, a double click) is seen rather than overwritten:
    the second of two simultaneous decisions waits, then finds the request decided
    (SCRUM-60 A4).
    """
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    locking = {"with_for_update": True, "populate_existing": True} if lock else {}
    event = db.session.get(Event, event_id, **locking)
    if event is None:
        raise _Rejected("Event request not found.", 404)
    if not _is_current_coordinator(user, event):
        raise _Rejected(denied, 403)
    return user, event


def _has_visible_text(text):
    """False for text made only of spaces of any kind, including invisible ones such
    as non-breaking and zero-width spaces, which would show the organiser nothing
    (SCRUM-60 A3). Must match VISIBLE in frontend/src/pages/ReviewRequestPage.jsx.
    """
    return any(char.isprintable() and not char.isspace() for char in text)


def _parse_decision(body):
    """(status, note) from the request body; raises _Rejected if it is invalid."""
    decision = body.get("decision") if isinstance(body, dict) else None
    if decision not in DECISION_STATUSES:
        raise _Rejected("Choose whether to approve or reject the request.", 400)

    rejecting = decision == "reject"
    reason = body.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise _Rejected("The reason must be text.", 400, field="reason")
    note = reason.strip() if reason and _has_visible_text(reason) else None
    if rejecting and note is None:
        raise _Rejected(REASON_REQUIRED, 400, field="reason")

    if note is not None:
        word_count = len(note.split())
        if word_count > MAX_DECISION_WORDS:
            kind = "reason" if rejecting else "note"
            raise _Rejected(
                f"Your {kind} is {word_count:,} words long. The limit is "
                f"{MAX_DECISION_WORDS:,} words, so remove "
                f"{word_count - MAX_DECISION_WORDS:,} and try again.",
                400,
            )
    return DECISION_STATUSES[decision], note


def _singapore_time(utc):
    local = utc + SINGAPORE_UTC_OFFSET
    return f"{local.day} {local:%b %Y} at {local:%H:%M} (Singapore time)"


def _decision_message(event, status, note, decider):
    """The organiser's notification text: the outcome, who decided and when (SCRUM-60)."""
    message = (
        f'Your event request "{event.title}" was {status} by {decider.email} '
        f"on {_singapore_time(event.decided_at)}."
    )
    if note:
        message += f" {'Reason' if status == 'rejected' else 'Note'}: {note}"
    return message


def _queue_decision_email(to_address, title, event_id, status, message):
    """Queue the organiser's email; False if the queue could not be reached.

    The decision and in-app notification are already saved by then, so a broker
    outage must not undo or hide a decision that was made. It takes plain values,
    not models, so it never needs the database after the commit.
    """
    try:
        tasks.send_notification_email.delay(
            to_address,
            f"Your event request was {status}: {title}",
            f"{message}\n\nSign in to ConnectSphere to see your event requests.",
        )
    except Exception:
        current_app.logger.exception("Could not queue decision email for event %s", event_id)
        return False
    return True


def _review_summary_payload(event, organiser):
    return {
        "id": event.id,
        "title": _recorded(event.title),
        "organiser": _user_summary(organiser) if organiser else None,
        "start_time": _isoformat(event.start_time),
        "submitted_at": _isoformat(event.submitted_at),
        "status": event.status,
    }


@events_bp.get("/review-requests")
@jwt_required()
def list_review_requests():
    """SCRUM-55: open requests assigned to the caller's current coordinator role."""
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        if user.role != COORDINATOR_ROLE:
            return _error("Only event coordinators can view requests for review.", 403)

        events = (
            Event.query.filter_by(coordinator_id=user.id)
            .filter(Event.status.in_(REVIEW_QUEUE_STATUSES))
            .all()
        )
        # Repeated requests from one organiser need only one User lookup.
        organisers = {organiser_id: db.session.get(User, organiser_id)
                      for organiser_id in {event.organiser_id for event in events}}
        requests = [_review_summary_payload(event, organisers[event.organiser_id])
                    for event in events]
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Review requests could not be loaded. Please try again.", 503, retryable=True
        )

    return jsonify({
        "requests": requests,
        "message": None if requests else "You have no submitted event requests to review.",
    })


@events_bp.get("/<int:event_id>/review")
@jwt_required()
def review_request(event_id: int):
    try:
        _, event = _assigned_request(
            event_id, "Only the event's assigned coordinator can review this request."
        )
        payload = _request_payload(event)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The request could not be loaded. Please try again.", 503, retryable=True)

    return jsonify({"request": payload})


@events_bp.post("/<int:event_id>/decision")
@jwt_required()
def decide_request(event_id: int):
    try:
        user, event = _assigned_request(
            event_id,
            "Only the event's assigned coordinator can approve or reject this request.",
            lock=True,
        )
        status, note = _parse_decision(request.get_json(silent=True))
        if event.status != SUBMITTED_STATUS:
            raise _Rejected(
                f"This request is {event.status}; only submitted requests can be "
                "approved or rejected.",
                409,
            )

        organiser = db.session.get(User, event.organiser_id)
        event.status = status
        event.decision_note = note
        event.decided_at = datetime.utcnow()
        event.decided_by_id = user.id
        message = _decision_message(event, status, note, user)
        # Saved in the same commit, so the organiser is never told about a decision
        # that was not saved, and a saved decision always has its notification.
        db.session.add(
            Notification(
                recipient_id=organiser.id,
                kind=f"request_{status}",
                message=message,
                event_id=event.id,
            )
        )
        # Everything the reply and the email need is read before the commit. Once the
        # decision is saved, a lost connection must not turn it into "not saved", or
        # the coordinator's retry would be refused as already decided (SCRUM-60 A6).
        payload = _request_payload(event)
        organiser_email = organiser.email
        title = event.title
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The decision was not saved, so the request is still submitted. Please try again.",
            503,
            retryable=True,
        )

    email_queued = _queue_decision_email(organiser_email, title, event_id, status, message)
    return jsonify(
        {
            "message": f'You {status} "{title}". {organiser_email} has been notified.',
            "request": payload,
            "notification": {"in_app": True, "email_queued": email_queued},
        }
    )


@events_bp.get("/requests")
@jwt_required()
def list_my_requests():
    """The organiser's submitted, approved and rejected requests (drafts are separate)."""
    try:
        user = _require_organiser("Only event organisers have event requests.")
        requests = (
            Event.query.filter(Event.organiser_id == user.id, Event.status != DRAFT_STATUS)
            .order_by(Event.submitted_at.desc().nulls_last(), Event.id.desc())
            .all()
        )
        deciders = _decider_summaries(requests)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your event requests could not be loaded. Please try again.", 503, retryable=True
        )

    return jsonify(
        {
            "requests": [
                {"id": r.id, "title": r.title, "status": r.status,
                 "submitted_at": _isoformat(r.submitted_at),
                 "decided_at": _isoformat(r.decided_at), "decision_note": r.decision_note,
                 "decided_by": deciders.get(r.decided_by_id)}
                for r in requests
            ],
            "message": None if requests else "You have not submitted any event requests yet.",
        }
    )


# ---------- Drafts and submitted requests together (SCRUM-59) ----------


def _newest_first(events, field):
    """Most recent first by `field`, rows without it last, then by id (newest first)."""
    return sorted(
        events,
        key=lambda e: (getattr(e, field) is not None, getattr(e, field) or datetime.min, e.id),
        reverse=True,
    )


@events_bp.get("/mine")
@jwt_required()
def list_mine():
    """The organiser's drafts and submitted requests as two groups.

    Loaded in one query, so a request submitted while the list loads can never
    appear in both groups or in neither.
    """
    try:
        user = _require_organiser("Only event organisers have event requests.")
        events = Event.query.filter_by(organiser_id=user.id).all()
        deciders = _decider_summaries(events)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your event requests could not be loaded. Please try again.", 503, retryable=True
        )

    drafts = [e for e in events if e.status == DRAFT_STATUS]
    submitted = [e for e in events if e.status != DRAFT_STATUS]
    return jsonify(
        {
            "drafts": [
                # A blank name is sent as null, so the page shows "Untitled draft" (A6).
                {"id": d.id, "title": _recorded(d.title), "status": d.status,
                 "last_saved_at": _isoformat(d.last_saved_at)}
                for d in _newest_first(drafts, "last_saved_at")
            ],
            "submitted": [
                {"id": r.id, "title": r.title, "status": r.status,
                 "submitted_at": _isoformat(r.submitted_at),
                 "decided_at": _isoformat(r.decided_at), "decision_note": r.decision_note,
                 "decided_by": deciders.get(r.decided_by_id)}
                for r in _newest_first(submitted, "submitted_at")
            ],
            "message": None if events else "You have no event requests yet.",
        }
    )


# ---------- The coordinator's managed events (SCRUM-62) ----------


@events_bp.get("/managed")
@jwt_required()
def list_managed():
    """The events the caller currently coordinates, whatever their status (A2).

    The same rule as the planning view (_is_current_coordinator), so every listed
    event can be opened there.
    """
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        if user.role != COORDINATOR_ROLE:
            return _error("Only event coordinators have managed events.", 403)
        # Soonest proposed date first, undated last (A4, open question Q3).
        events = (
            Event.query.filter_by(coordinator_id=user.id)
            .order_by(Event.start_time.asc().nulls_last(), Event.id)
            .all()
        )
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your managed events could not be loaded. Please try again.", 503, retryable=True
        )

    return jsonify(
        {
            "events": [
                # A blank name is sent as null, so the page shows "Not recorded" (A5).
                {"id": e.id, "title": _recorded(e.title),
                 "start_time": _isoformat(e.start_time), "status": e.status}
                for e in events
            ],
            "message": None if events else "You have no events assigned to you yet.",
        }
    )


# ---------- The events a Coordinator Lead assigned (SCRUM-83) ----------

SUPERVISED_ACTIVE_STATUSES = {"submitted", "under_review", "approved", "confirmed"}


@events_bp.get("/supervised")
@jwt_required()
def list_supervised():
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        if user.role != COORDINATOR_LEAD_ROLE:
            return _error("Only Event Coordinator Leads can view the events they assigned.", 403)
        raw = request.args.get("coordinator_id", "")
        coordinator_id = None
        if raw != "":
            if not raw.isdigit():
                return _error("Choose a coordinator from the list.", 400, field="coordinator_id")
            coordinator_id = int(raw)
        rows = (
            db.session.query(Event, User)
            .join(User, User.id == Event.coordinator_id)
            .filter(Event.coordinator_assigned_by_id == user.id)
            .filter(Event.status.in_(SUPERVISED_ACTIVE_STATUSES))
            .order_by(Event.start_time.asc().nulls_last(), Event.id)
            .all()
        )
        coordinators = {}
        for event, coordinator in rows:
            coordinators[coordinator.id] = _user_summary(coordinator)
        items = []
        for event, coordinator in rows:
            if coordinator_id is None or coordinator.id == coordinator_id:
                items.append({
                    "id": event.id, "title": _recorded(event.title),
                    "start_time": _isoformat(event.start_time), "status": event.status,
                    "coordinator": _user_summary(coordinator),
                })
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The events you assigned could not be loaded. Please try again.", 503, retryable=True
        )

    if items:
        message = None
    elif coordinator_id is not None:
        message = "None of your active events are assigned to this coordinator."
    else:
        message = "You have no active events with a coordinator you assigned."
    return jsonify({
        "events": items,
        "coordinators": sorted(coordinators.values(), key=lambda c: c["email"]),
        "message": message,
    })


# ---------- View event details (SCRUM-74) ----------


def _registered_counts(event_ids):
    """How many places are taken, by event ID. Only `registered` takes a place."""
    if not event_ids:
        return {}
    rows = (
        db.session.query(Registration.event_id, func.count(Registration.id))
        .filter(Registration.event_id.in_(event_ids), Registration.status == "registered")
        .group_by(Registration.event_id)
        .all()
    )
    return dict(rows)


def _registration_info(event, now, registered):
    """The registration state (open, closed or full) and numbers shown on the event page.

    Closed wins over full. It uses the same fields and half-open period as SCRUM-45.
    """
    capacity = event.registration_capacity
    slots = None if capacity is None else max(capacity - registered, 0)
    opens, closes = event.registration_opens_at, event.registration_closes_at
    if (
        event.status not in PUBLISHED_STATUSES
        or event.registration_required is not True
        or capacity is None
        or opens is None
        or closes is None
        or now < opens
        or now >= closes
    ):
        state = "closed"
    elif slots == 0:
        state = "full"
    else:
        state = "open"
    return {
        "state": state,
        "opens_at": _isoformat(opens),
        "closes_at": _isoformat(closes),
        "capacity": capacity,
        "registered_count": registered,
        "slots_remaining": slots,
    }


def _can_view_event(user, event):
    """Published events are visible to everyone; others only to their organiser,
    their assigned coordinator and admins (SCRUM-74 A2)."""
    if event.status in PUBLISHED_STATUSES:
        return True
    return (
        user.role == "admin"
        or event.organiser_id == user.id
        or _is_current_coordinator(user, event)
    )


def _register_decision(user, event, state, my_registration):
    """(can_register, reason): why an attendee can or cannot register (SCRUM-74 A7)."""
    if user.role != "attendee":
        return False, "not_attendee"
    if my_registration is not None:
        return False, "already_registered"
    if state == "closed":
        return False, "closed"
    if state == "full":
        return False, "full"
    return True, None


@events_bp.get("/<int:event_id>")
@jwt_required()
def get_event(event_id: int):
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        event = db.session.get(Event, event_id) if event_id <= DB_INTEGER_MAX else None
        # The same answer for an unknown event and one the caller may not see.
        if event is None or not _can_view_event(user, event):
            return _error(EVENT_NOT_FOUND, 404)

        registered = _registered_counts([event.id]).get(event.id, 0)
        registration = _registration_info(event, singapore_now(), registered)
        mine = Registration.query.filter(
            Registration.event_id == event.id,
            Registration.attendee_id == user.id,
            Registration.status.in_(("registered", "waitlisted")),
        ).first()
        venue = db.session.get(Venue, event.venue_id) if event.venue_id else None
        can_register, blocked_reason = _register_decision(
            user, event, registration["state"], mine
        )
        payload = {
            "id": event.id,
            "title": event.title,
            "description": _recorded(event.description),
            "status": event.status,
            "start_time": _isoformat(event.start_time),
            "end_time": _isoformat(event.end_time),
            "venue": (
                {"name": venue.name, "location": _recorded(venue.location)} if venue else None
            ),
            "registration": registration,
            "my_registration": {"id": mine.id, "status": mine.status} if mine else None,
            "can_register": can_register,
            "register_blocked_reason": blocked_reason,
            # SCRUM-61: the event page shows "Request reassignment" only to the main coordinator.
            "can_request_reassignment": _is_current_coordinator(user, event),
        }
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The event could not be loaded. Please try again.", 503, retryable=True)

    return jsonify({"event": payload})


# ---------- Request coordinator reassignment (SCRUM-61) ----------


def _reassignment_target(event_id):
    """The caller and event for a reassignment call; raises _Rejected for 401, 404, 403.

    Only the event's current main coordinator may use it (A1).
    """
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    event = db.session.get(Event, event_id) if event_id <= DB_INTEGER_MAX else None
    if event is None:
        raise _Rejected(EVENT_NOT_FOUND, 404)
    if not _is_current_coordinator(user, event):
        raise _Rejected(
            "Only the event's main coordinator can request a reassignment.", 403
        )
    return user, event


def _pending_request(event):
    return ReassignmentRequest.query.filter_by(event_id=event.id, status=PENDING).first()


def _reassignment_blocked(event, pending):
    """Why no request can be made for this event now, or None (A6, A7)."""
    closed = REASSIGNMENT_CLOSED_STATUSES.get(event.status)
    if closed:
        return closed
    if event.end_time is not None and event.end_time <= singapore_now():
        return "past"
    if pending is not None:
        return "pending"
    return None


def _reassignment_request_payload(request_row):
    return {
        "id": request_row.id,
        "event_id": request_row.event_id,
        "requester_id": request_row.requester_id,
        "coordinator_id": request_row.coordinator_id,
        "reason": request_row.reason,
        "status": request_row.status,
        "requested_at": request_row.requested_at.isoformat(),
    }


@events_bp.get("/<int:event_id>/reassignment")
@jwt_required()
def get_reassignment(event_id: int):
    try:
        user, event = _reassignment_target(event_id)
        pending = _pending_request(event)
        coordinators = _eligible_coordinators(event)
        blocked = _reassignment_blocked(event, pending)
        if blocked is None and not coordinators:
            blocked = "no_eligible_coordinators"
        payload = {
            "event": {"id": event.id, "title": event.title, "status": event.status},
            "coordinators": [_user_summary(c) for c in coordinators],
            "pending_request": _reassignment_request_payload(pending) if pending else None,
            "can_request": blocked is None,
            "blocked_reason": blocked,
            "message": REASSIGNMENT_MESSAGES.get(blocked),
        }
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The reassignment form could not be loaded. Please try again.", 503, retryable=True
        )

    return jsonify(payload)


def _parse_reassignment(body):
    """(coordinator_id, reason) from the request body; raises _Rejected if invalid."""
    if not isinstance(body, dict):
        raise _Rejected("Send the reassignment request as JSON.", 400)
    coordinator_id = body.get("coordinator_id")
    if isinstance(coordinator_id, bool) or not isinstance(coordinator_id, int):
        raise _field_error("coordinator_id", "Choose a coordinator.")
    reason = body.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise _field_error("reason", "Enter a reason for the reassignment.")
    reason = reason.strip()
    if len(reason) > MAX_REASON_LENGTH:
        raise _field_error(
            "reason", f"The reason must be {MAX_REASON_LENGTH} characters or fewer."
        )
    return coordinator_id, reason


def _queue_reassignment_email(to_address, title, requester_email, event_id):
    """Queue the selected coordinator's email; False if the queue could not be reached.

    The request and in-app notification are already saved by then, so a broker outage
    must not turn a saved request into a failure. It takes plain values, not models.
    """
    try:
        tasks.send_notification_email.delay(
            to_address,
            f"Reassignment request: {title}",
            f"{requester_email} has asked you to take over the event \"{title}\".\n\n"
            "Sign in to ConnectSphere to see the request.",
        )
    except Exception:
        current_app.logger.exception(
            "Could not queue reassignment email for event %s", event_id
        )
        return False
    return True


@events_bp.post("/<int:event_id>/reassignment")
@jwt_required()
def request_reassignment(event_id: int):
    try:
        user, event = _reassignment_target(event_id)
        blocked = _reassignment_blocked(event, _pending_request(event))
        if blocked:
            raise _Rejected(REASSIGNMENT_MESSAGES[blocked], 409, reason=blocked)
        coordinator_id, reason = _parse_reassignment(request.get_json(silent=True))
        # The same rule as the list, so the two can never disagree (A2).
        coordinator = next(
            (c for c in _eligible_coordinators(event) if c.id == coordinator_id), None
        )
        if coordinator is None:
            raise _Rejected("The selected user is not an eligible coordinator.", 422)

        request_row = ReassignmentRequest(
            event_id=event.id,
            requester_id=user.id,
            coordinator_id=coordinator.id,
            reason=reason,
            status=PENDING,
        )
        db.session.add(request_row)
        # Plain values, so nothing needs the database after the commit.
        title, requester_email, to_address = event.title, user.email, coordinator.email
        db.session.add(
            Notification(
                recipient_id=coordinator.id,
                kind=REASSIGNMENT_NOTIFICATION,
                message=(
                    f"{requester_email} has asked you to take over the event "
                    f'"{title}". Open the event to see their reason.'
                ),
                event_id=event.id,
            )
        )
        try:
            db.session.flush()
            payload = _reassignment_request_payload(request_row)
            db.session.commit()
        except IntegrityError:
            # Two requests at once: the unique index let only one through.
            db.session.rollback()
            raise _Rejected(
                REASSIGNMENT_MESSAGES[PENDING], 409, reason="pending"
            )
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("Your request was not saved. Please try again.", 503, retryable=True)

    queued = _queue_reassignment_email(to_address, title, requester_email, event_id)
    return (
        jsonify(
            {
                "message": f"Your request was sent to {to_address}.",
                "request": payload,
                "notification": {"in_app": True, "email_queued": queued},
            }
        ),
        201,
    )
