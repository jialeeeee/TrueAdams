from datetime import datetime

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
    facilities = db.Column(db.JSON)
    accessibility_features = db.Column(db.JSON)
    room_layouts = db.Column(db.JSON)
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
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # A single column, so an event can never have two current main coordinators.
    coordinator_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    coordinator_assigned_at = db.Column(db.DateTime)


class Registration(db.Model):
    __tablename__ = "registrations"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    attendee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
