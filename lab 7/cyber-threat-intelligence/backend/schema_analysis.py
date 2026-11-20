from datetime import datetime, timezone
from .db import db

COLLECTIONS = ["threats", "sources", "reports", "threat_source_links", "working_set_test"]

def analyze_collection(name):
    collection = db[name]
    pipeline = [
        {"$project": {"bytes": {"$bsonSize": "$$ROOT"}}},
        {"$group": {"_id": None, "count": {"$sum": 1},
                    "average_bytes": {"$avg": "$bytes"},
                    "min_bytes": {"$min": "$bytes"},
                    "max_bytes": {"$max": "$bytes"}}}
    ]
    result = list(collection.aggregate(pipeline))
    if not result:
        return {"collection": name, "count": 0, "average_bytes": None,
                "min_bytes": None, "max_bytes": None, "near_16_mib": 0}
    summary = result[0]
    near_count = collection.count_documents({"$expr": {"$gte": [{"$bsonSize": "$$ROOT"}, 15 * 1024 * 1024]}})
    summary.update({"collection": name, "near_16_mib": near_count})
    summary.pop("_id", None)
    return summary

def run_analysis():
    results = [analyze_collection(name) for name in COLLECTIONS]
    report = {"measured_at": datetime.now(timezone.utc), "collections": results,
              "threshold_bytes": 15 * 1024 * 1024,
              "mongo_document_limit_bytes": 16 * 1024 * 1024}
    db.schema_metrics.insert_one(report)
    for row in results:
        print(row)
    return report

if __name__ == "__main__":
    run_analysis()
