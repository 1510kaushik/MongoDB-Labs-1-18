from flask import Blueprint, jsonify

from .service import get_lab13_status

lab13_bp = Blueprint("lab13", __name__, url_prefix="/api/labs/13")


@lab13_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "lab": "Lab 13",
        "api": "running"
    }), 200


@lab13_bp.route("/status", methods=["GET"])
def status():
    result = get_lab13_status()

    components = [
        result["docker"]["status"],
        result["prometheus"]["status"],
        result["kubernetes"]["status"]
    ]

    overall = "success" if all(
        value == "success" for value in components
    ) else "warning"

    result["status"] = overall
    return jsonify(result), 200
