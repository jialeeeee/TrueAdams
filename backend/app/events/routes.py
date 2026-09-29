import re
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from .. import tasks
from ..extensions import db
from ..models import Event, EventClarification, Notification, User, Venue

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
# A coordinator's decision on a submitted request, and the status it leads to (SCRUM-32).
DECISION_STATUSES = {"approve": "approved", "reject": "rejected"}
MAX_DECISION_WORDS = 1000
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


def _is_current_coordinator(user, event):
    return user.role == COORDINATOR_ROLE and event.coordinator_id == user.id


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

        if not _is_current_coordinator(user, event) and user.id != event.organiser_id:
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


def _own_draft(event_id):
    """The caller's draft, checked in the order 401, 404, 403, 409."""
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    event = db.session.get(Event, event_id)
    if event is None:
        raise _Rejected("Event request not found.", 404)
    if user.role != ORGANISER_ROLE or event.organiser_id != user.id:
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
        db.session.commit()
        payload = _draft_payload(event)
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
        event = _own_draft(event_id)
        # Every field is checked before any is applied, so a refused save changes nothing.
        fields = _parse_draft(request.get_json(silent=True), creating=False)
        for field, value in fields.items():
            setattr(event, field, value)
        event.last_saved_at = datetime.utcnow()
        db.session.commit()
        payload = _draft_payload(event)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        return _draft_not_saved()

    return jsonify(payload)


@events_bp.post("/drafts/<int:event_id>/submit")
@jwt_required()
def submit_draft(event_id: int):
    try:
        event = _own_draft(event_id)
        missing = [f for f in REQUIRED_FOR_SUBMISSION if getattr(event, f) is None]
        if missing:
            labels = ", ".join(DRAFT_FIELDS[f] for f in missing)
            raise _Rejected(
                f"Complete these fields before submitting: {labels}.", 400, missing=missing
            )
        if event.end_time <= event.start_time:
            raise _field_error("end_time", "The end must be after the start.")

        event.status = SUBMITTED_STATUS
        event.submitted_at = datetime.utcnow()
        db.session.commit()
        payload = _draft_payload(event)
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


def _assigned_request(event_id, denied):
    """The request, for its assigned coordinator only; checked 401, 404, 403."""
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    event = db.session.get(Event, event_id)
    if event is None:
        raise _Rejected("Event request not found.", 404)
    if not _is_current_coordinator(user, event):
        raise _Rejected(denied, 403)
    return user, event


def _parse_decision(body):
    """(status, note) from the request body; raises _Rejected if it is invalid."""
    decision = body.get("decision") if isinstance(body, dict) else None
    if decision not in DECISION_STATUSES:
        raise _Rejected("Choose whether to approve or reject the request.", 400)

    rejecting = decision == "reject"
    reason = body.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise _Rejected("The reason must be text.", 400)
    note = reason.strip() if reason else None
    note = note or None
    if rejecting and note is None:
        raise _Rejected("Enter a reason for rejecting the request.", 400)

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


def _decision_message(event, status, note):
    message = f'Your event request "{event.title}" was {status}.'
    if note:
        message += f" {'Reason' if status == 'rejected' else 'Note'}: {note}"
    return message


def _queue_decision_email(organiser, event, status, note):
    """Queue the organiser's email; False if the queue could not be reached.

    The decision and in-app notification are already saved by then, so a broker
    outage must not undo or hide a decision that was made.
    """
    try:
        tasks.send_notification_email.delay(
            organiser.email,
            f"Your event request was {status}: {event.title}",
            f"{_decision_message(event, status, note)}\n\n"
            "Sign in to ConnectSphere to see your event requests.",
        )
    except Exception:
        current_app.logger.exception("Could not queue decision email for event %s", event.id)
        return False
    return True


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
            event_id, "Only the event's assigned coordinator can approve or reject this request."
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
        # Saved in the same commit, so the organiser is never told about a decision
        # that was not saved, and a saved decision always has its notification.
        db.session.add(
            Notification(
                recipient_id=organiser.id,
                kind=f"request_{status}",
                message=_decision_message(event, status, note),
                event_id=event.id,
            )
        )
        db.session.commit()
        payload = _request_payload(event)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The decision was not saved, so the request is still submitted. Please try again.",
            503,
            retryable=True,
        )

    email_queued = _queue_decision_email(organiser, event, status, note)
    return jsonify(
        {
            "message": f"The request was {status}. {organiser.email} has been notified.",
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
                 "decided_at": _isoformat(r.decided_at), "decision_note": r.decision_note}
                for r in requests
            ],
            "message": None if requests else "You have not submitted any event requests yet.",
        }
    )
