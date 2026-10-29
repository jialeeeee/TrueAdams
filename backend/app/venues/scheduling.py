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
# A tentative hold blocks its time too, but only until it expires (SCRUM-87 A3).
TENTATIVE_STATUS = "tentative"
# A hold whose expiry has passed (SCRUM-86 AC2). The expiry check records it, and until
# then a tentative hold past its expiry is shown as expired anyway (current_status).
EXPIRED_STATUS = "expired"

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
HOURS_NOT_RECORDED = "hours_not_recorded"
# Time covered only by an unexpired hold (SCRUM-87 A3).
TENTATIVE = "tentative"
# Why time is unavailable or tentative, in the order a slot lists them (SCRUM-64 A1,
# SCRUM-87 A3). Bookings, blocks and holds are named as on the calendar's periods.
BOOKING = "booking"
BLOCK = "block"
HOLD = "hold"
OUTSIDE_HOURS = "outside_operating_hours"
CAUSES = [BOOKING, BLOCK, HOLD, OUTSIDE_HOURS]

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


def occupied(record):
    """The (start, end) a booking, hold or block occupies: a booking's setup before and
    turnaround after its event are included (SCRUM-84 A1)."""
    if isinstance(record, VenueBooking):
        return (record.start_time - timedelta(minutes=record.setup_minutes or 0),
                record.end_time + timedelta(minutes=record.turnaround_minutes or 0))
    return record.start_time, record.end_time


def part(start, end):
    """A setup or turnaround part as {"start", "end", "minutes"}, or None if it is empty."""
    minutes = int((end - start).total_seconds() // 60)
    if minutes <= 0:
        return None
    return {"start": start.isoformat(), "end": end.isoformat(), "minutes": minutes}


def overlapping(query, model, start, end):
    """Rows of `model` whose occupied period overlaps [start, end).

    A booking's occupied period includes its setup and turnaround (SCRUM-84 A1); a
    block's is just its own period.
    """
    if model is VenueBooking:
        return query.filter(model.occupied_start < end, model.occupied_end > start)
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


def unexpired_holds(now):
    """Tentative holds whose expiry is later than `now`; at its expiry a hold has expired."""
    return VenueBooking.query.filter(VenueBooking.status == TENTATIVE_STATUS,
                                     VenueBooking.hold_expires_at > now)


def current_status(booking, now):
    """The booking's status now: a tentative hold has expired from its expiry itself,
    even before the expiry check records it (SCRUM-86 A3)."""
    if booking.status == TENTATIVE_STATUS and booking.hold_expires_at <= now:
        return EXPIRED_STATUS
    return booking.status


def holds(venue_ids, start, end, now):
    query = unexpired_holds(now).filter(VenueBooking.venue_id.in_(venue_ids))
    return overlapping(query, VenueBooking, start, end).all()


def within_hours(hours, start, end):
    """Whether [start, end), within one day, falls inside the venue's opening hours."""
    opening = hours.get(start.weekday()) if hours is not None else None
    if opening is None:
        return False
    opens, closes = opening
    return opens <= start.time() and end.time() <= closes


def day_slots(day, hours, periods):
    """Split one day into slots of consistent status and causes, 00:00 to next 00:00.

    `periods` are (kind, start, end) for confirmed bookings ("booking"), blocks
    ("block") and unexpired holds ("hold"). Time is unavailable while a booking or
    block covers it or outside the operating hours, and tentative while only a hold
    covers it. Each slot lists every cause (SCRUM-64 A1-A3, SCRUM-87 A3).
    """
    day_start = datetime.combine(day, time())
    day_end = day_start + timedelta(days=1)

    opening = hours.get(day.weekday()) if hours is not None else None
    opens = datetime.combine(day, opening[0]) if opening else None
    closes = datetime.combine(day, opening[1]) if opening else None

    clipped = [(kind, max(s, day_start), min(e, day_end)) for kind, s, e in periods
               if s < day_end and e > day_start]

    points = {day_start, day_end}
    if opening:
        points.update({opens, closes})
    for _, start, end in clipped:
        points.update({start, end})
    points = sorted(points)

    slots = []
    for start, end in zip(points, points[1:]):
        kinds = {kind for kind, s, e in clipped if s <= start < e}
        # Unrecorded hours can't place time outside them (SCRUM-64 A5).
        if hours is not None and not (opening and opens <= start < closes):
            kinds.add(OUTSIDE_HOURS)
        causes = [cause for cause in CAUSES if cause in kinds]
        if kinds - {HOLD}:
            status = UNAVAILABLE
        elif causes:
            status = TENTATIVE
        elif hours is None:
            status = HOURS_NOT_RECORDED
        else:
            status = AVAILABLE
        if slots and (slots[-1]["status"], slots[-1]["causes"]) == (status, causes):
            slots[-1]["end"] = end
        else:
            slots.append({"start": start, "end": end, "status": status, "causes": causes})
    return slots
