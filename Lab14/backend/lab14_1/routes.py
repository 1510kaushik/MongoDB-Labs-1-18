from flask import Blueprint, jsonify

from .service import get_lab14_metrics

lab14_1_bp = Blueprint(
    "lab14_1",
    __name__,
    url_prefix="/api/labs/14/monitoring"
)


@lab14_1_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "lab": "14.1",
        "api": "running"
    }), 200


@lab14_1_bp.route("/status", methods=["GET"])
def status():
    result = get_lab14_metrics()
    status_code = 200 if result.get("available") else 503
    return jsonify(result), status_code
