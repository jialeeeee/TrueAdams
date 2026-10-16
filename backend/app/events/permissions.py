"""Small event permission rules, independent of Flask and database access."""

COORDINATOR_ROLE = "coordinator"
# Week 7 change 5: oversees coordinators and assigns events to them (SCRUM-83 A2).
COORDINATOR_LEAD_ROLE = "coordinator_lead"
ORGANISER_ROLE = "organiser"
# Existing coordinator-information visibility; SCRUM-27 does not invent staff scope.
COORDINATOR_VIEWER_ROLES = {"admin", COORDINATOR_ROLE, "venue_staff", "tech_staff"}
# The existing coordinator story documents administrator reassignment authority.
REASSIGNMENT_ADMIN_ROLES = {"admin"}


def is_current_coordinator(user, event):
    return user is not None and user.role == COORDINATOR_ROLE and event.coordinator_id == user.id


def is_current_organiser(user, event):
    return user is not None and user.role == ORGANISER_ROLE and event.organiser_id == user.id


def can_view_coordinator(user, event):
    return user is not None and (
        user.role in COORDINATOR_VIEWER_ROLES or is_current_organiser(user, event)
    )


def can_view_clarifications(user, event):
    return is_current_coordinator(user, event) or is_current_organiser(user, event)


def can_reassign_coordinator(user, event):
    # SCRUM-27: initial assignment belongs to submission, never this endpoint.
    return user is not None and event.coordinator_id is not None and (
        is_current_coordinator(user, event) or user.role in REASSIGNMENT_ADMIN_ROLES
    )
