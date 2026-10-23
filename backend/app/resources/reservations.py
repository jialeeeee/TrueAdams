"""SCRUM-44: the rules for reserving equipment for one of an event's requirements.

Pure rules, independent of Flask and the database, like availability.py. The route
works out from the saved data what other overlapping events and this event have
reserved and passes it in. Reserving applies the same rules again, with the event,
requirement and equipment locked (A7).
"""

from ..events.equipment import EQUIPMENT_QUANTITY_MAX, describe
from .availability import is_suitable

# A reservation's status. Only reserved ones hold equipment; released ones are history.
RESERVED = "reserved"
RELEASED = "released"

# Where a requirement stands, with its label (A6).
CAN_RESERVE = "can_reserve"
FULLY_RESERVED = "fully_reserved"
NONE_AVAILABLE = "none_available"
STATE_LABELS = {
    CAN_RESERVE: "Equipment can be reserved",
    FULLY_RESERVED: "Fully reserved",
    NONE_AVAILABLE: "No suitable equipment is available to reserve",
}

# One item's quantity can be no more than one requirement can ask for (SCRUM-42 A5).
QUANTITY_MAX = EQUIPMENT_QUANTITY_MAX


def options(line, reserved_here):
    """The suitable items of an availability line (availability.check, with other events'
    reservations deducted), less what this event has already reserved of each for any
    of its requirements (A5). `reserved_here` maps an item's id to that quantity."""
    items = []
    for item in line["suitable"]:
        own = reserved_here.get(item["id"], 0)
        items.append({
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "quantity_available": item["quantity_available"],
            "reserved_for_other_events": item["reserved_for_other_events"],
            "reserved_for_this_event": own,
            "available_to_reserve": max(item["available_quantity"] - own, 0),
        })
    return items


def state(remaining, available):
    """Fully reserved once nothing more is needed; otherwise whether anything can be."""
    if remaining <= 0:
        return FULLY_RESERVED
    return NONE_AVAILABLE if available <= 0 else CAN_RESERVE


def _whole_number(value):
    # bool is an int in Python, but true is not a quantity or an id.
    return isinstance(value, int) and not isinstance(value, bool)


def parse_items(items):
    """The (item id, quantity) pairs chosen, in the order sent, and what is wrong with them."""
    if not isinstance(items, list) or not items:
        return [], ["Select at least one item of equipment and how many to reserve."]
    selection, problems = [], []
    for entry in items:
        entry = entry if isinstance(entry, dict) else {}
        resource_id, quantity = entry.get("resource_id"), entry.get("quantity")
        if not _whole_number(resource_id):
            problems.append("Each item must say which equipment to reserve.")
        elif not _whole_number(quantity) or not 1 <= quantity <= QUANTITY_MAX:
            problems.append(f"The quantity of each item must be a whole number from 1 to "
                            f"{QUANTITY_MAX}.")
        else:
            selection.append((resource_id, quantity))
    return selection, list(dict.fromkeys(problems))


def selection_problems(selection, resources, requirement, remaining):
    """What is wrong with the chosen items for this requirement: each must exist, suit it
    (A1) and be chosen once, and together they can't be more than it still needs (A6).
    `resources` maps the chosen ids that exist to their items."""
    problems, seen = [], set()
    name = describe(requirement.quantity, requirement.equipment_type)
    for resource_id, _ in selection:
        resource = resources.get(resource_id)
        if resource is None:
            problems.append(f"Equipment item {resource_id} was not found.")
        elif resource_id in seen:
            problems.append(f"{resource.name} is selected more than once.")
        elif not is_suitable(resource, requirement.equipment_type):
            problems.append(f"{resource.name} is not suitable for {name}: its category is "
                            f"{resource.category or 'not recorded'}.")
        seen.add(resource_id)
    if sum(quantity for _, quantity in selection) > remaining:
        held = requirement.quantity - remaining
        already = f" and {held} {'is' if held == 1 else 'are'} already reserved" if held else ""
        problems.append(f"Select no more than {remaining} in total: the requirement needs "
                        f"{requirement.quantity}{already}.")
    return list(dict.fromkeys(problems))


def shortfalls(selection, can_reserve, names):
    """The chosen items asked for beyond what can be reserved of them now (AC5).
    `can_reserve` maps an item's id to that quantity; items not in it have none."""
    return [{"resource_id": resource_id, "name": names[resource_id],
             "requested_quantity": quantity,
             "available_quantity": can_reserve.get(resource_id, 0)}
            for resource_id, quantity in selection if quantity > can_reserve.get(resource_id, 0)]


def not_enough_message(shortfalls):
    """Shows the staff member what is available instead (AC5)."""
    parts = []
    for item in shortfalls:
        available = item["available_quantity"]
        if available:
            verb = "is" if available == 1 else "are"
            parts.append(f"Only {available} × {item['name']} {verb} available for this event's "
                         f"period, not {item['requested_quantity']}.")
        else:
            parts.append(f"None of {item['name']} is available for this event's period.")
    return " ".join(parts + ["Nothing was reserved."])


def none_available_message(requirement):
    """AC6: there is no suitable equipment left to reserve for the requirement."""
    return (f"No suitable equipment is available for "
            f"{describe(requirement.quantity, requirement.equipment_type)} over this event's "
            "period, so it can't be reserved.")


def fully_reserved_message(requirement):
    return f"{describe(requirement.quantity, requirement.equipment_type)} is already fully reserved."


def describe_items(pairs):
    """(name, quantity) pairs as "2 × Shure SLX-D and 1 × Sennheiser EW-D"."""
    names = [describe(quantity, name) for name, quantity in pairs]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
