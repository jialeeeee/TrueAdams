"""Rows the coordinator and venue tests insert into the public tables.

Each test inserts what it needs through `AppTestCase.seed_*` inside a transaction
that is rolled back afterwards, so none of this is ever saved. Emails get a
per-run suffix (see tests/base.py) so parallel test runs never collide.

For venues, None means "not recorded". An empty list, False or 0 means the venue
was recorded as having none of that thing, which is a confirmed fact.
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

# `organiser` and `coordinator` refer to USERS keys.
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

VENUES = [
    {  # Every planning field recorded.
        "key": "fully_recorded",
        "name": "Aurora Ballroom",
        "description": "Pillarless ballroom with a sprung dance floor and harbour views.",
        "location": "Level 3, Marina Tower, 10 Bayfront Ave",
        "capacity": 400,
        "area_sqm": 850,
        "is_available": True,
        "facilities": ["Stage", "Projector", "PA system", "Wi-Fi", "Green room"],
        "accessibility_features": ["Wheelchair ramp", "Accessible toilets", "Hearing loop"],
        "room_layouts": ["theatre", "banquet", "cabaret", "cocktail"],
        "operating_hours": "Mon-Sun 08:00-23:00",
        "contact_email": "events@marinatower.test",
        "contact_phone": "+65 6123 4567",
        "parking_spaces": 120,
        "catering_available": True,
    },
    {  # Only location and facilities recorded.
        "key": "partially_recorded",
        "name": "Bayfront Pavilion",
        "description": None,
        "location": "Bayfront Park, East Lawn",
        "capacity": None,
        "area_sqm": None,
        "is_available": True,
        "facilities": ["Covered stage"],
        "accessibility_features": None,
        "room_layouts": None,
        "operating_hours": None,
        "contact_email": None,
        "contact_phone": None,
        "parking_spaces": None,
        "catering_available": None,
    },
    {  # Recorded as offering none of these: confirmed absences, not missing data.
        "key": "recorded_as_none",
        "name": "Civic Hall",
        "description": "Community hall available for bare-venue hire.",
        "location": "12 Civic Road",
        "capacity": 80,
        "area_sqm": 150,
        "is_available": True,
        "facilities": [],
        "accessibility_features": [],
        "room_layouts": ["theatre"],
        "operating_hours": "Mon-Fri 09:00-18:00",
        "contact_email": "hire@civichall.test",
        "contact_phone": "+65 6000 1111",
        "parking_spaces": 0,
        "catering_available": False,
    },
    {  # Recorded, but not currently bookable; it must still be browsable.
        "key": "unavailable",
        "name": "Dockside Studio",
        "description": "Industrial studio, closed for renovation until Q1 2027.",
        "location": "Pier 4, Harbourfront",
        "capacity": 60,
        "area_sqm": 200,
        "is_available": False,
        "facilities": ["Blackout blinds", "Lighting rig"],
        "accessibility_features": ["Step-free entrance"],
        "room_layouts": ["classroom", "boardroom"],
        "operating_hours": "By appointment",
        "contact_email": "studio@dockside.test",
        "contact_phone": None,
        "parking_spaces": 10,
        "catering_available": False,
    },
    {  # Blank strings were typed in but carry no information.
        "key": "blank_values",
        "name": "Evergreen Loft",
        "description": "   ",
        "location": "",
        "capacity": 50,
        "area_sqm": None,
        "is_available": True,
        "facilities": ["Kitchenette"],
        "accessibility_features": None,
        "room_layouts": ["u_shape"],
        "operating_hours": "  ",
        "contact_email": "",
        "contact_phone": None,
        "parking_spaces": None,
        "catering_available": None,
    },
]

# ---------- Venue availability (SCRUM-36) and venue search (SCRUM-37) ----------
#
# Keys match the refs in docs/test-cases/SCRUM-36-venue-availability.md (AV-SEED)
# and docs/test-cases/SCRUM-37-venue-search.md (SV-SEED). `venue` refers to VENUES
# or SEARCH_VENUES keys. Times are Singapore time, stored without a time zone.

# Extra venues for search, alongside VENUES (SV-SEED).
SEARCH_VENUES = [
    {  # Shares Aurora Ballroom's building, but is smaller and closes earlier.
        "key": "harbour_room",
        "name": "Harbour Room",
        "description": "Mid-sized function room overlooking the marina.",
        "location": "Level 2, Marina Tower, 10 Bayfront Ave",
        "capacity": 120,
        "area_sqm": 240,
        "is_available": True,
        "facilities": ["Projector", "Wi-Fi"],
        "accessibility_features": ["Wheelchair ramp"],
        "room_layouts": ["theatre", "classroom"],
        "operating_hours": "Mon-Sun 08:00-22:00",
        "contact_email": "rooms@marinatower.test",
        "contact_phone": "+65 6123 4568",
        "parking_spaces": 120,
        "catering_available": True,
    },
    {  # Same capacity as Aurora Ballroom, for capacity boundaries; no Wi-Fi or hearing loop.
        "key": "summit_hall",
        "name": "Summit Hall",
        "description": "Conference hall with fixed staging.",
        "location": "5 Orchard Link",
        "capacity": 400,
        "area_sqm": 900,
        "is_available": True,
        "facilities": ["Stage", "Projector", "PA system"],
        "accessibility_features": ["Wheelchair ramp", "Accessible toilets"],
        "room_layouts": ["theatre", "banquet"],
        "operating_hours": "Mon-Sat 08:00-23:00",
        "contact_email": "bookings@summithall.test",
        "contact_phone": "+65 6222 3333",
        "parking_spaces": 60,
        "catering_available": True,
    },
]

# AV-SEED: bookings and blocks for the availability calendar.
AVAILABILITY_BOOKINGS = [
    {"key": "B1", "venue": "fully_recorded", "status": "confirmed",
     "start_time": datetime(2026, 10, 15, 10, 0), "end_time": datetime(2026, 10, 15, 12, 0)},
    {"key": "B2", "venue": "fully_recorded", "status": "confirmed",
     "start_time": datetime(2026, 10, 15, 14, 0), "end_time": datetime(2026, 10, 15, 16, 0)},
    {"key": "B3", "venue": "fully_recorded", "status": "pending",
     "start_time": datetime(2026, 10, 15, 18, 0), "end_time": datetime(2026, 10, 15, 20, 0)},
    {"key": "B4", "venue": "fully_recorded", "status": "cancelled",
     "start_time": datetime(2026, 10, 15, 20, 0), "end_time": datetime(2026, 10, 15, 21, 0)},
    {"key": "B6", "venue": "recorded_as_none", "status": "confirmed",
     "start_time": datetime(2026, 10, 15, 9, 0), "end_time": datetime(2026, 10, 15, 18, 0)},
]

AVAILABILITY_BLOCKS = [
    {"key": "K1", "venue": "fully_recorded", "reason": "Floor polishing",
     "start_time": datetime(2026, 10, 15, 16, 0), "end_time": datetime(2026, 10, 15, 17, 0)},
    {"key": "K2", "venue": "fully_recorded", "reason": "Electrical works",
     "start_time": datetime(2026, 10, 16, 20, 0), "end_time": datetime(2026, 10, 17, 12, 0)},
    {"key": "K3", "venue": "fully_recorded", "reason": "AV rigging",
     "start_time": datetime(2026, 10, 15, 11, 0), "end_time": datetime(2026, 10, 15, 13, 0)},
]

# SV-SEED: bookings and blocks for venue search, all on Thu 15 Oct 2026.
SEARCH_BOOKINGS = [
    {"key": "B1", "venue": "fully_recorded", "status": "confirmed",
     "start_time": datetime(2026, 10, 15, 10, 0), "end_time": datetime(2026, 10, 15, 12, 0)},
    {"key": "B2", "venue": "summit_hall", "status": "pending",
     "start_time": datetime(2026, 10, 15, 10, 0), "end_time": datetime(2026, 10, 15, 12, 0)},
    {"key": "B3", "venue": "summit_hall", "status": "cancelled",
     "start_time": datetime(2026, 10, 15, 14, 0), "end_time": datetime(2026, 10, 15, 16, 0)},
    {"key": "B4", "venue": "recorded_as_none", "status": "confirmed",
     "start_time": datetime(2026, 10, 15, 9, 0), "end_time": datetime(2026, 10, 15, 18, 0)},
]

SEARCH_BLOCKS = [
    {"key": "K1", "venue": "harbour_room", "reason": "Maintenance",
     "start_time": datetime(2026, 10, 15, 13, 0), "end_time": datetime(2026, 10, 15, 15, 0)},
]
