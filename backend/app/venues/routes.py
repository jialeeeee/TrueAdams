from flask import Blueprint, jsonify

venues_bp = Blueprint("venues", __name__)


@venues_bp.get("/")
def list_venues():
    return jsonify([])


@venues_bp.post("/")
def create_venue():
    return jsonify({"message": "create venue not yet implemented"}), 501


@venues_bp.get("/<int:venue_id>/availability")
def check_availability(venue_id: int):
    return jsonify({"message": "availability check not yet implemented"}), 501
