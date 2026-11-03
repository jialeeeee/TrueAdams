from datetime import datetime

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import Notification, User

notifications_bp = Blueprint("notifications", __name__)

SESSION_INVALID = "Your session is no longer valid. Please log in again."
NOTIFICATION_NOT_FOUND = "Notification not found."
# Notification IDs live in a 32-bit column; a larger ID cannot exist.
DB_INTEGER_MAX = 2_147_483_647


def _error(message, status_code, **extra):
    return jsonify({"error": message, **extra}), status_code


def _current_user():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None


def _payload(notification):
    return {
        "id": notification.id,
        "kind": notification.kind,
        "message": notification.message,
        "event_id": notification.event_id,
        "created_at": notification.created_at.isoformat(),
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
    }


@notifications_bp.get("/")
@jwt_required()
def list_notifications():
    """The caller's own notifications, newest first."""
    try:
        user = _current_user()
        if user is None:
            return _error(SESSION_INVALID, 401)

        notifications = (
            Notification.query.filter_by(recipient_id=user.id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .all()
        )
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "Notifications could not be loaded. Please try again.", 503, retryable=True
        )

    return jsonify({
        "notifications": [_payload(n) for n in notifications],
        "message": None if notifications else "You have no notifications.",
    })


@notifications_bp.post("/<int:notification_id>/read")
@jwt_required()
def mark_read(notification_id: int):
    """Mark one of the caller's notifications read. Marking it again keeps the first time.
    Someone else's notification gets the same 404 as an unknown one, so its existence is
    not revealed."""
    try:
        user = _current_user()
        if user is None:
            return _error(SESSION_INVALID, 401)
        notification = (db.session.get(Notification, notification_id)
                        if notification_id <= DB_INTEGER_MAX else None)
        if notification is None or notification.recipient_id != user.id:
            return _error(NOTIFICATION_NOT_FOUND, 404)
        if notification.read_at is None:
            notification.read_at = datetime.utcnow()
            db.session.commit()
        payload = _payload(notification)
    except SQLAlchemyError:
        db.session.rollback()
        return _error(
            "The notification could not be marked as read. Please try again.", 503,
            retryable=True,
        )

    return jsonify({"notification": payload})
