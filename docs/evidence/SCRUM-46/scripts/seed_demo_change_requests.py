"""Demo data for one end-to-end run of SCRUM-46. Run from backend/ with its venv.

    python ../docs/evidence/SCRUM-46/scripts/seed_demo_change_requests.py

It writes committed rows, so it only runs against a database on this machine (DATABASE_URL
on localhost, built with ci/build_test_database.py): event_change_requests is not on
Supabase until db/event_change_requests.sql has been run there.

Adds, once, the demo organiser and coordinator (password Demo1234!), and on every run three
fresh events of demo.organiser: the approved "[Demo] Charity Gala 46" coordinated by
demo.coordinator, the approved "[Demo] Spring Fair 46" with no coordinator, and the
submitted "[Demo] Book Fair 46". Prints the event IDs as JSON.
"""
import json
import sys
from datetime import datetime

from sqlalchemy.engine import make_url
from werkzeug.security import generate_password_hash

sys.path.insert(0, ".")
from app import create_app
from app.extensions import db
from app.models import Event, User

PASSWORD = "Demo1234!"
ACCOUNTS = [("demo.organiser@connectsphere.demo", "organiser"),
            ("demo.coordinator@connectsphere.demo", "coordinator")]

app = create_app()
url = make_url(app.config["SQLALCHEMY_DATABASE_URI"] or "postgresql://")
if url.host not in {"localhost", "127.0.0.1"}:
    sys.exit(f"Refusing to write demo rows to {url.host}: use a local database.")

with app.app_context():
    users = {}
    for email, role in ACCOUNTS:
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(email=email, role=role, password_hash=generate_password_hash(PASSWORD))
            db.session.add(user)
        users[role] = user
    db.session.flush()
    now = datetime.utcnow()

    def event(title, status, coordinator, start, end, attendance, venue, equipment):
        row = Event(title=title, status=status, organiser_id=users["organiser"].id,
                    coordinator_id=coordinator.id if coordinator else None,
                    coordinator_assigned_at=now if coordinator else None,
                    start_time=start, end_time=end, expected_attendance=attendance,
                    venue_requirements=venue, equipment_requirements=equipment,
                    purpose="Demo", description="Demo event for SCRUM-46",
                    registration_required=False, created_at=now, submitted_at=now)
        db.session.add(row)
        return row

    gala = event("[Demo] Charity Gala 46", "approved", users["coordinator"],
                 datetime(2026, 12, 5, 18, 0), datetime(2026, 12, 5, 23, 0), 200,
                 "Ballroom for 200", "2 wireless microphones")
    fair = event("[Demo] Spring Fair 46", "approved", None,
                 datetime(2026, 12, 12, 10, 0), datetime(2026, 12, 12, 16, 0), 80, "Lawn", None)
    books = event("[Demo] Book Fair 46", "submitted", users["coordinator"],
                  datetime(2026, 12, 10, 9, 0), datetime(2026, 12, 10, 17, 0), 100, "Hall", None)
    db.session.commit()
    print(json.dumps({"gala": gala.id, "fair": fair.id, "books": books.id}))
