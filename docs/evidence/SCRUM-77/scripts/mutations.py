"""SCRUM-77 mutations for mutation_check.py: ways approving could be broken."""

ROUTES = "backend/app/events/routes.py"
REVIEW_PAGE = "frontend/src/pages/ReviewRequestPage.jsx"
MY_REQUESTS_PAGE = "frontend/src/pages/MyRequestsPage.jsx"
MY_EVENT_REQUESTS_PAGE = "frontend/src/pages/MyEventRequestsPage.jsx"

BACKEND_TESTS = [
    "tests.test_approve_event_request",
    "tests.test_event_decisions",
    "tests.test_my_event_requests",
]
FRONTEND_TESTS = [
    "src/pages/ReviewRequestPage.test.jsx",
    "src/pages/MyRequestsPage.test.jsx",
    "src/pages/MyEventRequestsPage.test.jsx",
]

MUTATIONS = [
    ("B1", "backend", "Approve a request that is under review", "AC1",
     ROUTES, "if event.status != SUBMITTED_STATUS:",
     'if event.status not in (SUBMITTED_STATUS, "under_review"):'),
    ("B2", "backend", "Approve a request in any status", "AC1",
     ROUTES, "if event.status != SUBMITTED_STATUS:", "if False:"),
    ("B3", "backend", "Let any coordinator approve, not just the assigned one", "AC2",
     ROUTES, "    if not _is_current_coordinator(user, event):\n        raise _Rejected(denied, 403)",
     "    if user.role != COORDINATOR_ROLE:\n        raise _Rejected(denied, 403)"),
    ("B4", "backend", "Let any role approve", "AC2",
     ROUTES, "    if not _is_current_coordinator(user, event):\n        raise _Rejected(denied, 403)",
     "    pass"),
    ("B5", "backend", "Approving sets the status to under review instead of approved", "AC3",
     ROUTES, 'DECISION_STATUSES = {"approve": "approved", "reject": "rejected"}',
     'DECISION_STATUSES = {"approve": "under_review", "reject": "rejected"}'),
    ("B6", "backend", "Approval saved but not committed", "AC3",
     ROUTES, "        title = event.title\n        db.session.commit()",
     "        title = event.title\n        db.session.flush()"),
    ("B7", "backend", "\"My requests\" hides approved requests from the organiser", "AC4",
     ROUTES, "for r in requests\n", 'for r in requests if r.status != "approved"\n'),
    ("B8", "backend", "\"My event requests\" hides approved requests from the organiser", "AC4",
     ROUTES, 'for r in _newest_first(submitted, "submitted_at")',
     'for r in _newest_first(submitted, "submitted_at") if r.status != "approved"'),
    ("F1", "frontend", "Review page offers Approve for any undecided status", "AC1",
     REVIEW_PAGE, 'const undecided = request.status === "submitted";',
     'const undecided = !["approved", "rejected"].includes(request.status);'),
    ("F2", "frontend", "Review page ignores the server's refusal", "AC1",
     REVIEW_PAGE, '{error && <p role="alert" id="decision-error">{error}</p>}', ""),
    ("F3", "frontend", "Review page keeps showing Submitted after approving", "AC3",
     REVIEW_PAGE, "      setRequest(decided);\n", ""),
    ("F4", "frontend", "\"My requests\" page drops the status", "AC4",
     MY_REQUESTS_PAGE,
     "? `Status: ${statusLabel(request.status)} · decided ${formatSavedAt(request.decided_at)}`",
     "? `Decided ${formatSavedAt(request.decided_at)}`"),
    ("F5", "frontend", "\"My event requests\" page drops the status", "AC4",
     MY_EVENT_REQUESTS_PAGE,
     "? `Status: ${statusLabel(request.status)} · decided ${formatSavedAt(request.decided_at)}`",
     "? `Decided ${formatSavedAt(request.decided_at)}`"),
]
