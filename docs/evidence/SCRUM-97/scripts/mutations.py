"""SCRUM-97 mutations: ways Technical Support's updates to equipment requirements could break.

Run with the SCRUM-77 runner, from the repo root (TEST_DATABASE_URL set for the backend):
    python docs/evidence/SCRUM-77/scripts/mutation_check.py docs/evidence/SCRUM-97/scripts/mutations.py backend|frontend

The backend side runs only SCRUM-97's tests, so a catch is theirs, not SCRUM-42's. The
frontend side runs the page's test file, which also holds SCRUM-42's and SCRUM-96's cases;
the results list the failing tests, so it shows which SCRUM-97 case caught each one.
"""

ROUTES = "backend/app/events/routes.py"
PAGE = "frontend/src/pages/EquipmentRequirementsPage.jsx"

BACKEND_TESTS = ["tests.test_tech_updates_equipment"]
FRONTEND_TESTS = ["src/pages/EquipmentRequirementsPage.test.jsx"]

# The setattr loop in update_equipment_arrangement (the coordinator's edit names it `name`).
APPLY = ("            for column, value in values.items():\n"
         "                setattr(requirement, column, value)")
CHANGED = ("        if any(getattr(requirement, column) != value "
           "for column, value in values.items()):")
FAILED = "        return _error(ARRANGEMENT_NOT_SAVED, 503, retryable=True)"
# The one 403 in _equipment_event (other helpers raise the same line).
DENIED = "    if not allowed(user, event):\n        raise _Rejected(denied, 403)"

