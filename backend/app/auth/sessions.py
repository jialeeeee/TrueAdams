"""SCRUM-75 AC6: a signed-out token is refused by every protected route.

flask-jwt-extended asks `is_revoked` about every token a `@jwt_required()` route receives.
A token is revoked when its user signed out of it (POST /api/auth/logout records its JWT
ID in revoked_tokens); the route then answers 401 "You have signed out."

If the check can't read the database, the request goes on to the route, which reads the
database itself and reports its own failure (AGENTS.md: a failed load is reported as a
failure, with the route's own message). The failure is logged. A signed-out token can then
only be used while the database is unreachable for this one check, and only until the
token expires (A9).
"""

from flask import current_app, jsonify
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db, jwt
from ..models import RevokedToken

SIGNED_OUT = "You have signed out. Please sign in again."


@jwt.token_in_blocklist_loader
def is_revoked(jwt_header, jwt_payload):
    try:
        return db.session.query(RevokedToken.id).filter_by(
            jti=jwt_payload["jti"]).first() is not None
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not check whether a token was signed out")
        return False


@jwt.revoked_token_loader
def signed_out(jwt_header, jwt_payload):
    return jsonify({"error": SIGNED_OUT}), 401
