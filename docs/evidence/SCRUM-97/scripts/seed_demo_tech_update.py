"""Demo data for one end-to-end run of SCRUM-97. Run from backend/ with its venv.

    python ../docs/evidence/SCRUM-97/scripts/seed_demo_tech_update.py

It writes committed rows, so it only runs against a database on this machine (DATABASE_URL
on localhost, built with ci/build_test_database.py).

Adds, once, the demo accounts (password Demo1234!): an organiser, a coordinator and two
Technical Support members. On every run it adds "[Demo] Charity Gala 97", approved, for
demo.organiser and coordinated by demo.coordinator, with 2 × Wireless microphone ("Lapel,
with spare batteries") and 1 × Projector (no technical requirements) recorded. Prints the
IDs as JSON.
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
    "tech": ("demo.tech@connectsphere.demo", "tech_staff"),
    "tech2": ("demo.tech2@connectsphere.demo", "tech_staff"),
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
    gala = Event(title="[Demo] Charity Gala 97", status="approved",
                 organiser_id=users["organiser"].id, coordinator_id=users["coordinator"].id,
                 start_time=datetime(2026, 12, 5, 18, 0), end_time=datetime(2026, 12, 5, 23, 0),
                 expected_attendance=120, created_at=now, submitted_at=now,
                 equipment_requirements="Two wireless microphones and a projector")
    db.session.add(gala)
    db.session.flush()
    requirements = []
    for equipment_type, quantity, technical in (
            ("Wireless microphone", 2, "Lapel, with spare batteries"),
            ("Projector", 1, None)):
        requirement = EquipmentRequirement(
            event_id=gala.id, equipment_type=equipment_type, quantity=quantity,
            technical_requirements=technical, status="requested",
            recorded_by_id=users["coordinator"].id, recorded_at=now, last_saved_at=now)
        db.session.add(requirement)
        requirements.append(requirement)
    db.session.flush()
    ids = {"gala": gala.id, "mic": requirements[0].id, "projector": requirements[1].id}
    db.session.commit()
    print(json.dumps(ids))
