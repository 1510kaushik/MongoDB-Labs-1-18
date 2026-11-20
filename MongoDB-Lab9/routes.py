from flask import Blueprint, jsonify, request
from service import run_benchmark

lab9_bp = Blueprint("lab9", __name__, url_prefix="/api/labs/9")


@lab9_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "success",
        "lab": "Lab 9",
        "message": "Lab 9 API is running"
    })


@lab9_bp.route("/write-concern", methods=["POST"])
def write_concern():
    try:
        data = request.get_json(silent=True) or {}
        document_count = data.get("document_count", 1000)

        if (
            isinstance(document_count, bool)
            or not isinstance(document_count, int)
            or not 1 <= document_count <= 100000
        ):
            return jsonify({
                "status": "error",
                "message": "document_count must be an integer between 1 and 100000"
            }), 400

        return jsonify(run_benchmark(document_count)), 200

    except Exception as error:
        return jsonify({
            "status": "error",
            "message": str(error)
        }), 500
