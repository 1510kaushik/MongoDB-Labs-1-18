from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime, timezone
from statistics import mean, median
from time import perf_counter_ns
import os
import uuid
import csv
import json

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env", encoding="utf-8-sig")

client = MongoClient(
    os.environ["MONGODB_URI"],
    serverSelectionTimeoutMS=5000
)
db = client[os.environ["MONGODB_DATABASE"]]

REPEATS = 100
WARMUPS = 10

tenants = sorted(
    doc["tenant_id"]
    for doc in db.tenants.find({}, {"tenant_id": 1, "_id": 0})
)

if len(tenants) != 5:
    raise RuntimeError(f"Expected 5 tenants, found {len(tenants)}")

target_collections = {
    tenant: f"tasks_tenant_{tenant}"
    for tenant in tenants
}

# Verify both strategies contain equivalent data.
for tenant in tenants:
    source_count = db.tasks.count_documents({"tenant_id": tenant})
    target_count = db[target_collections[tenant]].count_documents({})
    foreign_count = db[target_collections[tenant]].count_documents(
        {"tenant_id": {"$ne": tenant}}
    )

    if source_count != 100 or target_count != 100 or foreign_count != 0:
        raise RuntimeError(f"Validation failed for {tenant}")

if db.tasks.count_documents({}) != 500:
    raise RuntimeError("Expected 500 shared documents")


# Create equivalent indexes for tenant listing.
db.tasks.create_index(
    [("tenant_id", ASCENDING), ("created_at", DESCENDING)],
    name="tenant_created_at_benchmark"
)

for collection_name in target_collections.values():
    db[collection_name].create_index(
        [("created_at", DESCENDING)],
        name="created_at_benchmark"
    )


def shared_listing():
    return list(
        db.tasks.find({"tenant_id": tenants[0]})
        .sort("created_at", DESCENDING)
    )


def isolated_listing():
    return list(
        db[target_collections[tenants[0]]]
        .find({})
        .sort("created_at", DESCENDING)
    )


def shared_analytics():
    pipeline = [
        {
            "$group": {
                "_id": {
                    "tenant_id": "$tenant_id",
                    "status": "$status"
                },
                "task_count": {"$sum": 1}
            }
        }
    ]

    return sorted(
        (
            row["_id"]["tenant_id"],
            row["_id"]["status"],
            row["task_count"]
        )
        for row in db.tasks.aggregate(pipeline)
    )


def isolated_analytics():
    combined = []

    for tenant in tenants:
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "task_count": {"$sum": 1}
                }
            }
        ]

        for row in db[target_collections[tenant]].aggregate(pipeline):
            combined.append((tenant, row["_id"], row["task_count"]))

    return sorted(combined)


# These functions measure only the insert operation.
# Cleanup takes place outside the measured interval.
def create_shared_task():
    doc_id = str(uuid.uuid4())

    document = {
        "id": doc_id,
        "tenant_id": tenants[0],
        "title": "Benchmark task",
        "status": "pending",
        "priority": "medium",
        "created_at": datetime.now(timezone.utc)
    }

    start = perf_counter_ns()
    db.tasks.insert_one(document)
    elapsed = perf_counter_ns() - start

    db.tasks.delete_one({
        "id": doc_id,
        "tenant_id": tenants[0]
    })

    return elapsed


def create_isolated_task():
    doc_id = str(uuid.uuid4())

    document = {
        "id": doc_id,
        "tenant_id": tenants[0],
        "title": "Benchmark task",
        "status": "pending",
        "priority": "medium",
        "created_at": datetime.now(timezone.utc)
    }

    collection = db[target_collections[tenants[0]]]

    start = perf_counter_ns()
    collection.insert_one(document)
    elapsed = perf_counter_ns() - start

    collection.delete_one({"id": doc_id})

    return elapsed


def measure(name, operation, iterations=REPEATS, returns_elapsed=False):
    # Warm-up runs are excluded from the measurements.
    for _ in range(WARMUPS):
        operation()

    timings = []

    for _ in range(iterations):
        if returns_elapsed:
            # Write functions return their measured insert duration.
            elapsed_ns = operation()
        else:
            # For reads and analytics, measure the actual function call.
            start = perf_counter_ns()
            operation()
            elapsed_ns = perf_counter_ns() - start

        if not isinstance(elapsed_ns, int) or elapsed_ns <= 0:
            raise RuntimeError(f"Invalid timing for {name}: {elapsed_ns}")

        timings.append(elapsed_ns / 1_000_000)

    return {
        "operation": name,
        "iterations": iterations,
        "average_ms": round(mean(timings), 4),
        "median_ms": round(median(timings), 4),
        "minimum_ms": round(min(timings), 4),
        "maximum_ms": round(max(timings), 4)
    }


def main():
    results = []

    print("Database:", db.name)
    print("Tenants:", len(tenants))
    print("Shared documents:", db.tasks.count_documents({}))
    print("Benchmark iterations:", REPEATS)

    # Confirm result equivalence before timing.
    print("\nListing result equivalence:")
    assert len(shared_listing()) == 100
    assert len(isolated_listing()) == 100
    print("PASSED")

    print("\nAnalytics result equivalence:")
    assert shared_analytics() == isolated_analytics()
    print("PASSED")

    print("\nBenchmarking tenant listing...")
    results.append(
        measure("Document-level: list tenant tasks", shared_listing)
    )
    results.append(
        measure("Collection-per-tenant: list tenant tasks", isolated_listing)
    )

    print("Benchmarking task creation...")
    results.append(
        measure(
            "Document-level: create task",
            create_shared_task,
            returns_elapsed=True
        )
    )
    results.append(
        measure(
            "Collection-per-tenant: create task",
            create_isolated_task,
            returns_elapsed=True
        )
    )

    print("Benchmarking cross-tenant analytics...")
    results.append(
        measure(
            "Document-level: cross-tenant analytics",
            shared_analytics,
            iterations=50
        )
    )
    results.append(
        measure(
            "Collection-per-tenant: cross-tenant analytics",
            isolated_analytics,
            iterations=50
        )
    )

    # Verify no benchmark documents were left behind.
    for tenant in tenants:
        assert db.tasks.count_documents({"tenant_id": tenant}) == 100
        assert db[target_collections[tenant]].count_documents({}) == 100

    output_dir = BASE / "results"
    output_dir.mkdir(exist_ok=True)

    with (output_dir / "performance_benchmark.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    with (output_dir / "performance_benchmark.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(results, file, indent=4)

    print("\n--- CORRECTED PERFORMANCE RESULTS ---")
    for result in results:
        print(
            f"{result['operation']}: "
            f"average={result['average_ms']} ms, "
            f"median={result['median_ms']} ms"
        )

    print("\nData validation: PASSED")
    print("Shared documents: 500")
    print("Tenant-specific documents: 500")
    print("Corrected CSV and JSON results saved.")


if __name__ == "__main__":
    try:
        main()
    finally:
        client.close()
