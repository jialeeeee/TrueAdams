"""SCRUM-43 mutations: ways the equipment availability check could be broken.

Run with the SCRUM-77 runner, from the repo root:
    python docs/evidence/SCRUM-77/scripts/mutation_check.py docs/evidence/SCRUM-43/scripts/mutations.py backend|frontend
"""

ROUTES = "backend/app/events/routes.py"
RULES = "backend/app/resources/availability.py"
PAGE = "frontend/src/pages/EquipmentAvailabilityPage.jsx"
REQUIREMENTS_PAGE = "frontend/src/pages/EquipmentRequirementsPage.jsx"

BACKEND_TESTS = [
    "tests.test_equipment_availability",
    "tests.test_equipment_availability_unit",
]
FRONTEND_TESTS = [
    "src/pages/EquipmentAvailabilityPage.test.jsx",
    "src/pages/EquipmentRequirementsPage.test.jsx",
]

CHECK_LINK = "<Link to={`/events/${event.id}/equipment-availability`}>Check availability</Link>"

MUTATIONS = [
    # ---------- Backend ----------
    ("B1", "backend", "Check only the first requirement", "AC1",
     ROUTES, "checks = availability.check_all(requirements, resources, unavailable)",
     "checks = availability.check_all(requirements[:1], resources, unavailable)"),
    ("B2", "backend", "Match categories exactly, so case and spacing matter", "AC1 (A2)",
     RULES, "return bool(resource.category) and _key(resource.category) == _key(equipment_type)",
     "return bool(resource.category) and resource.category == equipment_type"),
    ("B3", "backend", "Count only the first suitable item's quantity", "AC2",
     RULES, 'available = sum(item["quantity_available"] for item in suitable)',
     'available = suitable[0]["quantity_available"] if suitable else 0'),
    ("B4", "backend", "Exactly the requested quantity is not enough", "AC2",
     RULES, "if available < requested:", "if available <= requested:"),
    ("B5", "backend", "Equipment with no quantity recorded is silently left out", "AC2 (A4)",
     RULES, '"reason": QUANTITY_NOT_RECORDED, "detail": "Quantity not recorded"})',
     '"reason": QUANTITY_NOT_RECORDED, "detail": "Quantity not recorded"}) if False else None'),
    ("B6", "backend", "Unavailable equipment is still counted", "AC3",
     RULES, "if unavailable.get(resource.id):", "if False:"),
    ("B7", "backend", "Any recorded unavailability excludes, whatever its period", "AC1, AC3",
     ROUTES, "EquipmentUnavailability, event.start_time, event.end_time).all()",
     "EquipmentUnavailability, datetime.min, datetime.max).all()"),
    ("B8", "backend", "An exclusion doesn't say why", "AC3",
     RULES, "f\"{(p.reason or '').strip() or 'no reason recorded'}\"", '"see the equipment record"'),
    ("B9", "backend", "Checking takes one of each suitable item out of stock", "AC4",
     ROUTES, "checks = availability.check_all(requirements, resources, unavailable)",
     "checks = availability.check_all(requirements, resources, unavailable)\n"
     "        Resource.query.filter(Resource.id.in_(suitable_ids or [0])).update("
     "{Resource.quantity_available: Resource.quantity_available - 1}, synchronize_session=False)\n"
     "        db.session.commit()"),
    ("B10", "backend", "A requirement that can be met is labelled reserved", "AC4",
     RULES, 'ENOUGH: "Enough available",', 'ENOUGH: "Reserved",'),
    ("B11", "backend", "Missing times are not reported; the check runs anyway", "AC5",
     ROUTES, "        _missing_times(event)\n\n        requirements =", "        requirements ="),
    ("B12", "backend", "A failed check is shown as an empty result", "AC5",
     ROUTES, "return _error(CHECK_NOT_COMPLETED, 503, retryable=True)",
     'return jsonify({"checks": [], "message": NO_EQUIPMENT_REQUIREMENTS})'),
    ("B13", "backend", "Anyone can run the check", "AC5 (A9)",
     ROUTES, "_equipment_event(event_id, is_tech_staff, EQUIPMENT_CHECK_TECH_ONLY)",
     "_equipment_event(event_id, lambda u, e: True, EQUIPMENT_CHECK_TECH_ONLY)"),
    ("B14", "backend", "Cancelled and rejected events are checked", "AC5 (A10)",
     ROUTES, "if event.status in EQUIPMENT_CLOSED_STATUSES:\n"
             '            raise _Rejected(f"This event is {event.status}, so there is no equipment',
     "if False:\n"
     '            raise _Rejected(f"This event is {event.status}, so there is no equipment'),
    # Added after the review of PR #48.
    ("B15", "backend", "Requirements for the same equipment each count all of it", "AC1, AC2 (A11)",
     ROUTES, "checks = availability.check_all(requirements, resources, unavailable)",
     "checks = [availability.check(q, resources, unavailable) for q in requirements]"),
    ("B16", "backend", "Enough by category is reported as plain enough", "AC1, AC2 (A3)",
     RULES, "return ENOUGH_BY_CATEGORY if technical else ENOUGH", "return ENOUGH"),
    ("B17", "backend", "Shared stock is judged against each requirement's own quantity", "AC2 (A11)",
     RULES, 'result = _result(line["available_quantity"], total, requirement.technical_requirements)',
     'result = _result(line["available_quantity"], requirement.quantity,'
     ' requirement.technical_requirements)'),

    # ---------- Frontend ----------
    ("F1", "frontend", "Technical Support get no link to the check", "AC1",
     REQUIREMENTS_PAGE, CHECK_LINK, "<span />"),
    ("F2", "frontend", "The coordinator is offered the check too", "AC1 (A9)",
     REQUIREMENTS_PAGE, "{page.can_update_arrangements && (\n        <Link",
     "{true && (\n        <Link"),
    ("F3", "frontend", "The available quantity is not shown", "AC2",
     PAGE, "`Requested: ${line.requested_quantity} · Available: ${line.available_quantity}`",
     "`Requested: ${line.requested_quantity}`"),
    ("F4", "frontend", "Whether there is enough is not shown", "AC2",
     PAGE, "<p>{line.result_label}</p>", ""),
    ("F5", "frontend", "The technical requirements note is not shown", "AC1",
     PAGE, "{line.technical_note && <p>{line.technical_note}</p>}", ""),
    ("F6", "frontend", "Excluded equipment is not listed", "AC3",
     PAGE, "{line.excluded.map((item) => (", "{[].map((item) => ("),
    ("F7", "frontend", "The page doesn't say checking reserves nothing", "AC4",
     PAGE, "<p>{result.notice}</p>", ""),
    ("F8", "frontend", "An error is not announced as an alert", "AC5",
     PAGE, '<p role="alert">{failure.message}</p>', "<p>{failure.message}</p>"),
    ("F9", "frontend", "A failed check offers no Retry", "AC5",
     PAGE, '{failure.retryable && <button type="button" onClick={load}>Retry</button>}', ""),
    # Added with the stale-result fix carried over from the review of PR #47.
    ("F10", "frontend", "Pages for different events share their result", "AC1, AC2",
     PAGE, "return <EventAvailability key={eventId} eventId={eventId} />;",
     "return <EventAvailability eventId={eventId} />;"),
    # Added after the review of PR #48.
    ("F11", "frontend", "The shared-stock note is not shown", "AC2 (A11)",
     PAGE, "{line.shared_note && <p>{line.shared_note}</p>}", ""),
]
