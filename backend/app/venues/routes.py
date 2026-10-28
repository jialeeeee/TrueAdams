import re
from datetime import date, datetime, time, timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from . import scheduling
from .. import tasks
from ..events.permissions import is_current_coordinator
from ..extensions import db
from ..local_time import singapore_now
from ..models import Event, Notification, User, Venue, VenueBooking, VenueChange

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
    """A request that cannot be served, with the message, status and any extra
    response fields (e.g. `fields`) to reply with."""

    def __init__(self, message, status_code, **extra):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra


def _error(message, status_code, **extra):
    return jsonify({"error": message, **extra}), status_code


def _require_viewer(roles=VENUE_VIEWER_ROLES, denied="You are not allowed to view venues."):
    """Load the stored caller; roles=None defers permission until after record lookup."""
    try:
        user = db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        user = None
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    if roles is not None and user.role not in roles:
        raise _Rejected(denied, 403)
    return user


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


# ---------- Maintain the venue catalogue (SCRUM-63) ----------

CATALOGUE_ROLES = {"venue_staff"}
_CATALOGUE_DENIED = "Only Venue Staff can add or edit venues."
# The defined lists a venue's facilities and accessibility features come from, so they can
# be used as search filters. Layouts are the keys a search already understands.
# Assumption A3: the lists in the SCRUM-63 test cases; the customer has not given more.
FACILITY_OPTIONS = ["Projector", "Microphone", "Video conferencing"]
ACCESSIBILITY_OPTIONS = ["Wheelchair ramp", "Hearing loop"]
LAYOUT_OPTIONS = ["theatre", "classroom", "boardroom", "banquet"]
# Catalogue field -> (label used in messages, defined list).
_LIST_FIELDS = {
    "facilities": ("Facilities", FACILITY_OPTIONS),
    "accessibility_features": ("Accessibility features", ACCESSIBILITY_OPTIONS),
    "room_layouts": ("Layouts", LAYOUT_OPTIONS),
}
CATALOGUE_FIELDS = ["name", "location", "capacity", *_LIST_FIELDS, "operating_hours"]
REQUIRED_FIELDS = {"name": "Name", "location": "Location", "capacity": "Capacity"}
TEXT_MAX_LENGTH = 255  # Venue.name and Venue.location columns.


def _catalogue_problems(body, creating):
    """(values, problems): the cleaned values for the fields sent, and a message for every
    invalid one, so they can all be corrected at once (SCRUM-63 AC5)."""
    values, problems = {}, {}
    for key in body:
        if key not in CATALOGUE_FIELDS:
            problems[key] = f"{key} cannot be set here."

    for key, label in REQUIRED_FIELDS.items():
        if key not in body:
            if creating:
                problems[key] = f"{label} is required."
            continue
        if key == "capacity":
            continue
        text = body[key].strip() if isinstance(body[key], str) else None
        if not text:
            problems[key] = f"{label} is required."
        elif len(text) > TEXT_MAX_LENGTH:
            problems[key] = f"{label} must be at most {TEXT_MAX_LENGTH} characters."
        else:
            values[key] = text

    if "capacity" in body:
        capacity = body["capacity"]
        if capacity is None or (isinstance(capacity, str) and not capacity.strip()):
            problems["capacity"] = "Capacity is required."
        else:
            whole = _whole_number(capacity)
            if whole is None:
                problems["capacity"] = "Capacity must be a whole number."
            elif whole < 1:
                problems["capacity"] = "Capacity must be a whole number of at least 1."
            else:
                values["capacity"] = whole

    for key, (label, options) in _LIST_FIELDS.items():
        if key not in body:
            continue
        chosen = body[key]
        if not isinstance(chosen, list) or not all(isinstance(item, str) for item in chosen):
            problems[key] = f"{label} must be chosen from the list."
            continue
        by_name = {option.lower(): option for option in options}
        unknown = [item for item in chosen if item.strip().lower() not in by_name]
        if unknown:
            problems[key] = f"{label} must be chosen from the list: {', '.join(unknown)} is not an option."
            continue
        values[key] = list(dict.fromkeys(by_name[item.strip().lower()] for item in chosen))

    if "operating_hours" in body:
        hours = body["operating_hours"]
        if hours is None or (isinstance(hours, str) and not hours.strip()):
            values["operating_hours"] = None  # Not recorded.
        elif not isinstance(hours, str) or not scheduling.parse_operating_hours(hours):
            problems["operating_hours"] = (
                "Operating hours must look like 'Mon-Fri 09:00-18:00' "
                "(separate several parts with commas).")
        else:
            values["operating_hours"] = hours.strip()
    return values, problems


