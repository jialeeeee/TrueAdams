"""SCRUM-96 mutations: ways Technical Support's view of the equipment requirements could break.

Run with the SCRUM-77 runner, from the repo root (TEST_DATABASE_URL set for the backend):
    python docs/evidence/SCRUM-77/scripts/mutation_check.py docs/evidence/SCRUM-96/scripts/mutations.py backend|frontend

The backend side runs only SCRUM-96's tests, so a catch is theirs, not SCRUM-42's. The
frontend side runs the page's test file, which also holds SCRUM-42's cases; the results
list the failing tests, so it shows which SCRUM-96 case caught each one.
"""

ROUTES = "backend/app/events/routes.py"
PERMISSIONS = "backend/app/events/permissions.py"
PAGE = "frontend/src/pages/EquipmentRequirementsPage.jsx"

BACKEND_TESTS = ["tests.test_tech_views_equipment"]
FRONTEND_TESTS = ["src/pages/EquipmentRequirementsPage.test.jsx"]

LOAD_FAILED = ('        return _error("The equipment requirements could not be loaded. '
               'Please try again.", 503,\n                      retryable=True)')

# The one 403 in _equipment_event (other helpers raise the same line).
DENIED = "    if not allowed(user, event):\n        raise _Rejected(denied, 403)"

