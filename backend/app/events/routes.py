from flask import Blueprint, jsonify

events_bp = Blueprint("events", __name__)


@events_bp.get("/")
def list_events():
    return jsonify([])


@events_bp.post("/")
def create_event():
    return jsonify({"message": "create event not yet implemented"}), 501


@events_bp.post("/<int:event_id>/change-requests")
def submit_change_request(event_id: int):
    return jsonify({"message": "change request not yet implemented"}), 501