def _whole_number(value):
    """The int for a whole number (4, 4.0 or "4"), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str) and re.fullmatch(r"-?\d+(\.0+)?", value.strip()):
        return int(float(value.strip()))
    return None


def _check_catalogue_request(body, creating):
    if not isinstance(body, dict):
        raise _Rejected("Send the venue details as a JSON object.", 400, fields={})
    values, problems = _catalogue_problems(body, creating)
    if problems:
        # Name the first problem in full so the whole reply says what to fix.
        raise _Rejected(next(iter(problems.values())), 400, fields=problems)
    return values


def _save_failed():
    db.session.rollback()
    return _error("The venue could not be saved. Your entries were not lost; please try again.",
                  503, retryable=True)


@venues_bp.get("/options")
@jwt_required()
def venue_options():
    try:
        _require_viewer(CATALOGUE_ROLES, _CATALOGUE_DENIED)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code)
    except SQLAlchemyError:
        return _load_failed()
    return jsonify({key: list(options) for key, (_, options) in _LIST_FIELDS.items()})


@venues_bp.post("/")
@jwt_required()
def create_venue():
    try:
        user = _require_viewer(CATALOGUE_ROLES, _CATALOGUE_DENIED)
        values = _check_catalogue_request(request.get_json(silent=True), creating=True)
        venue = Venue(**values)
        db.session.add(venue)
        db.session.flush()
        db.session.add(VenueChange(
            venue_id=venue.id, action="added", changed_by_id=user.id,
            changes={key: {"from": None, "to": value} for key, value in values.items()}))
        db.session.commit()
        payload = _details(venue)
    except _Rejected as rejected:
        db.session.rollback()
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        return _save_failed()
    return jsonify({"message": f"{payload['name']} was added to the catalogue.",
                    "venue": payload}), 201


@venues_bp.put("/<int:venue_id>")
@jwt_required()
def update_venue(venue_id: int):
    try:
        user = _require_viewer(CATALOGUE_ROLES, _CATALOGUE_DENIED)
        venue = db.session.get(Venue, venue_id)
        if venue is None:
            raise _Rejected("Venue not found.", 404)
        values = _check_catalogue_request(request.get_json(silent=True), creating=False)
        changes = {}
        for key, value in values.items():
            old = getattr(venue, key)
            if old != value:
                changes[key] = {"from": old, "to": value}
                setattr(venue, key, value)
        if changes:
            db.session.add(VenueChange(
                venue_id=venue.id, action="edited", changed_by_id=user.id, changes=changes))
        db.session.commit()
        payload = _details(venue)
    except _Rejected as rejected:
        db.session.rollback()
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        return _save_failed()
    return jsonify({"message": f"{payload['name']} was updated.", "venue": payload})


@venues_bp.get("/<int:venue_id>/history")
@jwt_required()
def venue_history(venue_id: int):
    try:
        _require_viewer(CATALOGUE_ROLES, _CATALOGUE_DENIED)
        if db.session.get(Venue, venue_id) is None:
            raise _Rejected("Venue not found.", 404)
        rows = (VenueChange.query.filter_by(venue_id=venue_id)
                .order_by(VenueChange.changed_at, VenueChange.id).all())
        history = []
        for row in rows:
            who = db.session.get(User, row.changed_by_id)
            history.append({
                "action": row.action,
                "changed_by": {"id": who.id, "email": who.email},
                "changed_at": row.changed_at.isoformat(),
                "changes": row.changes,
            })
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code)
    except SQLAlchemyError:
        return _load_failed()
    return jsonify({"history": history})


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


def _timing(record):
    """For a booking or hold with setup or turnaround: its event time, setup and
    turnaround (SCRUM-84 A1, A4); `start`/`end` beside it are the occupied period. Empty
    when it has neither, so such periods look as they did before SCRUM-84."""
    if not (record.setup_minutes or record.turnaround_minutes):
        return {}
    return {
        "event_start": record.start_time.isoformat(),
        "event_end": record.end_time.isoformat(),
        "setup": scheduling.part(scheduling.occupied(record)[0], record.start_time),
        "turnaround": scheduling.part(record.end_time, scheduling.occupied(record)[1]),
    }


def _period(kind, record):
    start, end = scheduling.occupied(record)
    period = {
        "type": kind,
        "id": record.id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "reason": getattr(record, "reason", None),
    }
    if isinstance(record, VenueBooking):
        period.update(_timing(record))
    if kind == scheduling.HOLD:
        period["expires_at"] = record.hold_expires_at.isoformat()  # SCRUM-87 A3
    return period


def _availability(venue, first, last):
    start = datetime.combine(first, datetime.min.time())
    end = datetime.combine(last + timedelta(days=1), datetime.min.time())

    records = [(scheduling.BOOKING, b)
               for b in scheduling.blocking_bookings([venue.id], start, end)]
    records += [(scheduling.BLOCK, b) for b in scheduling.blocks([venue.id], start, end)]
    records += [(scheduling.HOLD, h)
                for h in scheduling.holds([venue.id], start, end, singapore_now())]
    records.sort(key=lambda r: (*scheduling.occupied(r[1]), r[0], r[1].id))

    hours = scheduling.parse_operating_hours(venue.operating_hours)
    covered = [(kind, *scheduling.occupied(r)) for kind, r in records]
    days = []
    day = first
    while day <= last:
        slots = scheduling.day_slots(day, hours, covered)
        days.append({
            "date": day.isoformat(),
            "slots": [{"start": s["start"].isoformat(), "end": s["end"].isoformat(),
                       "status": s["status"], "causes": s["causes"]} for s in slots],
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
        # A venue held for the time is not offered either (SCRUM-87 A3, open question Q2).
        taken |= {h.venue_id for h in scheduling.holds(ids, start, end, singapore_now())}
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


# ---------- Venue booking requests (SCRUM-39) ----------

COORDINATOR_ROLE = "coordinator"
# Roles allowed to see pending venue requests (SCRUM-39 A8, open question Q8).
BOOKING_REVIEWER_ROLES = {"venue_staff"}
# Only approved events proceed to further planning (SCRUM-39 A2, open question Q2).
REQUESTABLE_EVENT_STATUS = "approved"
PENDING = "pending"
# The editing limit for long text (SCRUM-53), reused for venue requirements (A4).
REQUIREMENTS_MAX_LENGTH = 5000
BOOKING_FIELDS = {"event_id", "venue_id", "start_time", "end_time", "venue_requirements",
                  "setup_minutes", "turnaround_minutes"}
# Longest setup or turnaround, in minutes (SCRUM-84 A2): a day, until the customer says.
MAX_BUFFER_MINUTES = 1440
_LOCAL_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")


def _is_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_local_time(value, missing, invalid):
    """(datetime, None) or (None, problem) for a "YYYY-MM-DDTHH:MM" value."""
    if value is None or value == "":
        return None, missing
    if isinstance(value, str) and _LOCAL_DATETIME.match(value):
        try:
            return datetime.fromisoformat(value), None
        except ValueError:
            pass
    return None, invalid


def _parse_minutes(value):
    """Whole minutes from 0 to MAX_BUFFER_MINUTES (blank or missing means 0), else None."""
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        value = int(value.strip())
    if isinstance(value, int) and 0 <= value <= MAX_BUFFER_MINUTES:
        return value
    return None


def _booking_problems(body):
    """Every missing or invalid detail, so they can all be corrected at once (A9)."""
    problems = {}
    for key in body:
        if key not in BOOKING_FIELDS:
            problems[key] = f"{key} is not part of a venue request."

    if not _is_id(body.get("venue_id")):
        problems["venue_id"] = "Choose a venue."

    start, start_problem = _parse_local_time(
        body.get("start_time"), "Enter the start date and time.",
        "Enter the start as a date and time (YYYY-MM-DDTHH:MM).")
    end, end_problem = _parse_local_time(
        body.get("end_time"), "Enter the end date and time.",
        "Enter the end as a date and time (YYYY-MM-DDTHH:MM).")
    if start_problem:
        problems["start_time"] = start_problem
    if end_problem:
        problems["end_time"] = end_problem
    if start and end and end <= start:
        problems["end_time"] = "The end must be after the start."
    if start and start < singapore_now():
        problems["start_time"] = "The start must not be in the past."

    for key, label in (("setup_minutes", "Setup time"), ("turnaround_minutes", "Turnaround time")):
        if key in body and _parse_minutes(body[key]) is None:
            problems[key] = (
                f"{label} must be a whole number of minutes from 0 to {MAX_BUFFER_MINUTES}.")

    requirements = body.get("venue_requirements")
    if requirements is not None and not isinstance(requirements, str):
        problems["venue_requirements"] = "The venue requirements must be text."
    elif not (requirements or "").strip():
        problems["venue_requirements"] = "Enter the venue requirements."
    elif len(requirements.strip()) > REQUIREMENTS_MAX_LENGTH:
        problems["venue_requirements"] = (
            f"The venue requirements must be {REQUIREMENTS_MAX_LENGTH:,} characters or fewer."
        )
    return problems, start, end


def _booking_payload(booking):
    event = db.session.get(Event, booking.event_id)
    venue = db.session.get(Venue, booking.venue_id)
    requester = db.session.get(User, booking.requested_by_id)
    return {
        "id": booking.id,
        "status": booking.status,
        "event": {"id": event.id, "title": event.title,
                  "expected_attendance": event.expected_attendance},
        "venue": {"id": venue.id, "name": venue.name, "location": _recorded(venue.location)},
        "start_time": booking.start_time.isoformat(),
        "end_time": booking.end_time.isoformat(),
        # SCRUM-84: the venue is occupied from the start less the setup to the end plus the
        # turnaround.
        "setup_minutes": booking.setup_minutes or 0,
        "turnaround_minutes": booking.turnaround_minutes or 0,
        "occupied_start": scheduling.occupied(booking)[0].isoformat(),
        "occupied_end": scheduling.occupied(booking)[1].isoformat(),
        "venue_requirements": booking.venue_requirements,
        "requested_by": {"id": requester.id, "email": requester.email} if requester else None,
        "requested_at": booking.created_at.isoformat(),
    }


def _own_pending_request(event, venue_id, start, end):
    """The event's pending request for the venue whose occupied period overlaps
    `start`-`end`, or None. Asking again would only repeat it (SCRUM-85 A2, Q2)."""
    query = VenueBooking.query.filter_by(event_id=event.id, venue_id=venue_id, status=PENDING)
    return scheduling.overlapping(query, VenueBooking, start, end).first()


@venues_bp.post("/bookings")
@jwt_required()
def request_booking():
    try:
        user = _require_viewer({COORDINATOR_ROLE}, "Only event coordinators can request venues.")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise _Rejected("Send the venue request as JSON.", 400)
        if not _is_id(body.get("event_id")):
            raise _Rejected(
                "Choose the event to request a venue for.", 400,
                fields={"event_id": "Choose the event to request a venue for."},
            )

        # Locked until the request ends, so two submissions for one event are serialised.
        event = db.session.get(Event, body["event_id"], with_for_update=True,
                               populate_existing=True)
        if event is None:
            raise _Rejected("Event not found.", 404)
        if not is_current_coordinator(user, event):
            raise _Rejected(
                "Only the event's assigned coordinator can request a venue for it.", 403)

        problems, start, end = _booking_problems(body)
        if problems:
            raise _Rejected(
                "Some details are missing or invalid. Please correct them and try again.",
                400, fields=problems,
            )
        venue = db.session.get(Venue, body["venue_id"])
        if venue is None:
            raise _Rejected("Venue not found.", 404)
        if event.status != REQUESTABLE_EVENT_STATUS:
            raise _Rejected(
                "A venue can only be requested for an approved event. "
                f"This event is {event.status}.", 409)

        setup = _parse_minutes(body.get("setup_minutes"))
        turnaround = _parse_minutes(body.get("turnaround_minutes"))
        # SCRUM-84 A5: a request whose occupied period clashes is refused up front.
        occupied_start = start - timedelta(minutes=setup)
        occupied_end = end + timedelta(minutes=turnaround)
        # SCRUM-85: other venues may be requested alongside, but not this one again.
        duplicate = _own_pending_request(event, venue.id, occupied_start, occupied_end)
        if duplicate:
            raise _Rejected(
                f"This event already has a pending request for {venue.name} at an overlapping "
                f"time ({_period_text(duplicate.start_time, duplicate.end_time)}). Wait for "
                "Venue Staff to decide on it, or cancel it, before asking for that venue again.",
                409, reason="already_requested", booking_id=duplicate.id)
        conflicts = _conflicts_for(venue.id, occupied_start, occupied_end)
        if conflicts:
            clash = _clash(venue, conflicts, refused="requested")
            clash.extra["occupied"] = {"start": occupied_start.isoformat(),
                                       "end": occupied_end.isoformat()}
            raise clash

        booking = VenueBooking(
            event_id=event.id, venue_id=venue.id, status=PENDING,
            start_time=start, end_time=end,
            setup_minutes=setup, turnaround_minutes=turnaround,
            venue_requirements=body["venue_requirements"].strip(),
            requested_by_id=user.id, created_at=datetime.utcnow(),
        )
        db.session.add(booking)
        db.session.commit()
        payload = _booking_payload(booking)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your venue request was not sent. Your details are still here, so please try again.",
            503, retryable=True,
        )

    return jsonify({
        "message": (
            f"Your request to book {venue.name} for {event.title} has been sent to Venue "
            "Staff. It stays pending until they decide."
        ),
        "booking": payload,
    }), 201


@venues_bp.get("/bookings")
@jwt_required()
def list_booking_requests():
    # SCRUM-69: the assigned coordinator can recover decisions from request rows,
    # independently of notification delivery/ownership. Staff's existing list is unchanged.
    if "event_id" in request.args:
        return _event_booking_requests()
    try:
        _require_viewer(BOOKING_REVIEWER_ROLES, "Only Venue Staff can view venue requests.")
        bookings = (VenueBooking.query.filter_by(status=PENDING)
                    .order_by(VenueBooking.created_at, VenueBooking.id).all())
        payloads = [_booking_payload(b) for b in bookings]
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        return _load_failed("Venue requests could not be loaded. Please try again.")

    try:
        # SCRUM-41 A2: Venue Staff see each request's conflicts before approving it.
        for payload, booking in zip(payloads, bookings):
            payload["conflicts"] = _approval_conflicts(booking)
    except SQLAlchemyError:
        # Never show a request as clear when its conflicts were not checked (A5).
        return _load_failed(
            "Availability could not be verified for the venue requests. Please try again.")

    return jsonify({
        "bookings": payloads,
        "message": None if payloads else "There are no pending venue requests.",
    })


def _booking_decision_payload(booking):
    """Request details plus the durable decision, for rejection and coordinator reads."""
    decider = db.session.get(User, booking.decided_by_id) if booking.decided_by_id else None
    return {
        **_booking_payload(booking),
        "rejection_reason": booking.rejection_reason,
        "decided_at": booking.decided_at.isoformat() if booking.decided_at else None,
        "decided_by": {"id": decider.id, "email": decider.email} if decider else None,
        "hold": _coordinator_hold(booking),  # SCRUM-87 A10
    }


def _event_booking_requests():
    """SCRUM-69: only the current coordinator may read an event's saved requests."""
    try:
        user = _require_viewer(roles=None)
        event_id = request.args.get("event_id", "")
        if not _WHOLE_NUMBER.fullmatch(event_id):
            raise _Rejected("Choose an event to view its venue requests.", 400, field="event_id")
        event = db.session.get(Event, int(event_id))
        if event is None:
            raise _Rejected("Event not found.", 404)
        if not is_current_coordinator(user, event):
            raise _Rejected("Only the event's assigned coordinator can view its venue requests.", 403)
        bookings = (VenueBooking.query.filter_by(event_id=event.id)
                    .order_by(VenueBooking.created_at.desc(), VenueBooking.id.desc()).all())
        payloads = [_booking_decision_payload(booking) for booking in bookings]
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        return _load_failed("Saved venue outcomes could not be loaded. Please try again.")
    return jsonify({
        "bookings": payloads,
        "message": None if payloads else "There are no venue requests for this event.",
    })


