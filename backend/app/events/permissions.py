"""Small event permission rules, independent of Flask and database access."""

COORDINATOR_ROLE = "coordinator"
# Week 7 change 5: oversees coordinators and assigns events to them (SCRUM-83 A2).
COORDINATOR_LEAD_ROLE = "coordinator_lead"
# Only Leads reassign (SCRUM-82); admins and coordinators no longer can, and a coordinator
# asks for a reassignment through SCRUM-61 instead.
ORGANISER_ROLE = "organiser"
# Technical Support Staff arrange every event's equipment; nobody assigns them to
# events, so they can see all of them (SCRUM-42 A7).
TECH_STAFF_ROLE = "tech_staff"
# Existing coordinator-information visibility; SCRUM-27 does not invent staff scope.
COORDINATOR_VIEWER_ROLES = {"admin", COORDINATOR_ROLE, "venue_staff", "tech_staff"}


# CF01 (G4 clarification #22): a user may hold more than one role: `role` is the main one
# and `additional_roles` lists the others. Every permission check asks through these, so a
# role held either way counts. Test doubles without `additional_roles` hold one role.
def roles_of(user):
    return frozenset([user.role, *(getattr(user, "additional_roles", None) or [])])


def has_role(user, role):
    return user is not None and role in roles_of(user)


def has_any_role(user, roles):
    return user is not None and not roles_of(user).isdisjoint(roles)


def is_current_coordinator(user, event):
    return has_role(user, COORDINATOR_ROLE) and event.coordinator_id == user.id


def is_coordinator_lead(user):
    return has_role(user, COORDINATOR_LEAD_ROLE)


def is_current_organiser(user, event):
    return has_role(user, ORGANISER_ROLE) and event.organiser_id == user.id


def can_view_coordinator(user, event):
    return has_any_role(user, COORDINATOR_VIEWER_ROLES) or is_current_organiser(user, event)


def can_view_clarifications(user, event):
    return is_current_coordinator(user, event) or is_current_organiser(user, event)


def is_tech_staff(user, event=None):
    return has_role(user, TECH_STAFF_ROLE)


def can_view_equipment(user, event):
    """The event's coordinator and Technical Support Staff (SCRUM-42 A9)."""
    return is_current_coordinator(user, event) or is_tech_staff(user)

