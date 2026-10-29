import re
from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import and_, func
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from .. import tasks
from ..extensions import db
from ..models import (
    EquipmentRequirement,
    EquipmentReservation,
    EquipmentUnavailability,
    Event,
    EventChangeRequest,
    EventClarification,
    Notification,
    ReassignmentRequest,
    Registration,
    Resource,
    User,
    Venue,
    VenueBooking,
)
from ..registrations.routes import REGISTERED, REGISTRABLE_STATUS, WITHDRAWN, singapore_now
from ..resources import availability, reservations as reserving
from ..venues.scheduling import BLOCKING_BOOKING_STATUS, TENTATIVE_STATUS, overlapping
from . import change_requests, change_review, equipment, suitability
from .permissions import (
    COORDINATOR_ROLE,
    can_view_clarifications,
    can_view_coordinator,
    can_view_equipment,
    is_coordinator_lead,
    is_current_coordinator as _is_current_coordinator,
    is_current_organiser,
    is_tech_staff,
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
# Where starting a review moves a submitted request (SCRUM-31, reopened: AC8).
UNDER_REVIEW_STATUS = "under_review"
# SCRUM-55 confirmed queue eligibility; decision eligibility remains separate.
REVIEW_QUEUE_STATUSES = {"submitted", "under_review"}
# A coordinator's decision on a submitted request, and the status it leads to (SCRUM-32).
DECISION_STATUSES = {"approve": "approved", "reject": "rejected"}
# Requests that can be approved or rejected. Under review was added when SCRUM-31 was
# reopened, so starting a review never blocks the decision (its A13, open question Q7).
DECIDABLE_STATUSES = {SUBMITTED_STATUS, UNDER_REVIEW_STATUS}
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

# SCRUM-74. Only published events are visible to everyone: exactly the events that take
# registrations (SCRUM-45, reopened 18 Oct 2026), so attendees can find each one.
PUBLISHED_STATUSES = {REGISTRABLE_STATUS}
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


# SCRUM-90 AC3: only Safety Officers may read the safety queue, including no admin override.
SAFETY_CHECK_VIEWER_ROLES = {"safety_officer"}
# SCRUM-91 AC4: safety approval has no admin or coordinator override.
SAFETY_CHECK_APPROVER_ROLES = {"safety_officer"}


def _safety_schedule_covered(event, bookings):
    """PR #58: confirmed booked periods must cover the current event without gaps.

    Venues may cover different phases; setup/turnaround are not event activities.
    This cannot establish unrecorded requirements for particular venues (A6/Q6).
    """
    covered_until = event.start_time
    for booking in sorted(bookings, key=lambda row: row.start_time):
        if booking.start_time > covered_until:
            break
        covered_until = max(covered_until, booking.end_time)
        if covered_until >= event.end_time:
            return True
    return False


def _safety_check_payload(event, venues, equipment_lines):
    return {
        "id": event.id,
        "title": event.title,
        "venues": venues,
        "start_time": _isoformat(event.start_time),
        "end_time": _isoformat(event.end_time),
        "expected_attendance": event.expected_attendance,
        "equipment": equipment_lines,
    }


def _safety_check_items(events):
    """Reuse SCRUM-90 readiness for both the queue and SCRUM-91 approval."""
    event_ids = {event.id for event in events}
    items = []
    if event_ids:
        # Read only confirmed bookings for current candidates and their date range.
        # Use booked times here: setup/turnaround do not cover event activities.
        bookings = VenueBooking.query.filter_by(status=BLOCKING_BOOKING_STATUS).filter(
            VenueBooking.event_id.in_(event_ids),
            VenueBooking.start_time < max(event.end_time for event in events),
            VenueBooking.end_time > min(event.start_time for event in events)).all()
        requirements = EquipmentRequirement.query.filter(
            EquipmentRequirement.event_id.in_(event_ids)).all()
        reservations = EquipmentReservation.query.filter_by(status=reserving.RESERVED).filter(
            EquipmentReservation.event_id.in_(event_ids)).all()
        venue_ids = {booking.venue_id for booking in bookings}
        venues = {venue.id: venue for venue in Venue.query.filter(Venue.id.in_(venue_ids)).all()}

        event_venues = {}
        event_bookings = {}
        events_by_id = {event.id: event for event in events}
        for booking in bookings:
            event = events_by_id[booking.event_id]
            # The batch date range can include another event's obsolete periods.
            # Only booked activities overlapping this event belong in its row.
            if booking.end_time <= event.start_time or booking.start_time >= event.end_time:
                continue
            event_bookings.setdefault(booking.event_id, []).append(booking)
            venue = venues[booking.venue_id]
            event_venues.setdefault(booking.event_id, {})[venue.id] = {
                "id": venue.id, "name": venue.name,
            }
        event_requirements = {}
        for requirement in requirements:
            event_requirements.setdefault(requirement.event_id, []).append(requirement)
        reserved = {}
        for reservation in reservations:
            key = (reservation.event_id, reservation.requirement_id)
            reserved[key] = reserved.get(key, 0) + reservation.quantity

        for event in events:
            if not _safety_schedule_covered(event, event_bookings.get(event.id, [])):
                continue
            needed = event_requirements.get(event.id, [])
            # SCRUM-90 A1/Q1: an unprocessed organiser note is not "no equipment".
            if not needed and (event.equipment_requirements or "").strip():
                continue
            equipment_lines = [{
                "equipment_type": requirement.equipment_type,
                "quantity": requirement.quantity,
                "reserved_quantity": reserved.get((event.id, requirement.id), 0),
            } for requirement in needed]
            if any(line["reserved_quantity"] < line["quantity"] for line in equipment_lines):
                continue
            items.append(_safety_check_payload(
                event, list(event_venues[event.id].values()), equipment_lines))
    return items


@events_bp.get("/safety-checks")
@jwt_required()
def list_safety_checks():
    """SCRUM-90: confirmed venues and complete active equipment reservations."""
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        if user.role not in SAFETY_CHECK_VIEWER_ROLES:
            return _error("Only Safety Officers can view events awaiting a safety check.", 403)

        # PR #58: closed events and events ending now or earlier need no safety check.
        events = Event.query.filter(
            Event.end_time > singapore_now(),
            *[Event.status != status for status in EQUIPMENT_CLOSED_STATUSES]).all()
        events = [event for event in events
                  if event.start_time is not None and event.safety_decision != "approved"]
        items = _safety_check_items(events)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The safety check list could not be loaded. Please try again.",
                      503, retryable=True)

    return jsonify({"events": items, "message": None if items else
                    "There are no events awaiting a safety check."})


def _safety_decision_payload(event):
    officer = db.session.get(User, event.safety_decided_by_id)
    return {
        "decision": event.safety_decision,
        "officer": _user_summary(officer) if officer else None,
        "comment": event.safety_comment,
        "decided_at": _isoformat(event.safety_decided_at),
    }


@events_bp.post("/<int:event_id>/safety-checks/approve")
@jwt_required()
def approve_safety_check(event_id):
    """SCRUM-91: save safety approval without changing the event's lifecycle status."""
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        # Serialize decisions so a double submission cannot overwrite the officer
        # or create a second notification for the same approval.
        event = db.session.get(Event, event_id, with_for_update=True)
        if event is None:
            return _error("Event not found.", 404)
        if user.role not in SAFETY_CHECK_APPROVER_ROLES:
            return _error("Only Safety Officers can approve a safety check.", 403)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _error("Send the approval as a JSON object.", 400)
        comment = body.get("comment")
        if comment is not None and not isinstance(comment, str):
            return _error("The comment must be text.", 400, field="comment")
        comment = (comment or "").strip() or None
        if event.safety_decision == "approved":
            return _error("This safety check is already approved.", 409)
        if (event.status in EQUIPMENT_CLOSED_STATUSES or event.start_time is None
                or event.end_time is None or event.end_time <= singapore_now()
                or not _safety_check_items([event])):
            return _error("This event is no longer awaiting a safety check. Refresh the list.", 409)

        coordinator = db.session.get(User, event.coordinator_id) if event.coordinator_id else None
        event.safety_decision = "approved"
        event.safety_decided_by_id = user.id
        event.safety_comment = comment
        event.safety_decided_at = datetime.utcnow()
        message = (f'The safety check for "{event.title}" was approved by {user.email} '
                   f"on {_singapore_time(event.safety_decided_at)}.")
        if comment:
            message += f" Comment: {comment}"
        if coordinator:
            db.session.add(Notification(recipient_id=coordinator.id, event_id=event.id,
                                        kind="safety_approved", message=message))
        # Read reply/email values before commit expires the ORM objects. Approval
        # and in-app notification are saved together; queue email only afterward.
        payload = _safety_decision_payload(event)
        to_address = coordinator.email if coordinator else None
        title = event.title
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The safety decision was not saved. Please try again.", 503, retryable=True)

    email_queued = (_queue_email(to_address, f"Safety check approved: {title}", message, event_id)
                    if to_address else False)
    return jsonify({"message": "Safety check approved.", "safety_check": payload,
                    "notification": {"in_app": to_address is not None,
                                     "email_queued": email_queued}})


@events_bp.post("/")
def create_event():
    return jsonify({"message": "create event not yet implemented"}), 501


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
        "venue_bookings": _planning_venue_bookings(event),
        # Add only recorded safety decisions; preserve the existing payload for
        # events with no safety check (SCRUM-91 AC2).
        **({"safety_check": _safety_decision_payload(event)} if event.safety_decision else {}),
    }


def _planning_venue_bookings(event):
    """Every venue booking of the event, whatever its status, in time order (SCRUM-85 A7).

    An expired hold blocks nothing (SCRUM-87), so it is marked as expired rather than
    shown as a live hold.
    """
    bookings = (VenueBooking.query.filter_by(event_id=event.id)
                .order_by(VenueBooking.start_time, VenueBooking.id).all())
    venue_ids = {booking.venue_id for booking in bookings}
    venues = ({venue.id: venue for venue in Venue.query.filter(Venue.id.in_(venue_ids))}
              if venue_ids else {})
    now = singapore_now()
    listed = []
    for booking in bookings:
        venue = venues[booking.venue_id]
        held = booking.status == TENTATIVE_STATUS and booking.hold_expires_at is not None
        listed.append({
            "id": booking.id,
            "venue": {"id": venue.id, "name": venue.name, "location": _recorded(venue.location)},
            "start_time": _isoformat(booking.start_time),
            "end_time": _isoformat(booking.end_time),
            "setup_minutes": booking.setup_minutes or 0,
            "turnaround_minutes": booking.turnaround_minutes or 0,
            "status": booking.status,
            "hold_expires_at": _isoformat(booking.hold_expires_at) if held else None,
            "hold_expired": booking.hold_expires_at <= now if held else None,
        })
    return listed


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


REQUIREMENT_ITEM_MAX_LENGTH = 100
REQUIREMENT_MAX_ITEMS = 20


def _requirement_list_validator(label):
    """A list of short names (SCRUM-38). An empty list means none are needed; null
    clears it back to not recorded."""

    def validate(value):
        if value is None:
            return None, None
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return None, f"{label} must be a list of names."
        items = [" ".join(item.split()) for item in value]
        if any(not item for item in items):
            return None, f"{label} can't include a blank name."
        if any(len(item) > REQUIREMENT_ITEM_MAX_LENGTH for item in items):
            return None, (f"Each name in {label.lower()} must be "
                          f"{REQUIREMENT_ITEM_MAX_LENGTH} characters or fewer.")
        if len(items) > REQUIREMENT_MAX_ITEMS:
            return None, f"{label} can have at most {REQUIREMENT_MAX_ITEMS} names."
        return list(dict.fromkeys(items)), None

    return validate


