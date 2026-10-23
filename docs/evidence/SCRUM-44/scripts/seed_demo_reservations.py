"""Demo data for one end-to-end run of SCRUM-44. Run from backend/ with its venv.

    python ../docs/evidence/SCRUM-44/scripts/seed_demo_reservations.py            # seed
    python ../docs/evidence/SCRUM-44/scripts/seed_demo_reservations.py cancel ID  # cancel an event

It writes committed rows, so it only runs against a database on this machine (DATABASE_URL
on localhost, built with ci/build_test_database.py): equipment_reservations is not on
Supabase until db/equipment_reservations.sql has been run there.

Adds, once, the demo accounts (password Demo1234!) and demo equipment, and on every run two
fresh approved events of demo.coordinator on 5 Dec 2026: the "[Demo] Charity Gala"
(18:00-23:00: 3 microphones "Lapel", 1 projector, 1 hologram projector) and the overlapping
"[Demo] Winter Concert" (20:00-23:30: 2 microphones). Prints the event IDs as JSON.
`cancel` sets an event to cancelled through the app's models, as a cancel feature would
(there is none yet), so the release rule runs (A10).
"""
import json
import sys
from datetime import datetime

from sqlalchemy.engine import make_url
from werkzeug.security import generate_password_hash

sys.path.insert(0, ".")
from app import create_app
from app.extensions import db
from app.models import EquipmentRequirement, EquipmentUnavailability, Event, Resource, User

PASSWORD = "Demo1234!"
ACCOUNTS = [("demo.tech@connectsphere.demo", "tech_staff"),
            ("demo.coordinator@connectsphere.demo", "coordinator"),
            ("demo.organiser@connectsphere.demo", "organiser")]
MIC, PROJECTOR = "[Demo] Wireless microphone", "[Demo] Projector"
EQUIPMENT = [  # (name, category, quantity available)
    ("[Demo] Shure SLX-D 44", MIC, 2),
    ("[Demo] Sennheiser EW-D 44", "[demo]  wireless MICROPHONE", 2),
    ("[Demo] Epson EB-L 44", PROJECTOR, 1),
    ("[Demo] BenQ LU935 44", PROJECTOR, 2),
]

app = create_app()
url = make_url(app.config["SQLALCHEMY_DATABASE_URI"] or "postgresql://")
if url.host not in {"localhost", "127.0.0.1"}:
    sys.exit(f"Refusing to write demo rows to {url.host}: use a local database.")

with app.app_context():
    if sys.argv[1:2] == ["cancel"]:
        event = db.session.get(Event, int(sys.argv[2]))
        event.status = "cancelled"
        db.session.commit()
        print(json.dumps({"cancelled": event.id}))
        sys.exit(0)

    users = {}
    for email, role in ACCOUNTS:
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(email=email, role=role, password_hash=generate_password_hash(PASSWORD))
            db.session.add(user)
        users[role] = user
    items = {}
    for name, category, quantity in EQUIPMENT:
        item = Resource.query.filter_by(name=name).first()
        if item is None:
            item = Resource(name=name, category=category, quantity_available=quantity)
            db.session.add(item)
        items[name] = item
    db.session.flush()
    if not EquipmentUnavailability.query.filter_by(resource_id=items["[Demo] Epson EB-L 44"].id).first():
        db.session.add(EquipmentUnavailability(
            resource_id=items["[Demo] Epson EB-L 44"].id, start_time=datetime(2026, 12, 5, 17, 0),
            end_time=datetime(2026, 12, 5, 19, 0), reason="Lamp replacement"))

    def event(title, start, end, needs):
        row = Event(title=title, status="approved", organiser_id=users["organiser"].id,
                    coordinator_id=users["coordinator"].id, start_time=start, end_time=end,
                    submitted_at=datetime.utcnow(), coordinator_assigned_at=datetime.utcnow())
        db.session.add(row)
        db.session.flush()
        for equipment_type, quantity, technical in needs:
            db.session.add(EquipmentRequirement(event_id=row.id, equipment_type=equipment_type,
                                                quantity=quantity, technical_requirements=technical,
                                                recorded_by_id=users["coordinator"].id))
        return row

    gala = event("[Demo] Charity Gala", datetime(2026, 12, 5, 18, 0), datetime(2026, 12, 5, 23, 0),
                 [(MIC, 3, "Lapel"), (PROJECTOR, 1, None), ("[Demo] Hologram projector", 1, None)])
    concert = event("[Demo] Winter Concert", datetime(2026, 12, 5, 20, 0),
                    datetime(2026, 12, 5, 23, 30), [(MIC, 2, None)])
    db.session.commit()
    print(json.dumps({"gala": gala.id, "concert": concert.id}))
