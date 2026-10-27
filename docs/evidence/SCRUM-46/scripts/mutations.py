"""SCRUM-46 mutations: ways requesting a change could be broken.

Run with the SCRUM-77 runner, from the repo root (TEST_DATABASE_URL set for the backend):
    python docs/evidence/SCRUM-77/scripts/mutation_check.py docs/evidence/SCRUM-46/scripts/mutations.py backend|frontend
"""

ROUTES = "backend/app/events/routes.py"
RULES = "backend/app/events/change_requests.py"
PAGE = "frontend/src/pages/ChangeRequestPage.jsx"
LIST = "frontend/src/pages/MyEventRequestsPage.jsx"

BACKEND_TESTS = ["tests.test_change_requests", "tests.test_change_requests_unit"]
FRONTEND_TESTS = ["src/pages/ChangeRequestPage.test.jsx", "src/pages/MyEventRequestsPage.test.jsx"]

MUTATIONS = [
    # ---------- Backend: who and which events (AC1, AC5) ----------
    ("B1", "backend", "Anyone may request a change to any event", "AC1",
     ROUTES, "    if not is_current_organiser(user, event):\n        raise _Rejected(CHANGE_REQUEST_ORGANISER_ONLY, 403)",
     "    if False:\n        raise _Rejected(CHANGE_REQUEST_ORGANISER_ONLY, 403)"),
    ("B2", "backend", "Events that aren't approved can take a request", "AC1",
     ROUTES, "    if event.status != CHANGEABLE_STATUS:", "    if False:"),
    ("B3", "backend", "An event without a coordinator can take a request", "AC5",
     ROUTES, "    if coordinator is None:\n        # AC5", "    if False:\n        # AC5"),
    ("B22", "backend", "A coordinator whose role has changed still counts, and is notified", "AC5, AC9",
     ROUTES, "    return coordinator if _is_current_coordinator(coordinator, event) else None",
     "    return coordinator"),
    # ---------- Backend: what may be proposed (AC2, AC3, AC4) ----------
    ("B4", "backend", "Fields that aren't permitted are silently ignored", "AC2, AC4",
     RULES, "            problems[name] = f\"{name} can't be changed through a change request.\"\n", ""),
    ("B5", "backend", "Negative attendance is accepted", "AC4",
     RULES, "or value < 1:", "or value < -1000:"),
    ("B6", "backend", "An end before the start is accepted", "AC4",
     RULES, "if start is not None and end is not None and end <= start:", "if False:"),
    ("B7", "backend", "An end equal to the start is accepted", "AC4 (A4)",
     RULES, "and end <= start:", "and end < start:"),
    ("B8", "backend", "A proposed end is not compared with the current start", "AC4 (A4)",
     RULES, 'start = proposed.get("start_time", event.start_time)', 'start = proposed.get("start_time")'),
    ("B9", "backend", "Venue requirements can be cleared", "AC4 (A4)",
     RULES, 'REQUIRED_TEXT_FIELDS = {"venue_requirements"}', "REQUIRED_TEXT_FIELDS = set()"),
    ("B10", "backend", "Times that aren't date and time are accepted", "AC4 (A4)",
     RULES, "    if isinstance(value, str) and _LOCAL_DATETIME.match(value):\n        try:\n            return datetime",
     "    if isinstance(value, str):\n        try:\n            return datetime"),
    ("B11", "backend", "Unchanged values are recorded as changes", "AC3 (A3)",
     RULES, "if name in proposed and proposed[name] != _current(event, name):", "if name in proposed:"),
    ("B12", "backend", "A request that changes nothing is saved", "AC4 (A3)",
     ROUTES, "        if not changes:\n            raise _Rejected(NO_CHANGES_TO_REQUEST",
     "        if False:\n            raise _Rejected(NO_CHANGES_TO_REQUEST"),
    ("B13", "backend", "The current values are not recorded", "AC3 (A7)",
     RULES, 'changes[name] = {"from": _current(event, name), "to": proposed[name]}',
     'changes[name] = {"from": None, "to": proposed[name]}'),
    # ---------- Backend: saving (AC6, AC7, AC8) ----------
    ("B14", "backend", "The request isn't saved as Pending Review", "AC6",
     ROUTES, "                                 status=change_requests.PENDING_REVIEW,\n",
     '                                 status="submitted",\n'),
    ("B15", "backend", "The event isn't locked before the pending check", "AC6 (A6)",
     ROUTES, "event = db.session.get(Event, event_id, **locking) if event_id <= DB_INTEGER_MAX else None",
     "event = db.session.get(Event, event_id) if event_id <= DB_INTEGER_MAX else None"),
    ("B16", "backend", "The pending request is applied to the approved event", "AC7",
     ROUTES, "        db.session.add(row)\n",
     "        db.session.add(row)\n        for name, change in changes.items():\n            setattr(event, name, change[\"to\"])\n"),
    ("B17", "backend", "A failed save is reported as a success", "AC8",
     ROUTES, "    except SQLAlchemyError:\n        db.session.rollback()\n        return _error(CHANGE_NOT_SUBMITTED, 503, retryable=True)",
     '    except SQLAlchemyError:\n        db.session.rollback()\n        return jsonify({"message": "Saved"}), 201'),
    ("B18", "backend", "A failed load is shown as an empty form", "AC8",
     ROUTES, "return _error(CHANGE_FORM_NOT_LOADED, 503, retryable=True)",
     'return jsonify({"event": None, "fields": []})'),
    # ---------- Backend: the coordinator is told (AC9) ----------
    ("B19", "backend", "No in-app notification", "AC9",
     ROUTES, "        db.session.add(Notification(\n            recipient_id=coordinator.id, kind=CHANGE_REQUEST_NOTIFICATION",
     "        (Notification(\n            recipient_id=coordinator.id, kind=CHANGE_REQUEST_NOTIFICATION"),
    ("B20", "backend", "The notification doesn't say what would change", "AC9",
     ROUTES, 'f"{change_requests.describe(changes)}.")))', '"see the request.")))'),
    ("B21", "backend", "No email is queued", "AC9",
     ROUTES, "email_queued = _queue_change_request_email(to_address, title, requester, changes, event_id)",
     "email_queued = True"),
    # ---------- Backend: the one-pending index (AC6, AC8; team review, 27 Oct 2026) ----------
    ("B23", "backend", "A request refused by the one-pending index is reported as a failed save", "AC6",
     ROUTES, "        if _is_second_pending_request(error):\n", "        if False:\n"),
    ("B24", "backend", "Any refused save is reported as an already-pending request", "AC8",
     ROUTES, "        if _is_second_pending_request(error):\n", "        if True:\n"),
    # ---------- Frontend ----------
    ("F1", "frontend", "Every field is sent, not just the changed ones", "AC2",
     PAGE, ".filter(({ name }) => values[name] !== inputValue(name, current[name]))", ".filter(() => true)"),
    ("F2", "frontend", "Attendance is sent as text", "AC2",
     PAGE, 'return text.trim() === "" ? null : Number(text);', "return text;"),
    ("F3", "frontend", "The reason for each refused field isn't shown", "AC4",
     PAGE, "{problem && <span>{problem}</span>}", "{null}"),
    ("F4", "frontend", "The entries are lost after a refusal", "AC4, AC8",
     PAGE, "      setProblems(error.response?.data?.fields ?? {});\n",
     "      setProblems(error.response?.data?.fields ?? {});\n      setValues({});\n"),
    ("F5", "frontend", "The form is offered when no change can be requested", "AC1, AC5",
     PAGE, "{!submitted && form.can_request && (", "{!submitted && ("),
    ("F6", "frontend", "Why no change can be requested isn't shown", "AC1, AC5",
     PAGE, "{!submitted && form.message && <p>{form.message}</p>}", "{null}"),
    ("F7", "frontend", "No confirmation", "AC6",
     PAGE, '{submitted && <p role="status">{submitted.message}</p>}', "{null}"),
    ("F8", "frontend", "The pending request isn't shown", "AC6",
     PAGE, "{pending && <RequestedChanges request={pending} />}", "{null}"),
    ("F9", "frontend", "A request that changes nothing is sent", "AC4",
     PAGE, "if (Object.keys(proposal).length === 0) {", "if (false) {"),
    ("F10", "frontend", "No Retry after a failed load", "AC8",
     PAGE, '{loadError.retryable && <button type="button" onClick={load}>Retry</button>}', "{null}"),
    ("F11", "frontend", "Every submitted request offers a change", "AC1",
     LIST, '{request.status === "approved" && (', "{("),
]
