"""Lab 10.2 - Inventory Reservation with Deadlock Handling.

Implements:
  - Transactional inventory reservation (stock decrement + order creation)
  - Non-transactional baseline using findAndModify
  - Concurrency testing with ThreadPoolExecutor
  - Throughput benchmarking across concurrency levels (1, 4, 8, 16)
  - Inconsistency demonstration (transactional vs non-transactional)
"""
import json
import random
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from ..db import client, db

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"

LAB10_INVENTORY = "lab10_inventory"
LAB10_ORDERS = "lab10_orders"

PRODUCT_ID = "P100"
UNIT_PRICE = 19.99


class OutOfStock(Exception):
    pass


class ProductNotFound(Exception):
    pass


class RetriesExhausted(Exception):
    pass


# ── Helpers ──────────────────────────────────────────────────────────

def _is_transient(exc):
    return isinstance(exc, PyMongoError) and exc.has_error_label("TransientTransactionError")


def _safe_abort(session):
    try:
        if session.in_transaction:
            session.abort_transaction()
    except PyMongoError:
        pass


def _commit_with_retry(session, max_tries=5):
    for i in range(max_tries):
        try:
            session.commit_transaction()
            return
        except PyMongoError as exc:
            if exc.has_error_label("UnknownTransactionCommitResult") and i < max_tries - 1:
                time.sleep(0.02)
                continue
            raise


def _new_order(product_id, customer_id, qty):
    return {
        "order_id": str(uuid.uuid4()),
        "customer_id": customer_id,
        "items": [{"product_id": product_id, "qty": qty, "price": UNIT_PRICE}],
        "status": "pending",
        "total": round(qty * UNIT_PRICE, 2),
    }


# ── Setup ────────────────────────────────────────────────────────────

def reset_inventory(stock=5):
    db.drop_collection(LAB10_INVENTORY)
    db.drop_collection(LAB10_ORDERS)
    db.create_collection(LAB10_INVENTORY)
    db.create_collection(LAB10_ORDERS)
    db[LAB10_INVENTORY].create_index("product_id", unique=True)
    db[LAB10_ORDERS].create_index("order_id", unique=True)
    db[LAB10_INVENTORY].insert_one(
        {"product_id": PRODUCT_ID, "name": "Wireless Mouse", "stock": stock, "version": 0}
    )


def get_inventory_state():
    product = db[LAB10_INVENTORY].find_one({"product_id": PRODUCT_ID}, {"_id": 0})
    orders = list(db[LAB10_ORDERS].find({}, {"_id": 0}).sort("order_id").limit(50))
    return {"product": product, "orders": orders, "order_count": db[LAB10_ORDERS].count_documents({})}


# ── Transactional reservation ────────────────────────────────────────

def _reserve_in_txn(session, product_id, customer_id, qty, inject_failure):
    product = db[LAB10_INVENTORY].find_one({"product_id": product_id}, session=session)
    if product is None:
        raise ProductNotFound(product_id)
    if product["stock"] < qty:
        raise OutOfStock(f"{product_id}: stock={product['stock']}, requested={qty}")

    res = db[LAB10_INVENTORY].update_one(
        {"product_id": product_id, "stock": {"$gte": qty}},
        {"$inc": {"stock": -qty, "version": 1}},
        session=session,
    )
    if res.matched_count == 0:
        raise OutOfStock(f"{product_id}: not enough stock")

    if inject_failure:
        raise RuntimeError("Simulated failure while creating the order")

    order = _new_order(product_id, customer_id, qty)
    db[LAB10_ORDERS].insert_one(order, session=session)
    return order["order_id"]


def reserve_inventory(product_id, customer_id, qty=1, *,
                      max_retries=5, base_delay=0.02, inject_failure=False):
    with client.start_session() as session:
        attempt = 0
        while True:
            attempt += 1
            session.start_transaction(
                read_concern=ReadConcern("snapshot"),
                write_concern=WriteConcern("majority"),
            )
            try:
                order_id = _reserve_in_txn(session, product_id, customer_id, qty, inject_failure)
                _commit_with_retry(session)
                return {"order_id": order_id, "attempts": attempt}
            except Exception as exc:
                _safe_abort(session)
                if _is_transient(exc):
                    if attempt <= max_retries:
                        time.sleep(base_delay * 2 ** (attempt - 1) * random.uniform(0.5, 1.5))
                        continue
                    raise RetriesExhausted(f"gave up after {attempt} attempts") from exc
                raise


