from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash

from ..extensions import db
from ..models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    body = request.get_json(silent=True)
    email = body.get("email") if isinstance(body, dict) else None
    password = body.get("password") if isinstance(body, dict) else None
    if not isinstance(email, str) or not email.strip() or not isinstance(password, str) or not password:
        return jsonify({"error": "Email and password are required."}), 400

    try:
        user = User.query.filter_by(email=email).first()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({
            "error": "Sign-in is temporarily unavailable. Please try again.",
            "retryable": True,
        }), 503

    if user is None or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password."}), 401

    return jsonify({"access_token": create_access_token(identity=str(user.id))}), 200


@auth_bp.post("/register")
def register():
    return jsonify({"message": "register not yet implemented"}), 501
