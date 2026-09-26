"""Hardcoded test data for the view-venue-details feature.

Rows use the same column names as the `users` / `venues` tables, so they can
later be loaded as a Supabase seed without touching the tests.

`None` means "not recorded". An empty list, `False` or `0` means the venue was
recorded as having none of that thing, which is different and must be shown as
a confirmed fact rather than as missing information.
"""

USERS = [
    {"key": "coordinator", "email": "alice.coordinator@connectsphere.test", "role": "coordinator"},
    {"key": "venue_staff", "email": "gus.venue@connectsphere.test", "role": "venue_staff"},
    {"key": "organiser", "email": "dana.organiser@connectsphere.test", "role": "organiser"},
    {"key": "attendee", "email": "farah.attendee@connectsphere.test", "role": "attendee"},
    {"key": "tech_staff", "email": "hana.tech@connectsphere.test", "role": "tech_staff"},
]

# Every planning field recorded.
AURORA_BALLROOM = {
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
}

# Only the basics recorded; every other planning field is unknown.
BAYFRONT_PAVILION = {
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
}

# Recorded as offering none of these: confirmed absences, not missing data.
CIVIC_HALL = {
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
}

# Recorded, but not currently bookable; it must still be browsable.
DOCKSIDE_STUDIO = {
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
}

# Blank strings were typed in but carry no information.
EVERGREEN_LOFT = {
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
}

VENUES = [AURORA_BALLROOM, BAYFRONT_PAVILION, CIVIC_HALL, DOCKSIDE_STUDIO, EVERGREEN_LOFT]

# Planning fields whose absence must be reported as "not recorded".
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
