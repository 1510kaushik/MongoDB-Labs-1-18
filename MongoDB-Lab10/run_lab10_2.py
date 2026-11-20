
import json
from pathlib import Path
from datetime import datetime, timezone

from backend.db import client
from backend.lab10.inventory_reservation import (
    reset_product,
    get_product,
    get_all_products,
    get_all_orders,
    reserve_inventory,
    run_concurrent_reservations,
    benchmark_reservations,
)


RESULTS_DIR = Path("backend/lab10/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def run_tests():
    print("=" * 60)
    print("MONGODB LAB 10.2")
    print("INVENTORY RESERVATION TRANSACTION")
    print("=" * 60)

    results = {
        "lab": "Lab 10.2 - Inventory Reservation Transaction",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tests": [],
        "benchmarks": []
    }

    try:
        # MongoDB connection verification
        print("\nCHECKING MONGODB CONNECTION")

        hello = client.admin.command("hello")

        print("Replica set:", hello.get("setName"))
        print("Connected node:", hello.get("me"))
        print("Writable primary:", hello.get("isWritablePrimary"))

        if not hello.get("isWritablePrimary"):
            raise RuntimeError("Connected MongoDB node is not primary.")

        # Test 1: Initialize inventory
        print("\n" + "=" * 60)
        print("TEST 1: INITIALIZE INVENTORY")
        print("=" * 60)

        reset_product(
            "PROD001",
            "Wireless Headphones",
            stock=5
        )

        product = get_product("PROD001")

        print("Product:", json.dumps(product, indent=4, default=str))

        test1 = product is not None and product["stock"] == 5

        results["tests"].append({
            "test": "Initialize inventory",
            "status": "PASS" if test1 else "FAIL"
        })

        # Test 2: Single reservation
        print("\n" + "=" * 60)
        print("TEST 2: SINGLE INVENTORY RESERVATION")
        print("=" * 60)

        reset_product(
            "PROD001",
            "Wireless Headphones",
            stock=5
        )

        reservation = reserve_inventory(
            "PROD001",
            "CUSTOMER_SINGLE",
            1
        )

        print("Reservation:", json.dumps(
            reservation, indent=4, default=str
        ))

        print("Product after reservation:", get_product("PROD001"))

        test2 = (
            reservation["success"]
            and get_product("PROD001")["stock"] == 4
        )

        results["tests"].append({
            "test": "Single inventory reservation",
            "status": "PASS" if test2 else "FAIL"
        })

        # Test 3: Insufficient stock
        print("\n" + "=" * 60)
        print("TEST 3: INSUFFICIENT STOCK")
        print("=" * 60)

        reset_product(
            "PROD002",
            "Limited Edition Keyboard",
            stock=2
        )

        before = get_product("PROD002")

        failed_reservation = reserve_inventory(
            "PROD002",
            "CUSTOMER_TEST",
            5
        )

        after = get_product("PROD002")

        print("Reservation:", failed_reservation)
        print("Stock before:", before["stock"])
        print("Stock after:", after["stock"])

        test3 = (
            not failed_reservation["success"]
            and before["stock"] == after["stock"]
        )

        results["tests"].append({
            "test": "Insufficient stock protection",
            "status": "PASS" if test3 else "FAIL"
        })

        # Test 4: Concurrent reservations
        print("\n" + "=" * 60)
        print("TEST 4: CONCURRENT INVENTORY RESERVATIONS")
        print("=" * 60)

        concurrency = run_concurrent_reservations(
            "PROD_CONCURRENT",
            request_count=8,
            quantity=1
        )

        print(json.dumps(concurrency, indent=4, default=str))

        test4 = (
            concurrency["successful_reservations"] == 5
            and concurrency["failed_reservations"] == 3
            and concurrency["final_stock"] == 0
        )

        results["concurrency_test"] = concurrency

        results["tests"].append({
            "test": "8 concurrent requests against stock of 5",
            "status": "PASS" if test4 else "FAIL"
        })

        # Test 5: Performance benchmark
        print("\n" + "=" * 60)
        print("TEST 5: PERFORMANCE BENCHMARK")
        print("=" * 60)

        thread_counts = [1, 4, 8, 16]

        for method in ["transactional", "atomic"]:
            print(f"\nBenchmark method: {method.upper()}")

            for threads in thread_counts:
                benchmark = benchmark_reservations(
                    method=method,
                    thread_count=threads,
                    total_requests=100
                )

                results["benchmarks"].append(benchmark)

                print(
                    f"Threads: {benchmark['threads']} | "
                    f"Success: {benchmark['successful']} | "
                    f"Failed: {benchmark['failed']} | "
                    f"Time: {benchmark['elapsed_seconds']} sec | "
                    f"Throughput: "
                    f"{benchmark['throughput_requests_per_second']} "
                    f"requests/sec"
                )

        # Final database details
        print("\n" + "=" * 60)
        print("FINAL INVENTORY")
        print("=" * 60)

        final_products = get_all_products()

        print(json.dumps(
            final_products,
            indent=4,
            default=str
        ))

        print("\nTotal orders:", len(get_all_orders()))

        results["final_products"] = final_products
        results["total_orders"] = len(get_all_orders())

        # Summary
        passed = sum(
            1 for test in results["tests"]
            if test["status"] == "PASS"
        )

        failed = len(results["tests"]) - passed

        results["summary"] = {
            "total_tests": len(results["tests"]),
            "passed": passed,
            "failed": failed,
            "overall_status": "PASS" if failed == 0 else "FAIL"
        }

        # Save results
        output_file = RESULTS_DIR / "lab10_2_results.json"

        with output_file.open("w", encoding="utf-8") as file:
            json.dump(results, file, indent=4, default=str)

        print("\n" + "=" * 60)
        print("LAB 10.2 TEST SUMMARY")
        print("=" * 60)

        for test in results["tests"]:
            print(f"{test['test']}: {test['status']}")

        print("\nPassed:", passed)
        print("Failed:", failed)
        print("Overall status:", results["summary"]["overall_status"])
        print("\nResults saved to:", output_file)

        if failed:
            raise RuntimeError("One or more Lab 10.2 tests failed.")

    except Exception as error:
        print("\nLAB 10.2 FAILED:", error)
        raise

    finally:
        client.close()


if __name__ == "__main__":
    run_tests()
