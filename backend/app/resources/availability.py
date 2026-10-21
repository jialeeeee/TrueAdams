"""SCRUM-43: whether an event's equipment requirements can be met from the catalogue.

Pure rules, independent of Flask and the database, so SCRUM-44 can reuse them when it
deducts reserved quantities. The caller passes only the unavailable periods that
overlap the event (found with scheduling.overlapping). Nothing here reserves anything.
"""

ENOUGH = "enough"
# Enough by category, but the requirement has technical requirements that only Technical
# Support can check, so it is not reported as enough (A3, review of PR #48).
ENOUGH_BY_CATEGORY = "enough_by_category"
NOT_ENOUGH = "not_enough"
NONE_SUITABLE = "none_suitable"
RESULT_LABELS = {
    ENOUGH: "Enough available",
    ENOUGH_BY_CATEGORY: "Enough by category; technical requirements still to be checked",
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


def _result(available, requested, technical):
    if available == 0:
        return NONE_SUITABLE
    if available < requested:
        return NOT_ENOUGH
    return ENOUGH_BY_CATEGORY if technical else ENOUGH


def _describe(requirement):
    name = f"{requirement.quantity} × {requirement.equipment_type}"
    technical = requirement.technical_requirements
    return f"{name} ({technical})" if technical else name


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
    technical = requirement.technical_requirements
    result = _result(available, requirement.quantity, technical)
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
        # Other requirements of the event drawing on the same equipment (see check_all).
        "shared_with": [],
        "shared_requested_quantity": requirement.quantity,
        "shared_note": None,
    }


def check_all(requirements, resources, unavailable):
    """Every requirement's line. Requirements for the same equipment draw on one stock, so
    together they can't count the same items twice: if they need more than there is, none
    of them is enough. No requirement is given priority over another (A11, open question
    Q8; review of PR #48)."""
    lines = [check(requirement, resources, unavailable) for requirement in requirements]
    pools = {}
    for requirement, line in zip(requirements, lines):
        pools.setdefault(_key(requirement.equipment_type), []).append((requirement, line))
    for members in pools.values():
        if len(members) < 2:
            continue
        total = sum(requirement.quantity for requirement, _ in members)
        for requirement, line in members:
            others = [other for other, _ in members if other is not requirement]
            line["shared_with"] = [other.id for other in others]
            line["shared_requested_quantity"] = total
            line["shared_note"] = (
                f"Shared with {', '.join(_describe(other) for other in others)}: together "
                f"{total} requested, {line['available_quantity']} available.")
            result = _result(line["available_quantity"], total, requirement.technical_requirements)
            line["result"], line["result_label"] = result, RESULT_LABELS[result]
    return lines


def summary(lines):
    if not lines:
        return None
    met = sum(1 for line in lines if line["result"] == ENOUGH)
    if met == len(lines):
        return "Every equipment requirement can be met from available equipment."
    text = f"{met} of {len(lines)} equipment requirements can be met from available equipment."
    unchecked = sum(1 for line in lines if line["result"] == ENOUGH_BY_CATEGORY)
    if unchecked:
        has, its = ("has", "its") if unchecked == 1 else ("have", "their")
        text += (f" {unchecked} more {has} enough by category, but {its} technical "
                 "requirements are still to be checked.")
    return text