MUTATIONS = [
    # ---------- Backend: an update is saved with who and when (AC1) ----------
    ("B1", "backend", "The update is recorded as made by the event's coordinator", "AC1",
     ROUTES, "            requirement.arrangement_updated_by_id = user.id\n",
     "            requirement.arrangement_updated_by_id = event.coordinator_id\n"),
    ("B2", "backend", "The update's time is not when it was made", "AC1",
     ROUTES, "            requirement.arrangement_updated_at = datetime.utcnow()\n            label",
     "            requirement.arrangement_updated_at = requirement.recorded_at\n            label"),
    ("B3", "backend", "The status is not saved", "AC1",
     ROUTES, APPLY, APPLY.replace("                setattr",
                                  "                if column != \"status\":\n"
                                  "                    setattr")),
    ("B4", "backend", "The note is not saved", "AC1",
     ROUTES, APPLY, APPLY.replace("                setattr",
                                  "                if column != \"arrangement_note\":\n"
                                  "                    setattr")),
    ("B5", "backend", "An update that changes nothing still replaces who and when", "AC1",
     ROUTES, CHANGED, "        if True:"),
    ("B6", "backend", "A change to the note alone is treated as no change", "AC1",
     ROUTES, CHANGED, "        if values[\"status\"] != requirement.status:"),
    ("B7", "backend", "An update for details the coordinator has changed is saved", "AC1",
     ROUTES, '        if ("last_saved_at" in body\n',
     '        if False and ("last_saved_at" in body\n'),
    ("B8", "backend", "An update without last_saved_at (an older page) is refused", "AC1",
     ROUTES, '        if ("last_saved_at" in body\n                and',
     "        if (True\n                and"),
    ("B9", "backend", "A refusal for changed details doesn't ask the page to reload", "AC1",
     ROUTES, "409, reload=True)", "409)"),
    ("B10", "backend", "The requirement is not locked while it is checked and saved", "AC1",
     ROUTES, "        requirement = _event_requirement(event, requirement_id, lock=True)\n"
             "        _require_equipment_open(event)\n        body = _equipment_body",
     "        requirement = _event_requirement(event, requirement_id)\n"
     "        _require_equipment_open(event)\n        body = _equipment_body"),
    # ---------- Backend: only Technical Support Staff can update (AC2) ----------
    ("B11", "backend", "A draft's requirement can be updated", "AC2",
     ROUTES, "EQUIPMENT_TECH_ONLY,\n                                       hide_drafts=True)",
     "EQUIPMENT_TECH_ONLY)"),
    ("B12", "backend", "Anyone can update", "AC2",
     ROUTES, "_equipment_event(event_id, is_tech_staff, EQUIPMENT_TECH_ONLY",
     "_equipment_event(event_id, lambda user, event: True, EQUIPMENT_TECH_ONLY"),
    ("B13", "backend", "The event's coordinator can update", "AC2",
     ROUTES, "_equipment_event(event_id, is_tech_staff, EQUIPMENT_TECH_ONLY",
     "_equipment_event(event_id, can_view_equipment, EQUIPMENT_TECH_ONLY"),
    ("B14", "backend", "A refusal names the event", "AC2",
     ROUTES, DENIED, "    if not allowed(user, event):\n"
                     "        raise _Rejected(denied, 403, event=event.title)"),
    ("B15", "backend", "The requirement is looked up before the permission check", "AC2",
     ROUTES, "        user, event = _equipment_event(event_id, is_tech_staff, EQUIPMENT_TECH_ONLY,\n"
             "                                       hide_drafts=True)\n",
     "        _event_requirement(db.session.get(Event, event_id), requirement_id)\n"
     "        user, event = _equipment_event(event_id, is_tech_staff, EQUIPMENT_TECH_ONLY,\n"
     "                                       hide_drafts=True)\n"),
    # ---------- Backend: a failed save (AC3) ----------
    ("B16", "backend", "A failed save doesn't say the requirements are unchanged", "AC3",
     ROUTES, 'ARRANGEMENT_NOT_SAVED = ("The arrangement was not saved, and the recorded '
             'requirements are "\n                         "unchanged. Please try again.")',
     'ARRANGEMENT_NOT_SAVED = "The arrangement status was not saved. Please try again."'),
    ("B17", "backend", "A failed save is not retryable", "AC3",
     ROUTES, FAILED, "        return _error(ARRANGEMENT_NOT_SAVED, 503)"),
    ("B18", "backend", "A failed read or save is reported as \"not found\"", "AC3",
     ROUTES, FAILED, "        return _error(EVENT_NOT_FOUND, 404)"),

    # ---------- Frontend: who and when, and what is sent (AC1) ----------
    ("F1", "frontend", "Who updated the arrangement and when is not shown", "AC1",
     PAGE, "{requirement.arrangement_updated_by && requirement.arrangement_updated_at && (",
     "{false && ("),
    ("F2", "frontend", "The time is shown as raw UTC text", "AC1",
     PAGE, "on ${formatSavedAt(requirement.arrangement_updated_at)}",
     "on ${requirement.arrangement_updated_at}"),
    ("F3", "frontend", "The wrong person is named", "AC1",
     PAGE, "${requirement.arrangement_updated_by.email}", "${page.event.coordinator?.email}"),
    ("F4", "frontend", "The details shown are not sent with the update", "AC1",
     PAGE, "const body = { status, note, last_saved_at: requirement.last_saved_at };",
     "const body = { status, note };"),
    ("F5", "frontend", "A refusal for changed details doesn't show the new details", "AC1",
     PAGE, "      if (error.response?.data?.reload) load();\n", ""),
    # ---------- Frontend: refusals and failures (AC2, AC3) ----------
    ("F6", "frontend", "The requirement looks updated before the server agrees", "AC2, AC3",
     PAGE, "    startChange();\n    try {\n      // With the details shown",
     "    startChange();\n"
     "    setPage((p) => ({ ...p, requirements: p.requirements.map((r) => (r.id === requirement.id\n"
     "      ? { ...r, status, status_label: \"Being arranged\", arrangement_note: note } : r)) }));\n"
     "    try {\n      // With the details shown"),
    ("F7", "frontend", "A failed update shows no error", "AC2, AC3",
     PAGE, "      setFailure(explain(error, ARRANGEMENT_NOT_SAVED));\n", ""),
    ("F8", "frontend", "The server's explanation is ignored", "AC2, AC3",
     PAGE, "explain(error, ARRANGEMENT_NOT_SAVED)", "ARRANGEMENT_NOT_SAVED"),
    ("F9", "frontend", "With no reply, the page doesn't say the requirements are unchanged", "AC3",
     PAGE, '  "The arrangement was not saved, and the recorded requirements are unchanged. '
           'Check your connection and try again.";',
     '  "The arrangement status was not saved. Check your connection and try again.";'),
]
