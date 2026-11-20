from flask import Blueprint, jsonify

from .service import (
    check_tls_connection,
    run_rbac_tests,
    get_lab12_status,
)

lab12_bp = Blueprint(
    "lab12",
    __name__,
    url_prefix="/api/labs/12"
)


@lab12_bp.route("/health", methods=["GET"])
def health():
    result = check_tls_connection()
    status_code = 200 if result["status"] == "success" else 503

    return jsonify({
        "lab": "Lab 12",
        "api": "running",
        "tls": result,
    }), status_code


@lab12_bp.route("/status", methods=["GET"])
def status():
    result = get_lab12_status()
    tls_result = result.get("tls", {})
    status_code = 200 if tls_result.get("status") == "success" else 503

    return jsonify(result), status_code


@lab12_bp.route("/rbac/test", methods=["POST"])
def rbac_test():
    try:
        result = run_rbac_tests()
        status_code = 200 if result.get("status") == "success" else 503

        return jsonify({
            "lab": "Lab 12.1",
            "results": result,
        }), status_code

    except Exception as error:
        return jsonify({
            "status": "error",
            "message": f"{type(error).__name__}: {error}",
        }), 503
