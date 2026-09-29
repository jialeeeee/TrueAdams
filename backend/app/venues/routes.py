import re
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from . import scheduling
from ..extensions import db
from ..models import User, Venue

venues_bp = Blueprint("venues", __name__)

# Roles allowed to browse venues, open their details and view their availability.
VENUE_VIEWER_ROLES = {"coordinator", "venue_staff"}
# Longest availability range in days. A placeholder until the customer answers Q5.
MAX_RANGE_DAYS = 31
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
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


class _Rejected(Exception):
    """A request that cannot be served, with the message and status to reply with."""

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
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    if user.role not in VENUE_VIEWER_ROLES:
        raise _Rejected("You are not allowed to view venues.", 403)


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
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code)
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
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code)
    except SQLAlchemyError:
        return _load_failed()

    if details is None:
        return _error("Venue not found.", 404)
    return jsonify(details)


@venues_bp.post("/")
def create_venue():
    return jsonify({"message": "create venue not yet implemented"}), 501


def _parse_date(value, name):
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        raise _Rejected(f"{name} must be a valid date (YYYY-MM-DD).", 400)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _Rejected(f"{name} must be a valid date (YYYY-MM-DD).", 400) from None


def _date_range(args):
    first = _parse_date(args.get("from"), "The start date")
    last = _parse_date(args["to"], "The end date") if "to" in args else first
    if last < first:
        raise _Rejected("The end date must be on or after the start date.", 400)
    if (last - first).days + 1 > MAX_RANGE_DAYS:
        raise _Rejected(f"Choose a range of at most {MAX_RANGE_DAYS} days.", 400)
    return first, last


def _period(kind, record):
    return {
        "type": kind,
        "id": record.id,
        "start": record.start_time.isoformat(),
        "end": record.end_time.isoformat(),
        "reason": getattr(record, "reason", None),
    }


def _availability(venue, first, last):
    start = datetime.combine(first, datetime.min.time())
    end = datetime.combine(last + timedelta(days=1), datetime.min.time())

    records = [("booking", b) for b in scheduling.blocking_bookings([venue.id], start, end)]
    records += [("block", b) for b in scheduling.blocks([venue.id], start, end)]
    records.sort(key=lambda r: (r[1].start_time, r[1].end_time, r[0], r[1].id))

    hours = scheduling.parse_operating_hours(venue.operating_hours)
    covered = [(r.start_time, r.end_time) for _, r in records]
    days = []
    day = first
    while day <= last:
        slots = scheduling.day_slots(day, hours, covered)
        days.append({
            "date": day.isoformat(),
            "slots": [{"start": s["start"].isoformat(), "end": s["end"].isoformat(),
                       "status": s["status"]} for s in slots],
        })
        day += timedelta(days=1)

    return {
        "venue_id": venue.id,
        "from": first.isoformat(),
        "to": last.isoformat(),
        "periods": [_period(kind, record) for kind, record in records],
        "days": days,
        "message": None if records else "No bookings or blocks are recorded for this period.",
    }


@venues_bp.get("/<int:venue_id>/availability")
@jwt_required()
def check_availability(venue_id: int):
    try:
        _require_viewer()
        first, last = _date_range(request.args)
        venue = db.session.get(Venue, venue_id)
        body = _availability(venue, first, last) if venue else None
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code)
    except SQLAlchemyError:
        # Partial data could show booked time as free, so any failure fails the lot.
        return _load_failed()

    if body is None:
        return _error("Venue not found.", 404)
    return jsonify(body)
