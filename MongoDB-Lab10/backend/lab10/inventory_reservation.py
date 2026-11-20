
import time
import uuid
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from backend.db import client, db


products = db["products"]
orders = db["orders"]


class ProductNotFoundError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class RetryableReservationError(Exception):
    pass


def reset_product(product_id, name, stock):
    """Create or reset a product for a repeatable experiment."""

    products.replace_one(
        {"product_id": product_id},
        {
            "product_id": product_id,
            "name": name,
            "stock": stock,
            "version": 1,
            "updated_at": datetime.now(timezone.utc)
        },
        upsert=True
    )


def get_product(product_id):
    return products.find_one(
        {"product_id": product_id},
        {"_id": 0}
    )


def get_all_products():
    return list(products.find({}, {"_id": 0}))


def get_all_orders():
    return list(
        orders.find({}, {"_id": 0}).sort("created_at", -1)
    )


def reserve_inventory(
    product_id,
    customer_id,
    quantity,
    max_retries=10
):
    """
    Reserve stock and create an order in one MongoDB transaction.
    """

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    order_id = str(uuid.uuid4())

    for attempt in range(max_retries):
        try:
            with client.start_session() as session:
                with session.start_transaction():

                    product = products.find_one(
                        {"product_id": product_id},
                        session=session
                    )

                    if product is None:
                        raise ProductNotFoundError(
                            f"Product {product_id} was not found."
                        )

                    if product["stock"] < quantity:
                        raise InsufficientStockError(
                            "Not enough stock available."
                        )

                    update_result = products.update_one(
                        {
                            "product_id": product_id,
                            "stock": {"$gte": quantity},
                            "version": product["version"]
                        },
                        {
                            "$inc": {
                                "stock": -quantity,
                                "version": 1
                            },
                            "$set": {
                                "updated_at": datetime.now(timezone.utc)
                            }
                        },
                        session=session
                    )

                    if update_result.modified_count != 1:
                        raise RetryableReservationError(
                            "Product changed during reservation."
                        )

                    orders.insert_one(
                        {
                            "order_id": order_id,
                            "customer_id": customer_id,
                            "items": [
                                {
                                    "product_id": product_id,
                                    "quantity": quantity
                                }
                            ],
                            "status": "PENDING",
                            "total": 0,
                            "created_at": datetime.now(timezone.utc)
                        },
                        session=session
                    )

            return {
                "success": True,
                "order_id": order_id,
                "customer_id": customer_id,
                "product_id": product_id,
                "quantity": quantity,
                "message": "Inventory reserved successfully.",
                "attempts": attempt + 1
            }

        except InsufficientStockError as error:
            return {
                "success": False,
                "customer_id": customer_id,
                "product_id": product_id,
                "message": str(error),
                "reason": "INSUFFICIENT_STOCK"
            }

        except ProductNotFoundError as error:
            return {
                "success": False,
                "customer_id": customer_id,
                "product_id": product_id,
                "message": str(error),
                "reason": "PRODUCT_NOT_FOUND"
            }

        except RetryableReservationError:
            if attempt == max_retries - 1:
                return {
                    "success": False,
                    "customer_id": customer_id,
                    "product_id": product_id,
                    "message": "Maximum retry attempts reached.",
                    "reason": "RETRY_LIMIT"
                }

            time.sleep(0.02 * (attempt + 1))

        except PyMongoError as error:
            if error.has_error_label("TransientTransactionError"):
                if attempt == max_retries - 1:
                    return {
                        "success": False,
                        "customer_id": customer_id,
                        "product_id": product_id,
                        "message": str(error),
                        "reason": "TRANSACTION_RETRY_LIMIT"
                    }

                time.sleep(0.02 * (attempt + 1))
                continue

            raise

    return {
        "success": False,
        "message": "Reservation failed.",
        "reason": "UNKNOWN"
    }


def reserve_inventory_atomic(
    product_id,
    customer_id,
    quantity
):
    """
    Comparison implementation using one atomic stock update.

    The stock update is atomic, but the order insert is a separate
    operation and is not part of the same transaction.
    """

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    updated_product = products.find_one_and_update(
        {
            "product_id": product_id,
            "stock": {"$gte": quantity}
        },
        {
            "$inc": {
                "stock": -quantity,
                "version": 1
            },
            "$set": {
                "updated_at": datetime.now(timezone.utc)
            }
        },
        return_document=ReturnDocument.AFTER
    )

    if updated_product is None:
        return {
            "success": False,
            "customer_id": customer_id,
            "product_id": product_id,
            "message": "Insufficient stock or product not found.",
            "reason": "RESERVATION_FAILED"
        }

    order_id = str(uuid.uuid4())

    orders.insert_one(
        {
            "order_id": order_id,
            "customer_id": customer_id,
            "items": [
                {
                    "product_id": product_id,
                    "quantity": quantity
                }
            ],
            "status": "PENDING",
            "total": 0,
            "created_at": datetime.now(timezone.utc)
        }
    )

    return {
        "success": True,
        "order_id": order_id,
        "customer_id": customer_id,
        "product_id": product_id,
        "quantity": quantity,
        "message": "Inventory reserved using atomic update."
    }


def run_concurrent_reservations(
    product_id,
    request_count=8,
    quantity=1
):
    """Run multiple reservation requests concurrently."""

    reset_product(
        product_id,
        "Concurrent Test Product",
        stock=5
    )

    results = []

    with ThreadPoolExecutor(max_workers=request_count) as executor:
        futures = [
            executor.submit(
                reserve_inventory,
                product_id,
                f"CUSTOMER_{number:03d}",
                quantity
            )
            for number in range(1, request_count + 1)
        ]

        for future in futures:
            results.append(future.result())

    successful = sum(
        1 for result in results if result["success"]
    )

    failed = len(results) - successful

    return {
        "product_id": product_id,
        "requests": request_count,
        "initial_stock": 5,
        "successful_reservations": successful,
        "failed_reservations": failed,
        "final_stock": get_product(product_id)["stock"],
        "results": results
    }


def benchmark_reservations(
    method,
    thread_count,
    total_requests=100
):
    """
    Measure reservation throughput for a selected method
    and number of worker threads.
    """

    product_id = (
        f"BENCH_{method.upper()}_{thread_count}"
    )

    reset_product(
        product_id,
        "Performance Benchmark Product",
        stock=total_requests
    )

    if method == "transactional":
        reservation_function = reserve_inventory
    elif method == "atomic":
        reservation_function = reserve_inventory_atomic
    else:
        raise ValueError("Unknown benchmark method.")

    start_time = time.perf_counter()

    with ThreadPoolExecutor(max_workers=thread_count) as executor:
        futures = [
            executor.submit(
                reservation_function,
                product_id,
                f"BENCH_CUSTOMER_{number:04d}",
                1
            )
            for number in range(total_requests)
        ]

        results = [future.result() for future in futures]

    elapsed = time.perf_counter() - start_time

    successful = sum(
        1 for result in results if result["success"]
    )

    failed = total_requests - successful

    throughput = (
        successful / elapsed if elapsed > 0 else 0
    )

    return {
        "method": method,
        "threads": thread_count,
        "total_requests": total_requests,
        "successful": successful,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 4),
        "throughput_requests_per_second": round(
            throughput, 2
        ),
        "final_stock": get_product(product_id)["stock"]
    }