# ---------- Approving a venue booking request (SCRUM-40) ----------

CONFIRMED = scheduling.BLOCKING_BOOKING_STATUS
APPROVAL_NOTIFICATION = "venue_booking_approved"


def _when(value):
    return f"{value:%Y-%m-%d %H:%M}"


def _period_text(start, end):
    return f"{_when(start)} to {_when(end)}"


def _conflict(kind, record, **details):
    """One conflict entry: its kind, which record, and the (occupied) period it covers.
    A booking or hold also gives its event time, setup and turnaround (SCRUM-84 A4)."""
    start, end = scheduling.occupied(record)
    entry = {"type": kind, "id": record.id, "start": start.isoformat(), "end": end.isoformat()}
    if isinstance(record, VenueBooking):
        entry.update(_timing(record))
    return {**entry, **details}


def _approval_conflicts(booking):
    """Every prohibited conflict for approving `booking` now, in time order (A2, A3).

    Venue Staff also see these in the pending list before approving (SCRUM-41 A2).
    """
    start, end = scheduling.occupied(booking)
    return _conflicts_for(booking.venue_id, start, end)


def _conflicts_for(venue_id, start, end):
    """The conflicts for occupying `venue_id` from `start` to `end` (occupied times).

    Only that venue is checked: an event's bookings at other venues are not conflicts, so
    it can have several (SCRUM-85 A3). Its own booking at this venue is, like any other.
    """
    period = ([venue_id], start, end)
    conflicts = []
    for other in scheduling.blocking_bookings(*period):
        event = db.session.get(Event, other.event_id) if other.event_id else None
        conflicts.append(_conflict(
            "booking", other, event={"id": event.id, "title": event.title} if event else None))
    for block in scheduling.blocks(*period):
        conflicts.append(_conflict("block", block, reason=block.reason))
    # An unexpired tentative hold blocks its time until it expires (SCRUM-87 A3).
    for hold in scheduling.holds(*period, singapore_now()):
        event = db.session.get(Event, hold.event_id)
        conflicts.append(_conflict("hold", hold, event={"id": event.id, "title": event.title},
                                   expires_at=hold.hold_expires_at.isoformat()))
    return sorted(conflicts, key=lambda conflict: conflict["start"])


