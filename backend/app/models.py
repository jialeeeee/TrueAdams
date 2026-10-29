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
    # SCRUM-91: safety approval is separate from the coordinator's request decision.
    # NULL means not recorded. Audit fields are not editable through planning PATCH.
    safety_decision = db.Column(db.String(20))
    safety_decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    safety_comment = db.Column(db.Text)
    safety_decided_at = db.Column(db.DateTime)  # Naive UTC.
    # When (naive UTC) and by which coordinator the review was started, moving the
    # request to under_review (SCRUM-31, reopened). Records, not editable fields.
    review_started_at = db.Column(db.DateTime)
    review_started_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

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
        # SCRUM-84: setup and turnaround are whole minutes, up to a day each.
        db.CheckConstraint("setup_minutes between 0 and 1440",
                           name="venue_bookings_setup_minutes_range"),
        db.CheckConstraint("turnaround_minutes between 0 and 1440",
                           name="venue_bookings_turnaround_minutes_range"),
        # An event may have several pending requests, one per venue it needs (SCRUM-85
        # A1), so SCRUM-39's one-pending-request index is gone.
        # No two confirmed bookings at one venue may overlap, whichever code saves them
        # (SCRUM-41 A4). Periods are half-open, so touching is allowed; the venue id is
        # a one-value range so plain GiST can compare it without an extension. It is the
        # occupied period (setup before, turnaround after) that must not overlap (SCRUM-84).
        ExcludeConstraint(
            (db.text("int4range(venue_id, venue_id, '[]')"), "&&"),
            (db.text("tsrange(occupied_start, occupied_end)"), "&&"),
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
    # SCRUM-40/69: when (naive UTC) and by which Venue Staff member it was decided.
    decided_at = db.Column(db.DateTime)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    # SCRUM-69: saved on the request itself; NULL for requests without a rejection.
    rejection_reason = db.Column(db.Text)
    # SCRUM-87: a tentative hold: when (naive UTC) and by which Venue Staff member it
    # was placed, and when it expires (Singapore time, set by Venue Staff).
    held_at = db.Column(db.DateTime)
    held_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    hold_expires_at = db.Column(db.DateTime)
    # SCRUM-86: when (naive UTC) the coordinator was told the hold expires within 24
    # hours, so they are told once. NULL while that is still due.
    hold_warned_at = db.Column(db.DateTime)
    # SCRUM-84: minutes of setup before and turnaround after the event. The venue is
    # occupied from start_time - setup to end_time + turnaround, which the database works
    # out (occupied_start/occupied_end) so the no-overlap rule can use it.
    setup_minutes = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    turnaround_minutes = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    occupied_start = db.Column(
        db.DateTime,
        db.Computed("start_time - make_interval(mins => setup_minutes)", persisted=True))
    occupied_end = db.Column(
        db.DateTime,
        db.Computed("end_time + make_interval(mins => turnaround_minutes)", persisted=True))


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


class EquipmentRequirement(db.Model):
    """One item of equipment an event needs, recorded by its coordinator (SCRUM-42).

    Recording it reserves nothing and leaves equipment availability alone (AC5).
    """

    __tablename__ = "equipment_requirements"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="equipment_requirements_quantity_positive"),
        db.Index("equipment_requirements_event_id", "event_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    equipment_type = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    # NULL means none recorded.
    technical_requirements = db.Column(db.Text)
    # Set by Technical Support Staff as they arrange it: "requested", "being_arranged"
    # or "unavailable" (SCRUM-42 A7). Never reserved or fulfilled: that is SCRUM-44.
    status = db.Column(db.String(20), nullable=False, default="requested")
    arrangement_note = db.Column(db.Text)
    # Who recorded it, when, and when the coordinator last changed it (naive UTC).
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_saved_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    # Which Technical Support Staff member last updated the arrangement, and when (UTC).
    arrangement_updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    arrangement_updated_at = db.Column(db.DateTime)


class EquipmentUnavailability(db.Model):
    """A recorded period when an item of equipment can't be used, e.g. repair (SCRUM-43).

    It makes the whole item unavailable for any event it overlaps (A5).
    """

    __tablename__ = "equipment_unavailability"
    __table_args__ = (
        db.CheckConstraint("end_time > start_time",
                           name="equipment_unavailability_end_after_start"),
        db.Index("equipment_unavailability_resource_id", "resource_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"), nullable=False)
    # Singapore time, stored without a time zone; half-open [start, end).
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EquipmentReservation(db.Model):
    """A quantity of one item of equipment reserved for an event's requirement (SCRUM-44).

    Only "reserved" rows hold equipment. A released row is kept as history: it says when
    and why it stopped holding the equipment (A10).
    """

    __tablename__ = "equipment_reservations"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="equipment_reservations_quantity_positive"),
        db.CheckConstraint("end_time > start_time",
                           name="equipment_reservations_end_after_start"),
        db.Index("equipment_reservations_event_id", "event_id"),
        db.Index("equipment_reservations_requirement_id", "requirement_id"),
        db.Index("equipment_reservations_resource_id", "resource_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    # NULL once the requirement it was for has been removed; the release reason says so.
    requirement_id = db.Column(
        db.Integer, db.ForeignKey("equipment_requirements.id", ondelete="SET NULL"))
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    # The reservation period: the event's times when it was reserved (Singapore time,
    # stored without a time zone, half-open [start, end); A2).
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    # "reserved" or "released".
    status = db.Column(db.String(20), nullable=False, default="reserved")
    # Who reserved it and when, and when and why it was released (naive UTC).
    reserved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reserved_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    released_at = db.Column(db.DateTime)
    release_reason = db.Column(db.Text)


class EventChangeRequest(db.Model):
    """An organiser's request to change their approved event (SCRUM-46).

    It records what would change and leaves the event itself alone until the event's
    coordinator accepts it (SCRUM-46 AC7, SCRUM-70 AC8).
    """

    __tablename__ = "event_change_requests"
    __table_args__ = (
        # At most one request pending review per event (A6).
        db.Index(
            "event_change_requests_one_pending_per_event",
            "event_id",
            unique=True,
            postgresql_where=db.text("status = 'pending_review'"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # "pending_review", then "accepted" or "rejected" by the coordinator (SCRUM-70 A4).
    status = db.Column(db.String(20), nullable=False, default="pending_review")
    # {"<field>": {"from": current value, "to": proposed value}} for each field that
    # would change; times as Singapore-time ISO strings (A7).
    changes = db.Column(JSONB, nullable=False)
    # Naive UTC, like the other audit timestamps.
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    # SCRUM-70: when (naive UTC) and by which coordinator it was decided, and why it was
    # rejected. NULL while pending; the reason is NULL for an accepted request.
    decided_at = db.Column(db.DateTime)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    decision_reason = db.Column(db.Text)


class VenueChange(db.Model):
    """SCRUM-63: one add or edit of a venue, with who made it and when."""

    __tablename__ = "venue_changes"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey("venues.id"), nullable=False)
    # "added" or "edited".
    action = db.Column(db.String(10), nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # Naive UTC, like the other audit timestamps.
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    # {"<field>": {"from": ..., "to": ...}} for every field the change touched.
    changes = db.Column(JSONB, nullable=False)
