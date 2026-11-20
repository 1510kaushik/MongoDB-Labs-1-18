import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId
from pymongo.errors import PyMongoError

from .connection import client, db

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

HOTSPOT_COLLECTION = "hotspot_data"
HASHED_COLLECTION = "even_data"
DOCUMENT_COUNT = 10_000


SHARD_KEY_MATRIX = [
    {
        "key": "order_id",
        "cardinality": "High, assuming unique order IDs",
        "distribution": "Generally good for unique, non-monotonic values; sequential IDs can create an insert hotspot with ranged sharding",
        "query_targeting": "Good for order ID equality; customer queries may scatter across shards",
        "assessment": "Useful when order ID lookups dominate"
    },
    {
        "key": "customer_id",
        "cardinality": "Depends on the number of customers",
        "distribution": "Can be uneven when some customers create many more orders",
        "query_targeting": "Good for customer-specific equality queries",
        "assessment": "Useful when customer order history is the dominant workload"
    },
    {
        "key": "order_date",
        "cardinality": "High over time",
        "distribution": "Monotonically increasing values can concentrate new inserts on the chunk containing the highest values",
        "query_targeting": "Good for date-range queries when ranges align with chunk placement",
        "assessment": "Risk of write hotspots for continuously arriving orders"
    },
    {
        "key": "hashed customer_id",
        "cardinality": "Inherits cardinality from customer_id",
        "distribution": "Hashing generally spreads values more evenly across chunks",
        "query_targeting": "Customer equality queries can target a shard; customer ID range queries generally scatter",
        "assessment": "Strong candidate when customer equality queries and balanced distribution are priorities"
    }
]


def get_shard_key_analysis():
    return {
        "title": "Lab 11.1 - Evaluate Shard Key Choices",
        "recommendation": "Hashed customer_id",
        "justification": (
            "For a workload dominated by customer-specific equality queries, "
            "hashed customer_id offers a useful balance between query targeting "
            "and distribution. Validate this choice against real query frequency, "
            "customer activity skew, and range-query requirements."
        ),
        "decision_matrix": SHARD_KEY_MATRIX,
        "resharding": {
            "available_since": "MongoDB 5.0",
            "command": (
                'db.adminCommand({reshardCollection: "database.collection", '
                'key: {customer_id: "hashed"}})'
            ),
            "steps": [
                "Review query patterns and select the new shard key.",
                "Check unique-index compatibility and operational requirements.",
                "Run reshardCollection through mongos with the new key.",
                "MongoDB prepares recipient collections and required indexes.",
                "MongoDB clones documents and applies ongoing writes.",
                "MongoDB catches up changes, briefly blocks collection writes, and commits the new routing metadata.",
                "Verify the new shard-key pattern and data distribution."
            ],
            "limitations": [
                "Only one collection can be resharded at a time.",
                "The new shard key must satisfy existing unique-index requirements.",
                "Do not start index builds or perform prohibited collection DDL operations during resharding.",
                "The final cutover can temporarily block writes and increase application latency.",
                "Resharding requires additional cluster resources for copying and rebuilding data.",
                "Sharded time-series collections cannot be resharded."
            ]
        }
    }


def _extract_shards(value, found=None):
    if found is None:
        found = set()

    if isinstance(value, dict):
        shard_name = value.get("shardName")
        if isinstance(shard_name, str):
            found.add(shard_name)

        for key, child in value.items():
            if key == "shards" and isinstance(child, dict):
                found.update(child.keys())
            _extract_shards(child, found)

    elif isinstance(value, list):
        for child in value:
            _extract_shards(child, found)

    return sorted(found)


def _collection_stats(collection_name):
    result = db.command({"collStats": collection_name})
    shard_stats = result.get("shards", {})

    per_shard = {}
    for shard_name, values in shard_stats.items():
        per_shard[shard_name] = {
            "count": values.get("count", 0),
            "size": values.get("size", 0),
            "storageSize": values.get("storageSize", 0)
        }

    return {
        "collection": collection_name,
        "total_count": result.get("count", 0),
        "total_size_bytes": result.get("size", 0),
        "per_shard": per_shard
    }