def _clash(venue, conflicts, refused="approved"):
    """The refusal for a booking that clashes with other arrangements at `venue`."""
    return _Rejected(
        f"This booking can't be {refused} because it clashes with other arrangements "
        f"at {venue.name}.", 409, reason="conflict", conflicts=conflicts)


def _locked_venue_and_conflicts(booking, outcome="the booking was not approved"):
    """Lock the booking's venue, then find its conflicts (A7; SCRUM-41 A5).

    Without a completed check the booking is never confirmed or held, so a database
    failure here is reported as availability that could not be verified.
    """
    try:
        venue = db.session.get(Venue, booking.venue_id, with_for_update=True)
        return venue, _approval_conflicts(booking)
    except SQLAlchemyError:
        db.session.rollback()
        raise _Rejected(
            f"The venue's availability could not be verified, so {outcome}. It is still "
            "pending. Please try again.", 503, retryable=True,
        ) from None


def _queue_email(to_address, subject, body, event_id):
    """Queue an email about a venue booking; False if the queue could not be reached.

    The change and its in-app notification are already saved by then, so a broker
    outage must not undo or hide them. It takes plain values, not models.
    """
    try:
        tasks.send_notification_email.delay(to_address, subject, body)
    except Exception:
        current_app.logger.exception("Could not queue venue booking email for event %s",
                                     event_id)
        return False
    return True


