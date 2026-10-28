"""Demo data for one end-to-end run of SCRUM-70. Run from backend/ with its venv.

    python ../docs/evidence/SCRUM-70/scripts/seed_demo_change_reviews.py

It writes committed rows, so it only runs against a database on this machine (DATABASE_URL
on localhost, built with ci/build_test_database.py): the decision columns are not on
Supabase until db/event_change_request_decisions.sql has been run there.

Adds, once, the demo accounts (password Demo1234!): an organiser, two coordinators, a
Technical Support member and three attendees. On every run it adds, for demo.organiser:
  - "[Demo] Charity Gala 70", approved, coordinated by demo.coordinator, at the Grand
    Ballroom (a confirmed booking), with 2 wireless microphones reserved, two registered
    attendees and one who withdrew, and a pending request to move it a day later;
  - "[Demo] Book Launch 70", approved, coordinated by demo.coordinator, with a pending
    request to raise its attendance;
  - "[Demo] Spring Fair 70", approved, still waiting for a coordinator.
Prints the IDs as JSON.
"""
import json
import sys
from datetime import datetime

from sqlalchemy.engine import make_url
from werkzeug.security import generate_password_hash

sys.path.insert(0, ".")
from app import create_app
from app.extensions import db
from app.models import (EquipmentRequirement, EquipmentReservation, Event, EventChangeRequest,
                        Registration, Resource, User, Venue, VenueBooking)

PASSWORD = "Demo1234!"
ACCOUNTS = {
    "organiser": ("demo.organiser@connectsphere.demo", "organiser"),
    "coordinator": ("demo.coordinator@connectsphere.demo", "coordinator"),
    "other": ("demo.coordinator2@connectsphere.demo", "coordinator"),
    "tech": ("demo.tech@connectsphere.demo", "tech_staff"),
    "amy": ("demo.attendee1@connectsphere.demo", "attendee"),
    "bo": ("demo.attendee2@connectsphere.demo", "attendee"),
    "cy": ("demo.attendee3@connectsphere.demo", "attendee"),
}

app = create_app()
url = make_url(app.config["SQLALCHEMY_DATABASE_URI"] or "postgresql://")
if url.host not in {"localhost", "127.0.0.1"}:
    sys.exit(f"Refusing to write demo rows to {url.host}: use a local database.")

with app.app_context():
    users = {}
    for key, (email, role) in ACCOUNTS.items():
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(email=email, role=role, password_hash=generate_password_hash(PASSWORD))
            db.session.add(user)
        users[key] = user
    ballroom = Venue(name="[Demo] Grand Ballroom 70", capacity=220, location="Level 2")
    mics = Resource(name="[Demo] Shure SLX-D 70", category="Wireless microphone",
                    quantity_available=6)
    db.session.add_all([ballroom, mics])
    db.session.flush()
    now = datetime.utcnow()

    def event(title, start, end, attendance, coordinator=True, **extra):
        row = Event(title=title, status="approved", organiser_id=users["organiser"].id,
                    coordinator_id=users["coordinator"].id if coordinator else None,
                    coordinator_assigned_at=now if coordinator else None,
                    start_time=start, end_time=end, expected_attendance=attendance,
                    venue_requirements="Ballroom", equipment_requirements="2 microphones",
                    purpose="Demo", description="Demo event for SCRUM-70",
                    registration_required=True, created_at=now, submitted_at=now, **extra)
        db.session.add(row)
        return row

    gala = event("[Demo] Charity Gala 70", datetime(2026, 12, 5, 18, 0),
                 datetime(2026, 12, 5, 23, 0), 200, venue_id=ballroom.id,
                 registration_capacity=210, registration_opens_at=datetime(2026, 11, 1, 9, 0),
                 registration_closes_at=datetime(2026, 12, 1, 12, 0))
    launch = event("[Demo] Book Launch 70", datetime(2026, 12, 12, 10, 0),
                   datetime(2026, 12, 12, 12, 0), 80)
    fair = event("[Demo] Spring Fair 70", datetime(2026, 12, 19, 10, 0),
                 datetime(2026, 12, 19, 16, 0), 150, coordinator=False)
    db.session.flush()

    db.session.add(VenueBooking(venue_id=ballroom.id, event_id=gala.id, status="confirmed",
                                start_time=gala.start_time, end_time=gala.end_time,
                                requested_by_id=users["coordinator"].id, created_at=now,
                                venue_requirements="Ballroom", decided_at=now))
    requirement = EquipmentRequirement(event_id=gala.id, equipment_type="Wireless microphone",
                                       quantity=2, recorded_by_id=users["coordinator"].id)
    db.session.add(requirement)
    db.session.flush()
    db.session.add(EquipmentReservation(event_id=gala.id, requirement_id=requirement.id,
                                        resource_id=mics.id, quantity=2,
                                        start_time=gala.start_time, end_time=gala.end_time,
                                        status="reserved", reserved_by_id=users["tech"].id))
    for key, status in (("amy", "registered"), ("bo", "registered"), ("cy", "withdrawn")):
        db.session.add(Registration(event_id=gala.id, attendee_id=users[key].id, status=status))

    move = EventChangeRequest(event_id=gala.id, requested_by_id=users["organiser"].id,
                              status="pending_review", requested_at=now, changes={
                                  "start_time": {"from": "2026-12-05T18:00:00",
                                                 "to": "2026-12-06T18:00:00"},
                                  "end_time": {"from": "2026-12-05T23:00:00",
                                               "to": "2026-12-06T23:30:00"}})
    grow = EventChangeRequest(event_id=launch.id, requested_by_id=users["organiser"].id,
                              status="pending_review", requested_at=now, changes={
                                  "expected_attendance": {"from": 80, "to": 400}})
    db.session.add_all([move, grow])
    db.session.commit()
    print(json.dumps({"gala": gala.id, "launch": launch.id, "fair": fair.id,
                      "move": move.id, "grow": grow.id}))