NORMAL_FIELD_VALIDATORS = {
    "title": _validate_title,
    "purpose": _optional_text_validator("Purpose"),
    "description": _optional_text_validator("Description"),
    "accessibility_needs": _optional_text_validator("Accessibility needs"),
    # SCRUM-38: what the event needs of a venue. Not restricted: they are only used to
    # assess venues and change no existing arrangement.
    "required_facilities": _requirement_list_validator("Required facilities"),
    "required_accessibility_features": _requirement_list_validator(
        "Required accessibility features"),
    "required_layouts": _requirement_list_validator("Required layouts"),
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


# Reassigning an event's coordinator: Leads only since SCRUM-82 (A1).
REASSIGN_LEAD_ONLY = "Only Event Coordinator Leads can reassign coordinators."
COORDINATOR_UNASSIGNED_NOTIFICATION = "coordinator_unassigned"
NO_OTHER_ELIGIBLE_COORDINATOR = "No other eligible coordinator is available for this event."


def _require_reassignable(event):
    """Refuse (409) an event with no coordinator yet, or a draft or cancelled one (A2)."""
    if event.coordinator_id is None:
        raise _Rejected(
            "This event has no coordinator yet. Assign one from the queue.",
            409,
            reason="not_assigned",
            next_step={
                "action": "Assign a coordinator",
                "method": "POST",
                "url": url_for("events.assign_from_queue", event_id=event.id),
            },
        )
    if event.status in NON_ASSIGNABLE_STATUSES:
        raise _Rejected(f"A coordinator cannot be assigned to a {event.status} event.", 409)


@events_bp.get("/<int:event_id>/eligible-coordinators")
@jwt_required()
def list_eligible_coordinators(event_id: int):
    """Who the Lead may reassign the event to, with the event and its current
    coordinator for the reassign page (SCRUM-82 A3, A7)."""
    try:
        _, event = _lead_and_event(event_id, denied=REASSIGN_LEAD_ONLY)
        _require_reassignable(event)
        coordinators = _eligible_coordinators(event)
        payload = {
            "event_id": event.id,
            "event": _event_summary(event),
            "current_coordinator": _user_summary(db.session.get(User, event.coordinator_id)),
            "coordinators": [_user_summary(c) for c in coordinators],
            "message": None
            if coordinators
            else "No eligible coordinators are available for this event.",
        }
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("Eligible coordinators could not be loaded. Please try again.", 503, retryable=True)
    return jsonify(payload)


@events_bp.put("/<int:event_id>/coordinator")
@jwt_required()
def assign_coordinator(event_id: int):
    """Reassign an event to another coordinator (SCRUM-82).

    The single coordinator column is replaced, so an event never has two main
    coordinators. The change, who made it and when, and both coordinators' in-app
    notifications are saved in one commit, so a failed save changes nothing; the
    emails are queued only after it (A4-A6).
    """
    try:
        # SCRUM-27: re-read and lock, so two reassignments at once apply one at a time.
        lead, event = _lead_and_event(event_id, lock=True, denied=REASSIGN_LEAD_ONLY)
        coordinator_id = _parse_assignment(request.get_json(silent=True))
        _require_reassignable(event)
        if coordinator_id == event.coordinator_id:
            raise _Rejected("This user is already the event's coordinator.", 409)
        coordinator = _chosen_coordinator(
            event, coordinator_id, none_left=NO_OTHER_ELIGIBLE_COORDINATOR
        )

        previous = db.session.get(User, event.coordinator_id)
        message = _record_assignment(event, lead, coordinator)
        # Plain values, so nothing needs the database after the commit.
        title, new_address, previous_address = event.title, coordinator.email, previous.email
        unassigned = f'{lead.email} reassigned "{title}" to {new_address}.'
        db.session.add(
            Notification(
                recipient_id=previous.id,
                kind=COORDINATOR_UNASSIGNED_NOTIFICATION,
                message=unassigned,
                event_id=event.id,
            )
        )
        payload = {
            "message": message,
            **_assignment_payload(event),
            "previous_coordinator": _user_summary(previous),
            "assigned_by": _user_summary(lead),
        }
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The coordinator assignment could not be saved. Please try again.", 503, retryable=True
        )

    queued = [
        _queue_assignment_email(new_address, title, message, event_id),
        _queue_email(previous_address, f"You are no longer the coordinator for {title}",
                     unassigned, event_id),
    ]
    return jsonify({**payload, "notification": {"in_app": True, "email_queued": all(queued)}})


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

        # Week 7 change 5 (SCRUM-81 A9): no coordinator is assigned here any more; the
        # request waits in the Lead's queue (SCRUM-81 assigns it).
        now = datetime.utcnow()
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
    return {
        "id": event.id,
        "status": event.status,
        **fields,
        "submitted_at": _isoformat(event.submitted_at),
        "decided_at": _isoformat(event.decided_at),
        "decided_by": _recorded_user(event.decided_by_id),
        "decision_note": event.decision_note,
        # SCRUM-31 (reopened): who started the review and when (A11).
        "review_started_at": _isoformat(event.review_started_at),
        "review_started_by": _recorded_user(event.review_started_by_id),
    }


def _recorded_user(user_id):
    """The summary of the user an event records, or None if none is recorded."""
    user = db.session.get(User, user_id) if user_id else None
    return _user_summary(user) if user else None


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


@events_bp.post("/<int:event_id>/review")
@jwt_required()
def start_review(event_id: int):
    """SCRUM-31 (reopened): the assigned coordinator starts reviewing a submitted request.

    The row is read afresh and locked, so a second start at the same moment waits, then
    finds the request already under review and is refused (A15).
    """
    try:
        user, event = _assigned_request(
            event_id,
            "Only the event's assigned coordinator can start reviewing this request.",
            lock=True,
        )
        if event.status != SUBMITTED_STATUS:
            raise _Rejected(
                f"This request is {event.status}; only a submitted request can be put "
                "under review.",
                409,
            )

        event.status = UNDER_REVIEW_STATUS
        event.review_started_at = datetime.utcnow()
        event.review_started_by_id = user.id
        payload = _request_payload(event)
        title = event.title
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The review was not started, so the request is still submitted. Please try again.",
            503,
            retryable=True,
        )

    return jsonify({"message": f'You started reviewing "{title}".', "request": payload})


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
        if event.status not in DECIDABLE_STATUSES:
            raise _Rejected(
                f"This request is {event.status}; only submitted requests or those under "
                "review can be approved or rejected.",
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
            "The decision was not saved, so the request is unchanged. Please try again.",
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


# ---------- Registration information for the organiser (SCRUM-54) ----------

# Shown to users verbatim (AC4, AC5, AC6).
ORGANISERS_ONLY = "Only event organisers can view registration information for their events."
NOT_YOUR_EVENT = "You can only view registration information for events you organise."
NO_ORGANISED_EVENTS = "You have no events yet. Events appear here once you submit them."
NO_REGISTRATIONS = "No one has registered for this event yet."


def _registration_summary(event, registered):
    """Places, places taken and places left (A3). Only `registered` takes a place, as
    in SCRUM-45; with no capacity set, there is nothing to count places against."""
    capacity = event.registration_capacity
    return {
        "capacity": capacity,
        "registered_count": registered,
        "slots_remaining": None if capacity is None else max(capacity - registered, 0),
    }


def _event_with_registration_summary(event, registered):
    # The organiser's (SCRUM-54) and the coordinator's (SCRUM-72) lists show events alike.
    # A blank name is sent as null, so the page shows "Not recorded".
    return {
        "id": event.id,
        "title": _recorded(event.title),
        "start_time": _isoformat(event.start_time),
        "status": event.status,
        "registration": _registration_summary(event, registered),
    }


def _registration_detail_payload(registration, attendee):
    # Accounts record no name, so the email identifies the attendee (A5, open question Q4).
    return {
        "id": registration.id,
        "attendee": _user_summary(attendee),
        "registered_at": _isoformat(registration.registered_at),
        "status": registration.status,
    }


def _event_registrations(event):
    """(registration, attendee) pairs for every registration, whatever its status,
    earliest first (A4, open question Q3)."""
    return (
        db.session.query(Registration, User)
        .join(User, User.id == Registration.attendee_id)
        .filter(Registration.event_id == event.id)
        .order_by(Registration.registered_at, Registration.id)
        .all()
    )


@events_bp.get("/organised")
@jwt_required()
def list_organised():
    """The caller's events with their registration summary (AC1).

    Every non-draft event they organise, since drafts can't take registrations (A2,
    open question Q1); soonest proposed date first, undated last (A7). Nothing is sent
    unless every event and its count loaded (AC6).
    """
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        if user.role != ORGANISER_ROLE:
            return _error(ORGANISERS_ONLY, 403)
        events = (
            Event.query.filter(Event.organiser_id == user.id, Event.status != DRAFT_STATUS)
            .order_by(Event.start_time.asc().nulls_last(), Event.id)
            .all()
        )
        counts = _registered_counts([event.id for event in events])
        items = [_event_with_registration_summary(event, counts.get(event.id, 0))
                 for event in events]
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Your events' registration information could not be loaded. Please try again.",
            503, retryable=True,
        )

    return jsonify({"events": items, "message": None if items else NO_ORGANISED_EVENTS})


@events_bp.get("/<int:event_id>/registrations")
@jwt_required()
def get_event_registrations(event_id: int):
    """One event's summary and registrations, for its organiser only (AC2, AC4).

    Checked 401, 404, then 403 (A8); the refusal names nothing about the event. Nothing
    is sent unless the event, its count and its registrations all loaded (AC6).
    """
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        event = db.session.get(Event, event_id) if event_id <= DB_INTEGER_MAX else None
        if event is None:
            return _error(EVENT_NOT_FOUND, 404)
        if not is_current_organiser(user, event):
            return _error(NOT_YOUR_EVENT, 403)
        registered = _registered_counts([event.id]).get(event.id, 0)
        registrations = [
            _registration_detail_payload(registration, attendee)
            for registration, attendee in _event_registrations(event)
        ]
        payload = {
            "event": _event_with_registration_summary(event, registered),
            "registrations": registrations,
            "message": None if registrations else NO_REGISTRATIONS,
        }
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The registration information for this event could not be loaded. "
            "Please try again.",
            503, retryable=True,
        )

    return jsonify(payload)


# ---------- Registration information for the coordinator (SCRUM-72) ----------

# Shown to users verbatim (AC4, AC5).
COORDINATORS_ONLY = ("Only event coordinators can view registration information for their "
                     "assigned events.")
NOT_ASSIGNED_TO_YOU = "You can only view registration information for events assigned to you."
NO_ASSIGNED_EVENTS = "You have no events assigned to you yet."
# Registration.status for a registration the event cancelled; the attendee's own
# leaving is WITHDRAWN (SCRUM-68).
CANCELLED_REGISTRATION = "cancelled"


def _registration_counts_by_status(event):
    """How many of the event's registrations have each status; statuses with none are
    left out, so an empty result means nobody has ever registered (A5)."""
    rows = (
        db.session.query(Registration.status, func.count(Registration.id))
        .filter(Registration.event_id == event.id)
        .group_by(Registration.status)
        .all()
    )
    return dict(rows)


def _coordination_event_payload(event, venue):
    """The event as the coordinator plans around it: when, where and how many are
    expected (A4)."""
    return {
        "id": event.id,
        "title": _recorded(event.title),
        "start_time": _isoformat(event.start_time),
        "end_time": _isoformat(event.end_time),
        "status": event.status,
        "expected_attendance": event.expected_attendance,
        "venue": {"name": venue.name, "capacity": venue.capacity} if venue else None,
    }


def _registration_overview_payload(event, counts):
    """The registration figures for coordination, with no attendee's identity (A4, open
    question Q3): places as on the list (A3), who left, and the registration period."""
    return {
        **_registration_summary(event, counts.get(REGISTERED, 0)),
        "withdrawn_count": counts.get(WITHDRAWN, 0),
        "cancelled_count": counts.get(CANCELLED_REGISTRATION, 0),
        "opens_at": _isoformat(event.registration_opens_at),
        "closes_at": _isoformat(event.registration_closes_at),
    }


