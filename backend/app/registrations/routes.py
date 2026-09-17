from flask import Blueprint, jsonify

registrations_bp = Blueprint("registrations", __name__)


@registrations_bp.get("/")
def list_registrations():
    return jsonify([])


@registrations_bp.post("/")
def register_for_event():
    return jsonify({"message": "registration not yet implemented"}), 501
