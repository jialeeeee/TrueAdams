import re
from datetime import date, datetime, time, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from . import scheduling
from ..extensions import db
from ..models import User, Venue

venues_bp = Blueprint("venues", __name__)

# Roles allowed to browse venues, open their details and view their availability.
VENUE_VIEWER_ROLES = {"coordinator", "venue_staff"}
# Roles allowed to search for available venues (SCRUM-37 assumption A1).
VENUE_SEARCH_ROLES = {"coordinator"}
# Longest availability range in days. A placeholder until the customer answers Q5.
MAX_RANGE_DAYS = 31
# Layouts a search can ask for.
SUPPORTED_LAYOUTS = ["theatre", "banquet", "cabaret", "cocktail", "classroom", "boardroom",
                     "u_shape"]
# List fields a search can filter on: query parameter -> Venue column.
LIST_FILTERS = {
    "facility": "facilities",
    "accessibility": "accessibility_features",
    "layout": "room_layouts",
}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLOCK = re.compile(r"^\d{2}:\d{2}$")
_WHOLE_NUMBER = re.compile(r"^\d+$")
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


def _require_viewer(roles=VENUE_VIEWER_ROLES, denied="You are not allowed to view venues."):
    try:
        user = db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        user = None
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    if user.role not in roles:
        raise _Rejected(denied, 403)


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


def _load_failed(message="Venue information could not be loaded. Please try again."):
    db.session.rollback()
    return _error(message, 503, retryable=True)


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


def _parse_clock(value, name):
    if not isinstance(value, str) or not _CLOCK.match(value):
        raise _Rejected(f"{name} must be a valid time (HH:MM).", 400)
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise _Rejected(f"{name} must be a valid time (HH:MM).", 400) from None


def _search_filters(args):
    filters = {}

    if "min_capacity" in args:
        value = args["min_capacity"].strip()
        if not _WHOLE_NUMBER.match(value) or int(value) < 1:
            raise _Rejected("Minimum capacity must be a whole number of at least 1.", 400)
        filters["min_capacity"] = int(value)

    location = args.get("location", "").strip()
    if location:
        filters["location"] = location

    for param in LIST_FILTERS:
        wanted = [v.strip() for v in args.getlist(param) if v.strip()]
        if wanted:
            filters[param] = wanted
    for layout in filters.get("layout", []):
        if layout.lower() not in SUPPORTED_LAYOUTS:
            raise _Rejected(
                f"Layout must be one of: {', '.join(SUPPORTED_LAYOUTS)}.", 400
            )

    timing = [key for key in ("date", "start", "end") if key in args]
    if timing and len(timing) < 3:
        raise _Rejected("Enter the date, start time and end time together.", 400)
    if timing:
        day = _parse_date(args["date"], "The date")
        starts = _parse_clock(args["start"], "The start time")
        ends = _parse_clock(args["end"], "The end time")
        if ends <= starts:
            raise _Rejected("The end time must be after the start time.", 400)
        filters["period"] = (datetime.combine(day, starts), datetime.combine(day, ends))

    return filters


def _matching(recorded, wanted):
    """The recorded values matching every wanted value (ignoring case), or None.

    Values that were never recorded, or recorded as none, match nothing.
    """
    if not recorded:
        return None
    wanted_keys = {w.lower() for w in wanted}
    matched = [r for r in recorded if str(r).lower() in wanted_keys]
    if {str(m).lower() for m in matched} != wanted_keys:
        return None
    return matched


def _search_result(venue, filters):
    """The search result for a venue, or None if it misses any filter."""
    if "min_capacity" in filters and (
        venue.capacity is None or venue.capacity < filters["min_capacity"]
    ):
        return None

    location = _recorded(venue.location)
    if "location" in filters and (
        location is None or filters["location"].lower() not in location.lower()
    ):
        return None

    matches = {}
    for param, field in LIST_FILTERS.items():
        if param in filters:
            matched = _matching(getattr(venue, field), filters[param])
            if matched is None:
                return None
            matches[field] = matched

    if "period" in filters:
        hours = scheduling.parse_operating_hours(venue.operating_hours)
        if not scheduling.within_hours(hours, *filters["period"]):
            return None

    return {
        "id": venue.id,
        "name": venue.name,
        "location": location,
        "capacity": venue.capacity,
        "matches": matches,
        "details_url": f"/api/venues/{venue.id}",
    }


def _search(filters):
    # Venues marked as not bookable never appear (SCRUM-37 assumption A8).
    venues = Venue.query.filter(Venue.is_available.isnot(False)).order_by(Venue.name).all()
    results = [r for r in (_search_result(v, filters) for v in venues) if r is not None]

    if "period" in filters and results:
        start, end = filters["period"]
        ids = [r["id"] for r in results]
        taken = {b.venue_id for b in scheduling.blocking_bookings(ids, start, end)}
        taken |= {b.venue_id for b in scheduling.blocks(ids, start, end)}
        results = [r for r in results if r["id"] not in taken]

    return results


@venues_bp.get("/search")
@jwt_required()
def search_venues():
    try:
        _require_viewer(VENUE_SEARCH_ROLES, "You are not allowed to search venues.")
        results = _search(_search_filters(request.args))
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code)
    except SQLAlchemyError:
        # Without the availability check, booked venues could look free, so fail the lot.
        return _load_failed("The venue search could not be completed. Please try again.")

    return jsonify(
        {
            "venues": results,
            "message": None if results
            else "No venues match your filters. Try changing or removing some.",
        }
    )