@events_bp.get("/managed/registrations")
@jwt_required()
def list_managed_registrations():
    """The caller's assigned events with their registration summary (AC1).

    The same events as SCRUM-62's managed list (A1, A2), soonest proposed date first,
    undated last (A6). Nothing is sent unless every event and its count loaded (AC6).
    """
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        if user.role != COORDINATOR_ROLE:
            return _error(COORDINATORS_ONLY, 403)
        events = (
            Event.query.filter_by(coordinator_id=user.id)
            .order_by(Event.start_time.asc().nulls_last(), Event.id)
            .all()
        )
        counts = _registered_counts([event.id for event in events])
        items = [_event_with_registration_summary(event, counts.get(event.id, 0))
                 for event in events]
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The registration information for your events could not be loaded. "
            "Please try again.", 503, retryable=True)

    return jsonify({"events": items, "message": None if items else NO_ASSIGNED_EVENTS})


@events_bp.get("/<int:event_id>/registration-overview")
@jwt_required()
def get_registration_overview(event_id: int):
    """One assigned event's registration figures, for its current coordinator only (AC2,
    AC4).

    Checked 401, 404, then 403 (A7); the refusal names nothing about the event. Nothing
    is sent unless the event, its venue and its counts all loaded (AC6).
    """
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        event = db.session.get(Event, event_id) if event_id <= DB_INTEGER_MAX else None
        if event is None:
            return _error(EVENT_NOT_FOUND, 404)
        if not _is_current_coordinator(user, event):
            return _error(NOT_ASSIGNED_TO_YOU, 403)
        counts = _registration_counts_by_status(event)
        payload = {
            "event": _coordination_event_payload(event, _event_venue(event)),
            "registration": _registration_overview_payload(event, counts),
            "message": None if counts else NO_REGISTRATIONS,
        }
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The registration information for this event could not be loaded. "
            "Please try again.", 503, retryable=True)

    return jsonify(payload)


# ---------- The events a Coordinator Lead assigned (SCRUM-83) ----------

# Events still being worked on, so a Lead can supervise them (A3, open question Q2).
SUPERVISED_ACTIVE_STATUSES = {"submitted", "under_review", "approved", "confirmed"}
# A user ID in the coordinator filter. ASCII only: str.isdigit() also accepts "²".
_USER_ID = re.compile(r"[0-9]+", re.ASCII)
NO_ASSIGNED_EVENTS = "You have no active events with a coordinator you assigned."
NO_EVENTS_FOR_COORDINATOR = "None of your active events are assigned to this coordinator."


def _coordinator_filter():
    """The coordinator ID to filter by, or None for every coordinator (A6)."""
    value = request.args.get("coordinator_id", "")
    if value == "":
        return None
    if not _USER_ID.fullmatch(value):
        raise _Rejected("Choose a coordinator from the list.", 400, field="coordinator_id")
    return int(value)


def _supervised_events(lead):
    """(event, coordinator) pairs for the active events whose current coordinator
    assignment this Lead made (A1), soonest first, undated last (A5, open question Q4)."""
    return (
        db.session.query(Event, User)
        .join(User, User.id == Event.coordinator_id)
        .filter(
            Event.coordinator_assigned_by_id == lead.id,
            Event.status.in_(SUPERVISED_ACTIVE_STATUSES),
        )
        .order_by(Event.start_time.asc().nulls_last(), Event.id)
        .all()
    )


def _supervised_event_payload(event, coordinator):
    # A blank name is sent as null, so the page shows "Not recorded" (A5).
    return {
        "id": event.id,
        "title": _recorded(event.title),
        "start_time": _isoformat(event.start_time),
        "status": event.status,
        "coordinator": _user_summary(coordinator),
    }


@events_bp.get("/supervised")
@jwt_required()
def list_supervised():
    """The active events a Coordinator Lead assigned, optionally for one coordinator.

    The whole reply is built inside the try, so a failed load never sends part of the
    list (AC4). Refusals carry no event or coordinator data (AC3).
    """
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        if not is_coordinator_lead(user):
            return _error("Only Event Coordinator Leads can view the events they assigned.", 403)
        coordinator_id = _coordinator_filter()

        rows = _supervised_events(user)
        # The filter offers every coordinator of the Lead's events, whichever is chosen.
        coordinators = {coordinator.id: _user_summary(coordinator) for _, coordinator in rows}
        events = [
            _supervised_event_payload(event, coordinator)
            for event, coordinator in rows
            if coordinator_id in (None, coordinator.id)
        ]
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The events you assigned could not be loaded. Please try again.", 503, retryable=True
        )

    if events:
        message = None
    elif coordinator_id is None:
        message = NO_ASSIGNED_EVENTS
    else:
        message = NO_EVENTS_FOR_COORDINATOR
    return jsonify(
        {
            "events": events,
            "coordinators": sorted(coordinators.values(), key=lambda c: c["email"]),
            "message": message,
        }
    )


# ---------- A Coordinator Lead assigns a waiting event (SCRUM-81) ----------

# An event waits in the Lead's queue while it has this status and no coordinator
# (SCRUM-81 A1, A10). Submissions enter it with no coordinator (A9).
ASSIGNMENT_QUEUE_STATUSES = {"submitted"}
COORDINATOR_ASSIGNED_NOTIFICATION = "coordinator_assigned"
LEAD_ONLY = "Only Event Coordinator Leads can assign coordinators."
ALREADY_ASSIGNED = "This event already has a coordinator. Use the reassign function to change it."
NO_ELIGIBLE_COORDINATOR = "No eligible coordinator is available for this event."


def _waiting_for_assignment():
    """The SQL condition for an event in the queue; _require_waiting checks the same rule."""
    return and_(Event.status.in_(ASSIGNMENT_QUEUE_STATUSES), Event.coordinator_id.is_(None))


def _lead_and_event(event_id, lock=False, denied=LEAD_ONLY):
    """The calling Lead and the event, checked 401, 404, 403 (A7); `denied` is the 403.

    With `lock`, the event row is re-read and locked, so when two Leads assign at once
    the second sees the first's coordinator and is refused (A6).
    """
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    event = db.session.get(Event, event_id, with_for_update=lock, populate_existing=lock)
    if event is None:
        raise _Rejected(EVENT_NOT_FOUND, 404)
    if not is_coordinator_lead(user):
        raise _Rejected(denied, 403)
    return user, event


def _require_waiting(event):
    """Refuse (409) an event that already has a coordinator or is not in the queue."""
    if event.coordinator_id is not None:
        raise _Rejected(
            ALREADY_ASSIGNED,
            409,
            reason="already_assigned",
            next_step={
                "action": "Reassign the coordinator",
                "method": "PUT",
                "url": url_for("events.assign_coordinator", event_id=event.id),
            },
        )
    if event.status not in ASSIGNMENT_QUEUE_STATUSES:
        raise _Rejected(
            f"Only events waiting in the queue can be assigned. This event is {event.status}.",
            409,
            reason="not_in_queue",
        )


def _parse_assignment(body):
    """The chosen coordinator's ID; nothing else may be sent (no forged assigner)."""
    coordinator_id = body.get("coordinator_id") if isinstance(body, dict) else None
    if not isinstance(coordinator_id, int) or isinstance(coordinator_id, bool):
        raise _Rejected("Choose a coordinator.", 400, field="coordinator_id")
    if set(body) != {"coordinator_id"}:
        raise _Rejected("Only coordinator_id can be sent.", 400)
    return coordinator_id


def _chosen_coordinator(event, coordinator_id, none_left=NO_ELIGIBLE_COORDINATOR):
    """The chosen user, if eligible (A3); the same rule as the list the Lead chose from.

    `none_left` is the refusal when nobody is eligible at all.
    """
    eligible = _eligible_coordinators(event)
    coordinator = next((c for c in eligible if c.id == coordinator_id), None)
    if coordinator is None:
        message = none_left if not eligible else (
            "The selected user is not an eligible coordinator."
        )
        raise _Rejected(message, 422, field="coordinator_id")
    return coordinator


def _event_summary(event):
    return {
        "id": event.id,
        "title": event.title,
        "start_time": _isoformat(event.start_time),
        "status": event.status,
    }


def _record_assignment(event, lead, coordinator):
    """Make `coordinator` the event's coordinator, recording the Lead and the time, and
    notify them in the app (A4, A5). Returns the confirmation message; not committed."""
    event.coordinator_id = coordinator.id
    event.coordinator_assigned_by_id = lead.id
    event.coordinator_assigned_at = datetime.utcnow()
    db.session.add(
        Notification(
            recipient_id=coordinator.id,
            kind=COORDINATOR_ASSIGNED_NOTIFICATION,
            message=f'{lead.email} assigned you to coordinate "{event.title}".',
            event_id=event.id,
        )
    )
    return f"{coordinator.email} is now the coordinator for {event.title}."


def _queue_email(to_address, subject, body, event_id):
    """Queue an email; False if the queue could not be reached (A5).

    The change and its in-app notifications are already saved by then, so a broker
    outage must not undo them. It takes plain values, so it never needs the database.
    """
    try:
        tasks.send_notification_email.delay(to_address, subject, body)
    except Exception:
        current_app.logger.exception("Could not queue an email for event %s", event_id)
        return False
    return True


def _queue_assignment_email(to_address, title, message, event_id):
    """Tell a newly assigned coordinator by email (SCRUM-81, SCRUM-82)."""
    return _queue_email(
        to_address,
        f"You are now the coordinator for {title}",
        f"{message}\n\nSign in to ConnectSphere to see your managed events.",
        event_id,
    )


@events_bp.get("/<int:event_id>/assignment")
@jwt_required()
def get_assignment(event_id: int):
    """A waiting event and the coordinators the Lead may choose from (AC1, AC5)."""
    try:
        _, event = _lead_and_event(event_id)
        _require_waiting(event)
        coordinators = _eligible_coordinators(event)
        payload = {
            "event": _event_summary(event),
            "coordinators": [_user_summary(c) for c in coordinators],
            "message": None if coordinators else NO_ELIGIBLE_COORDINATOR,
        }
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The event could not be loaded. Please try again.", 503, retryable=True)
    return jsonify(payload)


@events_bp.post("/<int:event_id>/assignment")
@jwt_required()
def assign_from_queue(event_id: int):
    """Assign a waiting event's coordinator, record who did it, and notify them (AC1, AC2).

    The assignment and its in-app notification are saved in one commit, so a failed
    save changes nothing (AC5); the email is queued only after the commit.
    """
    try:
        lead, event = _lead_and_event(event_id, lock=True)
        coordinator_id = _parse_assignment(request.get_json(silent=True))
        _require_waiting(event)
        coordinator = _chosen_coordinator(event, coordinator_id)

        message = _record_assignment(event, lead, coordinator)
        # Plain values, so nothing needs the database after the commit.
        title, to_address = event.title, coordinator.email
        assignment = {
            "event_id": event.id,
            "coordinator": _user_summary(coordinator),
            "assigned_by": _user_summary(lead),
            "assigned_at": _isoformat(event.coordinator_assigned_at),
        }
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The assignment was not saved. Please try again.", 503, retryable=True)

    queued = _queue_assignment_email(to_address, title, message, event_id)
    return jsonify(
        {
            "message": message,
            "assignment": assignment,
            "notification": {"in_app": True, "email_queued": queued},
        }
    )


# ---------- The Lead's unassigned queue (SCRUM-81) ----------

QUEUE_EMPTY = "No event requests are waiting for a coordinator."


def _queue_event_payload(event, organiser):
    # Blank or missing values are sent as null, so the page shows "Not recorded" (A12).
    return {
        "id": event.id,
        "title": _recorded(event.title),
        "start_time": _isoformat(event.start_time),
        "status": event.status,
        "organiser": _user_summary(organiser),
        "submitted_at": _isoformat(event.submitted_at),
    }