def _run_explain(collection_name, query):
    command = {
        "explain": {
            "find": collection_name,
            "filter": query
        },
        "verbosity": "executionStats"
    }

    result = db.command(command)
    return {
        "targeted_shards": _extract_shards(result),
        "execution_time_ms": result.get("executionStats", {}).get(
            "executionTimeMillis"
        ),
        "total_docs_examined": result.get("executionStats", {}).get(
            "totalDocsExamined"
        ),
        "total_docs_returned": result.get("executionStats", {}).get(
            "nReturned"
        ),
        "query_planner": result.get("queryPlanner", {}),
        "raw_execution_stats": result.get("executionStats", {})
    }


def run_hotspot_experiment():
    try:
        client.admin.command({"ping": 1})

        db_name = db.name
        client.admin.command({"enableSharding": db_name})

        # Only the two Lab 11 experiment collections are dropped.
        db.drop_collection(HOTSPOT_COLLECTION)
        db.drop_collection(HASHED_COLLECTION)

        hotspot = db[HOTSPOT_COLLECTION]
        even = db[HASHED_COLLECTION]

        # Timestamp-based ranged shard key.
        hotspot.create_index([("ts", 1)])
        client.admin.command({
            "shardCollection": f"{db_name}.{HOTSPOT_COLLECTION}",
            "key": {"ts": 1}
        })

        # Hashed shard key. Initial chunks help demonstrate distribution
        # on a small local dataset.
        even.create_index([("user_id", "hashed")])
        client.admin.command({
            "shardCollection": f"{db_name}.{HASHED_COLLECTION}",
            "key": {"user_id": "hashed"},
            "numInitialChunks": 8
        })

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)

        timestamp_docs = []
        hashed_docs = []

        for index in range(DOCUMENT_COUNT):
            timestamp_docs.append({
                "ts": start + timedelta(seconds=index),
                "order_id": f"ORD-{index:06d}",
                "amount": 100 + (index % 900),
                "description": "Lab 11 timestamp hotspot test"
            })

            hashed_docs.append({
                "user_id": ObjectId(),
                "order_id": f"HASH-{index:06d}",
                "amount": 100 + (index % 900),
                "description": "Lab 11 hashed distribution test"
            })

        hotspot.insert_many(timestamp_docs, ordered=False)
        even.insert_many(hashed_docs, ordered=False)

        # Wait for the router to provide current collection statistics.
        timestamp_stats = _collection_stats(HOTSPOT_COLLECTION)
        hashed_stats = _collection_stats(HASHED_COLLECTION)

        # Equivalent time-window query on the timestamp collection.
        range_start = start + timedelta(seconds=1000)
        range_end = start + timedelta(seconds=2000)

        timestamp_query = {
            "ts": {
                "$gte": range_start,
                "$lt": range_end
            }
        }

        # Range query against the original field of the hashed shard key.
        sorted_ids = sorted(doc["user_id"] for doc in hashed_docs)
        user_range_query = {
            "user_id": {
                "$gte": sorted_ids[1000],
                "$lt": sorted_ids[2000]
            }
        }

        timestamp_explain = _run_explain(
            HOTSPOT_COLLECTION,
            timestamp_query
        )

        hashed_explain = _run_explain(
            HASHED_COLLECTION,
            user_range_query
        )

        report = {
            "lab": "11.2 - Shard Key Hotspot Detection",
            "database": db_name,
            "documents_inserted_per_collection": DOCUMENT_COUNT,
            "timestamp_collection": timestamp_stats,
            "hashed_collection": hashed_stats,
            "range_query_comparison": {
                "timestamp_range_query": timestamp_explain,
                "hashed_original_field_range_query": hashed_explain
            },
            "interpretation": [
                "A monotonically increasing ranged shard key directs new inserts toward the chunk containing the highest key values.",
                "A hashed shard key distributes hashed values across chunks, which can improve write distribution.",
                "Range queries on the original field of a hashed shard key generally require scatter-gather because hashing does not preserve the original value order.",
                "Actual shard counts depend on chunk placement and balancer activity; use the measured statistics above rather than assuming a fixed split."
            ]
        }

        output_path = RESULTS_DIR / "lab11_2_hotspot_report.json"
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(report, file, indent=4, default=str)

        return report

    except PyMongoError as error:
        return {
            "status": "error",
            "message": str(error)
        }
