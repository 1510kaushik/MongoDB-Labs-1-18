import json
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from .service import run_benchmark, RESULTS_DIR

lab9_bp = Blueprint(
    "lab9",
    __name__,
    url_prefix="/api/labs/9"
)


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


@lab9_bp.route("/history", methods=["GET"])
def benchmark_history():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    history = []

    files = sorted(
        RESULTS_DIR.glob("lab9_1_*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True
    )

    for file in files[:50]:
        try:
            report = json.loads(file.read_text(encoding="utf-8"))
            history.append({
                "filename": file.name,
                "timestamp": report.get("timestamp"),
                "document_count": report.get("document_count"),
                "replica_set": report.get("replica_set"),
                "results": report.get("results", {})
            })
        except (OSError, ValueError):
            continue

    return jsonify({
        "total": len(history),
        "history": history
    })


@lab9_bp.route("/results/<filename>", methods=["GET"])
def download_result(filename):
    if (
        Path(filename).name != filename
        or not filename.startswith("lab9_1_")
        or not filename.endswith(".json")
    ):
        return jsonify({"error": "Invalid result filename"}), 404

    result_file = RESULTS_DIR / filename

    if not result_file.is_file():
        return jsonify({"error": "Result file not found"}), 404

    return send_file(
        result_file,
        mimetype="application/json",
        as_attachment=True,
        download_name=filename
    )