@events_bp.get("/queue")
@jwt_required()
def list_queue():
    """Every event waiting for a coordinator, for any Lead (A10, A11), oldest submission
    first so nothing waits unseen; older rows with no submission time last (A13, Q9)."""
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        if not is_coordinator_lead(user):
            return _error("Only Event Coordinator Leads can view the queue.", 403)
        rows = (
            db.session.query(Event, User)
            .join(User, User.id == Event.organiser_id)
            .filter(_waiting_for_assignment())
            .order_by(Event.submitted_at.asc().nulls_last(), Event.id)
            .all()
        )
        events = [_queue_event_payload(event, organiser) for event, organiser in rows]
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The queue could not be loaded. Please try again.", 503, retryable=True)

    return jsonify({"events": events, "message": None if events else QUEUE_EMPTY})


# ---------- The coordinator sets up registration (SCRUM-45 AC7) ----------

# The only fields the settings take, all required together (A14).
SETTINGS_FIELDS = ("capacity", "opens_at", "closes_at")
SETTINGS_COORDINATOR_ONLY = "Only the event's coordinator can set up registration."


def _settings_event(event_id, lock=False):
    """The event, for its current coordinator only; checked 401, 404, 403 (A13).

    With `lock`, the row is re-read and locked, as registering does, so the number
    registered can't change while a new capacity is checked (A15).
    """
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    event = (db.session.get(Event, event_id, with_for_update=lock, populate_existing=lock)
             if event_id <= DB_INTEGER_MAX else None)
    if event is None:
        raise _Rejected(EVENT_NOT_FOUND, 404)
    if not _is_current_coordinator(user, event):
        raise _Rejected(SETTINGS_COORDINATOR_ONLY, 403)
    return event


def _settings_blocked(event):
    """Why the settings can't be changed now, as (reason, message), or None (A16)."""
    if event.status != REGISTRABLE_STATUS:
        return "not_approved", (
            "Registration can only be set up for an approved event. "
            f"This event is {event.status}.")
    if event.registration_required is not True:
        return "registration_not_needed", (
            "The organiser said this event doesn't need attendee registration. "
            "Change that through a change request first.")
    return None


def _local_time(value):
    """A "YYYY-MM-DDTHH:MM" Singapore time as a datetime, or None if it isn't one."""
    if not isinstance(value, str) or not _LOCAL_DATETIME.match(value):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:  # e.g. 30 February
        return None


def _parse_settings(body, event, venue):
    """(capacity, opens_at, closes_at) from the body, or a 400 naming the field (A14)."""
    if not isinstance(body, dict):
        raise _Rejected("Enter the number of places and the registration period.", 400)
    for key in body:
        if key not in SETTINGS_FIELDS:
            raise _Rejected(f"{key} can't be set here.", 400, field=key)
    capacity = body.get("capacity")
    if (not isinstance(capacity, int) or isinstance(capacity, bool)
            or not 1 <= capacity <= DB_INTEGER_MAX):
        raise _Rejected("Enter the number of places as a whole number of at least 1.",
                        400, field="capacity")
    opens, closes = _local_time(body.get("opens_at")), _local_time(body.get("closes_at"))
    if opens is None:
        raise _Rejected("Enter when registration opens (YYYY-MM-DDTHH:MM).",
                        400, field="opens_at")
    if closes is None:
        raise _Rejected("Enter when registration closes (YYYY-MM-DDTHH:MM).",
                        400, field="closes_at")
    if opens >= closes:
        raise _Rejected("Registration must open before it closes.", 400, field="closes_at")
    if event.start_time is not None and closes > event.start_time:
        raise _Rejected("Registration must close no later than the event starts "
                        f"({event.start_time:%Y-%m-%d %H:%M}).", 400, field="closes_at")
    if venue is not None and venue.capacity is not None and capacity > venue.capacity:
        raise _Rejected(f"The venue holds {venue.capacity} people, so there can be at most "
                        f"{venue.capacity} places.", 400, field="capacity")
    return capacity, opens, closes


def _settings_payload(event, venue, registered):
    blocked = _settings_blocked(event)
    return {
        "event_id": event.id,
        "capacity": event.registration_capacity,
        "opens_at": _isoformat(event.registration_opens_at),
        "closes_at": _isoformat(event.registration_closes_at),
        "registered_count": registered,
        "venue_capacity": venue.capacity if venue else None,
        "can_edit": blocked is None,
        "message": blocked[1] if blocked else None,
    }


def _event_venue(event):
    return db.session.get(Venue, event.venue_id) if event.venue_id else None


@events_bp.get("/<int:event_id>/registration-settings")
@jwt_required()
def get_registration_settings(event_id: int):
    """The event's places and registration period, for its coordinator (AC7)."""
    try:
        event = _settings_event(event_id)
        registered = _registered_counts([event.id]).get(event.id, 0)
        payload = _settings_payload(event, _event_venue(event), registered)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The registration settings could not be loaded. Please try again.",
                      503, retryable=True)
    return jsonify(payload)


@events_bp.put("/<int:event_id>/registration-settings")
@jwt_required()
def save_registration_settings(event_id: int):
    """Set the event's places and registration period (AC7): checked 401, 404, 403, then
    the values (400), then whether they can be changed now (409), as AGENTS.md orders."""
    try:
        event = _settings_event(event_id, lock=True)
        venue = _event_venue(event)
        capacity, opens, closes = _parse_settings(request.get_json(silent=True), event, venue)
        blocked = _settings_blocked(event)
        if blocked:
            raise _Rejected(blocked[1], 409, reason=blocked[0])
        registered = _registered_counts([event.id]).get(event.id, 0)
        if capacity < registered:
            raise _Rejected(f"{registered} people are already registered, so there must be "
                            f"at least {registered} places.", 409, reason="below_registered")

        event.registration_capacity = capacity
        event.registration_opens_at = opens
        event.registration_closes_at = closes
        payload = _settings_payload(event, venue, registered)
        payload["message"] = (
            f"Registration for {event.title} is set up: {capacity} places, open from "
            f"{opens:%Y-%m-%d %H:%M} to {closes:%Y-%m-%d %H:%M}."
        )
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The registration settings were not saved. Please try again.",
                      503, retryable=True)
    return jsonify(payload)


# ---------- View event details (SCRUM-74) ----------


def _registered_counts(event_ids):
    """How many places are taken, by event ID. Only `registered` takes a place."""
    if not event_ids:
        return {}
    rows = (
        db.session.query(Registration.event_id, func.count(Registration.id))
        .filter(Registration.event_id.in_(event_ids), Registration.status == REGISTERED)
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
            Registration.status == REGISTERED,
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


# ---------- Assess a venue against an event's requirements (SCRUM-38) ----------


@events_bp.get("/<int:event_id>/venue-suitability")
@jwt_required()
def venue_suitability(event_id: int):
    """A read-only check of the chosen venue against the event's saved requirements.

    It never books, requests or changes anything, and a database failure is an error,
    never a result with requirements quietly left out.
    """
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)

        event = db.session.get(Event, event_id)
        if event is None:
            return _error("Event not found.", 404)
        if not _is_current_coordinator(user, event):
            return _error("You are not allowed to check venues for this event.", 403)

        raw = request.args.get("venue_id", "").strip()
        if not raw.isdigit():
            return _error("Select a venue to check.", 400,
                          fields={"venue_id": "Select a venue to check."})
        venue = db.session.get(Venue, int(raw))
        if venue is None:
            return _error("Venue not found.", 404)

        checks, overall, summary = suitability.assess(event, venue)
        payload = {
            "event": {"id": event.id, "title": event.title},
            "venue": {"id": venue.id, "name": venue.name},
            "checks": checks,
            "overall": overall,
            "summary": summary,
        }
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The venue check could not be completed. Please try again.", 503,
                      retryable=True)

    return jsonify(payload)


# ---------- Record equipment requirements (SCRUM-42) ----------

# Events whose equipment requirements can be viewed but no longer changed (A4, open
# question Q2).
EQUIPMENT_CLOSED_STATUSES = {"cancelled", "rejected"}
EQUIPMENT_VIEW_DENIED = "You are not allowed to view this event's equipment requirements."
EQUIPMENT_COORDINATOR_ONLY = "Only the event's coordinator can record its equipment requirements."
EQUIPMENT_TECH_ONLY = "Only Technical Support Staff can update equipment arrangements."
EQUIPMENT_REQUESTS_TECH_ONLY = "Only Technical Support Staff can view equipment requests."
REQUIREMENT_NOT_FOUND = "Equipment requirement not found."
NO_EQUIPMENT_REQUIREMENTS = "No equipment requirements have been recorded for this event."
NO_EQUIPMENT_REQUESTS = "No events have equipment requirements to arrange."
EQUIPMENT_INVALID = "Some details are not valid. Please correct them and try again."
# A failed save leaves every recorded requirement as it was, and says so (AC7).
EQUIPMENT_NOT_SAVED = ("The equipment requirement was not saved, and the recorded "
                       "requirements are unchanged. Please try again.")
EQUIPMENT_NOT_REMOVED = ("The equipment requirement was not removed, and the recorded "
                         "requirements are unchanged. Please try again.")
ARRANGEMENT_NOT_SAVED = "The arrangement status was not saved. Please try again."


def _equipment_event(event_id, allowed, denied, hide_drafts=False):
    """The caller and the event, checked in the order 401, 404, 403 (A11). With
    hide_drafts, a draft is not found, as an unknown ID is: it is still the organiser's
    own (SCRUM-96 A3, SCRUM-74 A2)."""
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    event = db.session.get(Event, event_id) if event_id <= DB_INTEGER_MAX else None
    if event is None or (hide_drafts and event.status == DRAFT_STATUS):
        raise _Rejected(EVENT_NOT_FOUND, 404)
    if not allowed(user, event):
        raise _Rejected(denied, 403)
    return user, event


def _event_requirement(event, requirement_id, lock=False):
    """The requirement, only if it belongs to this event. Checked after permission, so
    people who may not see the event learn nothing about its requirements (A11).
    With lock, the row is held until commit and refreshed, so a reservation for it
    (SCRUM-44 A7) waits for this change or is seen by it."""
    locking = {"with_for_update": True, "populate_existing": True} if lock else {}
    requirement = (db.session.get(EquipmentRequirement, requirement_id, **locking)
                   if requirement_id <= DB_INTEGER_MAX else None)
    if requirement is None or requirement.event_id != event.id:
        raise _Rejected(REQUIREMENT_NOT_FOUND, 404)
    return requirement


def _equipment_closed_notice(event):
    return f"This event is {event.status}, so its equipment requirements can no longer be changed."


def _require_equipment_open(event):
    if event.status in EQUIPMENT_CLOSED_STATUSES:
        raise _Rejected(_equipment_closed_notice(event), 409)


def _equipment_body(what):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise _Rejected(f"Send the {what} as a JSON object.", 400)
    return body


def _valid_requirement(event, body, requirement_id=None):
    """The cleaned values, or a 422 naming every problem. The same type with the same
    technical requirements can't be recorded twice for one event (A5)."""
    values, problems = equipment.parse_requirement(body)
    if not problems:
        key = equipment.requirement_key(values["equipment_type"],
                                        values["technical_requirements"])
        others = EquipmentRequirement.query.filter(EquipmentRequirement.event_id == event.id)
        if requirement_id is not None:
            others = others.filter(EquipmentRequirement.id != requirement_id)
        if any(equipment.requirement_key(o.equipment_type, o.technical_requirements) == key
               for o in others):
            problems["equipment_type"] = (
                f"{values['equipment_type']} with these technical requirements is already "
                "recorded for this event. Change its quantity instead.")
    if problems:
        raise _Rejected(EQUIPMENT_INVALID, 422, fields=problems)
    return values


def _requirement_payload(requirement, users):
    updater = users.get(requirement.arrangement_updated_by_id)
    return {
        "id": requirement.id,
        "equipment_type": requirement.equipment_type,
        "quantity": requirement.quantity,
        "technical_requirements": _recorded(requirement.technical_requirements),
        "status": requirement.status,
        "status_label": equipment.status_label(requirement.status),
        "arrangement_note": _recorded(requirement.arrangement_note),
        "recorded_at": _isoformat(requirement.recorded_at),
        "last_saved_at": _isoformat(requirement.last_saved_at),
        "arrangement_updated_at": _isoformat(requirement.arrangement_updated_at),
        "arrangement_updated_by": _user_summary(updater) if updater else None,
    }


