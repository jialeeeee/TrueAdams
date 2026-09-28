"""Venue scheduling rules, shared by the availability calendar and venue search.

All times are Singapore time without a time zone. A period runs from its start up
to, but not including, its end, so periods that only touch do not overlap.
"""

import re
from datetime import datetime, time, timedelta

from ..models import VenueBlock, VenueBooking

# Only confirmed bookings make a venue unavailable; pending, rejected and cancelled
# ones do not (open question Q2 in the SCRUM-36 test cases).
BLOCKING_BOOKING_STATUS = "confirmed"

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
OUTSIDE_HOURS = "outside_operating_hours"
HOURS_NOT_RECORDED = "hours_not_recorded"

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# One "Mon-Fri 09:00-18:00" or "Sat 10:00-14:00" part of an operating-hours text.
_HOURS_PART = re.compile(
    r"^(?P<first>[A-Z][a-z]{2})(?:-(?P<last>[A-Z][a-z]{2}))?\s+"
    r"(?P<open>\d{2}:\d{2})-(?P<close>\d{2}:\d{2})$"
)


def parse_operating_hours(text):
    """Map weekday (0 = Monday) to (open, close) times, or None if not usable.

    Understands comma-separated parts such as "Mon-Fri 09:00-18:00, Sat 10:00-14:00".
    Missing, blank or free-text hours (e.g. "By appointment") return None.
    """
    if not text or not text.strip():
        return None

    hours = {}
    for part in text.split(","):
        match = _HOURS_PART.match(part.strip())
        if not match or match["first"] not in DAYS:
            return None
        last = match["last"] or match["first"]
        if last not in DAYS:
            return None
        try:
            opens = time.fromisoformat(match["open"])
            closes = time.fromisoformat(match["close"])
        except ValueError:
            return None
        if closes <= opens:
            return None

        first_day, last_day = DAYS.index(match["first"]), DAYS.index(last)
        day = first_day
        while True:
            hours[day] = (opens, closes)
            if day == last_day:
                break
            day = (day + 1) % 7
    return hours


def overlapping(query, model, start, end):
    """Rows of `model` whose period overlaps [start, end)."""
    return query.filter(model.start_time < end, model.end_time > start)


def blocking_bookings(venue_ids, start, end):
    query = VenueBooking.query.filter(
        VenueBooking.venue_id.in_(venue_ids),
        VenueBooking.status == BLOCKING_BOOKING_STATUS,
    )
    return overlapping(query, VenueBooking, start, end).all()


def blocks(venue_ids, start, end):
    query = VenueBlock.query.filter(VenueBlock.venue_id.in_(venue_ids))
    return overlapping(query, VenueBlock, start, end).all()


def day_slots(day, hours, periods):
    """Split one day into slots of consistent status, covering 00:00 to next 00:00.

    `periods` are (start, end) pairs of confirmed bookings and blocks. Being covered
    by one makes time unavailable, whatever the operating hours say.
    """
    day_start = datetime.combine(day, time())
    day_end = day_start + timedelta(days=1)

    opening = hours.get(day.weekday()) if hours is not None else None
    opens = datetime.combine(day, opening[0]) if opening else None
    closes = datetime.combine(day, opening[1]) if opening else None

    def base_status(moment):
        if hours is None:
            return HOURS_NOT_RECORDED
        if opening and opens <= moment < closes:
            return AVAILABLE
        return OUTSIDE_HOURS

    clipped = [(max(s, day_start), min(e, day_end)) for s, e in periods
               if s < day_end and e > day_start]

    points = {day_start, day_end}
    if opening:
        points.update({opens, closes})
    for start, end in clipped:
        points.update({start, end})
    points = sorted(points)

    slots = []
    for start, end in zip(points, points[1:]):
        covered = any(s <= start < e for s, e in clipped)
        status = UNAVAILABLE if covered else base_status(start)
        if slots and slots[-1]["status"] == status:
            slots[-1]["end"] = end
        else:
            slots.append({"start": start, "end": end, "status": status})
    return slots
