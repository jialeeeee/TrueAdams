from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint

from .extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="attendee")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Venue(db.Model):
    __tablename__ = "venues"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    capacity = db.Column(db.Integer)
    location = db.Column(db.String(255))
    is_available = db.Column(db.Boolean, default=True)

    # Planning characteristics. NULL means "not recorded"; an empty list, False
    # or 0 is a recorded absence, so none of these may have a default.
    description = db.Column(db.Text)
    area_sqm = db.Column(db.Integer)
    facilities = db.Column(JSONB(none_as_null=True))
    accessibility_features = db.Column(JSONB(none_as_null=True))
    room_layouts = db.Column(JSONB(none_as_null=True))
    operating_hours = db.Column(db.Text)
    contact_email = db.Column(db.String(255))
    contact_phone = db.Column(db.String(50))
    parking_spaces = db.Column(db.Integer)
    catering_available = db.Column(db.Boolean)


class Resource(db.Model):
    __tablename__ = "resources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    quantity_available = db.Column(db.Integer, default=0)


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), nullable=False, default="draft")
    organiser_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"))
    # Nullable so a draft can be saved before the dates are known; submission
    # requires them (SCRUM-29). Singapore time, stored without a time zone.
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Event request details from the organiser (SCRUM-29). NULL means not filled in.
    purpose = db.Column(db.Text)
    expected_attendance = db.Column(db.Integer)
    venue_requirements = db.Column(db.Text)
    accessibility_needs = db.Column(db.Text)
    equipment_requirements = db.Column(db.Text)
    registration_required = db.Column(db.Boolean)
    last_saved_at = db.Column(db.DateTime)
    submitted_at = db.Column(db.DateTime)

    # The coordinator's decision on a submitted request (SCRUM-32): the rejection
    # reason or optional approval note, when (naive UTC) and by whom.
    decision_note = db.Column(db.Text)
    decided_at = db.Column(db.DateTime)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    # A single column, so an event can never have two current main coordinators.
    coordinator_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    coordinator_assigned_at = db.Column(db.DateTime)
    # Who made the current assignment (SCRUM-83 A1). NULL means not recorded, e.g. the
    # automatic assignment on submission.
    coordinator_assigned_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    # Attendee registration (SCRUM-45). The period is Singapore time, stored without a
    # time zone. NULL means not recorded, which keeps registration closed.
    registration_opens_at = db.Column(db.DateTime)
    registration_closes_at = db.Column(db.DateTime)
    registration_capacity = db.Column(db.Integer)

    # What the event needs of a venue (SCRUM-38), as lists of names. NULL means not
    # recorded; an empty list means it needs none.
    required_facilities = db.Column(JSONB(none_as_null=True))
    required_accessibility_features = db.Column(JSONB(none_as_null=True))
    required_layouts = db.Column(JSONB(none_as_null=True))


class VenueBooking(db.Model):
    """A request to use a venue for a period. Only confirmed bookings block time."""

    __tablename__ = "venue_bookings"
    __table_args__ = (
        db.CheckConstraint("end_time > start_time", name="venue_bookings_end_after_start"),
        # An event can have at most one pending venue request (SCRUM-39 A6).
        db.Index(
            "venue_bookings_one_pending_per_event",
            "event_id",
            unique=True,
            postgresql_where=db.text("status = 'pending'"),
        ),
        # No two confirmed bookings at one venue may overlap, whichever code saves them
        # (SCRUM-41 A4). Periods are half-open, so touching is allowed; the venue id is
        # a one-value range so plain GiST can compare it without an extension.
        ExcludeConstraint(
            (db.text("int4range(venue_id, venue_id, '[]')"), "&&"),
            (db.text("tsrange(start_time, end_time)"), "&&"),
            name="venue_bookings_no_overlapping_confirmed",
            using="gist",
            where=db.text("status = 'confirmed'"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"), nullable=False)
    # The event the venue is booked for, once the booking request story records it.
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"))
    status = db.Column(db.String(20), nullable=False, default="pending")
    # Singapore time, stored without a time zone.
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    # When the request was made (naive UTC).
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # SCRUM-39: what Venue Staff assess the request against, and who asked.
    venue_requirements = db.Column(db.Text)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    # SCRUM-40: when (naive UTC) and by which Venue Staff member it was approved.
    decided_at = db.Column(db.DateTime)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    # SCRUM-87: a tentative hold: when (naive UTC) and by which Venue Staff member it
    # was placed, and when it expires (Singapore time, set by Venue Staff).
    held_at = db.Column(db.DateTime)
    held_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    hold_expires_at = db.Column(db.DateTime)


class VenueBlock(db.Model):
    """A recorded period when a venue cannot be used, e.g. maintenance."""

    __tablename__ = "venue_blocks"
    __table_args__ = (
        db.CheckConstraint("end_time > start_time", name="venue_blocks_end_after_start"),
    )

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"), nullable=False)
    reason = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Registration(db.Model):
    """An attendee's place at an event, or on its waiting list (SCRUM-45)."""

    __tablename__ = "registrations"
    __table_args__ = (
        # At most one active (registered) registration per attendee per event.
        db.Index(
            "registrations_one_active_per_attendee",
            "event_id",
            "attendee_id",
            unique=True,
            postgresql_where=db.text("status = 'registered'"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    attendee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    # "registered", "withdrawn" (the attendee left, SCRUM-68) or "cancelled". Only
    # registered ones take a place and are active (no waiting list since 18 Oct 2026).
    status = db.Column(db.String(20), nullable=False, default="registered")


class EventClarification(db.Model):
    """A question a coordinator sent to an event's organiser about their request."""

    __tablename__ = "event_clarifications"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    """An in-app notification for one user, e.g. a new clarification question."""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    kind = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)


class ReassignmentRequest(db.Model):
    """A coordinator's request that another coordinator takes over an event (SCRUM-61)."""

    __tablename__ = "reassignment_requests"
    __table_args__ = (
        # At most one pending request per event.
        db.Index(
            "reassignment_requests_one_pending_per_event",
            "event_id",
            unique=True,
            postgresql_where=db.text("status = 'pending'"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # The coordinator asked to take over.
    coordinator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    # "pending" is the only status until accepting and declining are built.
    status = db.Column(db.String(20), nullable=False, default="pending")
    # Naive UTC, like the other audit timestamps.
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
