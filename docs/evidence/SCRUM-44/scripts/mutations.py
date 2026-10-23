"""SCRUM-44 mutations: ways reserving equipment could be broken.

Run with the SCRUM-77 runner, from the repo root:
    python docs/evidence/SCRUM-77/scripts/mutation_check.py docs/evidence/SCRUM-44/scripts/mutations.py backend|frontend
"""

ROUTES = "backend/app/events/routes.py"
RULES = "backend/app/resources/availability.py"
RESERVING = "backend/app/resources/reservations.py"
RELEASE = "backend/app/resources/release.py"
PAGE = "frontend/src/pages/EquipmentReservationPage.jsx"
AVAILABILITY_PAGE = "frontend/src/pages/EquipmentAvailabilityPage.jsx"
REQUIREMENTS_PAGE = "frontend/src/pages/EquipmentRequirementsPage.jsx"

# SCRUM-42 and SCRUM-43 too: reserving changes the check, and editing a requirement releases.
BACKEND_TESTS = [
    "tests.test_equipment_reservation",
    "tests.test_equipment_reservation_unit",
    "tests.test_equipment_availability",
    "tests.test_equipment_availability_unit",
    "tests.test_equipment_requirements",
]
FRONTEND_TESTS = [
    "src/pages/EquipmentReservationPage.test.jsx",
    "src/pages/EquipmentAvailabilityPage.test.jsx",
    "src/pages/EquipmentRequirementsPage.test.jsx",
]

