from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash

from ..extensions import db
from ..models import RevokedToken, User
from ..roles import roles_of

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    body = request.get_json(silent=True)
    email = body.get("email") if isinstance(body, dict) else None
    password = body.get("password") if isinstance(body, dict) else None
    missing = []
    if not isinstance(email, str) or not email.strip():
        missing.append("email")
    if not isinstance(password, str) or not password:
        missing.append("password")
    if missing:
        return jsonify({"error": f"Please enter {' and '.join(missing)}.", "missing": missing}), 400

    try:
        user = User.query.filter_by(email=email).first()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            "error": "Sign-in is temporarily unavailable. Please try again.",
            "retryable": True,
        }), 503

    if user is None or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Email or password is incorrect"}), 401

    # SCRUM-75: the stored role selects an existing home page; API guards still
    # reload the user for authorization rather than trusting browser state. CF01: `roles`
    # lists every role the user holds, main role first, so the menu can show all their pages.
    return jsonify({
        "access_token": create_access_token(identity=str(user.id)),
        "role": user.role,
        "roles": [user.role, *sorted(roles_of(user) - {user.role})],
    }), 200


@auth_bp.post("/logout")
@jwt_required()
def logout():
    """SCRUM-75 AC6: sign out of this token, so the API refuses it from now on (A9).

    Only this token is signed out: the user's other sessions carry on. The browser forgets
    the token whatever this answers, so a failure here never keeps anyone signed in there.
    """
    claims = get_jwt()
    expires = claims.get("exp")
    try:
        db.session.add(RevokedToken(
            jti=claims["jti"], user_id=int(get_jwt_identity()),
            expires_at=(datetime.fromtimestamp(expires, timezone.utc).replace(tzinfo=None)
                        if expires else None)))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            "error": "Signing out on the server failed. Please try again.",
            "retryable": True,
        }), 503
    return jsonify({"message": "You have signed out."}), 200


@auth_bp.post("/register")
def register():
    return jsonify({"message": "register not yet implemented"}), 501