def _queue_coordinator_email(to_address, subject, message, event_id):
    """Queue the coordinator's email about a venue decision (see _queue_email)."""
    return _queue_email(
        to_address, subject,
        f"{message}\n\nSign in to ConnectSphere to see the event's planning information.",
        event_id)


@venues_bp.post("/bookings/<int:booking_id>/approve")
@jwt_required()
def approve_booking(booking_id: int):
    try:
        user = _require_viewer(BOOKING_REVIEWER_ROLES,
                               "Only Venue Staff can approve venue requests.")
        # The booking and its venue are locked until the decision is saved, so two
        # staff approving the same or overlapping requests are handled one at a time (A7).
        booking = db.session.get(VenueBooking, booking_id, with_for_update=True,
                                 populate_existing=True)
        if booking is None:
            raise _Rejected("Booking request not found.", 404)
        if booking.status != PENDING:
            raise _Rejected(
                f"This request is {booking.status}, so it can no longer be approved.",
                409, reason="not_pending")
        event = db.session.get(Event, booking.event_id)
        if event.status != REQUESTABLE_EVENT_STATUS:
            raise _Rejected(
                f"The event is {event.status}, so its venue booking can't be approved.",
                409, reason="event_not_approved")
        if booking.start_time <= singapore_now():
            raise _Rejected(
                "The requested time has already started, so the booking can't be approved.",
                409, reason="already_started")
        venue, conflicts = _locked_venue_and_conflicts(booking)
        if conflicts:
            raise _clash(venue, conflicts)
        # The event's first confirmed venue is its venue; later ones leave it (SCRUM-85 A4).
        first_venue = VenueBooking.query.filter_by(event_id=event.id,
                                                   status=CONFIRMED).first() is None

        booking.status = CONFIRMED
        booking.decided_at = datetime.utcnow()
        booking.decided_by_id = user.id
        if first_venue:
            event.venue_id = venue.id
        try:
            # Written now, so the database rule is checked before anything is announced.
            db.session.flush()
        except IntegrityError:
            # SCRUM-41 A4: the database rule refused it, so a clashing booking at this
            # venue was confirmed by code that did not take the venue lock.
            db.session.rollback()
            raise _clash(venue, _approval_conflicts(booking)) from None
        coordinator = db.session.get(User, event.coordinator_id)
        message = (
            f'Your venue request for "{event.title}" at {venue.name} '
            f"({_period_text(booking.start_time, booking.end_time)}) was approved by "
            f"{user.email}."
        )
        # Saved in the same commit, so the coordinator is never told about an approval
        # that was not saved, and a saved approval always has its notification.
        db.session.add(Notification(recipient_id=coordinator.id, kind=APPROVAL_NOTIFICATION,
                                    message=message, event_id=event.id))
        # Everything the reply and the email need is read before the commit.
        payload = {
            **_booking_payload(booking),
            "decided_at": booking.decided_at.isoformat(),
            "decided_by": {"id": user.id, "email": user.email},
        }
        to_address, title, venue_name, event_id = (coordinator.email, event.title,
                                                    venue.name, event.id)
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The approval was not saved, so the request is still pending. Please try again.",
            503, retryable=True,
        )

    email_queued = _queue_coordinator_email(
        to_address, f"Venue confirmed for {title}: {venue_name}", message, event_id)
    return jsonify({
        "message": f"You approved {venue_name} for {title}. {to_address} has been notified.",
        "booking": payload,
        "notification": {"in_app": True, "email_queued": email_queued},
    })


# ---------- Rejecting a pending request (SCRUM-69) ----------

# AC3 specifies characters, independently of the event decision's word limit.
MAX_REJECTION_REASON_LENGTH = 500
REJECTION_NOTIFICATION = "venue_booking_rejected"


def _rejection_reason(body):
    if not isinstance(body, dict):
        raise _Rejected("Send the rejection as JSON.", 400)
    reason = body.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise _Rejected("The rejection reason must be text.", 400, field="reason")
    reason = (reason or "").strip()
    if not reason:
        raise _Rejected("A rejection reason is required.", 400, field="reason")
    if len(reason) > MAX_REJECTION_REASON_LENGTH:
        raise _Rejected(
            f"The rejection reason must be {MAX_REJECTION_REASON_LENGTH} characters or fewer.",
            400, field="reason")
    return reason


