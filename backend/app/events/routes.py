from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import Event, User

events_bp = Blueprint("events", __name__)

COORDINATOR_ROLE = "coordinator"
# Roles allowed to assign, reassign and list eligible coordinators.
ASSIGNER_ROLES = {"admin", COORDINATOR_ROLE}
# Roles that work with the coordinator on an event's arrangements. The event's
# own organiser can also view its coordinator.
COORDINATOR_VIEWER_ROLES = ASSIGNER_ROLES | {"venue_staff", "tech_staff"}
NON_ASSIGNABLE_STATUSES = {"draft", "cancelled"}


@events_bp.get("/")
def list_events():
    return jsonify([])


@events_bp.post("/")
def create_event():
    return jsonify({"message": "create event not yet implemented"}), 501


@events_bp.post("/<int:event_id>/change-requests")
def submit_change_request(event_id: int):
    return jsonify({"message": "change request not yet implemented"}), 501


def _error(message, status_code):
    return jsonify({"error": message}), status_code


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