def _users_by_id(ids):
    ids = {i for i in ids if i is not None}
    return {u.id: u for u in User.query.filter(User.id.in_(ids)).all()} if ids else {}


def _equipment_page(user, event):
    """What the equipment page shows: the event, the organiser's note (A2) and the
    recorded requirements in the order they were recorded."""
    requirements = (EquipmentRequirement.query.filter_by(event_id=event.id)
                    .order_by(EquipmentRequirement.id).all())
    users = _users_by_id([event.coordinator_id]
                         + [r.arrangement_updated_by_id for r in requirements])
    coordinator = users.get(event.coordinator_id)
    is_open = event.status not in EQUIPMENT_CLOSED_STATUSES
    return {
        "event": {
            "id": event.id,
            "title": event.title,
            "status": event.status,
            "start_time": _isoformat(event.start_time),
            "end_time": _isoformat(event.end_time),
            "coordinator": _user_summary(coordinator) if coordinator else None,
        },
        "organiser_note": _recorded(event.equipment_requirements),
        "requirements": [_requirement_payload(r, users) for r in requirements],
        "can_edit": is_open and _is_current_coordinator(user, event),
        "can_update_arrangements": is_open and is_tech_staff(user),
        # SCRUM-44: whether to offer reserving, by the same rules as reserving (A4).
        "can_reserve": _can_reserve(user, event),
        "notice": None if is_open else _equipment_closed_notice(event),
        "message": None if requirements else NO_EQUIPMENT_REQUIREMENTS,
    }


def _with_requirement(page, requirement_id):
    requirement = next(r for r in page["requirements"] if r["id"] == requirement_id)
    return {"requirement": requirement, **page}


# The change is committed but the updated page could not be read back (AC7).
EQUIPMENT_SAVED_NOT_RELOADED = ("The change was saved, but the updated requirements could "
                                "not be loaded. Reload the page to see them.")


def _saved_reply(user, event, confirmation, requirement_id=None, status_code=200):
    """The reply once a change is committed. Reading the page back can still fail, and
    that must not be reported as a failed save: the change is in the database (AC7)."""
    try:
        page = _equipment_page(user, event)
        payload = _with_requirement(page, requirement_id) if requirement_id else page
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"confirmation": confirmation, "saved": True,
                        "refresh_error": EQUIPMENT_SAVED_NOT_RELOADED}), status_code
    return jsonify({"confirmation": confirmation, "saved": True, **payload}), status_code


@events_bp.get("/<int:event_id>/equipment-requirements")
@jwt_required()
def get_equipment_requirements(event_id: int):
    try:
        user, event = _equipment_event(event_id, can_view_equipment, EQUIPMENT_VIEW_DENIED,
                                       hide_drafts=True)
        payload = _equipment_page(user, event)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The equipment requirements could not be loaded. Please try again.", 503,
                      retryable=True)
    return jsonify(payload)


@events_bp.post("/<int:event_id>/equipment-requirements")
@jwt_required()
def record_equipment_requirement(event_id: int):
    """Record one requirement. It reserves nothing and changes no availability (AC5)."""
    try:
        user, event = _equipment_event(event_id, _is_current_coordinator,
                                       EQUIPMENT_COORDINATOR_ONLY)
        _require_equipment_open(event)
        values = _valid_requirement(event, _equipment_body("equipment requirement"))
        requirement = EquipmentRequirement(event_id=event.id, recorded_by_id=user.id,
                                           status=equipment.REQUESTED, **values)
        db.session.add(requirement)
        db.session.flush()  # Its id, read before the commit expires it.
        requirement_id = requirement.id
        name = equipment.describe(values["quantity"], values["equipment_type"])
        message = (f"Recorded {name} for {event.title}. "
                   "Recording a requirement does not reserve any equipment.")
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(EQUIPMENT_NOT_SAVED, 503, retryable=True)

    return _saved_reply(user, event, message, requirement_id, 201)


@events_bp.put("/<int:event_id>/equipment-requirements/<int:requirement_id>")
@jwt_required()
def edit_equipment_requirement(event_id: int, requirement_id: int):
    try:
        user, event = _equipment_event(event_id, _is_current_coordinator,
                                       EQUIPMENT_COORDINATOR_ONLY)
        # Locked first, so no reservation can be made between looking for them and
        # saving the change that releases them (SCRUM-44 A10, review).
        requirement = _event_requirement(event, requirement_id, lock=True)
        _require_equipment_open(event)
        values = _valid_requirement(event, _equipment_body("equipment requirement"),
                                    requirement.id)
        changed = any(getattr(requirement, name) != value for name, value in values.items())
        # Read before anything changes: saving the change releases them (SCRUM-44 A10).
        releases = changed and _holds_reservations(requirement)
        # Any arrangement was for the old details, so it starts again: the status goes
        # back to Requested and Technical Support's note and update are cleared (A8).
        reset = changed and (requirement.status != equipment.REQUESTED
                             or requirement.arrangement_note is not None
                             or requirement.arrangement_updated_by_id is not None)
        if changed:
            for name, value in values.items():
                setattr(requirement, name, value)
            requirement.status = equipment.REQUESTED
            requirement.arrangement_note = None
            requirement.arrangement_updated_by_id = None
            requirement.arrangement_updated_at = None
            requirement.last_saved_at = datetime.utcnow()
        name = equipment.describe(values["quantity"], values["equipment_type"])
        if not changed:
            message = f"No changes were made to {name}."
        elif reset:
            message = (f"Updated {name}. It is back to Requested and Technical Support's "
                       "earlier arrangement and note were cleared, because they were for "
                       "the old details.")
        else:
            message = f"Updated {name}."
        if releases:
            message += f" {RESERVATIONS_RELEASED}"
        requirement_id = requirement.id
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(EQUIPMENT_NOT_SAVED, 503, retryable=True)

    return _saved_reply(user, event, message, requirement_id)


@events_bp.delete("/<int:event_id>/equipment-requirements/<int:requirement_id>")
@jwt_required()
def remove_equipment_requirement(event_id: int, requirement_id: int):
    try:
        user, event = _equipment_event(event_id, _is_current_coordinator,
                                       EQUIPMENT_COORDINATOR_ONLY)
        requirement = _event_requirement(event, requirement_id, lock=True)  # as when editing
        _require_equipment_open(event)
        name = equipment.describe(requirement.quantity, requirement.equipment_type)
        releases = _holds_reservations(requirement)  # released on removal (SCRUM-44 A10)
        db.session.delete(requirement)
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(EQUIPMENT_NOT_REMOVED, 503, retryable=True)

    message = f"Removed {name}." + (f" {RESERVATIONS_RELEASED}" if releases else "")
    return _saved_reply(user, event, message)


@events_bp.patch("/<int:event_id>/equipment-requirements/<int:requirement_id>/arrangement")
@jwt_required()
def update_equipment_arrangement(event_id: int, requirement_id: int):
    """Technical Support Staff record how arranging a requirement is going (AC4). They
    can't mark it reserved or fulfilled: that is SCRUM-44 (AC6)."""
    try:
        user, event = _equipment_event(event_id, is_tech_staff, EQUIPMENT_TECH_ONLY)
        requirement = _event_requirement(event, requirement_id)
        _require_equipment_open(event)
        values, problems = equipment.parse_arrangement(_equipment_body("arrangement"))
        if problems:
            raise _Rejected(EQUIPMENT_INVALID, 422, fields=problems)
        for name, value in values.items():
            setattr(requirement, name, value)
        requirement.arrangement_updated_by_id = user.id
        requirement.arrangement_updated_at = datetime.utcnow()
        requirement_id = requirement.id
        db.session.commit()
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(ARRANGEMENT_NOT_SAVED, 503, retryable=True)

    label = equipment.status_label(values["status"])
    return _saved_reply(user, event, f"Arrangement status updated to {label}.", requirement_id)


@events_bp.get("/equipment-requests")
@jwt_required()
def list_equipment_requests():
    """Open events with recorded equipment requirements, soonest first, for Technical
    Support Staff to arrange (AC4)."""
    try:
        user = _current_user()
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)
        if not is_tech_staff(user):
            return _error(EQUIPMENT_REQUESTS_TECH_ONLY, 403)

        rows = (
            db.session.query(EquipmentRequirement.event_id, EquipmentRequirement.status,
                             func.count(EquipmentRequirement.id))
            .join(Event, Event.id == EquipmentRequirement.event_id)
            .filter(Event.status.notin_(EQUIPMENT_CLOSED_STATUSES))
            .group_by(EquipmentRequirement.event_id, EquipmentRequirement.status)
            .all()
        )
        counts = {}
        for event_id, status, count in rows:
            counts.setdefault(event_id, {})[status] = count
        events = (
            Event.query.filter(Event.id.in_(list(counts)))
            .order_by(Event.start_time.asc().nulls_last(), Event.id)
            .all()
        ) if counts else []
        coordinators = _users_by_id([event.coordinator_id for event in events])
        items = []
        for event in events:
            coordinator = coordinators.get(event.coordinator_id)
            items.append({
                "id": event.id,
                "title": event.title,
                "status": event.status,
                "start_time": _isoformat(event.start_time),
                "end_time": _isoformat(event.end_time),
                "coordinator": _user_summary(coordinator) if coordinator else None,
                "requirement_count": sum(counts[event.id].values()),
                "status_counts": {status: counts[event.id].get(status, 0)
                                  for status in equipment.ARRANGEMENT_STATUSES},
            })
    except SQLAlchemyError:
        db.session.rollback()
        return _error("The equipment requests could not be loaded. Please try again.", 503,
                      retryable=True)

    return jsonify({"events": items, "message": None if items else NO_EQUIPMENT_REQUESTS})


# ---------- Check equipment availability (SCRUM-43) ----------

EQUIPMENT_CHECK_TECH_ONLY = "Only Technical Support Staff can check equipment availability."
CHECK_DOES_NOT_RESERVE = "Checking availability does not reserve any equipment."
CHECK_NOT_COMPLETED = "The equipment availability check could not be completed. Please try again."
# The event fields the check needs, with how they are named in the error (AC5).
CHECK_TIME_FIELDS = {"start_time": "start time", "end_time": "end time"}


def _missing_times(event):
    """A 422 naming the event's times that aren't recorded (A10)."""
    missing = [name for name in CHECK_TIME_FIELDS if getattr(event, name) is None]
    if missing:
        labels = _join_words([CHECK_TIME_FIELDS[name] for name in missing])
        verb = "is" if len(missing) == 1 else "are"
        raise _Rejected(
            f"The event's {labels} {verb} not recorded, so equipment availability can't be "
            "checked. Ask the event's coordinator to record them.",
            422, missing=missing)


def _unavailable_periods(event, resource_ids):
    """{item id: its recorded unavailable periods overlapping the event} (SCRUM-43 A5)."""
    unavailable = {}
    if resource_ids:
        periods = overlapping(
            EquipmentUnavailability.query.filter(
                EquipmentUnavailability.resource_id.in_(resource_ids)),
            EquipmentUnavailability, event.start_time, event.end_time).all()
        for period in periods:
            unavailable.setdefault(period.resource_id, []).append(period)
    return unavailable


def _reserved_by_other_events(event, resource_ids):
    """{item id: quantity reserved for other events whose reservations overlap this one}.
    Touching periods don't overlap, and released reservations hold nothing (SCRUM-44 A5)."""
    if not resource_ids:
        return {}
    query = (db.session.query(EquipmentReservation.resource_id,
                              func.sum(EquipmentReservation.quantity))
             .filter(EquipmentReservation.resource_id.in_(resource_ids),
                     EquipmentReservation.status == reserving.RESERVED,
                     EquipmentReservation.event_id != event.id))
    rows = (overlapping(query, EquipmentReservation, event.start_time, event.end_time)
            .group_by(EquipmentReservation.resource_id).all())
    return {resource_id: int(total) for resource_id, total in rows}


