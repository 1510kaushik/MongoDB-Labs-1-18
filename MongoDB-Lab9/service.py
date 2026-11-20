import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient, WriteConcern

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"

MONGODB_URI = "mongodb://127.0.0.1:27018/?directConnection=true"
DATABASE_NAME = "mongodb_lab9"


def run_benchmark(document_count=1000):
    if (
        isinstance(document_count, bool)
        or not isinstance(document_count, int)
        or not 1 <= document_count <= 100000
    ):
        raise ValueError("Invalid document count")

    RESULTS_DIR.mkdir(exist_ok=True)

    client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=5000
    )

    try:
        client.admin.command("ping")

        config = client.admin.command("replSetGetConfig")["config"]

        voting_data_members = sum(
            1 for member in config["members"]
            if member.get("votes", 1) > 0
            and not member.get("arbiterOnly", False)
        )

        if voting_data_members < 1:
            raise RuntimeError("No voting data-bearing members found")

        concerns = {
            "w:1": 1,
            "w:majority": "majority",
            "w:all": voting_data_members
        }

        benchmark_results = {}

        for label, w_value in concerns.items():

            collection_name = "benchmark_" + uuid.uuid4().hex

            collection = client[DATABASE_NAME].get_collection(
                collection_name,
                write_concern=WriteConcern(w=w_value)
            )

            latencies = []

            for i in range(document_count):
                document = {
                    "sequence": i + 1,
                    "benchmark": label,
                    "created_at": datetime.now(timezone.utc)
                }

                start = time.perf_counter()

                collection.insert_one(document)

                elapsed_ms = (
                    time.perf_counter() - start
                ) * 1000

                latencies.append(elapsed_ms)

            total_time = sum(latencies)

            benchmark_results[label] = {
                "documents": document_count,
                "total_time_seconds": round(total_time / 1000, 6),
                "average_latency_ms": round(
                    total_time / document_count, 6
                ),
                "minimum_latency_ms": round(min(latencies), 6),
                "maximum_latency_ms": round(max(latencies), 6),
                "write_concern": w_value
            }

            collection.drop()

        report = {
            "lab": "9.1",
            "title": "Measure Write Concern Latency",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "replica_set": config["_id"],
            "voting_data_members": voting_data_members,
            "document_count": document_count,
            "results": benchmark_results
        }

        filename = (
            "lab9_1_" +
            datetime.now().strftime("%Y%m%d_%H%M%S") +
            ".json"
        )

        output_file = RESULTS_DIR / filename

        output_file.write_text(
            json.dumps(report, indent=4),
            encoding="utf-8"
        )

        return report

    finally:
        client.close()

