
import json
from pathlib import Path
from datetime import datetime, timezone

from backend.db import client, db
from backend.lab10.bank_transfer import (
    initialize_accounts,
    get_all_accounts,
    transfer_money,
    get_transaction_history,
    InsufficientFundsError,
)

RESULTS_DIR = Path("backend/lab10/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def test_successful_transfer():
    print("\nTEST 1: Successful bank transfer")

    result = transfer_money("ACC001", "ACC002", 100)

    print("Transfer result:", result)
    print("Balances:", get_all_accounts())

    return result["success"]


def test_insufficient_funds():
    print("\nTEST 2: Insufficient funds rollback")

    before = get_all_accounts()

    try:
        transfer_money("ACC001", "ACC002", 100000)
        print("ERROR: Transfer should have failed.")
        return False
    except InsufficientFundsError as error:
        print("Expected error:", error)

    after = get_all_accounts()

    passed = before == after

    print("Balances before:", before)
    print("Balances after:", after)
    print("Rollback verified:", "PASS" if passed else "FAIL")

    return passed


def test_forced_rollback():
    print("\nTEST 3: Forced transaction rollback after debit")

    before = get_all_accounts()

    try:
        with client.start_session() as session:
            with session.start_transaction():

                debit = db.accounts.update_one(
                    {
                        "account_id": "ACC001",
                        "balance": {"$gte": 50}
                    },
                    {
                        "$inc": {"balance": -50}
                    },
                    session=session
                )

                if debit.modified_count != 1:
                    raise RuntimeError("Debit failed.")

                print("Debit executed inside transaction.")

                # Simulate an error after the debit.
                # The transaction should be aborted.
                raise RuntimeError("SIMULATED FAILURE")

    except RuntimeError as error:
        if str(error) != "SIMULATED FAILURE":
            raise

        print("Expected simulated error:", error)

    after = get_all_accounts()

    passed = before == after

    print("Balances before:", before)
    print("Balances after:", after)
    print("Forced rollback:", "PASS" if passed else "FAIL")

    return passed


def run_tests():
    print("=" * 50)
    print("MONGODB LAB 10.1")
    print("BANK TRANSFER TRANSACTION")
    print("=" * 50)

    results = {
        "lab": "Lab 10.1 - Bank Transfer Transaction",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tests": []
    }

    try:
        print("\nChecking MongoDB connection...")

        hello = client.admin.command("hello")

        print("Replica set:", hello.get("setName"))
        print("Connected node:", hello.get("me"))
        print("Writable primary:", hello.get("isWritablePrimary"))

        if not hello.get("isWritablePrimary"):
            raise RuntimeError("Connected node is not the primary.")

        print("\nInitializing bank accounts...")
        initialize_accounts()

        print("\nInitial account balances:")
        print(json.dumps(get_all_accounts(), indent=4))

        # Test 1
        successful = test_successful_transfer()

        results["tests"].append({
            "test": "Successful bank transfer",
            "status": "PASS" if successful else "FAIL"
        })

        # Test 2
        insufficient = test_insufficient_funds()

        results["tests"].append({
            "test": "Insufficient funds rollback",
            "status": "PASS" if insufficient else "FAIL"
        })

        # Test 3
        forced_rollback = test_forced_rollback()

        results["tests"].append({
            "test": "Forced transaction rollback after debit",
            "status": "PASS" if forced_rollback else "FAIL"
        })

        print("\nTransaction history:")
        history = get_transaction_history()
        print(json.dumps(history, indent=4, default=str))

        results["transaction_history"] = history
        results["final_accounts"] = get_all_accounts()

        passed_count = sum(
            1 for test in results["tests"]
            if test["status"] == "PASS"
        )

        results["summary"] = {
            "total_tests": len(results["tests"]),
            "passed": passed_count,
            "failed": len(results["tests"]) - passed_count,
            "overall_status": (
                "PASS" if passed_count == len(results["tests"]) else "FAIL"
            )
        }

        output_file = RESULTS_DIR / "lab10_1_results.json"

        with output_file.open("w", encoding="utf-8") as file:
            json.dump(results, file, indent=4, default=str)

        print("\n" + "=" * 50)
        print("TEST SUMMARY")
        print("=" * 50)

        for test in results["tests"]:
            print(f'{test["test"]}: {test["status"]}')

        print("\nOverall status:", results["summary"]["overall_status"])
        print("Results saved to:", output_file)

    except Exception as error:
        print("\nLAB 10.1 FAILED:", error)
        raise

    finally:
        client.close()


if __name__ == "__main__":
    run_tests()
