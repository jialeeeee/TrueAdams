"""SCRUM-42 mutations: ways recording equipment requirements could be broken.

Run with the SCRUM-77 runner, from the repo root:
    python docs/evidence/SCRUM-77/scripts/mutation_check.py docs/evidence/SCRUM-42/scripts/mutations.py backend|frontend
"""

ROUTES = "backend/app/events/routes.py"
RULES = "backend/app/events/equipment.py"
PERMISSIONS = "backend/app/events/permissions.py"
PAGE = "frontend/src/pages/EquipmentRequirementsPage.jsx"
REQUESTS_PAGE = "frontend/src/pages/EquipmentRequestsPage.jsx"
PLANNING_PAGE = "frontend/src/pages/EventPlanningPage.jsx"
STATUSES = "frontend/src/utils/arrangementStatuses.js"

BACKEND_TESTS = [
    "tests.test_equipment_requirements",
    "tests.test_authorization_http_unit",
]
FRONTEND_TESTS = [
    "src/pages/EquipmentRequirementsPage.test.jsx",
    "src/pages/EquipmentRequestsPage.test.jsx",
    "src/pages/EventPlanningPage.test.jsx",
]

RECORD_START = ('def record_equipment_requirement(event_id: int):\n'
                '    """Record one requirement. It reserves nothing and changes no availability (AC5)."""\n'
                '    try:\n'
                '        user, event = _equipment_event(event_id, ')