MUTATIONS = [
    # ---------- Backend: what Technical Support see (AC1) ----------
    ("B1", "backend", "Technical requirements are left out", "AC1",
     ROUTES, '        "technical_requirements": _recorded(requirement.technical_requirements),\n'
             '        "status": requirement.status,',
     '        "technical_requirements": None,\n        "status": requirement.status,'),
    ("B2", "backend", "Every quantity is shown as 1", "AC1",
     ROUTES, '        "quantity": requirement.quantity,\n        "technical_requirements": _recorded',
     '        "quantity": 1,\n        "technical_requirements": _recorded'),
    ("B3", "backend", "Requirements are listed newest first", "AC1",
     ROUTES, "                    .order_by(EquipmentRequirement.id).all())\n"
             "    users = _users_by_id([event.coordinator_id]",
     "                    .order_by(EquipmentRequirement.id.desc()).all())\n"
     "    users = _users_by_id([event.coordinator_id]"),
    ("B4", "backend", "The organiser's note is left out", "AC1",
     ROUTES, '        "organiser_note": _recorded(event.equipment_requirements),',
     '        "organiser_note": None,'),
    ("B5", "backend", "Technical Support's arrangement note is left out", "AC1",
     ROUTES, '        "arrangement_note": _recorded(requirement.arrangement_note),',
     '        "arrangement_note": None,'),
    ("B6", "backend", "Technical Support are not offered arrangement updates", "AC1",
     ROUTES, '        "can_update_arrangements": is_open and is_tech_staff(user),',
     '        "can_update_arrangements": False,'),
    ("B7", "backend", "Cancelled and rejected events can't be opened", "AC1",
     ROUTES, "    if event is None or (hide_drafts and event.status == DRAFT_STATUS):",
     "    if event is None or (hide_drafts and event.status in (DRAFT_STATUS, \"cancelled\", "
     "\"rejected\")):"),
    ("B8", "backend", "A draft's equipment page is shown", "AC1, AC2",
     ROUTES, "    if event is None or (hide_drafts and event.status == DRAFT_STATUS):",
     "    if event is None:"),
    ("B9", "backend", "The view doesn't ask for drafts to be hidden", "AC1, AC2",
     ROUTES, "EQUIPMENT_VIEW_DENIED,\n                                       hide_drafts=True)",
     "EQUIPMENT_VIEW_DENIED)"),
    # ---------- Backend: who may view, and nothing changes (AC2) ----------
    ("B10", "backend", "Anyone signed in may view", "AC2",
     PERMISSIONS, "    return is_current_coordinator(user, event) or is_tech_staff(user)",
     "    return user is not None"),
    ("B11", "backend", "Every coordinator may view every event", "AC2",
     PERMISSIONS, "    return is_current_coordinator(user, event) or is_tech_staff(user)",
     "    return user.role == COORDINATOR_ROLE or is_tech_staff(user)"),
    ("B12", "backend", "Venue Staff count as Technical Support", "AC2",
     PERMISSIONS, "    return user is not None and user.role == TECH_STAFF_ROLE",
     "    return user is not None and user.role in {TECH_STAFF_ROLE, \"venue_staff\"}"),
    ("B13", "backend", "Admins and Coordinator Leads may view", "AC2",
     PERMISSIONS, "    return is_current_coordinator(user, event) or is_tech_staff(user)",
     "    return (is_current_coordinator(user, event) or is_tech_staff(user)\n"
     "            or user.role in {\"admin\", COORDINATOR_LEAD_ROLE})"),
    ("B14", "backend", "A refusal names the event", "AC2",
     ROUTES, DENIED, DENIED.replace("_Rejected(denied, 403)",
                                    "_Rejected(f\"{denied} ({event.title})\", 403)")),
    ("B15", "backend", "A refused view changes the event", "AC2",
     ROUTES, DENIED, DENIED.replace("        raise _Rejected(denied, 403)",
                                    "        event.last_saved_at = datetime.utcnow()\n"
                                    "        db.session.commit()\n"
                                    "        raise _Rejected(denied, 403)")),
    ("B16", "backend", "Viewing adds a notification", "AC2",
     ROUTES, "                                       hide_drafts=True)\n"
             "        payload = _equipment_page(user, event)",
     "                                       hide_drafts=True)\n"
     "        db.session.add(Notification(recipient_id=user.id, kind=\"equipment_viewed\",\n"
     "                                    message=\"Viewed\", event_id=event.id))\n"
     "        db.session.commit()\n"
     "        payload = _equipment_page(user, event)"),
    ("B17", "backend", "A deleted user's token is refused as 403, not 401", "AC2",
     ROUTES, "    own (SCRUM-96 A3, SCRUM-74 A2).\"\"\"\n    user = _current_user()\n    if user is None:\n",
     "    own (SCRUM-96 A3, SCRUM-74 A2).\"\"\"\n    user = _current_user()\n    if False:\n"),
    # ---------- Backend: a failed load (AC3) ----------
    ("B18", "backend", "A failed load is reported as an empty list", "AC3",
     ROUTES, LOAD_FAILED,
     '        return jsonify({"requirements": [], "message": NO_EQUIPMENT_REQUIREMENTS})'),
    ("B19", "backend", "A failed load is not marked retryable", "AC3",
     ROUTES, LOAD_FAILED, LOAD_FAILED.replace("retryable=True", "retryable=False")),
    ("B20", "backend", "A failed load is reported as \"Event not found.\"", "AC3",
     ROUTES, LOAD_FAILED, "        return _error(EVENT_NOT_FOUND, 404)"),

    # ---------- Frontend: what Technical Support see (AC1) ----------
    ("F1", "frontend", "Technical requirements are not shown", "AC1",
     PAGE, '      <p>{`Technical requirements: ${requirement.technical_requirements ?? "None recorded"}`}</p>\n',
     ""),
    ("F2", "frontend", "Blank technical requirements show nothing instead of \"None recorded\"", "AC1",
     PAGE, '?? "None recorded"', '?? ""'),
    ("F3", "frontend", "Quantities are not shown", "AC1",
     PAGE, "const describe = (requirement) => `${requirement.quantity} × ${requirement.equipment_type}`;",
     "const describe = (requirement) => `${requirement.equipment_type}`;"),
    ("F4", "frontend", "Technical Support are given the record form", "AC1",
     PAGE, "      {page.can_edit && (\n        <RequirementForm",
     "      {(page.can_edit || page.can_update_arrangements) && (\n        <RequirementForm"),
    # ---------- Frontend: refusals (AC2) ----------
    ("F5", "frontend", "Refusals offer Retry", "AC2",
     PAGE, "{loadError.retryable && <button", "{<button"),
    # ---------- Frontend: a failed load (AC3) ----------
    ("F6", "frontend", "A failed load offers no Retry", "AC3",
     PAGE, "{loadError.retryable && <button", "{false && <button"),
    ("F7", "frontend", "Retry does nothing", "AC3",
     PAGE, "onClick={load}>Retry", "onClick={() => {}}>Retry"),
    ("F8", "frontend", "A failed load is shown as nothing recorded", "AC3",
     PAGE, "        setLoadError({ message: explain(error, NOT_LOADED), retryable: canRetry(error) });",
     "        setPage({ event: {}, requirements: [], can_edit: false,\n"
     "                  message: \"No equipment requirements have been recorded for this event.\" });"),
    ("F9", "frontend", "The server's explanation is ignored", "AC3",
     PAGE, "explain(error, NOT_LOADED)", "NOT_LOADED"),
    ("F10", "frontend", "With no reply, the page doesn't say to check the connection", "AC3",
     PAGE, 'const NOT_LOADED = "The equipment requirements could not be loaded. Check your connection and try again.";',
     'const NOT_LOADED = "Something went wrong.";'),
    ("F11", "frontend", "The error stays after a successful Retry", "AC3",
     PAGE, "    setLoadError(null);\n    try {", "    try {"),
]
