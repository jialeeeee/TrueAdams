import unittest
import uuid
from datetime import datetime, timedelta

from flask_jwt_extended import create_access_token
from sqlalchemy import func
from sqlalchemy.orm import scoped_session, sessionmaker

from app import create_app
from app.config import TestConfig
from app.extensions import celery, db
from app.models import Event, Registration, Resource, User, Venue

_app = None

# Added to test emails so concurrent runs (CI, teammates) never collide on the
# unique email constraint while their uncommitted rows exist.
RUN_ID = uuid.uuid4().hex[:8]


def run_email(email):
    local, domain = email.split("@")
    return f"{local}+{RUN_ID}@{domain}"


def get_test_app():
    """One app (and so one connection pool) per test run, not per test."""
    global _app
    if _app is None:
        _app = create_app(TestConfig)
        celery.conf.task_always_eager = True
    return _app


class AppTestCase(unittest.TestCase):
    """Base class running each test against the Supabase `public` tables.

    Each test inserts the rows it needs inside a transaction that is rolled back
    afterwards, so nothing a test writes is ever saved or seen by the live app.
    Routes can still commit and roll back as usual: their session works inside a
    savepoint. Real data may be present, so tests must not assume their rows are
    the only ones.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not TestConfig.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError(
                "TEST_DATABASE_URL is not set. Add it to backend/.env (see README)."
            )

    def setUp(self):
        # Cleanups, not tearDown: they also run when a subclass's setUp fails part-way,
        # so a half-seeded transaction can never stay open holding row locks.
        self.app = get_test_app()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.addCleanup(self.app_context.pop)

        self.connection = db.engine.connect()
        self.addCleanup(self.connection.close)
        self.transaction = self.connection.begin()
        self.addCleanup(self.transaction.rollback)
        self._app_session = db.session
        db.session = scoped_session(
            sessionmaker(bind=self.connection, join_transaction_mode="create_savepoint")
        )
        self.addCleanup(self._restore_app_session)

        self.db = db
        self.client = self.app.test_client()
        self._user_count = 0

    def _restore_app_session(self):
        db.session.remove()
        db.session = self._app_session

    def make_user(self, email=None, role="attendee", password_hash="not-a-real-hash"):
        """Create a User for this test only. Emails are unique per call unless given."""
        email = email or run_email(f"user{self._user_count}@test.invalid")
        self._user_count += 1
        user = User(email=email, password_hash=password_hash, role=role)
        db.session.add(user)
        db.session.commit()
        return user

    def make_venue(self, name="Hall A", capacity=100, location="Level 1", is_available=True):
        venue = Venue(
            name=name, capacity=capacity, location=location, is_available=is_available
        )
        db.session.add(venue)
        db.session.commit()
        return venue

    def make_resource(self, name="Projector", category="av", quantity_available=5):
        resource = Resource(
            name=name, category=category, quantity_available=quantity_available
        )
        db.session.add(resource)
        db.session.commit()
        return resource

    def make_event(
        self,
        organiser=None,
        title="Annual Conference",
        status="draft",
        venue=None,
        start_time=None,
        duration=timedelta(hours=2),
        **kwargs,
    ):
        organiser = organiser or self.make_user(role="organiser")
        start_time = start_time or datetime(2026, 10, 1, 9, 0)
        event = Event(
            title=title,
            status=status,
            organiser_id=organiser.id,
            venue_id=venue.id if venue else None,
            start_time=start_time,
            end_time=start_time + duration,
            **kwargs,
        )
        db.session.add(event)
        db.session.commit()
        return event

    def make_registration(self, event=None, attendee=None):
        event = event or self.make_event()
        attendee = attendee or self.make_user(role="attendee")
        registration = Registration(event_id=event.id, attendee_id=attendee.id)
        db.session.add(registration)
        db.session.commit()
        return registration

    # ---------- Seeding (see tests/seed_data.py) ----------

    def _insert(self, model, objects):
        """Insert rows for this test only, reloading them in one query afterwards."""
        db.session.add_all(objects)
        db.session.flush()
        ids = [obj.id for obj in objects]
        db.session.commit()
        model.query.filter(model.id.in_(ids)).all()  # refresh the expired objects
        return objects

    def seed_users(self, rows):
        users = {
            row["key"]: User(email=run_email(row["email"]), password_hash="not-a-real-hash",
                             role=row["role"])
            for row in rows
        }
        self._insert(User, list(users.values()))
        return users

    def seed_events(self, rows, users):
        events = {}
        for row in rows:
            fields = {k: v for k, v in row.items() if k not in ("key", "organiser", "coordinator")}
            coordinator = users[row["coordinator"]] if row["coordinator"] else None
            events[row["key"]] = Event(
                organiser_id=users[row["organiser"]].id,
                coordinator_id=coordinator.id if coordinator else None,
                **fields,
            )
        self._insert(Event, list(events.values()))
        return events

    def seed_venues(self, rows):
        venues = {row["key"]: Venue(**{k: v for k, v in row.items() if k != "key"}) for row in rows}
        self._insert(Venue, list(venues.values()))
        return venues

    def missing_id(self, model):
        """An id no row of `model` has, whatever real data the table holds."""
        return (db.session.query(func.max(model.id)).scalar() or 0) + 1_000_000

    def auth_headers(self, user):
        """Bearer-token headers for a given user."""
        token = create_access_token(
            identity=str(user.id), additional_claims={"role": user.role}
        )
        return {"Authorization": f"Bearer {token}"}