def _suitable_resources(equipment_types, lock=False):
    """The catalogue items suiting any of these equipment types, by name, or by id when
    locked. Narrowed in SQL by the same key as availability.match_key (whitespace runs to
    one space, trimmed, lower case), so the whole catalogue is never loaded; is_suitable
    still decides (SCRUM-44 review)."""
    if not equipment_types:
        return []
    key = func.lower(func.btrim(func.regexp_replace(Resource.category, r"\s+", " ", "g")))
    query = Resource.query.filter(key.in_({availability.match_key(t) for t in equipment_types}))
    if lock:
        query = query.order_by(Resource.id).with_for_update().populate_existing()
    else:
        query = query.order_by(Resource.name, Resource.id)
    return [r for r in query.all()
            if any(availability.is_suitable(r, t) for t in equipment_types)]


def _availability_inputs(event, requirements):
    """The items suiting any requirement, with their overlapping unavailable periods and the
    quantities other overlapping events have reserved (SCRUM-43, SCRUM-44)."""
    resources = _suitable_resources([q.equipment_type for q in requirements])
    suitable_ids = [r.id for r in resources]
    return (resources, _unavailable_periods(event, suitable_ids),
            _reserved_by_other_events(event, suitable_ids))


@events_bp.get("/<int:event_id>/equipment-availability")
@jwt_required()
def check_equipment_availability(event_id: int):
    """Whether each recorded requirement can be met from the equipment catalogue over the
    event's period. Read-only: it reserves nothing (AC4)."""
    try:
        user, event = _equipment_event(event_id, is_tech_staff, EQUIPMENT_CHECK_TECH_ONLY)
        if event.status in EQUIPMENT_CLOSED_STATUSES:
            raise _Rejected(f"This event is {event.status}, so there is no equipment to arrange.",
                            409)
        _missing_times(event)

        requirements = (EquipmentRequirement.query.filter_by(event_id=event.id)
                        .order_by(EquipmentRequirement.id).all())
        resources, unavailable, reserved = _availability_inputs(event, requirements)
        # Requirements for the same equipment share its stock (review of PR #48).
        checks = availability.check_all(requirements, resources, unavailable, reserved)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(CHECK_NOT_COMPLETED, 503, retryable=True)

    return jsonify({
        "event": {
            "id": event.id,
            "title": event.title,
            "status": event.status,
            "start_time": _isoformat(event.start_time),
            "end_time": _isoformat(event.end_time),
        },
        "checks": checks,
        "summary": availability.summary(checks),
        "can_all_be_met": bool(checks) and all(c["result"] == availability.ENOUGH for c in checks),
        "can_reserve": _can_reserve(user, event),  # SCRUM-44
        "notice": CHECK_DOES_NOT_RESERVE,
        "message": None if checks else NO_EQUIPMENT_REQUIREMENTS,
    })


# ---------- Reserve equipment (SCRUM-44) ----------

# Only approved events can have equipment reserved, as only they can have a venue booked
# (A4, open question Q4).
RESERVABLE_EVENT_STATUS = "approved"
EQUIPMENT_RESERVED_NOTIFICATION = "equipment_reserved"
RESERVATIONS_VIEW_DENIED = "You are not allowed to view this event's equipment reservations."
RESERVE_TECH_ONLY = "Only Technical Support Staff can reserve equipment."
RESERVATIONS_NOT_LOADED = "The equipment reservations could not be loaded. Please try again."
# A failed save confirms nothing and leaves every reservation as it was (AC7).
EQUIPMENT_NOT_RESERVED = ("The equipment was not reserved, and the existing reservations are "
                          "unchanged. Please try again.")
RESERVED_NOT_RELOADED = ("The equipment was reserved, but the updated page could not be "
                         "loaded. Reload the page to see it.")
RESERVATIONS_RELEASED = "Its reserved equipment was released."
RESERVATION_REQUIREMENT_ID = "Choose the equipment requirement to reserve for."


def _holds_reservations(requirement):
    """Whether any equipment is reserved for the requirement now (SCRUM-44 A10)."""
    return db.session.query(
        EquipmentReservation.query.filter_by(requirement_id=requirement.id,
                                             status=reserving.RESERVED).exists()).scalar()


def _has_times(event):
    return event.start_time is not None and event.end_time is not None


def _not_reservable(event):
    """Why nothing can be reserved for the event now, or None (A4)."""
    if event.status in EQUIPMENT_CLOSED_STATUSES:
        return f"This event is {event.status}, so equipment can't be reserved for it."
    if event.status != RESERVABLE_EVENT_STATUS:
        return (f"Equipment can only be reserved for approved events. "
                f"This event is {event.status}.")
    if not _has_times(event):
        return ("The event's start or end time is not recorded, so equipment can't be "
                "reserved for it.")
    return None


def _can_reserve(user, event):
    return is_tech_staff(user) and _not_reservable(event) is None


def _minutes(value):
    return value.strftime("%Y-%m-%d %H:%M")


def _reserved_for(reservations):
    """{item id: quantity} of the reservations that still hold equipment."""
    totals = {}
    for reservation in reservations:
        if reservation.status == reserving.RESERVED:
            totals[reservation.resource_id] = (totals.get(reservation.resource_id, 0)
                                               + reservation.quantity)
    return totals


def _reservation_payload(reservation, names, users):
    reserver = users.get(reservation.reserved_by_id)
    return {
        "id": reservation.id,
        "requirement_id": reservation.requirement_id,
        "resource": {"id": reservation.resource_id, "name": names.get(reservation.resource_id)},
        "quantity": reservation.quantity,
        "start_time": _isoformat(reservation.start_time),
        "end_time": _isoformat(reservation.end_time),
        "status": reservation.status,
        "reserved_by": _user_summary(reserver) if reserver else None,
        "reserved_at": _isoformat(reservation.reserved_at),
        "released_at": _isoformat(reservation.released_at),
        "release_reason": reservation.release_reason,
    }


def _reservation_page(user, event):
    """The event, its reservation period, and for each requirement what is reserved and
    what can still be reserved (AC1), with the released reservations as history (AC9)."""
    requirements = (EquipmentRequirement.query.filter_by(event_id=event.id)
                    .order_by(EquipmentRequirement.id).all())
    rows = (EquipmentReservation.query.filter_by(event_id=event.id)
            .order_by(EquipmentReservation.id).all())
    timed = _has_times(event)
    resources, unavailable, reserved = (_availability_inputs(event, requirements) if timed
                                        else ([], {}, {}))
    reserved_here = _reserved_for(rows)
    names = {r.id: r.name for r in resources}
    unnamed = {r.resource_id for r in rows} - set(names)
    if unnamed:
        names.update({r.id: r.name for r in Resource.query.filter(Resource.id.in_(unnamed))})
    users = _users_by_id([event.coordinator_id] + [r.reserved_by_id for r in rows])
    coordinator = users.get(event.coordinator_id)
    notice = _not_reservable(event)

    lines = []
    for requirement in requirements:
        line = availability.check(requirement, resources, unavailable, reserved)
        held = [r for r in rows
                if r.requirement_id == requirement.id and r.status == reserving.RESERVED]
        reserved_quantity = sum(r.quantity for r in held)
        remaining = max(requirement.quantity - reserved_quantity, 0)
        options = reserving.options(line, reserved_here)
        available = sum(option["available_to_reserve"] for option in options)
        # Agrees with the notice when the event can't be reserved for (SCRUM-44 review).
        state = reserving.state(remaining, available, reservable=notice is None)
        lines.append({
            "id": requirement.id,
            "equipment_type": requirement.equipment_type,
            "quantity": requirement.quantity,
            "technical_requirements": _recorded(requirement.technical_requirements),
            "technical_note": line["technical_note"],
            "reserved_quantity": reserved_quantity,
            "remaining_quantity": remaining,
            "available_to_reserve": available,
            "state": state,
            "state_label": reserving.STATE_LABELS[state],
            "options": options,
            "excluded": line["excluded"],
            "reservations": [_reservation_payload(r, names, users) for r in held],
        })

    return {
        "event": {
            "id": event.id,
            "title": event.title,
            "status": event.status,
            "start_time": _isoformat(event.start_time),
            "end_time": _isoformat(event.end_time),
            "coordinator": _user_summary(coordinator) if coordinator else None,
        },
        "reservation_period": ({"start_time": _isoformat(event.start_time),
                                "end_time": _isoformat(event.end_time)} if timed else None),
        "can_reserve": _can_reserve(user, event),
        "notice": notice,
        "requirements": lines,
        "released": [_reservation_payload(r, names, users) for r in rows
                     if r.status == reserving.RELEASED],
        "message": None if requirements else NO_EQUIPMENT_REQUIREMENTS,
    }


@events_bp.get("/<int:event_id>/equipment-reservations")
@jwt_required()
def get_equipment_reservations(event_id: int):
    try:
        user, event = _equipment_event(event_id, can_view_equipment, RESERVATIONS_VIEW_DENIED)
        payload = _reservation_page(user, event)
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(RESERVATIONS_NOT_LOADED, 503, retryable=True)
    return jsonify(payload)


def _queue_reservation_email(to_address, title, message, event_id):
    """Tell the event's coordinator what was reserved (AC8)."""
    return _queue_email(
        to_address,
        f"Equipment reserved for {title}",
        f"{message}\n\nSign in to ConnectSphere to see the event's equipment.",
        event_id,
    )


