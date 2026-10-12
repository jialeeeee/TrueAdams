"""SCRUM-78 mutations: ways rejecting could be broken.

Run with the SCRUM-77 runner, from the repo root:
    python docs/evidence/SCRUM-77/scripts/mutation_check.py docs/evidence/SCRUM-78/scripts/mutations.py backend|frontend
"""

ROUTES = "backend/app/events/routes.py"
REVIEW_PAGE = "frontend/src/pages/ReviewRequestPage.jsx"
MY_REQUESTS_PAGE = "frontend/src/pages/MyRequestsPage.jsx"
MY_EVENT_REQUESTS_PAGE = "frontend/src/pages/MyEventRequestsPage.jsx"
REASON_LINE = '<p>{`${request.status === "rejected" ? "Reason" : "Note"}: ${request.decision_note}`}</p>'

BACKEND_TESTS = [
    "tests.test_reject_event_request",
    "tests.test_event_decisions",
    "tests.test_decision_accountability",
    "tests.test_my_event_requests",
]
FRONTEND_TESTS = [
    "src/pages/ReviewRequestPage.test.jsx",
    "src/pages/MyRequestsPage.test.jsx",
    "src/pages/MyEventRequestsPage.test.jsx",
]

MUTATIONS = [
    ("B1", "backend", "Reject a request that is under review", "AC1",
     ROUTES, "if event.status != SUBMITTED_STATUS:",
     'if event.status not in (SUBMITTED_STATUS, "under_review"):'),
    ("B2", "backend", "Reject a request in any status", "AC1",
     ROUTES, "if event.status != SUBMITTED_STATUS:", "if False:"),
    ("B3", "backend", "Let any coordinator reject, not just the assigned one", "AC2",
     ROUTES, "    if not _is_current_coordinator(user, event):\n        raise _Rejected(denied, 403)",
     "    if user.role != COORDINATOR_ROLE:\n        raise _Rejected(denied, 403)"),
    ("B4", "backend", "Let any role reject", "AC2",
     ROUTES, "    if not _is_current_coordinator(user, event):\n        raise _Rejected(denied, 403)",
     "    pass"),
    ("B5", "backend", "Check the reason before permission", "AC2, AC3",
     ROUTES,
     "        user, event = _assigned_request(\n            event_id,\n"
     "            \"Only the event's assigned coordinator can approve or reject this request.\",",
     "        _parse_decision(request.get_json(silent=True))\n"
     "        user, event = _assigned_request(\n            event_id,\n"
     "            \"Only the event's assigned coordinator can approve or reject this request.\","),
    ("B6", "backend", "Reject without a reason", "AC3",
     ROUTES, "if rejecting and note is None:", "if False:"),
    ("B7", "backend", "Accept a reason made only of spaces", "AC3",
     ROUTES, "note = reason.strip() if reason and _has_visible_text(reason) else None",
     "note = reason if reason else None"),
    ("B8", "backend", "Rejecting sets the status to under review instead of rejected", "AC4",
     ROUTES, 'DECISION_STATUSES = {"approve": "approved", "reject": "rejected"}',
     'DECISION_STATUSES = {"approve": "approved", "reject": "under_review"}'),
    ("B9", "backend", "The reason is not saved", "AC5",
     ROUTES, "        event.decision_note = note\n", "        event.decision_note = None\n"),
    ("B10", "backend", "\"My requests\" hides rejected requests from the organiser", "AC6",
     ROUTES, "for r in requests\n", 'for r in requests if r.status != "rejected"\n'),
    ("B11", "backend", "\"My event requests\" hides rejected requests from the organiser", "AC6",
     ROUTES, 'for r in _newest_first(submitted, "submitted_at")',
     'for r in _newest_first(submitted, "submitted_at") if r.status != "rejected"'),
    ("F1", "frontend", "Review page sends a blank reason instead of refusing it", "AC3",
     REVIEW_PAGE, 'if (decision === "reject" && !reason) {', "if (false) {"),
    ("F2", "frontend", "Review page's Reject button approves", "AC4",
     REVIEW_PAGE, 'onClick={() => decide("reject")}', 'onClick={() => decide("approve")}'),
    ("F3", "frontend", "Review page does not show the saved reason", "AC5",
     REVIEW_PAGE, REASON_LINE, "<p></p>"),
    ("F4", "frontend", "\"My requests\" page does not show the reason", "AC6",
     MY_REQUESTS_PAGE, REASON_LINE, "<p></p>"),
    ("F5", "frontend", "\"My event requests\" page does not show the reason", "AC6",
     MY_EVENT_REQUESTS_PAGE, REASON_LINE, "<p></p>"),
]
