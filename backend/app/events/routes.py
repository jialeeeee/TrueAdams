from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from .. import tasks
from ..extensions import db
from ..models import Event, EventClarification, Notification, User

events_bp = Blueprint("events", __name__)

COORDINATOR_ROLE = "coordinator"
# Roles allowed to assign, reassign and list eligible coordinators.
ASSIGNER_ROLES = {"admin", COORDINATOR_ROLE}
# Roles that work with the coordinator on an event's arrangements. The event's
# own organiser can also view its coordinator.
COORDINATOR_VIEWER_ROLES = ASSIGNER_ROLES | {"venue_staff", "tech_staff"}
NON_ASSIGNABLE_STATUSES = {"draft", "cancelled"}
# Statuses in which a request is under review, so the organiser can be asked questions.
CLARIFIABLE_STATUSES = {"submitted", "under_review"}
MAX_CLARIFICATION_WORDS = 1000
CLARIFICATION_NOTIFICATION = "clarification_requested"


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
