"""Demo data for trying SCRUM-62 in the web app. Run from backend/ with its venv.

Idempotent: does nothing if the demo coordinator already exists.
"""
import sys
from datetime import datetime

sys.path.insert(0, ".")
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Event, User, Venue

PASSWORD = "Demo1234!"

app = create_app()
with app.app_context():
    if User.query.filter_by(email="demo.coordinator@connectsphere.demo").first():
        print("Demo data already present.")
        sys.exit(0)

    def user(email, role):
        u = User(email=email, password_hash=generate_password_hash(PASSWORD), role=role)
        db.session.add(u)
        return u

    coord = user("demo.coordinator@connectsphere.demo", "coordinator")
    other = user("demo.coordinator2@connectsphere.demo", "coordinator")
    user("demo.coordinator3@connectsphere.demo", "coordinator")  # no events: empty state
    organiser = user("demo.organiser@connectsphere.demo", "organiser")
    venue = Venue(name="[Demo] Aurora Ballroom", location="Level 3, Marina Tower, 10 Bayfront Ave",
                  capacity=400, is_available=True)
    db.session.add(venue)
    db.session.flush()

    assigned = datetime(2026, 10, 1, 2, 0)
    rows = [
        dict(title="[Demo] Harbour Lights Festival", status="submitted", coordinator_id=coord.id,
             venue_id=venue.id, start_time=datetime(2026, 12, 12, 17, 0),
             end_time=datetime(2026, 12, 12, 22, 0),
             purpose="Celebrate the harbour's reopening with the local community.",
             description="Waterfront lantern festival with live music and food stalls.",
             expected_attendance=350,
             venue_requirements="Waterfront access and space for 20 food stalls.",
             accessibility_needs="Step-free routes and a quiet area.",
             equipment_requirements="Stage lighting and a PA system.",
             registration_required=True),
        dict(title="[Demo] Alumni Mixer", status="approved", coordinator_id=coord.id,
             start_time=datetime(2026, 11, 20, 18, 30), end_time=datetime(2026, 11, 20, 21, 0),
             purpose="Reconnect alumni.", registration_required=False),
        dict(title="[Demo] Winter Networking Night", status="cancelled", coordinator_id=coord.id,
             start_time=datetime(2026, 10, 30, 19, 0), end_time=datetime(2026, 10, 30, 21, 0)),
        dict(title="   ", status="under_review", coordinator_id=coord.id),
        dict(title="[Demo] Product Launch", status="submitted", coordinator_id=other.id,
             start_time=datetime(2026, 11, 25, 14, 0), end_time=datetime(2026, 11, 25, 16, 0)),
    ]
    for row in rows:
        db.session.add(Event(organiser_id=organiser.id, coordinator_assigned_at=assigned,
                             submitted_at=assigned, **row))
    db.session.commit()
    print("Demo data added.")
