"""Fresh demo requests for one end-to-end run of SCRUM-77/78. Run from backend/ with its venv.

Uses the SCRUM-62 demo accounts (demo.*@connectsphere.demo, password Demo1234!) and
adds new rows on every run, because approving or rejecting one uses it up. Every
row is titled "[Demo] ...". Prints the new IDs as JSON for the end-to-end script.
"""
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")
from app import create_app
from app.extensions import db
from app.models import Event, User

app = create_app()
with app.app_context():
    users = {u.email.split("@")[0]: u for u in
             User.query.filter(User.email.like("demo.%@connectsphere.demo"))}
    if "demo.coordinator" not in users:
        sys.exit("Demo accounts missing: run docs/evidence/SCRUM-62/scripts/seed_demo_data.py first.")
    stamp = datetime.now().strftime("%d %b %H:%M:%S")
    common = dict(organiser_id=users["demo.organiser"].id,
                  coordinator_id=users["demo.coordinator"].id,
                  coordinator_assigned_at=datetime.utcnow(), submitted_at=datetime.utcnow(),
                  purpose="Bring residents together by the river.",
                  description="An evening of local bands on the riverside lawn.",
                  start_time=datetime(2026, 12, 19, 18, 0), end_time=datetime(2026, 12, 19, 22, 0),
                  expected_attendance=300, venue_requirements="Open lawn with power",
                  registration_required=True)
    rows = {
        "submitted": Event(title=f"[Demo] Riverside Concert ({stamp})", status="submitted", **common),
        "under_review": Event(title=f"[Demo] Spring Fair ({stamp})", status="under_review", **common),
    }
    db.session.add_all(rows.values())
    db.session.commit()
    print(json.dumps({key: {"id": e.id, "title": e.title} for key, e in rows.items()}))