MUTATIONS = [
    # ---------- Backend ----------
    ("B1", "backend", "Let any coordinator record, not only the event's", "AC1",
     ROUTES, RECORD_START + "_is_current_coordinator,",
     RECORD_START + "lambda u, e: u.role == COORDINATOR_ROLE,"),
    ("B2", "backend", "Record requirements for cancelled and rejected events", "AC1",
     ROUTES,
     '_require_equipment_open(event)\n'
     '        values = _valid_requirement(event, _equipment_body("equipment requirement"))',
     'values = _valid_requirement(event, _equipment_body("equipment requirement"))'),
    ("B3", "backend", "Accept a blank equipment type", "AC2",
     RULES, 'elif not _collapse(equipment_type or ""):', "elif equipment_type is None:"),
    ("B4", "backend", "Accept a quantity of 0 or above the maximum", "AC2",
     RULES, "or not 1 <= quantity <= EQUIPMENT_QUANTITY_MAX):", "or quantity < 0):"),
    ("B5", "backend", "Allow the same requirement to be recorded twice", "AC2",
     ROUTES, "        if any(equipment.requirement_key(", "        if False and any(equipment.requirement_key("),
    ("B6", "backend", "Name only the first invalid field", "AC2",
     ROUTES,
     "raise _Rejected(EQUIPMENT_INVALID, 422, fields=problems)\n    return values",
     "raise _Rejected(EQUIPMENT_INVALID, 422, fields=dict(list(problems.items())[:1]))\n"
     "    return values"),
    ("B7", "backend", "Show other events' requirements with this event's", "AC3",
     ROUTES, "requirements = (EquipmentRequirement.query.filter_by(event_id=event.id)",
     "requirements = (EquipmentRequirement.query.filter(EquipmentRequirement.id > 0)"),
    ("B8", "backend", "Leave out the organiser's equipment note", "AC3",
     ROUTES, '"organiser_note": _recorded(event.equipment_requirements),',
     '"organiser_note": None,'),
    ("B9", "backend", "Technical Support Staff can't view requirements", "AC4",
     PERMISSIONS, "return is_current_coordinator(user, event) or is_tech_staff(user)",
     "return is_current_coordinator(user, event)"),
    ("B10", "backend", "Anyone can update an arrangement", "AC4",
     ROUTES, "_equipment_event(event_id, is_tech_staff, EQUIPMENT_TECH_ONLY)",
     "_equipment_event(event_id, lambda u, e: True, EQUIPMENT_TECH_ONLY)"),
    ("B11", "backend", "An arrangement update isn't saved", "AC4",
     ROUTES,
     "        for name, value in values.items():\n"
     "            setattr(requirement, name, value)\n"
     "        requirement.arrangement_updated_by_id = user.id",
     "        requirement.arrangement_updated_by_id = user.id"),
    ("B12", "backend", "Editing the details keeps the old arrangement status", "AC4 (A8)",
     ROUTES,
     "            requirement.status = equipment.REQUESTED\n"
     "            requirement.arrangement_note = None",
     "            requirement.arrangement_note = None"),
    ("B13", "backend", "Technical Support can mark a requirement reserved", "AC4, AC6",
     RULES, '    "unavailable": "Suitable equipment unavailable",\n}',
     '    "unavailable": "Suitable equipment unavailable",\n    "reserved": "Reserved",\n}'),
    ("B14", "backend", "Recording reduces the equipment's available quantity", "AC5",
     ROUTES, "        db.session.add(requirement)\n        db.session.flush()",
     "        from ..models import Resource\n"
     "        Resource.query.filter(func.lower(Resource.category) == values['equipment_type'].lower())"
     ".update({Resource.quantity_available: Resource.quantity_available - values['quantity']},"
     " synchronize_session=False)\n"
     "        db.session.add(requirement)\n        db.session.flush()"),
    ("B15", "backend", "A recorded requirement is shown as reserved", "AC5, AC6",
     ROUTES, "status=equipment.REQUESTED, **values)", 'status="reserved", **values)'),
    ("B16", "backend", "Marking a requirement unavailable removes it", "AC6",
     ROUTES,
     "        requirement.arrangement_updated_at = datetime.utcnow()\n"
     "        requirement_id = requirement.id",
     "        requirement.arrangement_updated_at = datetime.utcnow()\n"
     "        if requirement.status == 'unavailable':\n"
     "            db.session.delete(requirement)\n"
     "        requirement_id = requirement.id"),
    ("B17", "backend", "A failed save is not rolled back", "AC7",
     ROUTES,
     "        db.session.rollback()\n"
     "        return _error(EQUIPMENT_NOT_SAVED, 503, retryable=True)\n\n"
     "    return _saved_reply(user, event, message, requirement_id, 201)",
     "        return _error(EQUIPMENT_NOT_SAVED, 503, retryable=True)\n\n"
     "    return _saved_reply(user, event, message, requirement_id, 201)"),
    ("B18", "backend", "A failed load is shown as an empty list", "AC7",
     ROUTES,
     'return _error("The equipment requirements could not be loaded. Please try again.", 503,\n'
     "                      retryable=True)",
     'return jsonify({"requirements": [], "message": NO_EQUIPMENT_REQUIREMENTS})'),
    # Added after the review of PR #47.
    ("B19", "backend", "A failure after saving is reported as a failed save", "AC7",
     ROUTES,
     '        return jsonify({"confirmation": confirmation, "saved": True,\n'
     '                        "refresh_error": EQUIPMENT_SAVED_NOT_RELOADED}), status_code',
     "        return _error(EQUIPMENT_NOT_SAVED, 503, retryable=True)"),
    ("B20", "backend", "Editing keeps Technical Support's old note and who updated it", "AC4 (A8)",
     ROUTES,
     "            requirement.arrangement_note = None\n"
     "            requirement.arrangement_updated_by_id = None\n"
     "            requirement.arrangement_updated_at = None\n",
     ""),

    # ---------- Frontend ----------
    ("F1", "frontend", "The planning page has no Equipment requirements link", "AC1",
     PLANNING_PAGE, "<Link to={`/events/${event.id}/equipment`}>Equipment requirements</Link>",
     "{null}"),
    ("F2", "frontend", "Cancelled and rejected events still show the record form", "AC1",
     PAGE, "{page.can_edit && (\n        <RequirementForm", "{true && (\n        <RequirementForm"),
    ("F3", "frontend", "Invalid fields are not named next to the field", "AC2",
     PAGE, "fieldErrors[name] && <p id={`${name}-error`}>{fieldErrors[name]}</p>;", "false;"),
    ("F4", "frontend", "What was entered is cleared when a save fails", "AC2, AC7",
     PAGE, "setFailure(explain(error, NOT_SAVED));",
     "setFailure(explain(error, NOT_SAVED));\n      resetForm();"),
    ("F5", "frontend", "The quantity is sent as text", "AC1",
     PAGE, 'quantity: form.quantity.trim() === "" ? null : Number(form.quantity),',
     "quantity: form.quantity,"),
    ("F6", "frontend", "The recorded requirements are not listed", "AC3",
     PAGE, "{page.requirements.length > 0 ? (", "{false ? ("),
    ("F7", "frontend", "The confirmation is not shown", "AC3, AC5",
     PAGE, "setConfirmation(response.data.confirmation);", 'setConfirmation("");'),
    ("F8", "frontend", "Technical Support Staff get no status controls", "AC4",
     PAGE, "{page.can_update_arrangements && (\n        // Keyed",
     "{false && (\n        // Keyed"),
    ("F9", "frontend", "Technical Support are offered a Reserved status", "AC4, AC6",
     STATUSES, '  ["unavailable", "Suitable equipment unavailable"],\n];',
     '  ["unavailable", "Suitable equipment unavailable"],\n  ["reserved", "Reserved"],\n];'),
    ("F10", "frontend", "Equipment requests link to the planning page instead", "AC4",
     REQUESTS_PAGE, "<Link to={`/events/${event.id}/equipment`}>{event.title}</Link>",
     "<Link to={`/events/${event.id}/planning`}>{event.title}</Link>"),
    ("F11", "frontend", "A failed load offers no Retry", "AC7",
     PAGE, "setLoadError({ message: explain(error, NOT_LOADED), retryable: canRetry(error) });",
     "setLoadError({ message: explain(error, NOT_LOADED), retryable: false });"),
    # Added after the review of PR #47.
    ("F12", "frontend", "Pages for different events share their state", "AC3",
     PAGE, "return <EventEquipment key={eventId} eventId={eventId} />;",
     "return <EventEquipment eventId={eventId} />;"),
    ("F13", "frontend", "An older load can replace a newer list", "AC3",
     PAGE, "if (attempt === latest.current) setPage(response.data);", "setPage(response.data);"),
    ("F14", "frontend", "A change saved without its list coming back is not reloaded", "AC7",
     PAGE, "      load();\n      return;", "      return;"),
]
