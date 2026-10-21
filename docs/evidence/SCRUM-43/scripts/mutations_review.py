"""SCRUM-43 mutations re-run after the reviews: F10 (the stale-result fix carried over
from PR #47), the new ones from the review of PR #48 (B15-B17, F11) and the three whose
code that fix changed (B1, B4, B9). Same runner:
    python docs/evidence/SCRUM-77/scripts/mutation_check.py docs/evidence/SCRUM-43/scripts/mutations_review.py frontend
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("mutations", Path(__file__).with_name("mutations.py"))
_all = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_all)

SELECTED = {"B1", "B4", "B9", "B15", "B16", "B17", "F10", "F11"}
BACKEND_TESTS = _all.BACKEND_TESTS
FRONTEND_TESTS = _all.FRONTEND_TESTS
MUTATIONS = [m for m in _all.MUTATIONS if m[0] in SELECTED]
