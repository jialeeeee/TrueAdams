from flask import Blueprint, jsonify

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    return jsonify({"message": "login not yet implemented"}), 501


@auth_bp.post("/register")
def register():
    return jsonify({"message": "register not yet implemented"}), 501
