"""Demo data for one end-to-end run of SCRUM-42. Run from backend/ with its venv.

    python ../docs/evidence/SCRUM-42/scripts/seed_demo_equipment.py           # seed
    python ../docs/evidence/SCRUM-42/scripts/seed_demo_equipment.py check ID  # after

Uses the SCRUM-62 demo accounts (demo.*@connectsphere.demo, password Demo1234!) and
adds, once, a Technical Support demo account (demo.tech) and demo equipment
("[Demo] Shure SLX-D", category Wireless microphone, 4 available). Every run adds
fresh "[Demo] ..." events for demo.coordinator: an approved one with the organiser's
equipment note, and a cancelled one with a requirement already recorded. Prints the
new IDs as JSON for the end-to-end script.

`check ID` prints the demo equipment's available quantity and the event's recorded
requirements, read straight from the database (AC5: recording reserves nothing).
"""
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import EquipmentRequirement, Event, Resource, User

PASSWORD = "Demo1234!"
TECH = "demo.tech@connectsphere.demo"
EQUIPMENT = "[Demo] Shure SLX-D"

app = create_app()
with app.app_context():
    resource = Resource.query.filter_by(name=EQUIPMENT).first()

    if sys.argv[1:2] == ["check"]:
        event_id = int(sys.argv[2])
        rows = (EquipmentRequirement.query.filter_by(event_id=event_id)
                .order_by(EquipmentRequirement.id).all())
        print(json.dumps({
            "equipment": {"name": resource.name, "quantity_available": resource.quantity_available},
            "requirements": [[r.equipment_type, r.quantity, r.technical_requirements, r.status,
                              r.arrangement_note] for r in rows],
        }))
        sys.exit(0)

    users = {u.email.split("@")[0]: u for u in
             User.query.filter(User.email.like("demo.%@connectsphere.demo"))}
    if "demo.coordinator" not in users:
        sys.exit("Demo accounts missing: run docs/evidence/SCRUM-62/scripts/seed_demo_data.py first.")
    if "demo.tech" not in users:
        users["demo.tech"] = User(email=TECH, password_hash=generate_password_hash(PASSWORD),
                                  role="tech_staff")
        db.session.add(users["demo.tech"])
    if resource is None:
        resource = Resource(name=EQUIPMENT, category="Wireless microphone", quantity_available=4)
        db.session.add(resource)

    stamp = datetime.now().strftime("%d %b %H:%M:%S")
    common = dict(organiser_id=users["demo.organiser"].id,
                  coordinator_id=users["demo.coordinator"].id,
                  coordinator_assigned_at=datetime.utcnow(), submitted_at=datetime.utcnow(),
                  purpose="Raise funds for the harbour restoration.",
                  description="A seated dinner with speeches and a live band.",
                  expected_attendance=180, venue_requirements="Ballroom with a stage",
                  registration_required=False)
    gala = Event(title=f"[Demo] Harbour Gala ({stamp})", status="approved",
                 start_time=datetime(2026, 12, 5, 18, 0), end_time=datetime(2026, 12, 5, 23, 0),
                 equipment_requirements="Two wireless microphones and a projector", **common)
    closed = Event(title=f"[Demo] Lantern Walk ({stamp})", status="cancelled",
                   start_time=datetime(2026, 11, 28, 19, 0), end_time=datetime(2026, 11, 28, 21, 0),
                   **common)
    db.session.add_all([gala, closed])
    db.session.flush()
    db.session.add(EquipmentRequirement(event_id=closed.id, equipment_type="Projector", quantity=1,
                                        recorded_by_id=users["demo.coordinator"].id))
    db.session.commit()
    print(json.dumps({
        "gala": {"id": gala.id, "title": gala.title},
        "closed": {"id": closed.id, "title": closed.title},
        "equipment": {"id": resource.id, "quantity_available": resource.quantity_available},
    }))
