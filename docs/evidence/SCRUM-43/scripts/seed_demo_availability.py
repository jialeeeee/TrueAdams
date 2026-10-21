"""Demo data for one end-to-end run of SCRUM-43. Run from backend/ with its venv.

    python ../docs/evidence/SCRUM-43/scripts/seed_demo_availability.py           # seed
    python ../docs/evidence/SCRUM-43/scripts/seed_demo_availability.py check     # after

Uses the SCRUM-62 demo accounts and SCRUM-42's demo.tech (run
docs/evidence/SCRUM-42/scripts/seed_demo_equipment.py first). Adds once two demo
microphones and two demo projectors, one of them unavailable on 5 Dec 2026 17:00-19:00
("Lamp replacement").
Every run adds fresh "[Demo] ..." events for demo.coordinator: a timed, approved one with
three requirements, and one with no times recorded. Prints the IDs as JSON.

The demo categories carry a "[Demo]" prefix, so real equipment in the shared catalogue
never matches the demo requirements, and the check's numbers stay predictable.
`check` prints the demo equipment's available quantities (AC4: checking reserves nothing).
"""
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")
from app import create_app
from app.extensions import db
from app.models import EquipmentRequirement, EquipmentUnavailability, Event, Resource, User

MIC, PROJECTOR = "[Demo] Wireless microphone", "[Demo] Projector"
EQUIPMENT = [  # (name, category, quantity available)
    ("[Demo] Shure SLX-D 43", MIC, 2),
    ("[Demo] Sennheiser EW-D 43", "[demo]  wireless MICROPHONE", 2),
    ("[Demo] Epson EB-L", PROJECTOR, 1),
    ("[Demo] BenQ LU935", PROJECTOR, 2),
]
NAMES = [name for name, _, _ in EQUIPMENT]

app = create_app()
with app.app_context():
    if sys.argv[1:2] == ["check"]:
        rows = Resource.query.filter(Resource.name.in_(NAMES)).order_by(Resource.name).all()
        print(json.dumps({r.name: r.quantity_available for r in rows}))
        sys.exit(0)

    users = {u.email.split("@")[0]: u for u in
             User.query.filter(User.email.like("demo.%@connectsphere.demo"))}
    if "demo.tech" not in users:
        sys.exit("demo.tech missing: run docs/evidence/SCRUM-42/scripts/seed_demo_equipment.py first.")
    items = {r.name: r for r in Resource.query.filter(Resource.name.in_(NAMES))}
    for name, category, quantity in EQUIPMENT:
        if name not in items:
            items[name] = Resource(name=name, category=category, quantity_available=quantity)
            db.session.add(items[name])
    db.session.flush()
    epson = items["[Demo] Epson EB-L"]
    if not EquipmentUnavailability.query.filter_by(resource_id=epson.id).first():
        db.session.add(EquipmentUnavailability(
            resource_id=epson.id, start_time=datetime(2026, 12, 5, 17, 0),
            end_time=datetime(2026, 12, 5, 19, 0), reason="Lamp replacement"))

    stamp = datetime.now().strftime("%d %b %H:%M:%S")
    common = dict(organiser_id=users["demo.organiser"].id,
                  coordinator_id=users["demo.coordinator"].id,
                  coordinator_assigned_at=datetime.utcnow(), submitted_at=datetime.utcnow(),
                  purpose="Raise funds for the harbour restoration.", expected_attendance=180)
    gala = Event(title=f"[Demo] Harbour Gala ({stamp})", status="approved",
                 start_time=datetime(2026, 12, 5, 18, 0), end_time=datetime(2026, 12, 5, 23, 0),
                 **common)
    untimed = Event(title=f"[Demo] Untimed Talk ({stamp})", status="submitted", **common)
    db.session.add_all([gala, untimed])
    db.session.flush()
    for equipment_type, quantity, technical in [(MIC, 3, "Lapel"), (PROJECTOR, 1, None),
                                                ("[Demo] Hologram projector", 1, None)]:
        db.session.add(EquipmentRequirement(event_id=gala.id, equipment_type=equipment_type,
                                            quantity=quantity, technical_requirements=technical,
                                            recorded_by_id=users["demo.coordinator"].id))
    db.session.add(EquipmentRequirement(event_id=untimed.id, equipment_type=MIC, quantity=1,
                                        recorded_by_id=users["demo.coordinator"].id))
    db.session.commit()
    print(json.dumps({"gala": {"id": gala.id, "title": gala.title},
                      "untimed": {"id": untimed.id, "title": untimed.title}}))
