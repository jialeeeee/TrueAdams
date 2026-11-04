"""CF01 (G4 clarification #22): a user may hold more than one role.

`User.role` is the main role and `User.additional_roles` lists any others. The rules for
one user (roles_of, has_role, has_any_role) live in events/permissions.py, which imports
nothing so it can be checked on its own; they are re-exported here with the database
filter, so routes import every role helper from one place.
"""

from sqlalchemy import or_

from .events.permissions import has_any_role, has_role, roles_of  # noqa: F401 (re-exported)
from .models import User


def holding(roles):
    """A filter for User queries: users who hold any of these roles, as main or other role."""
    roles = list(roles)
    return or_(User.role.in_(roles),
               *[User.additional_roles.contains([role]) for role in roles])
