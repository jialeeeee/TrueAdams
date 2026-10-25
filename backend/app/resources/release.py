"""SCRUM-44 A10: release equipment reservations when what they were for changes (AC9).

A rule applied whenever such a change is saved, by any screen or code path: there is no
"cancel event" feature yet, and accepted change requests (SCRUM-46) will come later.
Before every flush, an event's reservations are released when it becomes cancelled or
rejected or its start or end time changes, and a requirement's when its type, quantity
or technical requirements change or it is removed. A released reservation keeps its row,
with when and why, and no longer holds any equipment.
"""

from datetime import datetime

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from ..models import EquipmentRequirement, EquipmentReservation, Event
from .reservations import RELEASED, RESERVED

# Event statuses that end its reservations: nothing will take place to use them.
RELEASING_EVENT_STATUSES = {"cancelled", "rejected"}
# The reservation period was the event's times when it was reserved (A2), so new times
# need a new reservation (open question Q9).
EVENT_PERIOD_FIELDS = ("start_time", "end_time")
# What a reservation was chosen for (SCRUM-42 A5). Its arrangement status and note are not.
REQUIREMENT_FIELDS = ("equipment_type", "quantity", "technical_requirements")

EVENT_TIMES_CHANGED = "The event's times were changed."
REQUIREMENT_CHANGED = "The equipment requirement was changed."
REQUIREMENT_REMOVED = "The equipment requirement was removed."


def _changed(session, obj, names):
    """Whether any of these attributes is being saved with a new value, so saving
    unchanged releases nothing. When the old value wasn't loaded (after a commit expired
    it), SQLAlchemy records any value set as added, so it is compared with the saved row
    (SCRUM-44 review: SCRUM-46 may set an event's times to the ones it already has)."""
    unknown = []
    for name in names:
        history = inspect(obj).attrs[name].history
        if not history.added:
            continue
        if history.deleted:
            if history.added[0] != history.deleted[0]:
                return True
        else:
            unknown.append(name)
    if not unknown:
        return False
    model = type(obj)
    saved = (session.query(*[getattr(model, name) for name in unknown])
             .filter(model.id == obj.id).one_or_none())
    if saved is None:
        return True
    return any(getattr(obj, name) != value for name, value in zip(unknown, saved))


def _event_reason(session, obj):
    added = inspect(obj).attrs.status.history.added
    status = added[0] if added else None
    if status in RELEASING_EVENT_STATUSES:
        return f"The event was {status}."
    if _changed(session, obj, EVENT_PERIOD_FIELDS):
        return EVENT_TIMES_CHANGED
    return None


def _release(session, model, row_id, column, reason, now):
    # Lock the event or requirement first, as reserving does (A7), so a reservation being
    # saved at the same moment is either seen here and released, or sees this change.
    session.query(model.id).filter(model.id == row_id).with_for_update().all()
    held = session.query(EquipmentReservation).filter(column == row_id,
                                                      EquipmentReservation.status == RESERVED)
    for reservation in held:
        reservation.status = RELEASED
        reservation.released_at = now
        reservation.release_reason = reason


@event.listens_for(Session, "before_flush")
def release_changed_reservations(session, flush_context, instances):
    now = datetime.utcnow()
    with session.no_autoflush:
        for obj in list(session.dirty):
            if isinstance(obj, Event):
                reason = _event_reason(session, obj)
                if reason:
                    _release(session, Event, obj.id, EquipmentReservation.event_id, reason, now)
            elif (isinstance(obj, EquipmentRequirement)
                  and _changed(session, obj, REQUIREMENT_FIELDS)):
                _release(session, EquipmentRequirement, obj.id,
                         EquipmentReservation.requirement_id, REQUIREMENT_CHANGED, now)
        for obj in list(session.deleted):
            if isinstance(obj, EquipmentRequirement):
                _release(session, EquipmentRequirement, obj.id,
                         EquipmentReservation.requirement_id, REQUIREMENT_REMOVED, now)
