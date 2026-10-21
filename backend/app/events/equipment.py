"""SCRUM-42: what makes an equipment requirement valid, and its arrangement statuses.

Pure rules, independent of Flask and the database. Each parser returns the cleaned
values and a dict of problems by field, so every invalid field is named at once.
"""

EQUIPMENT_TYPE_MAX_LENGTH = 100  # The database column limit.
# The largest quantity one requirement may ask for (A5, open question Q3).
EQUIPMENT_QUANTITY_MAX = 1000
TECHNICAL_REQUIREMENTS_MAX_LENGTH = 1000
ARRANGEMENT_NOTE_MAX_LENGTH = 1000

REQUESTED = "requested"
# What Technical Support Staff can say about a requirement, in display order, with
# its label (A7, open question Q6). None says reserved or fulfilled: reserving is
# SCRUM-44. Must match ARRANGEMENT_STATUSES in
# frontend/src/pages/EquipmentRequirementsPage.jsx.
ARRANGEMENT_STATUSES = {
    REQUESTED: "Requested",
    "being_arranged": "Being arranged",
    "unavailable": "Suitable equipment unavailable",
}


def _collapse(text):
    return " ".join(text.split())


def describe(quantity, equipment_type):
    """How a requirement is named in messages, e.g. "2 × Wireless microphone"."""
    return f"{quantity} × {equipment_type}"


def status_label(status):
    return ARRANGEMENT_STATUSES.get(status, status)


def requirement_key(equipment_type, technical_requirements):
    """Two requirements with the same key are the same requirement (A5): the same type
    and technical requirements, ignoring case and spacing."""
    return (_collapse(equipment_type).lower(), _collapse(technical_requirements or "").lower())


def _optional_text(value, label, max_length):
    if value is not None and not isinstance(value, str):
        return None, f"{label} must be text."
    text = (value or "").strip()
    if len(text) > max_length:
        return None, f"{label} must be {max_length} characters or fewer."
    return text or None, None  # Blank means none recorded.


def parse_requirement(body):
    """The equipment type, quantity and technical requirements from a request body."""
    values, problems = {}, {}

    equipment_type = body.get("equipment_type")
    if equipment_type is not None and not isinstance(equipment_type, str):
        problems["equipment_type"] = "Equipment type must be text."
    elif not _collapse(equipment_type or ""):
        problems["equipment_type"] = "Enter the equipment type."
    elif len(_collapse(equipment_type)) > EQUIPMENT_TYPE_MAX_LENGTH:
        problems["equipment_type"] = (
            f"Equipment type must be {EQUIPMENT_TYPE_MAX_LENGTH} characters or fewer.")
    else:
        values["equipment_type"] = _collapse(equipment_type)

    quantity = body.get("quantity")
    # bool is an int in Python, but true is not a quantity.
    if (isinstance(quantity, bool) or not isinstance(quantity, int)
            or not 1 <= quantity <= EQUIPMENT_QUANTITY_MAX):
        problems["quantity"] = (
            f"Quantity must be a whole number from 1 to {EQUIPMENT_QUANTITY_MAX}.")
    else:
        values["quantity"] = quantity

    technical, problem = _optional_text(body.get("technical_requirements"),
                                        "Technical requirements",
                                        TECHNICAL_REQUIREMENTS_MAX_LENGTH)
    if problem:
        problems["technical_requirements"] = problem
    else:
        values["technical_requirements"] = technical

    return values, problems


def parse_arrangement(body):
    """Technical Support's arrangement status and, if sent, their note (null clears it)."""
    values, problems = {}, {}

    status = body.get("status")
    if not isinstance(status, str) or status not in ARRANGEMENT_STATUSES:
        labels = list(ARRANGEMENT_STATUSES.values())
        problems["status"] = f"Choose {', '.join(labels[:-1])} or {labels[-1]}."
    else:
        values["status"] = status

    if "note" in body:
        note, problem = _optional_text(body["note"], "Note", ARRANGEMENT_NOTE_MAX_LENGTH)
        if problem:
            problems["note"] = problem
        else:
            values["arrangement_note"] = note

    return values, problems
