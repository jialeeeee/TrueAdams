from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import User, Venue

venues_bp = Blueprint("venues", __name__)

# Roles allowed to browse venues and open their details.
VENUE_VIEWER_ROLES = {"coordinator", "venue_staff"}
# Planning fields reported on the details page, in display order.
DETAIL_FIELDS = [
    "description",
    "location",
    "capacity",
    "area_sqm",
    "facilities",
    "accessibility_features",
    "room_layouts",
    "operating_hours",
    "contact_email",
    "contact_phone",
    "parking_spaces",
    "catering_available",
]


class _AccessDenied(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _error(message, status_code, **extra):
    return jsonify({"error": message, **extra}), status_code


def _require_viewer():
    try:
        user = db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        user = None
    if user is None:
        raise _AccessDenied("Your session is no longer valid. Please log in again.", 401)
    if user.role not in VENUE_VIEWER_ROLES:
        raise _AccessDenied("You are not allowed to view venues.", 403)


def _recorded(value):
    """Return the value, or None if it was never recorded (NULL or blank text)."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _summary(venue):
    return {
        "id": venue.id,
        "name": venue.name,
        "location": _recorded(venue.location),
        "capacity": venue.capacity,
        "is_available": venue.is_available,
    }


def _details(venue):
    fields = {name: _recorded(getattr(venue, name)) for name in DETAIL_FIELDS}
    return {
        "id": venue.id,
        "name": venue.name,
        "is_available": venue.is_available,
        **fields,
        "not_recorded": [name for name in DETAIL_FIELDS if fields[name] is None],
    }


def _load_failed():
    db.session.rollback()
    return _error(
        "Venue information could not be loaded. Please try again.", 503, retryable=True
    )


@venues_bp.get("/")
@jwt_required()
def list_venues():
    try:
        _require_viewer()
        venues = [_summary(v) for v in Venue.query.order_by(Venue.name).all()]
    except _AccessDenied as denied:
        return _error(denied.message, denied.status_code)
    except SQLAlchemyError:
        return _load_failed()

    return jsonify(
        {
            "venues": venues,
            "message": None if venues else "No venues have been recorded yet.",
        }
    )


@venues_bp.get("/<int:venue_id>")
@jwt_required()
def get_venue(venue_id: int):
    try:
        _require_viewer()
        venue = db.session.get(Venue, venue_id)
        details = _details(venue) if venue else None
    except _AccessDenied as denied:
        return _error(denied.message, denied.status_code)
    except SQLAlchemyError:
        return _load_failed()

    if details is None:
        return _error("Venue not found.", 404)
    return jsonify(details)


@venues_bp.post("/")
def create_venue():
    return jsonify({"message": "create venue not yet implemented"}), 501


@venues_bp.get("/<int:venue_id>/availability")
def check_availability(venue_id: int):
    return jsonify({"message": "availability check not yet implemented"}), 501