@venues_bp.post("/bookings/<int:booking_id>/reject")
@jwt_required()
def reject_booking(booking_id: int):
    try:
        # Load the user first, then the record, then check permission (AGENTS.md).
        user = _require_viewer(roles=None)
        booking = db.session.get(VenueBooking, booking_id, with_for_update=True,
                                 populate_existing=True)
        if booking is None:
            raise _Rejected("Booking request not found.", 404)
        if user.role not in BOOKING_REVIEWER_ROLES:
            raise _Rejected("Only Venue Staff can reject venue requests.", 403)
        reason = _rejection_reason(request.get_json(silent=True))
        if booking.status != PENDING:
            raise _Rejected(
                f"This request is {booking.status}, so it can no longer be rejected.",
                409, reason="not_pending")
        event = db.session.get(Event, booking.event_id, with_for_update=True,
                               populate_existing=True) if booking.event_id else None
        coordinator = (db.session.get(User, event.coordinator_id)
                       if event and event.coordinator_id else None)
        if event is None or coordinator is None:
            raise _Rejected(
                "The request needs an event with an assigned coordinator before it can be rejected.",
                409)
        venue = db.session.get(Venue, booking.venue_id)
        # Retain the request row and all arrangements; rejecting reserves nothing.
        booking.status = "rejected"
        booking.rejection_reason = reason
        booking.decided_at = datetime.utcnow()
        booking.decided_by_id = user.id
        message = (
            f'Your venue request for "{event.title}" at {venue.name} '
            f"({_period_text(booking.start_time, booking.end_time)}) was rejected by "
            f"{user.email}. Reason: {reason}"
        )
        db.session.add(Notification(recipient_id=coordinator.id, kind=REJECTION_NOTIFICATION,
                                    message=message, event_id=event.id))
        payload = _booking_decision_payload(booking)
        to_address, title, venue_name, event_id = (coordinator.email, event.title,
                                                  venue.name, event.id)
        # A saved rejection must always have its in-app notification, and vice versa.
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The rejection was not saved. Please try again.", 503, retryable=True)

    email_queued = _queue_coordinator_email(
        to_address, f"Venue request rejected for {title}: {venue_name}", message, event_id)
    return jsonify({
        "message": f"The venue request for {title} at {venue_name} was rejected.",
        "booking": payload,
        "notification": {"in_app": True, "email_queued": email_queued},
    })


# ---------- Tentative holds (SCRUM-87) ----------

TENTATIVE = scheduling.TENTATIVE_STATUS
HOLD_PLACED_NOTIFICATION = "venue_hold_placed"
HOLD_CHANGED_NOTIFICATION = "venue_hold_expiry_changed"
# The only field a hold or a change of its expiry takes (A2).
HOLD_FIELDS = {"expires_at"}


def _hold_expiry(body, booking):
    """The expiry Venue Staff entered: later than now and no later than the start (A2)."""
    body = body if isinstance(body, dict) else {}
    for key in body:
        if key not in HOLD_FIELDS:
            raise _Rejected(f"{key} is not part of a hold.", 400, field=key)
    expires_at, problem = _parse_local_time(
        body.get("expires_at"), "Enter the hold's expiry date and time.",
        "Enter the expiry as a date and time (YYYY-MM-DDTHH:MM).")
    if problem:
        raise _Rejected(problem, 400, field="expires_at")
    if expires_at <= singapore_now():
        raise _Rejected("The expiry must be in the future.", 400, field="expires_at")
    # A hold can't outlast the time it holds (open question Q1).
    if expires_at > booking.start_time:
        raise _Rejected(
            "The hold must expire no later than the booking's start "
            f"({_when(booking.start_time)}).", 400, field="expires_at")
    return expires_at


def _hold_payload(booking):
    holder = db.session.get(User, booking.held_by_id)
    return {
        **_booking_payload(booking),
        "hold": {
            "held_at": booking.held_at.isoformat(),
            "held_by": {"id": holder.id, "email": holder.email},
            "expires_at": booking.hold_expires_at.isoformat(),
        },
    }


def _coordinator_hold(booking):
    """What the coordinator sees of a hold: its expiry and whether that has passed, by
    A3's rule; None for any other booking (A10, open question Q5)."""
    if booking.status != TENTATIVE:
        return None
    return {"expires_at": booking.hold_expires_at.isoformat(),
            "expired": booking.hold_expires_at <= singapore_now()}


@venues_bp.post("/bookings/<int:booking_id>/hold")
@jwt_required()
def place_hold(booking_id: int):
    try:
        user = _require_viewer(BOOKING_REVIEWER_ROLES,
                               "Only Venue Staff can place tentative holds.")
        # Locked as for an approval, so decisions on one venue are made one at a time (A4).
        booking = db.session.get(VenueBooking, booking_id, with_for_update=True,
                                 populate_existing=True)
        if booking is None:
            raise _Rejected("Booking request not found.", 404)
        expires_at = _hold_expiry(request.get_json(silent=True), booking)
        if booking.status != PENDING:
            raise _Rejected(
                f"This request is {booking.status}, so it can't be placed on hold.",
                409, reason="not_pending")
        event = db.session.get(Event, booking.event_id)
        if event.status != REQUESTABLE_EVENT_STATUS:
            raise _Rejected(
                f"The event is {event.status}, so its venue booking can't be placed on hold.",
                409, reason="event_not_approved")
        venue, conflicts = _locked_venue_and_conflicts(booking, "no hold was placed")
        if conflicts:
            raise _clash(venue, conflicts, refused="placed on hold")

        # The hold starts now (A1); the event's venue and status are unchanged.
        booking.status = TENTATIVE
        booking.held_at = datetime.utcnow()
        booking.held_by_id = user.id
        booking.hold_expires_at = expires_at
        coordinator = db.session.get(User, event.coordinator_id)
        message = (
            f'{user.email} placed a tentative hold on {venue.name} for "{event.title}" '
            f"({_period_text(booking.start_time, booking.end_time)}). It expires on "
            f"{_when(expires_at)} (Singapore time)."
        )
        # Saved in the same commit as the hold (A6).
        db.session.add(Notification(recipient_id=coordinator.id, kind=HOLD_PLACED_NOTIFICATION,
                                    message=message, event_id=event.id))
        payload = _hold_payload(booking)
        to_address, title, venue_name, event_id = (coordinator.email, event.title,
                                                    venue.name, event.id)
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The hold was not saved, so the request is still pending. Please try again.",
            503, retryable=True,
        )

    email_queued = _queue_coordinator_email(
        to_address, f"Tentative hold on {venue_name} for {title}", message, event_id)
    return jsonify({
        "message": (
            f"You placed a tentative hold on {venue_name} for {title} until "
            f"{_when(expires_at)}. {to_address} has been notified."
        ),
        "booking": payload,
        "notification": {"in_app": True, "email_queued": email_queued},
    })


