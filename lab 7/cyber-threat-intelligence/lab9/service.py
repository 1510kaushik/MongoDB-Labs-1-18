import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pymongo.write_concern import WriteConcern
from backend.db import db


RESULTS_DIR = Path(__file__).resolve().parent / "results"
WRITE_TIMEOUT_MS = 15000


def get_data_member_count():
    config = db.client.admin.command({"replSetGetConfig": 1})
    members = config["config"]["members"]

    data_members = [
        member for member in members
        if not member.get("arbiterOnly", False)
        and member.get("votes", 1) > 0
    ]

    if not data_members:
        raise RuntimeError("No voting data-bearing replica-set members found.")

    return len(data_members)


def run_benchmark(document_count=1000):

    if (
        isinstance(document_count, bool)
        or not isinstance(document_count, int)
        or not 1 <= document_count <= 100000
    ):
        raise ValueError("document_count must be between 1 and 100000")

    db.client.admin.command("ping")

    replica_set = db.client.admin.command(
        {"replSetGetStatus": 1}
    ).get("set")

    data_members = get_data_member_count()

    concerns = [
        ("w:1", 1),
        ("w:majority", "majority"),
        ("w:all", data_members)
    ]

    benchmark_id = str(uuid.uuid4())
    results = []

    for label, write_value in concerns:

        collection_name = (
            f"lab9_benchmark_{uuid.uuid4().hex}"
        )

        collection = db.get_collection(
            collection_name,
            write_concern=WriteConcern(
                w=write_value,
                wtimeout=WRITE_TIMEOUT_MS
            )
        )

        latencies = []
        total_start = time.perf_counter()

        try:
            for sequence in range(1, document_count + 1):

                document = {
                    "benchmark_id": benchmark_id,
                    "sequence": sequence,
                    "write_concern": label,
                    "created_at": datetime.now(timezone.utc)
                }

                start = time.perf_counter()
                collection.insert_one(document)
                elapsed = time.perf_counter() - start

                latencies.append(elapsed * 1000)

            total_ms = (
                time.perf_counter() - total_start
            ) * 1000

            results.append({
                "write_concern": label,
                "mongodb_w_value": write_value,
                "documents_inserted": len(latencies),
                "total_time_ms": round(total_ms, 3),
                "average_latency_ms": round(
                    sum(latencies) / len(latencies), 4
                ),
                "min_latency_ms": round(min(latencies), 4),
                "max_latency_ms": round(max(latencies), 4)
            })

        finally:
            collection.drop()

    report = {
        "status": "success",
        "lab": "Lab 9.1",
        "title": "Write Concern Latency Benchmark",
        "benchmark_id": benchmark_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db.name,
        "replica_set": replica_set,
        "voting_data_members": data_members,
        "document_count": document_count,
        "results": results
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    filename = (
        "lab9_1_"
        + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        + ".json"
    )

    with open(RESULTS_DIR / filename, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    report["result_file"] = filename

    return report
