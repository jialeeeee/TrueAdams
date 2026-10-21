"""SCRUM-42 mutations re-run after the review of PR #47: the new ones (B19, B20, F12-F14)
and the four whose code the fixes changed (B12, B14, B16, B17). Same runner:
    python docs/evidence/SCRUM-77/scripts/mutation_check.py docs/evidence/SCRUM-42/scripts/mutations_review.py backend|frontend
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("mutations", Path(__file__).with_name("mutations.py"))
_all = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_all)

SELECTED = {"B12", "B14", "B16", "B17", "B19", "B20", "F12", "F13", "F14"}
BACKEND_TESTS = _all.BACKEND_TESTS
FRONTEND_TESTS = _all.FRONTEND_TESTS
MUTATIONS = [m for m in _all.MUTATIONS if m[0] in SELECTED]
