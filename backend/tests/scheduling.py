"""Shared setup for the venue availability (SCRUM-36) and venue search (SCRUM-37) tests.

Not a test module itself: `unittest discover` only collects test*.py files.
"""

from contextlib import contextmanager
from datetime import timedelta

import psycopg2
from flask_jwt_extended import create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app.models import VenueBlock, VenueBooking
from tests.test_venue_details import VenueTestCase


class SchedulingTestCase(VenueTestCase):
    """VenueTestCase plus seeding for bookings and blocks, and targeted outages."""

    def setUp(self):
        super().setUp()
        self.bookings = {}
        self.blocks = {}

    # ---------- Seeding ----------

    def seed_bookings(self, rows):
        new = {
            row["key"]: VenueBooking(
                venue_id=self.venues[row["venue"]].id,
                status=row["status"],
                start_time=row["start_time"],
                end_time=row["end_time"],
            )
            for row in rows
        }
        self._insert(VenueBooking, list(new.values()))
        self.bookings.update(new)
        return new

    def seed_blocks(self, rows):
        new = {
            row["key"]: VenueBlock(
                venue_id=self.venues[row["venue"]].id,
                reason=row["reason"],
                start_time=row["start_time"],
                end_time=row["end_time"],
            )
            for row in rows
        }
        self._insert(VenueBlock, list(new.values()))
        self.blocks.update(new)
        return new

    # ---------- Authentication variants ----------

    def expired_headers(self, user):
        token = create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.role},
            expires_delta=timedelta(seconds=-1),
        )
        return {"Authorization": f"Bearer {token}"}

    def deleted_user_headers(self, role="coordinator"):
        ghost = self.make_user(role=role)
        headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        return headers

    # ---------- Failures ----------

    @contextmanager
    def queries_fail_on(self, *tables):
        """Make queries fail, as a dropped Supabase connection would.

        With `tables`, only statements mentioning one of them fail, so a request
        can half-succeed. Savepoint statements still run so the test survives.
        """

        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith(("SAVEPOINT", "ROLLBACK", "RELEASE")):
                return
            if tables and not any(table in statement for table in tables):
                return
            raise OperationalError(
                statement, parameters, psycopg2.OperationalError("simulated database outage")
            )

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            yield
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

    def get_while_failing(self, url, *tables, query_string=None):
        # Build the token first: reading the user's id is itself a query.
        headers = self.auth_headers(self.users["coordinator"])
        # Tests share the request's session; start the request cold, as in production.
        self.db.session.expire_all()
        with self.queries_fail_on(*tables):
            return self.client.get(url, headers=headers, query_string=query_string)