@venues_bp.patch("/bookings/<int:booking_id>/hold")
@jwt_required()
def change_hold_expiry(booking_id: int):
    try:
        user = _require_viewer(BOOKING_REVIEWER_ROLES,
                               "Only Venue Staff can change a hold's expiry.")
        booking = db.session.get(VenueBooking, booking_id, with_for_update=True,
                                 populate_existing=True)
        if booking is None:
            raise _Rejected("Booking request not found.", 404)
        expires_at = _hold_expiry(request.get_json(silent=True), booking)
        if booking.status != TENTATIVE:
            raise _Rejected(
                "This booking is not a tentative hold, so it has no expiry to change.",
                409, reason="not_a_hold")
        previous = booking.hold_expires_at
        if previous <= singapore_now():
            raise _Rejected(
                f"This hold expired on {_when(previous)}, so its expiry can no longer be "
                "changed.", 409, reason="expired")

        booking.hold_expires_at = expires_at
        event = db.session.get(Event, booking.event_id)
        venue = db.session.get(Venue, booking.venue_id)
        coordinator = db.session.get(User, event.coordinator_id)
        message = (
            f'{user.email} changed the tentative hold on {venue.name} for "{event.title}" '
            f"({_period_text(booking.start_time, booking.end_time)}). It now expires on "
            f"{_when(expires_at)} (Singapore time) instead of {_when(previous)}."
        )
        # Saved in the same commit as the change (A6, open question Q3).
        db.session.add(Notification(recipient_id=coordinator.id,
                                    kind=HOLD_CHANGED_NOTIFICATION,
                                    message=message, event_id=event.id))
        payload = _hold_payload(booking)
        to_address, title, venue_name, event_id = (coordinator.email, event.title,
                                                    venue.name, event.id)
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The new expiry was not saved, so the hold's expiry is unchanged. "
            "Please try again.", 503, retryable=True,
        )

    email_queued = _queue_coordinator_email(
        to_address, f"Tentative hold on {venue_name} for {title}: new expiry", message,
        event_id)
    return jsonify({
        "message": (
            f"The hold on {venue_name} for {title} now expires on {_when(expires_at)}. "
            f"{to_address} has been notified."
        ),
        "booking": payload,
        "notification": {"in_app": True, "email_queued": email_queued},
    })


@venues_bp.get("/holds")
@jwt_required()
def list_holds():
    try:
        _require_viewer(BOOKING_REVIEWER_ROLES, "Only Venue Staff can view tentative holds.")
        # Soonest expiry first, so the holds about to lapse are seen first (A8).
        holds = (scheduling.unexpired_holds(singapore_now())
                 .order_by(VenueBooking.hold_expires_at, VenueBooking.id).all())
        payloads = [_hold_payload(hold) for hold in holds]
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        return _load_failed("Tentative holds could not be loaded. Please try again.")

    return jsonify({
        "holds": payloads,
        "message": None if payloads else "There are no tentative holds.",
    })


# ---------- The coordinator cancels a booking (SCRUM-94) ----------

CANCELLED = "cancelled"
# Bookings that hold, or may yet hold, their venue (AC1, A2).
CANCELLABLE_STATUSES = {PENDING, TENTATIVE, CONFIRMED}
CANCELLATION_NOTIFICATION = "venue_booking_cancelled"
# Venue Staff can't open the event's planning view, so their email points to their list.
STAFF_EMAIL_FOOTER = "Sign in to ConnectSphere to see the venue requests."


# The only field a cancellation takes: other bookings of the event to cancel too (SCRUM-85 A6).
CANCEL_FIELDS = {"also_cancel"}
# The same answer for another event's booking and an unknown one, so neither is revealed.
NOT_THIS_EVENTS_BOOKINGS = "Choose only other venue bookings of this event to cancel too."


def _cancelling_booking(user, booking_id):
    """The booking and its event, locked, if `user` may cancel the event's bookings
    (A1, A6, A7).

    Locked, so a cancellation and a Venue Staff decision happen one at a time.
    """
    booking = db.session.get(VenueBooking, booking_id, with_for_update=True,
                             populate_existing=True)
    if booking is None:
        raise _Rejected("Booking not found.", 404)
    event = db.session.get(Event, booking.event_id, with_for_update=True,
                           populate_existing=True) if booking.event_id else None
    if event is None or not is_current_coordinator(user, event):
        raise _Rejected(
            "Only the event's assigned coordinator can cancel its venue bookings.", 403)
    return booking, event


