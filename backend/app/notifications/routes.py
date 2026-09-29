from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import Notification, User

notifications_bp = Blueprint("notifications", __name__)


def _error(message, status_code, **extra):
    return jsonify({"error": message, **extra}), status_code


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
        try:
            user = db.session.get(User, int(get_jwt_identity()))
        except (TypeError, ValueError):
            user = None
        if user is None:
            return _error("Your session is no longer valid. Please log in again.", 401)

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

    return jsonify({"notifications": [_payload(n) for n in notifications]})
