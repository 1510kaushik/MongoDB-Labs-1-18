"""Lab 10.1 - Bank Transfer Transaction Service.

Implements multi-document transactions with:
  - Session-based atomic transfers (debit + credit + history)
  - Application-level and filter-guard balance checks
  - Retry logic with exponential backoff for TransientTransactionError
  - Commit retry for UnknownTransactionCommitResult
"""
import json
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from ..db import client, db

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"

# ── Database names for lab 10 collections (inside the existing DB) ──

LAB10_ACCOUNTS = "lab10_accounts"
LAB10_TRANSFER_HISTORY = "lab10_transfer_history"

DEFAULT_ACCOUNTS = [
    {"account_id": "A1001", "owner": "Alice", "balance": 1000, "version": 1},
    {"account_id": "A1002", "owner": "Bob",   "balance": 500,  "version": 1},
]


class InsufficientFunds(Exception):
    """Source account does not have enough balance."""


class AccountNotFound(Exception):
    """Source or destination account does not exist."""


# ── Helpers ──────────────────────────────────────────────────────────

def _has_label(exc, label):
    return isinstance(exc, PyMongoError) and exc.has_error_label(label)


def _safe_abort(session):
    try:
        if session.in_transaction:
            session.abort_transaction()
    except PyMongoError:
        pass


def _commit_with_retry(session, max_tries=5):
    for attempt in range(max_tries):
        try:
            session.commit_transaction()
            return
        except PyMongoError as exc:
            if _has_label(exc, "UnknownTransactionCommitResult") and attempt < max_tries - 1:
                time.sleep(0.05)
                continue
            raise


# ── Setup ────────────────────────────────────────────────────────────

def reset_accounts():
    """Drop and recreate accounts + transfer_history with fresh seed data."""
    db.drop_collection(LAB10_ACCOUNTS)
    db.drop_collection(LAB10_TRANSFER_HISTORY)
    db.create_collection(LAB10_ACCOUNTS)
    db.create_collection(LAB10_TRANSFER_HISTORY)
    db[LAB10_ACCOUNTS].create_index("account_id", unique=True)
    db[LAB10_ACCOUNTS].insert_many([dict(a) for a in DEFAULT_ACCOUNTS])


def get_balances():
    return {
        a["account_id"]: a["balance"]
        for a in db[LAB10_ACCOUNTS].find({}, {"_id": 0}).sort("account_id")
    }


def get_accounts():
    return list(db[LAB10_ACCOUNTS].find({}, {"_id": 0}).sort("account_id"))