def _also_cancel_ids(body):
    """The ids of the event's other bookings the coordinator chose to cancel too; none
    when there is no body (SCRUM-85 A6)."""
    if body is None:
        return []
    if not isinstance(body, dict):
        raise _Rejected("Send the cancellation as JSON.", 400)
    for key in body:
        if key not in CANCEL_FIELDS:
            raise _Rejected(f"{key} is not part of a cancellation.", 400, field=key)
    ids = body.get("also_cancel", [])
    if not isinstance(ids, list) or not all(_is_id(value) for value in ids):
        raise _Rejected("List the other bookings to cancel too by their ids.", 400,
                        field="also_cancel")
    return ids


def _other_bookings(event, booking, ids):
    """The event's other bookings with these ids, locked, in id order (SCRUM-85 A6)."""
    ids = sorted(set(ids) - {booking.id})
    if not ids:
        return []
    others = (VenueBooking.query
              .filter(VenueBooking.id.in_(ids), VenueBooking.event_id == event.id)
              .order_by(VenueBooking.id).with_for_update().populate_existing().all())
    if len(others) != len(ids):
        raise _Rejected(NOT_THIS_EVENTS_BOOKINGS, 400, field="also_cancel")
    return others


def _require_cancellable(booking):
    if booking.status not in CANCELLABLE_STATUSES:
        raise _Rejected(f"This booking is {booking.status}, so it can't be cancelled.",
                        409, reason="not_cancellable")


def _release_event_venue(event, released):
    """Approving made the event's first confirmed venue its venue (SCRUM-40 A4, SCRUM-85
    A4). When `released` ((booking, previous status) pairs) leaves no confirmed booking
    there, it moves to the venue of the earliest confirmed booking left, or is cleared
    (A3, Q3; SCRUM-85 Q3)."""
    if event.venue_id is None or not any(
            previous == CONFIRMED and booking.venue_id == event.venue_id
            for booking, previous in released):
        return
    remaining = (VenueBooking.query.filter_by(event_id=event.id, status=CONFIRMED)
                 .order_by(VenueBooking.start_time, VenueBooking.id).all())
    if any(booking.venue_id == event.venue_id for booking in remaining):
        return
    event.venue_id = remaining[0].venue_id if remaining else None


def _names(words):
    """'A', 'A and B' or 'A, B and C', each name once, in order."""
    words = list(dict.fromkeys(words))
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _cancellation_message(user, event, released, venues):
    """What Venue Staff are told: every booking cancelled, with its previous status."""
    if len(released) == 1:
        booking, previous = released[0]
        return (
            f'{user.email} cancelled the {previous} booking of {venues[booking.venue_id].name} '
            f'for "{event.title}" ({_period_text(booking.start_time, booking.end_time)}). '
            "The venue is free again for that time."
        )
    described = [
        f"the {previous} booking of {venues[booking.venue_id].name} "
        f"({_period_text(booking.start_time, booking.end_time)})"
        for booking, previous in released
    ]
    return (f'{user.email} cancelled {len(released)} venue bookings for "{event.title}": '
            f"{'; '.join(described)}. The venues are free again for those times.")


def _notify_venue_staff(message, event_id):
    """Add an in-app notification for every Venue Staff member; return their addresses.

    Venue Staff aren't linked to venues, so all of them are told (A4, open question Q4).
    """
    staff = User.query.filter(User.role.in_(BOOKING_REVIEWER_ROLES)).all()
    for member in staff:
        db.session.add(Notification(recipient_id=member.id, kind=CANCELLATION_NOTIFICATION,
                                    message=message, event_id=event_id))
    return [member.email for member in staff]


@venues_bp.post("/bookings/<int:booking_id>/cancel")
@jwt_required()
def cancel_booking(booking_id: int):
    try:
        # Load the user first, then the record, then check permission (AGENTS.md, A6),
        # then the body (SCRUM-85 A6), then whether every booking can be cancelled.
        user = _require_viewer(roles=None)
        booking, event = _cancelling_booking(user, booking_id)
        others = _other_bookings(event, booking, _also_cancel_ids(request.get_json(silent=True)))
        cancelling = [booking, *others]
        for each in cancelling:
            _require_cancellable(each)
        venues = {each.venue_id: db.session.get(Venue, each.venue_id) for each in cancelling}

        # The rows and their other columns are kept; only the status changes (A3). All of
        # them are cancelled together, or none is (SCRUM-85 A6, Q5).
        released = [(each, each.status) for each in cancelling]
        for each in cancelling:
            each.status = CANCELLED
        _release_event_venue(event, released)
        message = _cancellation_message(user, event, released, venues)
        # Saved in the same commit as the cancellation, so neither exists without the other.
        staff_addresses = _notify_venue_staff(message, event.id)
        payload = _booking_decision_payload(booking)
        also_cancelled = [_booking_decision_payload(other) for other in others]
        title, event_id = event.title, event.id
        venue_names = _names([venues[each.venue_id].name for each in cancelling])
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The cancellation was not saved, so the booking is unchanged. Please try again.",
            503, retryable=True,
        )

    if others:
        subject = f"Venue bookings cancelled for {title}: {venue_names}"
        confirmation = (f"You cancelled the bookings of {venue_names} for {title}. The venues "
                        "are free again for those times, and Venue Staff have been notified.")
    else:
        subject = f"Venue booking cancelled for {title}: {venue_names}"
        confirmation = (f"You cancelled the booking of {venue_names} for {title}. The venue is "
                        "free again for that time, and Venue Staff have been notified.")
    queued = [_queue_email(address, subject, f"{message}\n\n{STAFF_EMAIL_FOOTER}", event_id)
              for address in staff_addresses]
    return jsonify({
        "message": confirmation,
        "booking": payload,
        "also_cancelled": also_cancelled,
        "notification": {"in_app": True, "email_queued": all(queued)},
    })
