"""SCRUM-70: what a change request affects, and what deciding it takes.

Pure rules, independent of Flask and the database, like change_requests.py. The route
loads the event's arrangements as plain values and works out who may decide; these rules
say which arrangements a change affects and why (A3), check a decision (A4, A5) and give
the values an accepted request applies (A6).
"""

from datetime import datetime

from .change_requests import ACCEPTED, PERMITTED_FIELDS, REJECTED, TIME_FIELDS

DECISIONS = {"accept": ACCEPTED, "reject": REJECTED}
# AC4. Must match MAX_REASON_LENGTH in frontend/src/pages/ChangeRequestReviewPage.jsx.
REASON_MAX_LENGTH = 500
# Must match REASON_REQUIRED in frontend/src/pages/ChangeRequestReviewPage.jsx.
REASON_REQUIRED = "A reason is required to reject this change request."
# Venue bookings that hold, or may yet hold, their venue (SCRUM-94 AC1). A tentative one
# only while its hold lasts (SCRUM-87).
LIVE_BOOKING_STATUSES = {"pending", "confirmed"}
TENTATIVE = "tentative"
NOTHING_AFFECTED = ("Nothing recorded for this event is affected by these changes: no venue "
                    "bookings, equipment or registrations.")


class Refused(Exception):
    """A decision that can't be made as sent: the message to show, and the field at fault."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def _has_visible_text(text):
    # As _has_visible_text in routes.py (SCRUM-60 A3): spaces of any kind, including
    # invisible ones, are not a reason.
    return any(char.isprintable() and not char.isspace() for char in text)


def parse_decision(body):
    """(status, reason) from the request body, or Refused. A reason is only kept when
    rejecting (A5)."""
    decision = body.get("decision") if isinstance(body, dict) else None
    if not isinstance(decision, str) or decision not in DECISIONS:
        raise Refused("Choose whether to accept or reject the change request.")
    reason = body.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise Refused("The reason must be text.", "reason")
    if decision == "accept":
        return ACCEPTED, None
    reason = reason.strip() if reason and _has_visible_text(reason) else None
    if reason is None:
        raise Refused(REASON_REQUIRED, "reason")
    if len(reason) > REASON_MAX_LENGTH:
        raise Refused(f"Your reason is {len(reason):,} characters long. The limit is "
                      f"{REASON_MAX_LENGTH} characters, so remove "
                      f"{len(reason) - REASON_MAX_LENGTH:,} and try again.", "reason")
    return REJECTED, reason


def changes_times(changes):
    """Whether the request changes the event's start or end (AC9)."""
    return any(name in changes for name in TIME_FIELDS)


def applied_values(changes):
    """The event's new values, from the request as stored (A6)."""
    return {name: (datetime.fromisoformat(change["to"])
                   if name in TIME_FIELDS and change["to"] is not None else change["to"])
            for name, change in changes.items() if name in PERMITTED_FIELDS}


def _shown(value):
    return value.strftime("%Y-%m-%d %H:%M")


def _is_live(booking, now):
    if booking["status"] == TENTATIVE:
        return booking["hold_expires_at"] is not None and booking["hold_expires_at"] > now
    return booking["status"] in LIVE_BOOKING_STATUSES


def _people(count, one, many):
    return f"{count} {one if count == 1 else many}"


def _booking_reasons(booking, changes):
    reasons = []
    if changes_times(changes):
        reasons.append("Booked for the current date and time; it isn't moved automatically.")
    if "expected_attendance" in changes:
        capacity, attendance = booking["venue"]["capacity"], changes["expected_attendance"]["to"]
        if capacity is not None and capacity < attendance:
            reasons.append(f"{booking['venue']['name']} holds {capacity} people, fewer than the "
                           f"new expected attendance of {attendance}.")
    if "venue_requirements" in changes:
        reasons.append("Venue Staff assessed it against the current venue requirements.")
    return reasons


def _equipment_reasons(requirement, changes):
    reasons = []
    if changes_times(changes) and requirement["reserved"]:
        reasons.append(f"{requirement['reserved']} reserved for the current date and time; "
                       "they are released if the change is accepted.")
    if "equipment_requirements" in changes:
        reasons.append("Recorded from the current equipment requirements.")
    return reasons


def _registration_reasons(registration, changes):
    reasons = []
    registered = registration["registered"]
    if changes_times(changes):
        if registered:
            reasons.append(f"{_people(registered, 'registered attendee', 'registered attendees')} "
                           f"will be told the new date and time.")
        start = changes.get("start_time", {}).get("to")
        closes = registration["closes_at"]
        if start is not None and closes is not None and closes > datetime.fromisoformat(start):
            reasons.append(f"Registration closes {_shown(closes)}, after the new start "
                           f"{_shown(datetime.fromisoformat(start))}.")
    if "expected_attendance" in changes:
        attendance = changes["expected_attendance"]["to"]
        if registered > attendance:
            reasons.append(f"{registered} people are already registered, more than the new "
                           f"expected attendance of {attendance}.")
        capacity = registration["capacity"]
        if capacity is not None and capacity > attendance:
            reasons.append(f"Registration has {capacity} places, more than the new expected "
                           f"attendance of {attendance}.")
    return reasons


def impact(changes, bookings, equipment, registration, now):
    """Which of the event's live arrangements the changes affect, each with why (A3).

    `changes` is the request as stored; `bookings` the event's venue bookings, each with
    its venue's id, name and capacity; `equipment` its equipment requirements with the
    quantity reserved for each; `registration` the number registered, the places set and
    when registration closes; `now` the current Singapore time, for holds.
    """
    venue_bookings = []
    for booking in bookings:
        reasons = _booking_reasons(booking, changes) if _is_live(booking, now) else []
        if reasons:
            venue_bookings.append({
                "id": booking["id"],
                "venue": {"id": booking["venue"]["id"], "name": booking["venue"]["name"]},
                "start_time": booking["start_time"].isoformat(),
                "end_time": booking["end_time"].isoformat(),
                "status": booking["status"],
                "reasons": reasons,
            })
    affected_equipment = []
    for requirement in equipment:
        reasons = _equipment_reasons(requirement, changes)
        if reasons:
            affected_equipment.append({**requirement, "reasons": reasons})
    registrations = {"registered": registration["registered"],
                     "capacity": registration["capacity"],
                     "reasons": _registration_reasons(registration, changes)}
    affected = bool(venue_bookings or affected_equipment or registrations["reasons"])
    return {
        "venue_bookings": venue_bookings,
        "equipment": affected_equipment,
        "registrations": registrations,
        "affected": affected,
        "message": None if affected else NOTHING_AFFECTED,
    }
