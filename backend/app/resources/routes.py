from flask import Blueprint, jsonify

resources_bp = Blueprint("resources", __name__)


@resources_bp.get("/")
def list_resources():
    return jsonify([])


@resources_bp.post("/<int:resource_id>/reservations")
def reserve_resource(resource_id: int):
    return jsonify({"message": "reservation not yet implemented"}), 501
