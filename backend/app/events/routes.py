from datetime import datetime

from flask import Blueprint, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import Event, User, Venue

events_bp = Blueprint("events", __name__)

COORDINATOR_ROLE = "coordinator"
# Roles allowed to assign, reassign and list eligible coordinators.
ASSIGNER_ROLES = {"admin", COORDINATOR_ROLE}
# Roles that work with the coordinator on an event's arrangements. The event's
# own organiser can also view its coordinator.
COORDINATOR_VIEWER_ROLES = ASSIGNER_ROLES | {"venue_staff", "tech_staff"}
NON_ASSIGNABLE_STATUSES = {"draft", "cancelled"}
# Fields on the coordinator's planning view, in display order.
PLANNING_FIELDS = [
    "title",
    "description",
    "status",
    "start_time",
    "end_time",
    "venue",
    "organiser",
    "coordinator",
    "coordinator_assigned_at",
    "created_at",
]
# Limits on the fields a coordinator may change directly (the normal editing rules).
TITLE_MAX_LENGTH = 255
DESCRIPTION_MAX_LENGTH = 5000
# Statuses in which an event's planning information can no longer be edited.
NON_EDITABLE_STATUSES = {"cancelled"}


@events_bp.get("/")
def list_events():
    return jsonify([])


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


def _isoformat(value):
    return value.isoformat() if value else None


def _planning_payload(event):
    venue = db.session.get(Venue, event.venue_id) if event.venue_id else None
    organiser = db.session.get(User, event.organiser_id)
    coordinator = db.session.get(User, event.coordinator_id)
    fields = {
        "title": _recorded(event.title),
        "description": _recorded(event.description),
        "status": _recorded(event.status),
        "start_time": _isoformat(event.start_time),
        "end_time": _isoformat(event.end_time),
        "venue": {"id": venue.id, "name": venue.name, "location": venue.location}
        if venue
        else None,
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

        if user.role != COORDINATOR_ROLE or event.coordinator_id != user.id:
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


def _validate_description(value):
    if value is not None and not isinstance(value, str):
        return None, "Description must be text."
    description = (value or "").strip()
    if len(description) > DESCRIPTION_MAX_LENGTH:
        return None, f"Description must be {DESCRIPTION_MAX_LENGTH} characters or fewer."
    return description or None, None  # Blank clears it.


NORMAL_FIELD_VALIDATORS = {
    "title": _validate_title,
    "description": _validate_description,
}

# Fields whose changes affect existing arrangements, so they go through the review
# process (a change request) instead of being saved directly. In display order.
RESTRICTED_FIELD_LABELS = {
    "venue_id": "venue",
    "start_time": "start time",
    "end_time": "end time",
}


def _parse_restricted(name, value):
    """Read a restricted field's value so it can be compared with the saved one."""
    if value is None:
        return None, None
    if name == "venue_id":
        if isinstance(value, bool) or not isinstance(value, int):
            return None, "Choose a venue."
        return value, None
    problem = f"Enter the {RESTRICTED_FIELD_LABELS[name]} as a date and time."
    if not isinstance(value, str):
        return None, problem
    try:
        return datetime.fromisoformat(value), None
    except ValueError:
        return None, problem


def _validate_planning_edits(event, body):
    """Split the requested edits into values to save, corrections to make, and
    restricted changes that need review."""
    changes, corrections, needs_review = {}, {}, {}
    for name, value in body.items():
        if name in RESTRICTED_FIELD_LABELS:
            parsed, problem = _parse_restricted(name, value)
            if problem:
                corrections[name] = problem
            elif parsed != getattr(event, name):  # Unchanged values are ignored.
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

        if user.role != COORDINATOR_ROLE or event.coordinator_id != user.id:
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
    user = _current_user()
    if user is None:
        return _error("Your session is no longer valid. Please log in again.", 401)

    event = db.session.get(Event, event_id)
    if event is None:
        return _error("Event not found.", 404)

    if user.role not in COORDINATOR_VIEWER_ROLES and user.id != event.organiser_id:
        return _error("You are not allowed to view this event's coordinator.", 403)

    return jsonify(_assignment_payload(event))


@events_bp.get("/<int:event_id>/eligible-coordinators")
@jwt_required()
def list_eligible_coordinators(event_id: int):
    user = _current_user()
    if user is None:
        return _error("Your session is no longer valid. Please log in again.", 401)

    event = db.session.get(Event, event_id)
    if event is None:
        return _error("Event not found.", 404)

    if user.role not in ASSIGNER_ROLES:
        return _error("You are not allowed to assign coordinators.", 403)

    coordinators = _eligible_coordinators(event)
    return jsonify(
        {
            "event_id": event.id,
            "coordinators": [_user_summary(c) for c in coordinators],
            "message": None
            if coordinators
            else "No eligible coordinators are available for this event.",
        }
    )


@events_bp.put("/<int:event_id>/coordinator")
@jwt_required()
def assign_coordinator(event_id: int):
    user = _current_user()
    if user is None:
        return _error("Your session is no longer valid. Please log in again.", 401)

    event = db.session.get(Event, event_id)
    if event is None:
        return _error("Event not found.", 404)

    if user.role not in ASSIGNER_ROLES:
        return _error("You are not allowed to assign coordinators.", 403)

    body = request.get_json(silent=True)
    coordinator_id = body.get("coordinator_id") if isinstance(body, dict) else None
    if not isinstance(coordinator_id, int) or isinstance(coordinator_id, bool):
        return _error("coordinator_id must be an integer.", 400)

    if event.status in NON_ASSIGNABLE_STATUSES:
        return _error(
            f"A coordinator cannot be assigned to a {event.status} event.", 409
        )

    if coordinator_id == event.coordinator_id:
        return _error("This user is already the event's coordinator.", 409)

    coordinator = db.session.get(User, coordinator_id)
    if coordinator is None or coordinator.role != COORDINATOR_ROLE:
        return _error("The selected user is not an eligible coordinator.", 422)

    event.coordinator_id = coordinator.id
    event.coordinator_assigned_at = datetime.utcnow()
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The coordinator assignment could not be saved. Please try again.", 500
        )

    return jsonify(
        {
            "message": f"{coordinator.email} is now the coordinator for {event.title}.",
            **_assignment_payload(event),
        }
    )