MUTATIONS = [
    # ---------- Backend: what can be reserved (AC2, AC4) ----------
    ("B1", "backend", "Other events' reservations are not deducted", "AC4",
     RULES, "taken = reserved.get(resource.id, 0)", "taken = 0"),
    ("B2", "backend", "An event's own reservations count against it", "AC4 (A11)",
     ROUTES, "EquipmentReservation.event_id != event.id))", "EquipmentReservation.event_id != -1))"),
    ("B3", "backend", "Released reservations still hold equipment", "AC9",
     ROUTES, "EquipmentReservation.status == reserving.RESERVED,\n                     EquipmentReservation.event_id",
     "EquipmentReservation.event_id"),
    ("B4", "backend", "Reservations count whatever their period, so touching ones overlap", "AC4 (A5)",
     ROUTES, "rows = (overlapping(query, EquipmentReservation, event.start_time, event.end_time)\n",
     "rows = (query\n"),
    ("B5", "backend", "What the event already reserved is not taken off what it can still reserve", "AC2, AC4",
     RESERVING, 'own = reserved_here.get(item["id"], 0)', "own = 0"),
    ("B6", "backend", "The availability check ignores reservations", "AC4 (A11)",
     ROUTES, "checks = availability.check_all(requirements, resources, unavailable, reserved)",
     "checks = availability.check_all(requirements, resources, unavailable)"),
    # ---------- Backend: reserving (AC2, AC3, AC5, AC6) ----------
    ("B7", "backend", "Availability is not checked again: other events' new reservations are missed", "AC2",
     ROUTES, "                                  _reserved_by_other_events(event, suitable_ids))",
     "                                  {})"),
    ("B8", "backend", "The chosen equipment is not locked before checking", "AC2 (A7)",
     ROUTES, ".with_for_update().populate_existing().all()) if suitable_ids else []",
     ".populate_existing().all()) if suitable_ids else []"),
    ("B9", "backend", "Unsuitable equipment can be reserved", "AC2 (A1)",
     RESERVING, "elif not is_suitable(resource, requirement.equipment_type):", "elif False:"),
    ("B10", "backend", "The same item can be chosen twice", "AC2",
     RESERVING, "elif resource_id in seen:", "elif False:"),
    ("B11", "backend", "A quantity of 0 is accepted", "AC2",
     RESERVING, "not 1 <= quantity <= QUANTITY_MAX", "not 0 <= quantity <= QUANTITY_MAX"),
    ("B12", "backend", "A requirement can get more than it needs", "AC2 (A6)",
     RESERVING, "if sum(quantity for _, quantity in selection) > remaining:", "if False:"),
    ("B13", "backend", "A fully reserved requirement is not refused as such", "AC2 (A6)",
     ROUTES, "if remaining <= 0:\n            raise _Rejected(reserving.fully_reserved_message",
     "if False:\n            raise _Rejected(reserving.fully_reserved_message"),
    ("B14", "backend", "The reservation period is not the event's", "AC3 (A2)",
     ROUTES, "start_time=event.start_time, end_time=event.end_time,\n                                     status=reserving.RESERVED",
     "start_time=event.start_time, end_time=event.start_time + timedelta(hours=1),\n                                     status=reserving.RESERVED"),
    ("B15", "backend", "The confirmation leaves out the period", "AC3",
     ROUTES, 'confirmation = f"Reserved {what} for {needed} at {title}, {period}."',
     'confirmation = f"Reserved {what} for {needed} at {title}."'),
    ("B16", "backend", "More than available can be reserved", "AC5",
     ROUTES, "if shortfalls:\n            raise _Rejected(reserving.not_enough_message",
     "if False:\n            raise _Rejected(reserving.not_enough_message"),
    ("B17", "backend", "The refusal doesn't give the available quantity", "AC5",
     ROUTES, "available_quantity=available, shortfalls=shortfalls)", "retry=False)"),
    ("B18", "backend", "Reserving goes on when no suitable equipment is available", "AC6",
     ROUTES, "if available == 0:\n            raise _Rejected(reserving.none_available_message",
     "if False:\n            raise _Rejected(reserving.none_available_message"),
    # ---------- Backend: failed saves and notifications (AC7, AC8) ----------
    ("B19", "backend", "A failed save is reported as saved", "AC7",
     ROUTES, "return _error(EQUIPMENT_NOT_RESERVED, 503, retryable=True)",
     'return jsonify({"confirmation": "Reserved.", "saved": True}), 201'),
    ("B20", "backend", "The email is queued before the reservation is saved", "AC7 (A9)",
     ROUTES, "        db.session.flush()  # The ids, read before the commit expires them.\n        reservation_ids",
     "        _queue_reservation_email(coordinator.email, title, message, event_id)\n"
     "        db.session.flush()  # The ids, read before the commit expires them.\n        reservation_ids"),
    ("B21", "backend", "The coordinator gets no in-app notification", "AC8",
     ROUTES, "if coordinator:\n            db.session.add(Notification(recipient_id=coordinator.id,\n"
             "                                        kind=EQUIPMENT_RESERVED_NOTIFICATION,",
     "if False:\n            db.session.add(Notification(recipient_id=coordinator.id,\n"
     "                                        kind=EQUIPMENT_RESERVED_NOTIFICATION,"),
    ("B22", "backend", "The coordinator gets no email", "AC8",
     ROUTES, "email_queued = (_queue_reservation_email(to_address, title, message, event_id)\n"
             "                    if to_address else False)", "email_queued = False"),
    # ---------- Backend: releasing (AC9) ----------
    ("B23", "backend", "Cancelling an event doesn't release its reservations", "AC9",
     RELEASE, "if status in RELEASING_EVENT_STATUSES:", "if False:"),
    ("B24", "backend", "Changing a requirement doesn't release its reservations", "AC9",
     RELEASE, "elif isinstance(obj, EquipmentRequirement) and _changed(obj, REQUIREMENT_FIELDS):",
     "elif False:"),
    ("B25", "backend", "Removing a requirement doesn't release its reservations", "AC9",
     RELEASE, "if isinstance(obj, EquipmentRequirement):\n                _release",
     "if False:\n                _release"),
    ("B26", "backend", "Changing the event's times doesn't release its reservations", "AC9 (A10)",
     RELEASE, "if _changed(obj, EVENT_PERIOD_FIELDS):", "if False:"),
    ("B27", "backend", "Any change to an event releases its reservations", "AC9 (A10)",
     RELEASE, "return any(inspect(obj).attrs[name].history.added for name in names)", "return True"),
    ("B28", "backend", "A release doesn't record when", "AC9 (A10)",
     RELEASE, "        reservation.released_at = now\n", ""),
    ("B29", "backend", "The SCRUM-42 edit doesn't say the reservation was released", "AC9",
     ROUTES, "if releases:\n            message +=", "if False:\n            message +="),
    # ---------- Backend: who and which events (A3, A4) ----------
    ("B30", "backend", "Anyone may reserve", "AC2 (A3)",
     ROUTES, "_equipment_event(event_id, is_tech_staff, RESERVE_TECH_ONLY)",
     "_equipment_event(event_id, lambda user, event: True, RESERVE_TECH_ONLY)"),
    ("B31", "backend", "Anyone may view the reservations", "AC1 (A3)",
     ROUTES, "_equipment_event(event_id, can_view_equipment, RESERVATIONS_VIEW_DENIED)",
     "_equipment_event(event_id, lambda user, event: True, RESERVATIONS_VIEW_DENIED)"),
    ("B32", "backend", "The coordinator is offered reserving", "AC1 (A3)",
     ROUTES, '"can_reserve": is_tech_staff(user) and notice is None,', '"can_reserve": notice is None,'),
    ("B33", "backend", "Events that aren't approved can be reserved for", "AC1 (A4)",
     ROUTES, "if refusal:\n            raise _Rejected(refusal, 409)", "if False:\n            raise _Rejected(refusal, 409)"),
    ("B34", "backend", "A failed load is shown as an empty page", "AC1",
     ROUTES, "return _error(RESERVATIONS_NOT_LOADED, 503, retryable=True)",
     'return jsonify({"requirements": [], "released": []})'),

    # ---------- Frontend ----------
    ("F1", "frontend", "No form to reserve with", "AC2",
     PAGE, "{reservable && (", "{false && ("),
    ("F2", "frontend", "A form is offered when nothing can be reserved", "AC6",
     PAGE, 'const reservable = canReserve && requirement.state === "can_reserve";',
     "const reservable = canReserve;"),
    ("F3", "frontend", "The coordinator is offered the form", "AC1 (A3)",
     PAGE, 'const reservable = canReserve && requirement.state === "can_reserve";',
     'const reservable = requirement.state === "can_reserve";'),
    ("F4", "frontend", "Every item is sent, with or without a quantity", "AC2",
     PAGE, '.filter((option) => (chosen[option.id] ?? "").trim() !== "" && Number(chosen[option.id]) !== 0)',
     ".filter(() => true)"),
    ("F5", "frontend", "The reservation period is not shown", "AC1",
     PAGE, "{period && (", "{false && ("),
    ("F6", "frontend", "How much is reserved is not shown", "AC3",
     PAGE, "`Reserved: ${requirement.reserved_quantity} of ${requirement.quantity}`",
     "`Reserved: ${requirement.quantity}`"),
    ("F7", "frontend", "Other events' reservations are not explained", "AC4",
     PAGE, "if (option.reserved_for_other_events) held.push(", "if (false) held.push("),
    ("F8", "frontend", "The confirmation is not shown", "AC3",
     PAGE, '{confirmation && <p role="status">{confirmation}</p>}', ""),
    ("F9", "frontend", "A refusal is not shown", "AC5, AC7",
     PAGE, '{failure && <p role="alert">{failure}</p>}', ""),
    ("F10", "frontend", "The selection is cleared after a failed save", "AC7",
     PAGE, "      setFailures((all) => ({ ...all, [requirement.id]: explain(error, NOT_RESERVED) }));\n",
     "      setFailures((all) => ({ ...all, [requirement.id]: explain(error, NOT_RESERVED) }));\n"
     "      setQuantities((all) => ({ ...all, [requirement.id]: {} }));\n"),
    ("F11", "frontend", "Released reservations are not listed", "AC9",
     PAGE, "{page.released.length > 0 && (", "{false && ("),
    ("F12", "frontend", "A page for the previous event can show under the next", "AC1",
     PAGE, "return <EventReservations key={eventId} eventId={eventId} />;",
     "return <EventReservations eventId={eventId} />;"),
    ("F13", "frontend", "The availability check hides other events' reservations", "AC4",
     AVAILABILITY_PAGE, "const countedItem = (item) => (item.reserved_for_other_events",
     "const countedItem = (item) => (false"),
    ("F14", "frontend", "Technical Support and the coordinator get the same link", "AC1",
     REQUIREMENTS_PAGE, '{page.can_update_arrangements ? "Reserve equipment" : "Reserved equipment"}',
     '"Reserve equipment"'),
]
