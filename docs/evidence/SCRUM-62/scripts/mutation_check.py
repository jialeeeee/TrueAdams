"""Break SCRUM-62 code one way at a time and check the tests catch it.

Run from the repo root. Every file is restored after each mutation (and at exit).
Usage: python mutation_check.py backend|frontend
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PY = ROOT / "backend/.venv/Scripts/python.exe"

BACKEND = [
    ("B1", "list every event, not just the caller's", "AC1 / TC-62-01",
     "backend/app/events/routes.py",
     "Event.query.filter_by(coordinator_id=user.id)", "Event.query"),
    ("B2", "let any role load the list", "AC1 / TC-62-05",
     "backend/app/events/routes.py",
     "if user.role != COORDINATOR_ROLE:\n            return _error(\"Only event coordinators",
     "if False:\n            return _error(\"Only event coordinators"),
    ("B3", "order by ID instead of proposed date", "AC1 / TC-62-03",
     "backend/app/events/routes.py",
     ".order_by(Event.start_time.asc().nulls_last(), Event.id)", ".order_by(Event.id)"),
    ("B4", "send the end time as the proposed date", "AC1 / TC-62-02",
     "backend/app/events/routes.py",
     '"start_time": _isoformat(e.start_time), "status": e.status}',
     '"start_time": _isoformat(e.end_time), "status": e.status}'),
    ("B5", "send a blank name as-is instead of null", "AC5 / TC-62-09",
     "backend/app/events/routes.py",
     '{"id": e.id, "title": _recorded(e.title),', '{"id": e.id, "title": e.title,'),
    ("B6", "no empty-state message", "AC4 / TC-62-08",
     "backend/app/events/routes.py",
     '"message": None if events else "You have no events assigned to you yet."',
     '"message": None'),
    ("B7", "database failure not caught", "A7 / TC-62-10",
     "backend/app/events/routes.py",
     'except SQLAlchemyError:\n        db.session.rollback()\n        return _error(\n            "Your managed events',
     'except ZeroDivisionError:\n        db.session.rollback()\n        return _error(\n            "Your managed events'),
]

FRONTEND = [
    ("F1", "list shows a missing name as blank", "AC5 / TC-62-12, 15",
     "frontend/src/pages/ManagedEventsPage.jsx",
     "{event.title || NOT_RECORDED}", "{event.title}"),
    ("F2", "list links to the review page, not planning", "AC2 / TC-62-12",
     "frontend/src/pages/ManagedEventsPage.jsx",
     "to={`/events/${event.id}/planning`}", "to={`/events/${event.id}/review`}"),
    ("F3", "list drops the status", "AC1 / TC-62-11",
     "frontend/src/pages/ManagedEventsPage.jsx",
     "{`Status: ${statusLabel(event.status)}`}", "{\"\"}"),
    ("F4", "list converts the proposed date through the browser time zone", "AC1 / TC-62-11",
     "frontend/src/pages/ManagedEventsPage.jsx",
     'return value ? value.slice(0, 16).replace("T", " ") : NOT_RECORDED;',
     'return value ? new Date(value + "Z").toLocaleString() : NOT_RECORDED;'),
    ("F5", "list hides the empty-state message", "AC4 / TC-62-13",
     "frontend/src/pages/ManagedEventsPage.jsx",
     "{result && result.events.length === 0 && <p>{result.message}</p>}", ""),
    ("F6", "planning page shows unrecorded fields as blank", "AC5 / TC-62-15",
     "frontend/src/pages/EventPlanningPage.jsx",
     'if (value === null || value === undefined || value === "") return NOT_RECORDED;',
     'if (value === null || value === undefined || value === "") return "";'),
    ("F7", "planning page treats registration 'No' as not recorded", "AC5 / TC-62-15",
     "frontend/src/pages/EventPlanningPage.jsx",
     'if (value === null || value === undefined || value === "") return NOT_RECORDED;',
     'if (value === null || value === undefined || value === "" || value === false) return NOT_RECORDED;'),
    ("F8", "planning page drops the coordinator line", "AC3 / TC-62-14",
     "frontend/src/pages/EventPlanningPage.jsx",
     '<p>{`Coordinator: ${display("coordinator", event.coordinator)}`}</p>', ""),
    ("F9", "planning page drops the status line", "AC3 / TC-62-14",
     "frontend/src/pages/EventPlanningPage.jsx",
     "<p>{`Status: ${statusLabel(event.status)}`}</p>", ""),
    ("F10", "planning page offers Retry after a refusal", "A7 / TC-62-16",
     "frontend/src/pages/EventPlanningPage.jsx",
     "retryable: !failure.response || data?.retryable === true", "retryable: true"),
]


def run_backend():
    r = subprocess.run([str(PY), "-m", "unittest", "tests.test_managed_events"],
                       cwd=ROOT / "backend", capture_output=True, text=True)
    out = r.stdout + r.stderr
    failed = sorted(set(re.findall(r"^(?:FAIL|ERROR): (test_\w+)", out, re.M)))
    return r.returncode, failed, out


def run_frontend():
    r = subprocess.run("npx vitest run src/pages/ManagedEventsPage.test.jsx "
                       "src/pages/EventPlanningPage.test.jsx",
                       cwd=ROOT / "frontend", capture_output=True, text=True, shell=True,
                       encoding="utf-8", errors="replace")
    out = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr)
    failed = sorted(set(m.strip() for m in re.findall(r"^\s*(?:×|FAIL)\s+.*?> (.+?)(?:\s+\d+ms)?$", out, re.M)))
    return r.returncode, failed, out


def main(which):
    mutations, runner = (BACKEND, run_backend) if which == "backend" else (FRONTEND, run_frontend)
    code, failed, out = runner()
    if code != 0:
        print("BASELINE FAILS — fix before mutating\n", out[-3000:])
        sys.exit(1)
    print(f"baseline: all {which} SCRUM-62 tests pass")
    for mid, what, traces, path, old, new in mutations:
        file = ROOT / path
        original = file.read_bytes()
        text = original.decode("utf-8")
        if text.count(old) != 1:
            print(f"{mid}: SKIPPED — pattern found {text.count(old)} times")
            continue
        try:
            file.write_bytes(text.replace(old, new).encode("utf-8"))
            code, failed, out = runner()
        finally:
            file.write_bytes(original)
        caught = "CAUGHT" if code != 0 else "MISSED"
        print(f"{mid} | {what} | {traces} | {caught} | {', '.join(failed) or '-'}")
    code, _, _ = runner()
    print("after restore:", "all pass" if code == 0 else "FAILING — check files")


if __name__ == "__main__":
    main(sys.argv[1])
