"""SCRUM-46: what an organiser may propose in a change request, and how it is described.

Pure rules, independent of Flask and the database, like equipment.py. The route checks
who may ask and whether the event can take a request; these rules check the proposal.
parse_proposal returns the changes and a dict of problems by field, so every problem is
named at once (A4).
"""

import re
from datetime import datetime

PENDING_REVIEW = "pending_review"
# The coordinator's decision on a request (SCRUM-70 A4).
ACCEPTED = "accepted"
REJECTED = "rejected"
STATUS_LABELS = {PENDING_REVIEW: "Pending Review", ACCEPTED: "Accepted", REJECTED: "Rejected"}

# The fields an organiser can ask to change, in display order, with their labels (A2):
# the event's date and time, expected attendance, and the venue and equipment
# requirements from their request (SCRUM-29's labels). Open questions Q2, Q3.
PERMITTED_FIELDS = {
    "start_time": "Start",
    "end_time": "End",
    "expected_attendance": "Expected attendance",
    "venue_requirements": "Venue requirements",
    "equipment_requirements": "Equipment requirements",
}
TIME_FIELDS = ("start_time", "end_time")
# Venue requirements are required for a request (SCRUM-29), so they can't be cleared;
# equipment requirements are optional, so blank means none.
REQUIRED_TEXT_FIELDS = {"venue_requirements"}
# As for the coordinator's text fields (SCRUM-53).
TEXT_MAX_LENGTH = 5000
_LOCAL_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")


def _time(value, label):
    if isinstance(value, str) and _LOCAL_DATETIME.match(value):
        try:
            return datetime.fromisoformat(value), None
        except ValueError:
            pass
    return None, f"{label} must be a valid date and time (YYYY-MM-DDTHH:MM)."


def _attendance(value, label):
    # bool is an int in Python, but true is not a number of people.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None, f"{label} must be a whole number of at least 1."
    return value, None


def _text(name, value, label):
    if value is not None and not isinstance(value, str):
        return None, f"{label} must be text."
    text = (value or "").strip()
    if not text and name in REQUIRED_TEXT_FIELDS:
        return None, f"{label} can't be blank."
    if len(text) > TEXT_MAX_LENGTH:
        return None, f"{label} must be {TEXT_MAX_LENGTH} characters or fewer."
    return text or None, None


def _parse(name, value):
    label = PERMITTED_FIELDS[name]
    if name in TIME_FIELDS:
        return _time(value, label)
    if name == "expected_attendance":
        return _attendance(value, label)
    return _text(name, value, label)


def _current(event, name):
    """The saved value, with text tidied the way proposals are, so they compare."""
    value = getattr(event, name)
    return (value.strip() or None) if isinstance(value, str) else value


def _minutes(value):
    return value.strftime("%Y-%m-%d %H:%M")


def parse_proposal(event, body):
    """The changes proposed for `event` as {field: {"from", "to"}} in field order, and the
    problems by field. A value equal to the current one is not a change (A3)."""
    problems, proposed = {}, {}
    for name, value in body.items():
        if name not in PERMITTED_FIELDS:
            problems[name] = f"{name} can't be changed through a change request."
            continue
        parsed, problem = _parse(name, value)
        if problem:
            problems[name] = problem
        else:
            proposed[name] = parsed

    # The end must be after the start the event would have (A4).
    if not any(name in problems for name in TIME_FIELDS):
        start = proposed.get("start_time", event.start_time)
        end = proposed.get("end_time", event.end_time)
        if start is not None and end is not None and end <= start:
            if "end_time" in proposed:
                problems["end_time"] = "The end must be after the start."
            else:
                problems["start_time"] = (f"The start must be before the end, "
                                          f"{_minutes(end)}.")

    changes = {}
    for name in PERMITTED_FIELDS:
        if name in proposed and proposed[name] != _current(event, name):
            changes[name] = {"from": _current(event, name), "to": proposed[name]}
    return changes, problems


def _json(value):
    return value.isoformat() if isinstance(value, datetime) else value


def as_json(changes):
    """The changes as stored, with times as Singapore-time ISO strings (A7)."""
    return {name: {"from": _json(change["from"]), "to": _json(change["to"])}
            for name, change in changes.items()}


def _shown(value):
    if value is None:
        return "none"
    if isinstance(value, datetime):
        return _minutes(value)
    if isinstance(value, str) and _LOCAL_DATETIME.match(value):
        return value[:16].replace("T", " ")
    return str(value)


def describe(changes):
    """'Start: 2026-12-05 18:00 → 2026-12-06 18:00; Expected attendance: 200 → 250' (A8).
    Takes parsed or stored changes."""
    return "; ".join(f"{PERMITTED_FIELDS[name]}: {_shown(change['from'])} → {_shown(change['to'])}"
                     for name, change in changes.items())
