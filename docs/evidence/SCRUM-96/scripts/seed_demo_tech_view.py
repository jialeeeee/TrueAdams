"""Demo data for one end-to-end run of SCRUM-96. Run from backend/ with its venv.

    python ../docs/evidence/SCRUM-96/scripts/seed_demo_tech_view.py

It writes committed rows, so it only runs against a database on this machine (DATABASE_URL
on localhost, built with ci/build_test_database.py).

Adds, once, the demo accounts (password Demo1234!): an organiser, two coordinators and a
Technical Support member. On every run it adds, for demo.organiser:
  - "[Demo] Charity Gala 96", approved, coordinated by demo.coordinator, with 2 × Wireless
    microphone ("Lapel, with spare batteries") and 1 × Projector (no technical
    requirements) recorded, and the organiser's note "Two wireless microphones and a
    projector";
  - "[Demo] Harbour Lights 96", a draft with the organiser's note "Smoke machine and
    strobe lights".
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
from app.models import EquipmentRequirement, Event, User

PASSWORD = "Demo1234!"
ACCOUNTS = {
    "organiser": ("demo.organiser@connectsphere.demo", "organiser"),
    "coordinator": ("demo.coordinator@connectsphere.demo", "coordinator"),
    "other": ("demo.coordinator2@connectsphere.demo", "coordinator"),
    "tech": ("demo.tech@connectsphere.demo", "tech_staff"),
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
    db.session.flush()

    now = datetime.utcnow()
    gala = Event(title="[Demo] Charity Gala 96", status="approved",
                 organiser_id=users["organiser"].id, coordinator_id=users["coordinator"].id,
                 start_time=datetime(2026, 12, 5, 18, 0), end_time=datetime(2026, 12, 5, 23, 0),
                 expected_attendance=120, created_at=now, submitted_at=now,
                 equipment_requirements="Two wireless microphones and a projector")
    draft = Event(title="[Demo] Harbour Lights 96", status="draft",
                  organiser_id=users["organiser"].id,
                  start_time=datetime(2026, 12, 12, 19, 0), end_time=datetime(2026, 12, 12, 22, 0),
                  created_at=now, last_saved_at=now,
                  equipment_requirements="Smoke machine and strobe lights")
    db.session.add_all([gala, draft])
    db.session.flush()
    for equipment_type, quantity, technical in (
            ("Wireless microphone", 2, "Lapel, with spare batteries"),
            ("Projector", 1, None)):
        db.session.add(EquipmentRequirement(
            event_id=gala.id, equipment_type=equipment_type, quantity=quantity,
            technical_requirements=technical, status="requested",
            recorded_by_id=users["coordinator"].id, recorded_at=now, last_saved_at=now))
    db.session.commit()
    print(json.dumps({"gala": gala.id, "draft": draft.id}))
