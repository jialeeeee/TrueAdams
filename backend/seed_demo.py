"""Demo data for a live walk-through of ConnectSphere. Run from backend/ with its venv:

    DEMO_PASSWORD='choose-one' python seed_demo.py                 # DATABASE_URL on this machine
    DEMO_PASSWORD='choose-one' python seed_demo.py --allow-remote  # e.g. the team's Supabase

It writes committed rows to DATABASE_URL (not TEST_DATABASE_URL), so against Supabase it is
run once by the project owner, after every db/*.sql script has been run. It is safe to run
again: each account is matched by email and each event by title, and anything already there
is left as it is. Every row it adds is named "[Demo] ..." so it is easy to tell apart.

The password is read from DEMO_PASSWORD so that it is never committed with the code.

What it adds (one account per role, email demo.<role>@connectsphere.demo):
  - three venues with hours, facilities and setup/turnaround, and two equipment types;
  - an event at each step of the demo path, from a draft to a confirmed event:
      Draft Workshop         draft, for the organiser to submit
      Unassigned Talk        submitted, waiting in the Lead's queue for a coordinator
      Review Panel           submitted to the coordinator, ready to review and decide
      Planning Festival      approved; a pending venue request for Venue Staff, a
                             requested microphone for Technical Support, registration open
      Held Seminar           approved; a tentative hold for the coordinator to confirm
      Ready Gala             approved; venue confirmed and equipment reserved, so it is
                             in the Safety Officer's queue, and then can be confirmed
      Confirmed Expo         confirmed, with attendees registered; recording an unavailable
                             period at its venue starts the replacement-venue flow
Prints what it added as JSON.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

from sqlalchemy.engine import make_url
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.local_time import singapore_now
from app.models import (EquipmentRequirement, EquipmentReservation, Event, Registration,
                        Resource, User, Venue, VenueBooking)

LOCAL_HOSTS = {"localhost", "127.0.0.1"}
EMAIL_DOMAIN = "connectsphere.demo"
# key: (email local part, role)
ACCOUNTS = {
    "admin": ("demo.admin", "admin"),
    "lead": ("demo.lead", "coordinator_lead"),
    "coordinator": ("demo.coordinator", "coordinator"),
    "coordinator2": ("demo.coordinator2", "coordinator"),
    "organiser": ("demo.organiser", "organiser"),
    "venue": ("demo.venue", "venue_staff"),
    "tech": ("demo.tech", "tech_staff"),
    "safety": ("demo.safety", "safety_officer"),
    "attendee1": ("demo.attendee1", "attendee"),
    "attendee2": ("demo.attendee2", "attendee"),
    "attendee3": ("demo.attendee3", "attendee"),
}
VENUES = {
    "ballroom": dict(
        name="[Demo] Aurora Ballroom", capacity=300, location="Level 3, Marina Tower",
        description="Pillarless ballroom with a fixed stage.", area_sqm=600,
        facilities=["Stage", "Projector", "PA system", "Wi-Fi"],
        accessibility_features=["Wheelchair ramp", "Accessible toilets", "Hearing loop"],
        room_layouts=["theatre", "banquet", "cocktail"],
        operating_hours="Mon-Sun 08:00-23:00", contact_email="ballroom@connectsphere.demo",
        parking_spaces=80, catering_available=True, setup_minutes=60, turnaround_minutes=60),
    "harbour": dict(
        name="[Demo] Harbour Room", capacity=120, location="Level 1, Bayfront Centre",
        description="Function room overlooking the bay.", area_sqm=220,
        facilities=["Projector", "Wi-Fi"], accessibility_features=["Wheelchair ramp"],
        room_layouts=["theatre", "classroom"], operating_hours="Mon-Sun 08:00-22:00",
        contact_email="harbour@connectsphere.demo", parking_spaces=20,
        catering_available=False, setup_minutes=30, turnaround_minutes=30),
    "loft": dict(
        name="[Demo] Evergreen Loft", capacity=60, location="Level 5, Garden Block",
        description="Small loft for seminars.", area_sqm=110, facilities=["Wi-Fi"],
        accessibility_features=["Lift access"], room_layouts=["classroom", "boardroom"],
        operating_hours="Mon-Sat 09:00-21:00", contact_email="loft@connectsphere.demo",
        parking_spaces=0, catering_available=False, setup_minutes=15, turnaround_minutes=15),
}
RESOURCES = {
    "mics": dict(name="[Demo] Wireless microphone", category="Wireless microphone",
                 quantity_available=8),
    "projector": dict(name="[Demo] Laser projector", category="Projector",
                      quantity_available=2),
}


def _refuse_unless_allowed(app, allow_remote):
    url = make_url(app.config["SQLALCHEMY_DATABASE_URI"] or "postgresql://")
    if url.host not in LOCAL_HOSTS and not allow_remote:
        sys.exit(f"DATABASE_URL points at {url.host}. Pass --allow-remote to write demo rows "
                 "there (the project owner, once).")


def _get_or_add(model, lookup, **fields):
    row = model.query.filter_by(**lookup).first()
    if row is not None:
        return row, False
    row = model(**lookup, **fields)
    db.session.add(row)
    db.session.flush()
    return row, True


def _at(day, hour):
    """Singapore time, `day` days from today, on the hour."""
    today = singapore_now().replace(hour=0, minute=0, second=0, microsecond=0)
    return today + timedelta(days=day, hours=hour)


def seed(password):
    added = {"accounts": [], "venues": [], "resources": [], "events": []}
    hashed = generate_password_hash(password)
    users = {}
    for key, (local, role) in ACCOUNTS.items():
        users[key], new = _get_or_add(User, {"email": f"{local}@{EMAIL_DOMAIN}"},
                                      role=role, password_hash=hashed)
        if new:
            added["accounts"].append(users[key].email)
    venues = {}
    for key, fields in VENUES.items():
        venues[key], new = _get_or_add(Venue, {"name": fields["name"]},
                                       **{k: v for k, v in fields.items() if k != "name"})
        if new:
            added["venues"].append(venues[key].name)
    resources = {}
    for key, fields in RESOURCES.items():
        resources[key], new = _get_or_add(Resource, {"name": fields["name"]},
                                          **{k: v for k, v in fields.items() if k != "name"})
        if new:
            added["resources"].append(resources[key].name)

    now = datetime.utcnow()
    organiser, coordinator, lead = users["organiser"], users["coordinator"], users["lead"]

    def event(title, status, day, start_hour, hours, coordinated=True, **fields):
        """The event, or None if a previous run already added it (left untouched)."""
        row, new = _get_or_add(
            Event, {"title": title}, status=status, organiser_id=organiser.id,
            start_time=_at(day, start_hour), end_time=_at(day, start_hour + hours),
            description=fields.pop("description", f"{title[7:]} for the ConnectSphere demo."),
            purpose="Demonstrate the ConnectSphere workflow end to end.",
            expected_attendance=fields.pop("expected_attendance", 80),
            venue_requirements=fields.pop("venue_requirements", "Theatre layout with a projector"),
            accessibility_needs="Wheelchair access", registration_required=True,
            last_saved_at=now, submitted_at=None if status == "draft" else now,
            coordinator_id=coordinator.id if coordinated else None,
            coordinator_assigned_at=now if coordinated else None,
            coordinator_assigned_by_id=lead.id if coordinated else None,
            **fields)
        if not new:
            return None
        added["events"].append(f"{title} ({status})")
        return row

    def decided(**extra):
        return dict(decided_at=now, decided_by_id=coordinator.id,
                    decision_note="Approved for the demo.", **extra)

    def open_registration(day, capacity):
        return dict(registration_capacity=capacity, registration_opens_at=_at(-1, 9),
                    registration_closes_at=_at(day - 1, 23))

    def booking(row, venue, status, **fields):
        db.session.add(VenueBooking(
            event_id=row.id, venue_id=venue.id, status=status, start_time=row.start_time,
            end_time=row.end_time, venue_requirements=row.venue_requirements,
            requested_by_id=coordinator.id, created_at=now, **fields))

    def equipment(row, resource, quantity, reserve):
        requirement = EquipmentRequirement(
            event_id=row.id, equipment_type=resource.category, quantity=quantity,
            status="being_arranged" if reserve else "requested", recorded_by_id=coordinator.id)
        db.session.add(requirement)
        db.session.flush()
        if reserve:
            db.session.add(EquipmentReservation(
                event_id=row.id, requirement_id=requirement.id, resource_id=resource.id,
                quantity=quantity, start_time=row.start_time, end_time=row.end_time,
                reserved_by_id=users["tech"].id))

    def register(row, *attendees):
        for key in attendees:
            db.session.add(Registration(event_id=row.id, attendee_id=users[key].id))

    event("[Demo] Draft Workshop", "draft", 40, 10, 3, coordinated=False)
    event("[Demo] Unassigned Talk", "submitted", 42, 14, 2, coordinated=False)
    event("[Demo] Review Panel", "submitted", 44, 9, 4)

    row = event("[Demo] Planning Festival", "approved", 30, 10, 6,
                expected_attendance=250, **decided(**open_registration(30, 250)))
    if row:
        booking(row, venues["ballroom"], "pending")
        equipment(row, resources["mics"], 2, reserve=False)
        register(row, "attendee1")

    row = event("[Demo] Held Seminar", "approved", 35, 13, 3, expected_attendance=40,
                **decided())
    if row:
        booking(row, venues["loft"], "tentative", held_at=now, held_by_id=users["venue"].id,
                hold_expires_at=_at(7, 12))

    row = event("[Demo] Ready Gala", "approved", 25, 18, 4, expected_attendance=100,
                **decided(**open_registration(25, 100)))
    if row:
        booking(row, venues["harbour"], "confirmed", decided_at=now,
                decided_by_id=users["venue"].id)
        row.venue_id = venues["harbour"].id
        equipment(row, resources["projector"], 1, reserve=True)
        register(row, "attendee2")

    row = event("[Demo] Confirmed Expo", "confirmed", 20, 9, 8, expected_attendance=200,
                safety_decision="approved", safety_decided_by_id=users["safety"].id,
                safety_decided_at=now, confirmed_by_id=coordinator.id, confirmed_at=now,
                **decided(**open_registration(20, 200)))
    if row:
        booking(row, venues["ballroom"], "confirmed", decided_at=now,
                decided_by_id=users["venue"].id)
        row.venue_id = venues["ballroom"].id
        equipment(row, resources["mics"], 4, reserve=True)
        register(row, "attendee1", "attendee2")

    db.session.commit()
    return added


def main():
    parser = argparse.ArgumentParser(description="Add the ConnectSphere demo data.")
    parser.add_argument("--allow-remote", action="store_true",
                        help="write to a DATABASE_URL that is not on this machine")
    args = parser.parse_args()
    password = os.environ.get("DEMO_PASSWORD", "")
    if len(password) < 8:
        sys.exit("Set DEMO_PASSWORD (8 characters or more) for the demo accounts.")
    app = create_app()
    _refuse_unless_allowed(app, args.allow_remote)
    with app.app_context():
        print(json.dumps(seed(password), indent=2))


if __name__ == "__main__":
    main()
