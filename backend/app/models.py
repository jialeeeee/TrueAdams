from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB

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


class VenueBooking(db.Model):
    """A request to use a venue for a period. Only confirmed bookings block time."""

    __tablename__ = "venue_bookings"
    __table_args__ = (
        db.CheckConstraint("end_time > start_time", name="venue_bookings_end_after_start"),
    )

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"), nullable=False)
    # The event the venue is booked for, once the booking request story records it.
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"))
    status = db.Column(db.String(20), nullable=False, default="pending")
    # Singapore time, stored without a time zone.
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
    __tablename__ = "registrations"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    attendee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)


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
