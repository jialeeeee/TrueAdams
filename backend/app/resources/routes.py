from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

resources_bp = Blueprint("resources", __name__)


# Stubs, free to be built by their story (AGENTS.md). Signed-in users only, like every
# other /api route except login and register.
@resources_bp.get("/")
@jwt_required()
def list_resources():
    return jsonify([])


@resources_bp.post("/<int:resource_id>/reservations")
@jwt_required()
def reserve_resource(resource_id: int):
    return jsonify({"message": "reservation not yet implemented"}), 501
