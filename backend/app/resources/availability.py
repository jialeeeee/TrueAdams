"""SCRUM-43: whether an event's equipment requirements can be met from the catalogue.

Pure rules, independent of Flask and the database, so SCRUM-44 can reuse them when it
deducts reserved quantities. The caller passes only the unavailable periods that
overlap the event (found with scheduling.overlapping). Nothing here reserves anything.
"""

ENOUGH = "enough"
NOT_ENOUGH = "not_enough"
NONE_SUITABLE = "none_suitable"
RESULT_LABELS = {
    ENOUGH: "Enough available",
    NOT_ENOUGH: "Not enough available",
    NONE_SUITABLE: "No suitable equipment available",
}

# Why a suitable item is not counted.
UNAVAILABLE = "unavailable"
QUANTITY_NOT_RECORDED = "quantity_not_recorded"


def _key(text):
    return " ".join(text.split()).lower()


def is_suitable(resource, equipment_type):
    """An item suits a requirement when its category matches the requirement's equipment
    type, ignoring case and spacing (A2, open question Q1)."""
    return bool(resource.category) and _key(resource.category) == _key(equipment_type)


def _time(value):
    return value.strftime("%Y-%m-%d %H:%M")


def _unavailable_detail(periods):
    return "; ".join(
        f"Unavailable {_time(p.start_time)} to {_time(p.end_time)}: "
        f"{(p.reason or '').strip() or 'no reason recorded'}"
        for p in sorted(periods, key=lambda p: p.start_time))


def check(requirement, resources, unavailable):
    """One line of the check: the requirement, the suitable items counted, and the ones
    left out and why. `unavailable` maps an item's id to its overlapping periods."""
    suitable, excluded = [], []
    for resource in resources:
        if not is_suitable(resource, requirement.equipment_type):
            continue
        if unavailable.get(resource.id):
            # A recorded period makes the whole item unavailable (A5, open question Q4).
            excluded.append({"id": resource.id, "name": resource.name, "reason": UNAVAILABLE,
                             "detail": _unavailable_detail(unavailable[resource.id])})
        elif resource.quantity_available is None:
            # Not recorded is never counted as available (A4, open question Q3).
            excluded.append({"id": resource.id, "name": resource.name,
                             "reason": QUANTITY_NOT_RECORDED, "detail": "Quantity not recorded"})
        else:
            suitable.append({"id": resource.id, "name": resource.name,
                             "category": resource.category,
                             "quantity_available": resource.quantity_available})

    available = sum(item["quantity_available"] for item in suitable)
    if available == 0:
        result = NONE_SUITABLE
    elif available >= requirement.quantity:
        result = ENOUGH
    else:
        result = NOT_ENOUGH
    technical = requirement.technical_requirements
    return {
        "requirement_id": requirement.id,
        "equipment_type": requirement.equipment_type,
        "requested_quantity": requirement.quantity,
        "technical_requirements": technical,
        # Free text on both sides, so shown rather than matched (A3, open question Q2).
        "technical_note": (f"Technical Support must confirm the technical requirements: "
                           f"{technical}") if technical else None,
        "available_quantity": available,
        "result": result,
        "result_label": RESULT_LABELS[result],
        "suitable": suitable,
        "excluded": excluded,
    }


def summary(lines):
    if not lines:
        return None
    met = sum(1 for line in lines if line["result"] == ENOUGH)
    if met == len(lines):
        return "Every equipment requirement can be met from available equipment."
    return f"{met} of {len(lines)} equipment requirements can be met from available equipment."