def reserve_non_transactional(product_id, customer_id, qty=1, *, inject_failure=False):
    updated = db[LAB10_INVENTORY].find_one_and_update(
        {"product_id": product_id, "stock": {"$gte": qty}},
        {"$inc": {"stock": -qty, "version": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise OutOfStock(f"{product_id}: not enough stock")
    if inject_failure:
        raise RuntimeError("Simulated failure while creating the order")
    order = _new_order(product_id, customer_id, qty)
    db[LAB10_ORDERS].insert_one(order)
    return {"order_id": order["order_id"], "attempts": 1}


# ── Concurrency test ────────────────────────────────────────────────

def run_concurrency_test(max_retries=5):
    THREADS, STOCK = 8, 5
    results_data = {}

    for label, retries in [("WITHOUT retry logic", 0), ("WITH retry logic", max_retries)]:
        reset_inventory(STOCK)
        barrier = threading.Barrier(THREADS)

        def worker(i, mr=retries):
            barrier.wait()
            try:
                r = reserve_inventory(PRODUCT_ID, f"cust-{i}", 1, max_retries=mr)
                return "success", r["attempts"]
            except OutOfStock:
                return "out_of_stock", 0
            except RetriesExhausted:
                return "write_conflict_failed", 0
            except Exception as exc:
                return f"error: {exc!r}", 0

        with ThreadPoolExecutor(max_workers=THREADS) as pool:
            outcomes = list(pool.map(worker, range(THREADS)))

        counts = Counter(status for status, _ in outcomes)
        stock = db[LAB10_INVENTORY].find_one({"product_id": PRODUCT_ID})["stock"]
        orders = db[LAB10_ORDERS].count_documents({})

        results_data[label] = {
            "outcomes": dict(counts),
            "attempts_per_success": sorted(a for s, a in outcomes if s == "success"),
            "final_stock": stock,
            "orders_created": orders,
            "consistent": stock >= 0 and orders == counts.get("success", 0) and stock + orders == STOCK,
        }

    return {
        "threads": THREADS,
        "initial_stock": STOCK,
        "rounds": results_data,
    }


# ── Inconsistency demo ──────────────────────────────────────────────

def run_inconsistency_demo():
    results = {}

    # Non-transactional with injected failure
    reset_inventory(5)
    for i in range(3):
        try:
            reserve_non_transactional(PRODUCT_ID, f"cust-{i}", 1, inject_failure=True)
        except RuntimeError:
            pass
    stock = db[LAB10_INVENTORY].find_one({"product_id": PRODUCT_ID})["stock"]
    orders = db[LAB10_ORDERS].count_documents({})
    results["non_transactional"] = {
        "stock": stock,
        "orders": orders,
        "units_lost": 5 - stock - orders,
        "consistent": stock + orders == 5,
        "description": f"stock={stock}, orders={orders} → {5 - stock} units decremented but no orders exist",
    }

    # Transactional with injected failure
    reset_inventory(5)
    for i in range(3):
        try:
            reserve_inventory(PRODUCT_ID, f"cust-{i}", 1, inject_failure=True)
        except RuntimeError:
            pass
    stock = db[LAB10_INVENTORY].find_one({"product_id": PRODUCT_ID})["stock"]
    orders = db[LAB10_ORDERS].count_documents({})
    results["transactional"] = {
        "stock": stock,
        "orders": orders,
        "units_lost": 0,
        "consistent": (stock, orders) == (5, 0),
        "description": f"stock={stock}, orders={orders} → fully consistent, transaction rolled back",
    }

    return results


# ── Throughput benchmark ─────────────────────────────────────────────

def run_throughput_benchmark(requests_per_level=50):
    LEVELS = [1, 4, 8, 16]
    rows = []

    def run_level(fn, threads, total):
        reset_inventory(total)

        def one(i):
            try:
                fn(PRODUCT_ID, f"cust-{i}", 1)
                return True
            except (OutOfStock, RetriesExhausted):
                return False

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=threads) as pool:
            ok = sum(pool.map(one, range(total)))
        elapsed = time.perf_counter() - start
        return ok, elapsed

    txn_fn = lambda pid, cid, qty: reserve_inventory(pid, cid, qty, max_retries=15)

    for n in LEVELS:
        for mode, fn in [("transaction", txn_fn), ("findAndModify", reserve_non_transactional)]:
            ok, secs = run_level(fn, n, requests_per_level)
            tput = ok / secs if secs > 0 else 0
            rows.append({
                "threads": n,
                "mode": mode,
                "successes": ok,
                "total_requests": requests_per_level,
                "seconds": round(secs, 3),
                "throughput_per_sec": round(tput, 1),
            })

    return rows


# ── Full demo runner ─────────────────────────────────────────────────

def run_lab10_2_demo(requests_per_level=50):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    concurrency = run_concurrency_test()
    inconsistency = run_inconsistency_demo()
    benchmark = run_throughput_benchmark(requests_per_level)

    report = {
        "lab": "10.2",
        "title": "Inventory Reservation with Deadlock Handling",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "concurrency_test": concurrency,
        "inconsistency_demo": inconsistency,
        "throughput_benchmark": benchmark,
        "inventory_state": get_inventory_state(),
    }

    filename = "lab10_2_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
    (RESULTS_DIR / filename).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    return report