def get_transfer_history():
    rows = list(
        db[LAB10_TRANSFER_HISTORY]
        .find({}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(50)
    )
    for r in rows:
        if hasattr(r.get("timestamp"), "isoformat"):
            r["timestamp"] = r["timestamp"].isoformat()
    return rows


# ── Core transfer logic ─────────────────────────────────────────────

def _transfer_in_txn(session, src, dst, amount, *, precheck, fail_after_debit):
    accounts = db[LAB10_ACCOUNTS]

    source = accounts.find_one({"account_id": src}, session=session)
    if source is None:
        raise AccountNotFound(src)
    if accounts.find_one({"account_id": dst}, session=session) is None:
        raise AccountNotFound(dst)

    if precheck and source["balance"] < amount:
        raise InsufficientFunds(
            f"{src} has {source['balance']}, tried to transfer {amount}"
        )

    debit = accounts.update_one(
        {"account_id": src, "balance": {"$gte": amount}},
        {"$inc": {"balance": -amount, "version": 1}},
        session=session,
    )
    if debit.matched_count == 0:
        raise InsufficientFunds(f"{src} cannot cover {amount}")

    if fail_after_debit:
        raise RuntimeError("Simulated crash after debit, before credit")

    credit = accounts.update_one(
        {"account_id": dst},
        {"$inc": {"balance": amount, "version": 1}},
        session=session,
    )
    if credit.matched_count == 0:
        raise AccountNotFound(dst)

    transfer_id = str(uuid.uuid4())
    db[LAB10_TRANSFER_HISTORY].insert_one(
        {
            "transfer_id": transfer_id,
            "from": src,
            "to": dst,
            "amount": amount,
            "timestamp": datetime.now(timezone.utc),
        },
        session=session,
    )
    return transfer_id


def transfer(src, dst, amount, *, max_retries=5, precheck=True,
             fail_after_debit=False):
    """Move `amount` from src→dst atomically. Returns dict with result info."""
    retry_log = []
    with client.start_session() as session:
        for attempt in range(max_retries + 1):
            session.start_transaction(
                read_concern=ReadConcern("snapshot"),
                write_concern=WriteConcern("majority"),
            )
            try:
                transfer_id = _transfer_in_txn(
                    session, src, dst, amount,
                    precheck=precheck, fail_after_debit=fail_after_debit,
                )
                _commit_with_retry(session)
                return {
                    "transfer_id": transfer_id,
                    "attempts": attempt + 1,
                    "retries": retry_log,
                    "status": "success",
                }
            except Exception as exc:
                _safe_abort(session)
                if _has_label(exc, "TransientTransactionError") and attempt < max_retries:
                    delay = 0.1 * 2 ** attempt + random.uniform(0, 0.05)
                    retry_log.append({
                        "attempt": attempt + 1,
                        "error": str(exc),
                        "delay_s": round(delay, 3),
                    })
                    time.sleep(delay)
                    continue
                raise


# ── Full demo runner (called from the API) ───────────────────────────

def run_lab10_1_demo():
    """Execute all Lab 10.1 steps and return a structured report."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    steps = []

    # STEP 1: Create accounts
    reset_accounts()
    accounts = get_accounts()
    steps.append({
        "step": 1,
        "title": "Create accounts collection + insert two accounts",
        "accounts": accounts,
        "status": "success",
    })

    # STEP 2: Successful transfer
    result = transfer("A1001", "A1002", 200)
    balances = get_balances()
    steps.append({
        "step": 2,
        "title": "Successful transfer of 200 (A1001 → A1002)",
        "result": result,
        "balances": balances,
        "assertion": balances == {"A1001": 800, "A1002": 700},
        "status": "success",
    })

    # STEP 3: Insufficient funds
    before = get_balances()
    history_before = db[LAB10_TRANSFER_HISTORY].count_documents({})
    try:
        transfer("A1001", "A1002", 5000)
        step3_error = None
    except InsufficientFunds as exc:
        step3_error = str(exc)
    after = get_balances()
    history_after = db[LAB10_TRANSFER_HISTORY].count_documents({})
    steps.append({
        "step": 3,
        "title": "Insufficient funds – transfer 5000 (must roll back)",
        "before": before,
        "after": after,
        "error": step3_error,
        "rollback_verified": before == after and history_before == history_after,
        "status": "success" if before == after else "failed",
    })

    # STEP 3b: Filter guard only (no precheck)
    try:
        transfer("A1001", "A1002", 5000, precheck=False)
        step3b_error = None
    except InsufficientFunds as exc:
        step3b_error = str(exc)
    after3b = get_balances()
    steps.append({
        "step": "3b",
        "title": "Filter guard only – precheck OFF",
        "error": step3b_error,
        "balances": after3b,
        "rollback_verified": after3b == before,
        "status": "success" if after3b == before else "failed",
    })

    # STEP 3c: Crash after debit – proves real rollback
    try:
        transfer("A1001", "A1002", 100, fail_after_debit=True)
        step3c_error = None
    except RuntimeError as exc:
        step3c_error = str(exc)
    after3c = get_balances()
    steps.append({
        "step": "3c",
        "title": "Crash AFTER debit – proves transaction rollback",
        "error": step3c_error,
        "balances": after3c,
        "rollback_verified": after3c == before,
        "status": "success" if after3c == before else "failed",
    })

    # ACTIVITY: 10 concurrent transfers with retry + exponential backoff
    reset_accounts()
    results_list = []
    lock = threading.Lock()
    errors = []

    def worker():
        try:
            r = transfer("A1001", "A1002", 10, max_retries=8)
            with lock:
                results_list.append(r)
        except Exception as exc:
            with lock:
                errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final_balances = get_balances()
    total_money = sum(final_balances.values())
    all_retries = []
    for r in results_list:
        all_retries.extend(r.get("retries", []))

    steps.append({
        "step": "activity",
        "title": "10 concurrent transfers → write conflicts → exponential backoff",
        "total_transfers": len(results_list),
        "attempts_per_transfer": sorted([r["attempts"] for r in results_list]),
        "final_balances": final_balances,
        "total_money_preserved": total_money == 1500,
        "total_money": total_money,
        "transfer_history_count": db[LAB10_TRANSFER_HISTORY].count_documents({}),
        "retry_events": all_retries[:20],
        "errors": errors,
        "status": "success" if len(results_list) == 10 and total_money == 1500 else "partial",
    })

    report = {
        "lab": "10.1",
        "title": "Bank Transfer Transaction",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "transfer_history": get_transfer_history(),
    }

    filename = "lab10_1_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
    (RESULTS_DIR / filename).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    return report
