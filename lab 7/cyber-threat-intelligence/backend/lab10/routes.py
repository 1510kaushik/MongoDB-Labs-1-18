import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from .bank_transfer import (
    run_lab10_1_demo,
    reset_accounts,
    get_accounts,
    get_balances,
    get_transfer_history,
    transfer,
    InsufficientFunds,
    AccountNotFound,
)
from .inventory_reservation import (
    run_lab10_2_demo,
    reset_inventory,
    get_inventory_state,
    reserve_inventory,
    reserve_non_transactional,
    run_concurrency_test,
    run_inconsistency_demo,
    run_throughput_benchmark,
    OutOfStock,
    RetriesExhausted,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"

lab10_bp = Blueprint(
    "lab10",
    __name__,
    url_prefix="/api/labs/10"
)


@lab10_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "success",
        "lab": "Lab 10",
        "message": "Lab 10 API is running"
    })


# ── Lab 10.1: Bank Transfer ─────────────────────────────────────────

@lab10_bp.route("/bank/run", methods=["POST"])
def run_bank_demo():
    """Run the full Lab 10.1 demo (all steps + activity)."""
    try:
        report = run_lab10_1_demo()
        return jsonify(report), 200
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@lab10_bp.route("/bank/setup", methods=["POST"])
def setup_bank():
    """Reset accounts to initial state."""
    try:
        reset_accounts()
        return jsonify({"status": "success", "accounts": get_accounts()})
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@lab10_bp.route("/bank/accounts", methods=["GET"])
def bank_accounts():
    try:
        return jsonify({"accounts": get_accounts(), "balances": get_balances()})
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@lab10_bp.route("/bank/transfer", methods=["POST"])
def bank_transfer():
    """Execute a single transfer."""
    try:
        data = request.get_json(silent=True) or {}
        src = data.get("from", "A1001")
        dst = data.get("to", "A1002")
        amount = data.get("amount", 100)

        if not isinstance(amount, (int, float)) or amount <= 0:
            return jsonify({"status": "error", "message": "amount must be a positive number"}), 400

        result = transfer(src, dst, amount)
        result["balances"] = get_balances()
        return jsonify(result), 200
    except InsufficientFunds as exc:
        return jsonify({
            "status": "insufficient_funds",
            "message": str(exc),
            "balances": get_balances(),
        }), 200
    except AccountNotFound as exc:
        return jsonify({"status": "error", "message": f"Account not found: {exc}"}), 404
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@lab10_bp.route("/bank/history", methods=["GET"])
def bank_history():
    try:
        return jsonify({"history": get_transfer_history()})
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


# ── Lab 10.2: Inventory Reservation ─────────────────────────────────

@lab10_bp.route("/inventory/run", methods=["POST"])
def run_inventory_demo():
    """Run the full Lab 10.2 demo (concurrency + inconsistency + benchmark)."""
    try:
        data = request.get_json(silent=True) or {}
        requests_per_level = data.get("requests_per_level", 50)

        if not isinstance(requests_per_level, int) or not 10 <= requests_per_level <= 500:
            return jsonify({
                "status": "error",
                "message": "requests_per_level must be an integer between 10 and 500"
            }), 400

        report = run_lab10_2_demo(requests_per_level)
        return jsonify(report), 200
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@lab10_bp.route("/inventory/setup", methods=["POST"])
def setup_inventory():
    """Reset inventory to initial state."""
    try:
        data = request.get_json(silent=True) or {}
        stock = data.get("stock", 5)
        reset_inventory(stock)
        return jsonify({"status": "success", "state": get_inventory_state()})
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@lab10_bp.route("/inventory/state", methods=["GET"])
def inventory_state():
    try:
        return jsonify(get_inventory_state())
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@lab10_bp.route("/inventory/concurrency", methods=["POST"])
def inventory_concurrency():
    """Run the concurrency test only."""
    try:
        result = run_concurrency_test()
        return jsonify(result), 200
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@lab10_bp.route("/inventory/inconsistency", methods=["POST"])
def inventory_inconsistency():
    """Run the inconsistency demo only."""
    try:
        result = run_inconsistency_demo()
        return jsonify(result), 200
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


@lab10_bp.route("/inventory/benchmark", methods=["POST"])
def inventory_benchmark():
    """Run the throughput benchmark only."""
    try:
        data = request.get_json(silent=True) or {}
        requests_per_level = data.get("requests_per_level", 50)
        result = run_throughput_benchmark(requests_per_level)
        return jsonify({"benchmark": result}), 200
    except Exception as error:
        return jsonify({"status": "error", "message": str(error)}), 500


# ── Shared: saved results history ────────────────────────────────────

@lab10_bp.route("/history", methods=["GET"])
def lab10_history():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    history = []

    files = sorted(
        list(RESULTS_DIR.glob("lab10_*.json")),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    for f in files[:50]:
        try:
            report = json.loads(f.read_text(encoding="utf-8"))
            history.append({
                "filename": f.name,
                "lab": report.get("lab"),
                "title": report.get("title"),
                "timestamp": report.get("timestamp"),
            })
        except (OSError, ValueError):
            continue

    return jsonify({"total": len(history), "history": history})
