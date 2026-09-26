"""Hardcoded test data for the event-coordinator assignment feature.

Rows are plain dicts keyed by a stable `key` and use the same column names as
the `users` / `events` tables, so the same data can later be loaded as a
Supabase seed (or replaced by queries against a Supabase test project) without
touching the tests themselves. Cross-references (`organiser`, `coordinator`)
point at user keys and are resolved to ids by the loader.
"""

from datetime import datetime

USERS = [
    {"key": "admin", "email": "admin@connectsphere.test", "role": "admin"},
    {"key": "alice", "email": "alice.coordinator@connectsphere.test", "role": "coordinator"},
    {"key": "ben", "email": "ben.coordinator@connectsphere.test", "role": "coordinator"},
    {"key": "chloe", "email": "chloe.coordinator@connectsphere.test", "role": "coordinator"},
    {"key": "dana", "email": "dana.organiser@connectsphere.test", "role": "organiser"},
    {"key": "evan", "email": "evan.organiser@connectsphere.test", "role": "organiser"},
    {"key": "farah", "email": "farah.attendee@connectsphere.test", "role": "attendee"},
    {"key": "gus", "email": "gus.venue@connectsphere.test", "role": "venue_staff"},
    {"key": "hana", "email": "hana.tech@connectsphere.test", "role": "tech_staff"},
]

EVENTS = [
    {
        "key": "unassigned",
        "title": "Tech Summit 2026",
        "status": "submitted",
        "organiser": "dana",
        "start_time": datetime(2026, 11, 10, 9, 0),
        "end_time": datetime(2026, 11, 10, 17, 0),
        "coordinator": None,
        "coordinator_assigned_at": None,
    },
    {
        "key": "assigned",
        "title": "Charity Gala",
        "status": "submitted",
        "organiser": "dana",
        "start_time": datetime(2026, 12, 5, 18, 0),
        "end_time": datetime(2026, 12, 5, 23, 0),
        "coordinator": "alice",
        "coordinator_assigned_at": datetime(2026, 9, 1, 10, 0),
    },
    {
        "key": "evans_event",
        "title": "Product Launch",
        "status": "submitted",
        "organiser": "evan",
        "start_time": datetime(2026, 11, 20, 14, 0),
        "end_time": datetime(2026, 11, 20, 16, 0),
        "coordinator": "ben",
        "coordinator_assigned_at": datetime(2026, 9, 2, 15, 30),
    },
    {
        "key": "draft",
        "title": "Draft Workshop",
        "status": "draft",
        "organiser": "dana",
        "start_time": datetime(2027, 1, 15, 10, 0),
        "end_time": datetime(2027, 1, 15, 12, 0),
        "coordinator": None,
        "coordinator_assigned_at": None,
    },
    {
        "key": "cancelled",
        "title": "Cancelled Meetup",
        "status": "cancelled",
        "organiser": "dana",
        "start_time": datetime(2026, 10, 30, 19, 0),
        "end_time": datetime(2026, 10, 30, 21, 0),
        "coordinator": None,
        "coordinator_assigned_at": None,
    },
]
