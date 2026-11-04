"""When an event's safety decision stops applying, and what clearing it does.

Pure rules on an Event, independent of Flask and the database, like permissions.py. A
safety decision (SCRUM-91, SCRUM-92) is made on the event's arrangements as they were then.
When those arrangements change significantly, the decision no longer describes the event,
so it is cleared and the event goes back through the safety check before it can be
confirmed again (W706).
"""

# The Event columns that make up its safety decision (SCRUM-91 AC2, SCRUM-92 AC3).
SAFETY_DECISION_FIELDS = ("safety_decision", "safety_decided_by_id", "safety_comment",
                          "safety_decided_at")
CONFIRMED_STATUS = "confirmed"
# SCRUM-70 AC11: a Confirmed event "returns to Approved", which is the Planning stage
# (SCRUM-92 A2).
PLANNING_STATUS = "approved"


def clear_safety_decision(event):
    """Clear the event's safety decision and send a Confirmed event back to Planning, so it
    needs a new safety check and a new confirmation (SCRUM-70 AC11).

    Any decision is cleared, not only an approval: a rejection or a request for changes
    was also made on the old arrangements, and clearing it puts the event back on the
    Safety Officer's list once its arrangements are ready (SCRUM-70 A11). Who confirmed it
    and when are kept, as a record that it was confirmed once.

    Returns whether there was a decision to clear."""
    had_decision = event.safety_decision is not None
    for name in SAFETY_DECISION_FIELDS:
        setattr(event, name, None)
    if event.status == CONFIRMED_STATUS:
        event.status = PLANNING_STATUS
    return had_decision
