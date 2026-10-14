import re
from datetime import date, datetime, time, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from . import scheduling
from ..events.permissions import is_current_coordinator
from ..extensions import db
from ..models import Event, User, Venue, VenueBooking

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


# ---------- Venue booking requests (SCRUM-39) ----------

COORDINATOR_ROLE = "coordinator"
# Roles allowed to see pending venue requests (SCRUM-39 A8, open question Q8).
BOOKING_REVIEWER_ROLES = {"venue_staff"}
# Only approved events proceed to further planning (SCRUM-39 A2, open question Q2).
REQUESTABLE_EVENT_STATUS = "approved"
PENDING = "pending"
# The editing limit for long text (SCRUM-53), reused for venue requirements (A4).
REQUIREMENTS_MAX_LENGTH = 5000
BOOKING_FIELDS = {"event_id", "venue_id", "start_time", "end_time", "venue_requirements"}
_LOCAL_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
# Singapore has had no daylight saving since 1982, so a fixed offset is exact.
SINGAPORE = timezone(timedelta(hours=8))


class _BookingRejected(Exception):
    """A booking request that cannot be served, with the reply to send instead."""

    def __init__(self, message, status_code, **extra):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra


def _singapore_now():
    """The current Singapore time without a time zone, as booking times are stored."""
    return datetime.now(SINGAPORE).replace(tzinfo=None)


def _caller(roles, denied):
    try:
        user = db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        user = None
    if user is None:
        raise _BookingRejected("Your session is no longer valid. Please log in again.", 401)
    if user.role not in roles:
        raise _BookingRejected(denied, 403)
    return user


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
    if start and start < _singapore_now():
        problems["start_time"] = "The start must not be in the past."

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
        "venue_requirements": booking.venue_requirements,
        "requested_by": {"id": requester.id, "email": requester.email} if requester else None,
        "requested_at": booking.created_at.isoformat(),
    }


ALREADY_PENDING = (
    "A venue request for this event is already pending. Venue Staff must decide on it "
    "before you request another venue."
)


@venues_bp.post("/bookings")
@jwt_required()
def request_booking():
    try:
        user = _caller({COORDINATOR_ROLE}, "Only event coordinators can request venues.")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise _BookingRejected("Send the venue request as JSON.", 400)
        if not _is_id(body.get("event_id")):
            raise _BookingRejected(
                "Choose the event to request a venue for.", 400,
                fields={"event_id": "Choose the event to request a venue for."},
            )

        # Locked until the request ends, so two submissions for one event are serialised.
        event = db.session.get(Event, body["event_id"], with_for_update=True,
                               populate_existing=True)
        if event is None:
            raise _BookingRejected("Event not found.", 404)
        if not is_current_coordinator(user, event):
            raise _BookingRejected(
                "Only the event's assigned coordinator can request a venue for it.", 403)

        problems, start, end = _booking_problems(body)
        if problems:
            raise _BookingRejected(
                "Some details are missing or invalid. Please correct them and try again.",
                400, fields=problems,
            )
        venue = db.session.get(Venue, body["venue_id"])
        if venue is None:
            raise _BookingRejected("Venue not found.", 404)
        if event.status != REQUESTABLE_EVENT_STATUS:
            raise _BookingRejected(
                "A venue can only be requested for an approved event. "
                f"This event is {event.status}.", 409)
        if VenueBooking.query.filter_by(event_id=event.id, status=PENDING).first():
            raise _BookingRejected(ALREADY_PENDING, 409)

        booking = VenueBooking(
            event_id=event.id, venue_id=venue.id, status=PENDING,
            start_time=start, end_time=end,
            venue_requirements=body["venue_requirements"].strip(),
            requested_by_id=user.id, created_at=datetime.utcnow(),
        )
        db.session.add(booking)
        try:
            db.session.commit()
        except IntegrityError:
            # Another submission for this event won the race (A6).
            db.session.rollback()
            raise _BookingRejected(ALREADY_PENDING, 409) from None
        payload = _booking_payload(booking)
    except _BookingRejected as rejected:
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
    try:
        _caller(BOOKING_REVIEWER_ROLES, "Only Venue Staff can view venue requests.")
        bookings = (VenueBooking.query.filter_by(status=PENDING)
                    .order_by(VenueBooking.created_at, VenueBooking.id).all())
        payloads = [_booking_payload(b) for b in bookings]
    except _BookingRejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        return _load_failed("Venue requests could not be loaded. Please try again.")

    return jsonify({
        "bookings": payloads,
        "message": None if payloads else "There are no pending venue requests.",
    })