@events_bp.post("/<int:event_id>/equipment-reservations")
@jwt_required()
def reserve_equipment(event_id: int):
    """Reserve items and quantities for one of the event's requirements (AC2, AC3).

    Availability is worked out again from the saved data with the event, the requirement
    and the suitable equipment locked, in that order, so two reservations (or a reservation
    and a cancellation) can't both take the same units (A7). Everything is checked before
    anything is saved, and the reservations and the coordinator's notification are saved
    together, so a refusal or a failed save changes nothing (AC5-AC7)."""
    try:
        user, event = _equipment_event(event_id, is_tech_staff, RESERVE_TECH_ONLY)
        body = _equipment_body("reservation")
        requirement_id = body.get("requirement_id")
        if not isinstance(requirement_id, int) or isinstance(requirement_id, bool):
            raise _Rejected(EQUIPMENT_INVALID, 422,
                            fields={"requirement_id": RESERVATION_REQUIREMENT_ID})
        event = db.session.get(Event, event.id, with_for_update=True, populate_existing=True)
        requirement = _event_requirement(event, requirement_id, lock=True)
        refusal = _not_reservable(event)
        if refusal and event.status == RESERVABLE_EVENT_STATUS:
            _missing_times(event)  # 422 naming the times (A13)
        if refusal:
            raise _Rejected(refusal, 409)

        # Stable from here: another reservation for this event waits for the event's lock.
        own = EquipmentReservation.query.filter_by(event_id=event.id,
                                                   status=reserving.RESERVED).all()
        held = sum(r.quantity for r in own if r.requirement_id == requirement.id)
        remaining = requirement.quantity - held
        if remaining <= 0:
            raise _Rejected(reserving.fully_reserved_message(requirement), 409)

        selection, problems = reserving.parse_items(body.get("items"))
        chosen = {}
        if not problems:
            ids = [resource_id for resource_id, _ in selection
                   if 1 <= resource_id <= DB_INTEGER_MAX]
            chosen = ({r.id: r for r in Resource.query.filter(Resource.id.in_(ids))}
                      if ids else {})
            problems = reserving.selection_problems(selection, chosen, requirement, remaining)
        if problems:
            raise _Rejected(EQUIPMENT_INVALID, 422, fields={"items": " ".join(problems)})

        # Checked again now, with the suitable equipment locked (AC2, A7).
        locked = _suitable_resources([requirement.equipment_type], lock=True)
        suitable_ids = [r.id for r in locked]
        line = availability.check(requirement, locked,
                                  _unavailable_periods(event, suitable_ids),
                                  _reserved_by_other_events(event, suitable_ids))
        can_reserve = {option["id"]: option["available_to_reserve"]
                       for option in reserving.options(line, _reserved_for(own))}
        available = sum(can_reserve.values())
        if available == 0:
            raise _Rejected(reserving.none_available_message(requirement), 409,
                            available_quantity=0)
        shortfalls = reserving.shortfalls(selection, can_reserve,
                                          {r.id: r.name for r in chosen.values()})
        if shortfalls:
            raise _Rejected(reserving.not_enough_message(shortfalls), 409,
                            available_quantity=available, shortfalls=shortfalls)

        now = datetime.utcnow()
        rows = [EquipmentReservation(event_id=event.id, requirement_id=requirement.id,
                                     resource_id=resource_id, quantity=quantity,
                                     start_time=event.start_time, end_time=event.end_time,
                                     status=reserving.RESERVED, reserved_by_id=user.id,
                                     reserved_at=now)
                 for resource_id, quantity in selection]
        db.session.add_all(rows)
        what = reserving.describe_items([(chosen[resource_id].name, quantity)
                                         for resource_id, quantity in selection])
        needed = equipment.describe(requirement.quantity, requirement.equipment_type)
        period = f"{_minutes(event.start_time)} to {_minutes(event.end_time)}"
        title = event.title
        coordinator = db.session.get(User, event.coordinator_id) if event.coordinator_id else None
        message = f"Technical Support reserved {what} for {needed} at {title}, {period}."
        if coordinator:
            db.session.add(Notification(recipient_id=coordinator.id,
                                        kind=EQUIPMENT_RESERVED_NOTIFICATION,
                                        message=message, event_id=event.id))
        db.session.flush()  # The ids, read before the commit expires them.
        reservation_ids = [row.id for row in rows]
        to_address = coordinator.email if coordinator else None
        db.session.commit()
    except _Rejected as rejected:
        db.session.rollback()  # Releases the locks taken above.
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(EQUIPMENT_NOT_RESERVED, 503, retryable=True)

    # After the commit: a queue outage must not undo or hide the reservation (A9).
    email_queued = (_queue_reservation_email(to_address, title, message, event_id)
                    if to_address else False)
    confirmation = f"Reserved {what} for {needed} at {title}, {period}."
    if to_address:
        confirmation += " The event's coordinator has been notified."
    notification = {"in_app": to_address is not None, "email_queued": email_queued}
    try:
        page = _reservation_page(user, event)
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"confirmation": confirmation, "saved": True,
                        "notification": notification,
                        "refresh_error": RESERVED_NOT_RELOADED}), 201
    made = [reservation for line in page["requirements"] for reservation in line["reservations"]
            if reservation["id"] in reservation_ids]
    return jsonify({"confirmation": confirmation, "saved": True, "reservations": made,
                    "notification": notification, **page}), 201


# ---------- Request a change to an approved event (SCRUM-46) ----------

# Only approved events can have a change requested (A1, open question Q1).
CHANGEABLE_STATUS = "approved"
CHANGE_REQUEST_NOTIFICATION = "change_requested"
CHANGE_REQUEST_ORGANISER_ONLY = "You can only request changes to events you organise."
CHANGE_FORM_NOT_LOADED = "The change request form could not be loaded. Please try again."
# A failed save leaves the event and its requests as they were (AC8).
CHANGE_NOT_SUBMITTED = ("Your change request was not submitted, and the event is unchanged. "
                        "Please try again.")
CHANGES_INVALID = "Some changes can't be requested. Please correct them and try again."
NO_CHANGES_TO_REQUEST = "There are no changes to request. Change at least one value."
CHANGE_ALREADY_PENDING = ("A change request for this event is already pending review. You can "
                          "request another once it has been decided.")
# The database's guard on A6 (models.EventChangeRequest), so a save it refuses is told
# apart from any other refused save.
ONE_PENDING_INDEX = "event_change_requests_one_pending_per_event"


def _change_request_event(event_id, lock=False):
    """The caller and their event, checked in the order 401, 404, 403 (A9). With lock,
    the event is held until commit, so two requests for it are checked one at a time (A6)."""
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    locking = {"with_for_update": True, "populate_existing": True} if lock else {}
    event = db.session.get(Event, event_id, **locking) if event_id <= DB_INTEGER_MAX else None
    if event is None:
        raise _Rejected(EVENT_NOT_FOUND, 404)
    if not is_current_organiser(user, event):
        raise _Rejected(CHANGE_REQUEST_ORGANISER_ONLY, 403)
    return user, event


def _pending_change_request(event):
    return EventChangeRequest.query.filter_by(event_id=event.id,
                                              status=change_requests.PENDING_REVIEW).first()


def _reviewing_coordinator(event):
    """The event's coordinator, or None (A5). As everywhere else (_is_current_coordinator),
    that is the assigned user while they still have the coordinator role, so someone whose
    role has changed is neither shown nor notified."""
    if event.coordinator_id is None:
        return None
    coordinator = db.session.get(User, event.coordinator_id)
    return coordinator if _is_current_coordinator(coordinator, event) else None


def _is_second_pending_request(error):
    """Whether a refused save broke the one-pending index (A6), not some other rule."""
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == ONE_PENDING_INDEX


def _change_request_blocked(event, coordinator, pending):
    """Why no change can be requested for the event now, as (reason, message), or None."""
    if event.status != CHANGEABLE_STATUS:
        return "not_approved", (
            "Changes can only be requested for approved events. "
            f"This event is {event.status.replace('_', ' ')}.")
    if coordinator is None:
        # AC5: nobody would review it. It waits in the Lead's queue (SCRUM-70 AC5, A9).
        return "no_coordinator", (
            "This event is waiting for a coordinator to be assigned, so there is nobody to "
            "review a change request yet. Please try again once a coordinator is assigned.")
    if pending is not None:
        return "pending", CHANGE_ALREADY_PENDING  # A6, open question Q5
    return None


def _change_request_payload(row, users):
    """The request, with the coordinator's decision once there is one (SCRUM-70 A4).
    `users` holds its requester and decider by id."""
    requester = users.get(row.requested_by_id)
    decider = users.get(row.decided_by_id)
    return {
        "id": row.id,
        "event_id": row.event_id,
        "status": row.status,
        "status_label": change_requests.STATUS_LABELS.get(row.status, row.status),
        # JSONB doesn't keep key order, so the fields' display order is used.
        "changes": [{"field": name, "label": label, "from": row.changes[name]["from"],
                     "to": row.changes[name]["to"]}
                    for name, label in change_requests.PERMITTED_FIELDS.items()
                    if name in row.changes],
        "requested_by": _user_summary(requester) if requester else None,
        "requested_at": _isoformat(row.requested_at),
        "decided_at": _isoformat(row.decided_at),
        "decided_by": _user_summary(decider) if decider else None,
        "decision_reason": row.decision_reason,
    }


def _request_users(rows):
    """The requesters and deciders of these requests, by id."""
    return _users_by_id([user_id for row in rows if row is not None
                         for user_id in (row.requested_by_id, row.decided_by_id)])


def _latest_decision(event):
    """The event's most recently decided change request, or None (SCRUM-70 AC3)."""
    return (EventChangeRequest.query
            .filter(EventChangeRequest.event_id == event.id,
                    EventChangeRequest.decided_at.isnot(None))
            .order_by(EventChangeRequest.decided_at.desc(), EventChangeRequest.id.desc())
            .first())


@events_bp.get("/<int:event_id>/change-requests")
@jwt_required()
def get_change_request_form(event_id: int):
    """The organiser's form: the event's current values of the fields they may change,
    and whether a change can be requested now, with why not (AC1, AC5)."""
    try:
        _, event = _change_request_event(event_id)
        coordinator = _reviewing_coordinator(event)
        pending = _pending_change_request(event)
        blocked = _change_request_blocked(event, coordinator, pending)
        latest = _latest_decision(event)
        users = _request_users([pending, latest])
        current = {name: (_isoformat(getattr(event, name))
                          if name in change_requests.TIME_FIELDS
                          else _recorded(getattr(event, name)))
                   for name in change_requests.PERMITTED_FIELDS}
        payload = {
            "event": {
                "id": event.id,
                "title": event.title,
                "status": event.status,
                "coordinator": _user_summary(coordinator) if coordinator else None,
                "current": current,
            },
            "fields": [{"name": name, "label": label}
                       for name, label in change_requests.PERMITTED_FIELDS.items()],
            "can_request": blocked is None,
            "blocked_reason": blocked[0] if blocked else None,
            "message": blocked[1] if blocked else None,
            "pending_request": _change_request_payload(pending, users) if pending else None,
            # SCRUM-70 AC3: the organiser sees the outcome of their last decided request.
            "latest_decision": _change_request_payload(latest, users) if latest else None,
        }
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(CHANGE_FORM_NOT_LOADED, 503, retryable=True)
    return jsonify(payload)


def _queue_change_request_email(to_address, title, requester, changes, event_id):
    """Tell the event's coordinator what was asked for (AC9)."""
    lines = "\n".join(change_requests.describe({name: change})
                      for name, change in changes.items())
    return _queue_email(
        to_address,
        f"Change request for {title}",
        f'{requester} has requested changes to "{title}":\n\n{lines}\n\n'
        "Sign in to ConnectSphere to review the request.",
        event_id,
    )


@events_bp.post("/<int:event_id>/change-requests")
@jwt_required()
def submit_change_request(event_id: int):
    """Record the organiser's proposed changes as a request pending review (AC3, AC6).

    The event is locked, then checked; every proposed value is checked before anything
    is saved; and the request and the coordinator's notification are saved together, so
    a refusal or a failed save changes nothing (AC4, AC8). The event itself is never
    changed here (AC7)."""
    try:
        user, event = _change_request_event(event_id, lock=True)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise _Rejected("Send the change request as a JSON object.", 400)
        coordinator = _reviewing_coordinator(event)
        blocked = _change_request_blocked(event, coordinator, _pending_change_request(event))
        if blocked:
            raise _Rejected(blocked[1], 409, reason=blocked[0])
        changes, problems = change_requests.parse_proposal(event, body)
        if problems:
            raise _Rejected(CHANGES_INVALID, 422, fields=problems)
        if not changes:
            raise _Rejected(NO_CHANGES_TO_REQUEST, 422, fields={})

        title, requester, to_address = event.title, user.email, coordinator.email
        row = EventChangeRequest(event_id=event.id, requested_by_id=user.id,
                                 status=change_requests.PENDING_REVIEW,
                                 changes=change_requests.as_json(changes),
                                 requested_at=datetime.utcnow())
        db.session.add(row)
        db.session.add(Notification(
            recipient_id=coordinator.id, kind=CHANGE_REQUEST_NOTIFICATION, event_id=event.id,
            message=(f'{requester} requested changes to "{title}": '
                     f"{change_requests.describe(changes)}.")))
        db.session.flush()  # The id, read before the commit expires it.
        payload = _change_request_payload(row, {user.id: user})
        db.session.commit()
    except _Rejected as rejected:
        db.session.rollback()  # Releases the event's lock.
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except IntegrityError as error:
        db.session.rollback()
        if _is_second_pending_request(error):
            # Another request for the event was saved first (A6).
            return _error(CHANGE_ALREADY_PENDING, 409, reason="pending")
        return _error(CHANGE_NOT_SUBMITTED, 503, retryable=True)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(CHANGE_NOT_SUBMITTED, 503, retryable=True)

    # After the commit: a queue outage must not undo or hide the request (A8).
    email_queued = _queue_change_request_email(to_address, title, requester, changes, event_id)
    labels = _join_words([change_requests.PERMITTED_FIELDS[name] for name in changes])
    return jsonify({
        "message": (f'Your change request for "{title}" ({labels}) is '
                    f"{payload['status_label']}. The event's coordinator, {to_address}, "
                    "has been notified."),
        "request": payload,
        "notification": {"in_app": True, "email_queued": email_queued},
    }), 201


