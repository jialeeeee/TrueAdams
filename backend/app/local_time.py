"""Singapore local time, for stories that store event-related times as naive
Singapore timestamps: registration periods (SCRUM-45) and venue booking requests
(SCRUM-39)."""

from datetime import datetime, timedelta, timezone

# Singapore has had no daylight saving since 1982, so a fixed offset is exact and
# avoids depending on the host's time zone database.
SINGAPORE = timezone(timedelta(hours=8))


def singapore_now():
    """The current Singapore time without a time zone, as event times are stored."""
    return datetime.now(SINGAPORE).replace(tzinfo=None)
