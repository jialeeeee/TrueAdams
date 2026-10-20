"""SCRUM-38: assess a venue against an event's requirements, from their saved details.

Pure rules, independent of Flask and the database. Each check is `match`, `mismatch`,
`unable_to_assess` (the information needed was not recorded, so nothing is assumed) or
`not_required` (the event recorded that it needs nothing of that kind).
"""

MATCH = "match"
MISMATCH = "mismatch"
UNABLE = "unable_to_assess"
NOT_REQUIRED = "not_required"

MEETS = "meets"
DOES_NOT_MEET = "does_not_meet"

# (requirement kind, Event column, Venue column, heading, singular label)
LIST_REQUIREMENTS = [
    ("facility", "required_facilities", "facilities", "Facilities", "Facility"),
    ("accessibility", "required_accessibility_features", "accessibility_features",
     "Accessibility features", "Accessibility"),
    ("layout", "required_layouts", "room_layouts", "Layouts", "Layout"),
]


def _key(text):
    return " ".join(text.split()).lower()


def _check(requirement, item, label, status, detail):
    return {"requirement": requirement, "item": item, "label": label, "status": status,
            "detail": detail}


def _attendance(event, venue):
    expected, capacity = event.expected_attendance, venue.capacity
    if expected is None:
        return _check("attendance", None, "Attendance", UNABLE,
                      "The event's expected attendance is not recorded.")
    if capacity is None:
        return _check("attendance", None, "Attendance", UNABLE,
                      f"{venue.name}'s capacity is not recorded.")
    if expected > capacity:
        return _check("attendance", None, "Attendance", MISMATCH,
                      f"{expected} expected, but the capacity is {capacity}.")
    return _check("attendance", None, "Attendance", MATCH,
                  f"{expected} expected, within the capacity of {capacity}.")


def _list_checks(event, venue, requirement, event_field, venue_field, heading, label):
    needed = getattr(event, event_field)
    offered = getattr(venue, venue_field)
    if needed is None:
        return [_check(requirement, None, heading, UNABLE,
                       f"The event's required {heading.lower()} are not recorded.")]
    if not needed:
        return [_check(requirement, None, heading, NOT_REQUIRED,
                       f"The event does not need any {heading.lower()}.")]

    checks = []
    for raw in needed:
        item = " ".join(raw.split())
        name = f"{label}: {item}"
        if offered is None:
            checks.append(_check(requirement, item, name, UNABLE,
                                 f"{venue.name}'s {heading.lower()} are not recorded."))
        elif _key(item) in {_key(o) for o in offered}:
            checks.append(_check(requirement, item, name, MATCH, f"{venue.name} has {item}."))
        else:
            checks.append(_check(requirement, item, name, MISMATCH,
                                 f"{venue.name} does not have {item}."))
    return checks


def assess(event, venue):
    """(checks, overall, summary) for `event` at `venue`."""
    checks = [_attendance(event, venue)]
    for spec in LIST_REQUIREMENTS:
        checks.extend(_list_checks(event, venue, *spec))

    statuses = {check["status"] for check in checks}
    # A mismatch is decisive; otherwise anything unassessed stops it passing.
    if MISMATCH in statuses:
        overall = DOES_NOT_MEET
        summary = f"{venue.name} does not meet all the checked requirements."
    elif UNABLE in statuses:
        overall = UNABLE
        summary = (f"Some requirements could not be assessed for {venue.name}, so it can't "
                   "be said to meet them.")
    else:
        overall = MEETS
        summary = f"{venue.name} meets the checked requirements."
    return checks, overall, summary