# ---------- Review a change request (SCRUM-70) ----------

CHANGE_REVIEW_COORDINATOR_ONLY = "Only the event's coordinator can review its change requests."
CHANGE_REVIEWERS_ONLY = "Only event coordinators can review change requests."
CHANGE_REQUEST_NOT_FOUND = "Change request not found."
CHANGE_REVIEW_NOT_LOADED = "The change request could not be loaded. Please try again."
CHANGE_REVIEWS_NOT_LOADED = "Change requests could not be loaded. Please try again."
NO_CHANGE_REQUESTS_TO_REVIEW = "You have no change requests to review."
# AC6: a failed save changes nothing.
CHANGE_DECISION_NOT_SAVED = ("The decision was not saved, so the change request and the event "
                             "are unchanged. Please try again.")
# What the organiser is told of the decision (AC7, A7).
CHANGE_DECISION_NOTIFICATIONS = {change_requests.ACCEPTED: "change_request_accepted",
                                 change_requests.REJECTED: "change_request_rejected"}
# What registered attendees are told when an accepted change moves the event (AC9, A7).
EVENT_DETAILS_CHANGED_NOTIFICATION = "event_details_changed"


def _review_target(event_id, request_id, lock=False):
    """The caller, the event and its change request, checked in the order 401, 404, 403
    (A8). With lock, the event and then the request are read FOR UPDATE, in the order
    submitting a request locks them, so decisions and new requests happen one at a time."""
    user = _current_user()
    if user is None:
        raise _Rejected("Your session is no longer valid. Please log in again.", 401)
    locking = {"with_for_update": True, "populate_existing": True} if lock else {}
    event = db.session.get(Event, event_id, **locking) if event_id <= DB_INTEGER_MAX else None
    if event is None:
        raise _Rejected(EVENT_NOT_FOUND, 404)
    row = (db.session.get(EventChangeRequest, request_id, **locking)
           if request_id <= DB_INTEGER_MAX else None)
    # Another event's request is not found here, so its existence isn't revealed.
    if row is None or row.event_id != event.id:
        raise _Rejected(CHANGE_REQUEST_NOT_FOUND, 404)
    if not _is_current_coordinator(user, event):
        raise _Rejected(CHANGE_REVIEW_COORDINATOR_ONLY, 403)
    return user, event, row


def _decision_blocked(event, row):
    """Why the request can't be decided now, as (reason, message), or None (A1, A4)."""
    if row.status != change_requests.PENDING_REVIEW:
        return "decided", f"This change request was already {row.status}."
    if event.status != CHANGEABLE_STATUS:
        return "not_approved", (
            "A change request can only be decided while its event is approved. "
            f"This event is {event.status.replace('_', ' ')}.")
    return None


def _change_impact(event, row):
    """What the request would affect, from the event's arrangements as recorded now (A3)."""
    bookings = (VenueBooking.query.filter_by(event_id=event.id)
                .order_by(VenueBooking.start_time, VenueBooking.id).all())
    venue_ids = {booking.venue_id for booking in bookings}
    venues = ({venue.id: venue for venue in Venue.query.filter(Venue.id.in_(venue_ids))}
              if venue_ids else {})
    requirements = (EquipmentRequirement.query.filter_by(event_id=event.id)
                    .order_by(EquipmentRequirement.id).all())
    reserved = dict(
        db.session.query(EquipmentReservation.requirement_id,
                         func.sum(EquipmentReservation.quantity))
        .filter(EquipmentReservation.event_id == event.id,
                EquipmentReservation.status == reserving.RESERVED)
        .group_by(EquipmentReservation.requirement_id).all())
    registered = Registration.query.filter_by(event_id=event.id, status=REGISTERED).count()
    return change_review.impact(
        row.changes,
        [{"id": booking.id, "status": booking.status,
          "venue": {"id": booking.venue_id, "name": venues[booking.venue_id].name,
                    "capacity": venues[booking.venue_id].capacity},
          "start_time": booking.start_time, "end_time": booking.end_time,
          "hold_expires_at": booking.hold_expires_at} for booking in bookings],
        [{"id": requirement.id, "equipment_type": requirement.equipment_type,
          "quantity": requirement.quantity, "reserved": int(reserved.get(requirement.id, 0))}
         for requirement in requirements],
        {"registered": registered, "capacity": event.registration_capacity,
         "closes_at": event.registration_closes_at},
        singapore_now(),
    )


@events_bp.get("/change-requests")
@jwt_required()
def list_change_requests_to_review():
    """The pending change requests of the events the caller coordinates, oldest first (A10)."""
    try:
        user = _current_user()
        if user is None:
            raise _Rejected("Your session is no longer valid. Please log in again.", 401)
        if user.role != COORDINATOR_ROLE:
            raise _Rejected(CHANGE_REVIEWERS_ONLY, 403)
        rows = (EventChangeRequest.query
                .join(Event, Event.id == EventChangeRequest.event_id)
                .filter(Event.coordinator_id == user.id,
                        EventChangeRequest.status == change_requests.PENDING_REVIEW)
                .order_by(EventChangeRequest.requested_at, EventChangeRequest.id).all())
        events = ({event.id: event for event in
                   Event.query.filter(Event.id.in_({row.event_id for row in rows}))}
                  if rows else {})
        users = _request_users(rows)
        requests = [{**_change_request_payload(row, users),
                     "event": {"id": row.event_id, "title": events[row.event_id].title,
                               "status": events[row.event_id].status}}
                    for row in rows]
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(CHANGE_REVIEWS_NOT_LOADED, 503, retryable=True)
    return jsonify({"requests": requests,
                    "message": None if requests else NO_CHANGE_REQUESTS_TO_REVIEW})


@events_bp.get("/<int:event_id>/change-requests/<int:request_id>")
@jwt_required()
def review_change_request(event_id: int, request_id: int):
    """The request, what it would affect, and whether it can be decided now (AC2, A1)."""
    try:
        _, event, row = _review_target(event_id, request_id)
        organiser = db.session.get(User, event.organiser_id)
        blocked = _decision_blocked(event, row)
        payload = {
            "event": {"id": event.id, "title": event.title, "status": event.status,
                      "organiser": _user_summary(organiser) if organiser else None},
            "request": _change_request_payload(row, _request_users([row])),
            # Only before deciding (AC2): once decided, the event's arrangements no longer
            # describe what the request would change.
            "impact": (_change_impact(event, row)
                       if row.status == change_requests.PENDING_REVIEW else None),
            "can_decide": blocked is None,
            "blocked_reason": blocked[0] if blocked else None,
            "message": blocked[1] if blocked else None,
        }
    except _Rejected as rejected:
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(CHANGE_REVIEW_NOT_LOADED, 503, retryable=True)
    return jsonify(payload)


def _has_reserved_equipment(event):
    return db.session.query(EquipmentReservation.query.filter_by(
        event_id=event.id, status=reserving.RESERVED).exists()).scalar()


def _registered_attendees(event):
    """Everyone registered for the event now; not those who withdrew (AC9)."""
    return (User.query.join(Registration, Registration.attendee_id == User.id)
            .filter(Registration.event_id == event.id, Registration.status == REGISTERED)
            .order_by(User.id).distinct().all())


def _change_decision_message(title, status, decider, row):
    """The organiser's notification: the outcome, who decided and when, and the changes
    or the reason (AC7)."""
    message = (f'Your change request for "{title}" was {status} by {decider.email} on '
               f"{_singapore_time(row.decided_at)}.")
    if status == change_requests.ACCEPTED:
        return f"{message} The event now shows: {change_requests.describe(row.changes)}."
    return f"{message} Reason: {row.decision_reason}"


def _new_details_message(event):
    """What registered attendees are told when the event moves (AC9)."""
    venue = db.session.get(Venue, event.venue_id) if event.venue_id else None
    where = f"at {venue.name}" if venue else "at a venue still to be confirmed"
    return (f'The date and time of "{event.title}" have changed. It now runs from '
            f"{event.start_time:%Y-%m-%d %H:%M} to {event.end_time:%Y-%m-%d %H:%M} "
            f"(Singapore time) {where}.")


def _queue_emails(emails, event_id):
    """Queue each (address, subject, body); stop at the first that can't be queued, since
    the queue is then down for the rest too (A7). False if any was not queued."""
    return all(_queue_email(*email, event_id) for email in emails)


@events_bp.post("/<int:event_id>/change-requests/<int:request_id>/decision")
@jwt_required()
def decide_change_request(event_id: int, request_id: int):
    """Accept or reject a pending change request (AC3).

    The decision, the event's new values (AC8) and the notifications to the organiser and,
    when the event moves, its registered attendees (AC7, AC9) are saved in one commit, so a
    refusal or a failed save changes nothing (AC6). Emails are queued after it."""
    try:
        user, event, row = _review_target(event_id, request_id, lock=True)
        try:
            status, reason = change_review.parse_decision(request.get_json(silent=True))
        except change_review.Refused as refused:
            extra = {"field": refused.field} if refused.field else {}
            raise _Rejected(refused.message, 400, **extra) from None
        blocked = _decision_blocked(event, row)
        if blocked:
            raise _Rejected(blocked[1], 409, reason=blocked[0])

        accepted = status == change_requests.ACCEPTED
        moves = accepted and change_review.changes_times(row.changes)
        # New times release the event's reserved equipment (SCRUM-44 A10), so say so.
        releases = moves and _has_reserved_equipment(event)
        organiser = db.session.get(User, event.organiser_id)
        row.status = status
        row.decided_at = datetime.utcnow()
        row.decided_by_id = user.id
        row.decision_reason = reason
        if accepted:
            for name, value in change_review.applied_values(row.changes).items():
                setattr(event, name, value)
        title = event.title
        message = _change_decision_message(title, status, user, row)
        db.session.add(Notification(recipient_id=organiser.id, event_id=event.id,
                                    kind=CHANGE_DECISION_NOTIFICATIONS[status], message=message))
        emails = [(organiser.email, f"Your change request was {status}: {title}",
                   f"{message}\n\nSign in to ConnectSphere to see your event's change requests.")]
        attendees = _registered_attendees(event) if moves else []
        if attendees:
            details = _new_details_message(event)
            for attendee in attendees:
                db.session.add(Notification(recipient_id=attendee.id, event_id=event.id,
                                            kind=EVENT_DETAILS_CHANGED_NOTIFICATION,
                                            message=details))
            emails += [(attendee.email, f"New date and time for {title}",
                        f"{details}\n\nSign in to ConnectSphere to see the event's details.")
                       for attendee in attendees]
        db.session.flush()  # Saved now, so the reply is built from what will be committed.
        payload = _change_request_payload(row, {**_request_users([row]), user.id: user})
        organiser_email = organiser.email
        db.session.commit()
    except _Rejected as rejected:
        db.session.rollback()  # Releases the locks.
        return _error(rejected.message, rejected.status_code, **rejected.extra)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(CHANGE_DECISION_NOT_SAVED, 503, retryable=True)

    # After the commit: a queue outage must not undo or hide the decision (A7).
    email_queued = _queue_emails(emails, event_id)
    if accepted:
        confirmation = (f'You accepted the change request for "{title}". The event now shows '
                        "the new values.")
        if releases:
            confirmation += f" {RESERVATIONS_RELEASED}"
    else:
        confirmation = f'You rejected the change request for "{title}".'
    confirmation += f" {organiser_email} has been notified"
    if attendees:
        told = (f"{len(attendees)} registered attendee was" if len(attendees) == 1
                else f"{len(attendees)} registered attendees were")
        confirmation += f", and {told} told the new date and time"
    return jsonify({
        "message": f"{confirmation}.",
        "request": payload,
        "notification": {"in_app": True, "email_queued": email_queued,
                         "attendees_notified": len(attendees)},
    })
