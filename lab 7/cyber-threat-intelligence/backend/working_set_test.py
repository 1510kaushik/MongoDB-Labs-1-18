from datetime import datetime, timezone
import random
import string
from .db import db

def main():
    collection = db["working_set_test"]
    # Explicitly isolated synthetic benchmark collection; real collections are not modified.
    collection.drop()
    alphabet = string.ascii_letters + string.digits
    batch = []
    for i in range(100_000):
        doc = {
            "_id": i,
            "test_record": True,
            "created_at": datetime.now(timezone.utc),
            "random_key": random.randint(1, 1_000_000),
            "payload": "".join(random.choices(alphabet, k=1750))
        }
        batch.append(doc)
        if len(batch) == 1000:
            collection.insert_many(batch, ordered=False)
            batch.clear()
            if (i + 1) % 10_000 == 0:
                print(f"Inserted {i + 1:,} synthetic documents")
    if batch:
        collection.insert_many(batch, ordered=False)
    stats = list(collection.aggregate([
        {"$project": {"bytes": {"$bsonSize": "$$ROOT"}}},
        {"$group": {"_id": None, "count": {"$sum": 1},
                    "average_bytes": {"$avg": "$bytes"},
                    "min_bytes": {"$min": "$bytes"}, "max_bytes": {"$max": "$bytes"}}}
    ]))
    print("Working-set BSON size measurements:", stats)
    print("Collection storage stats:", db.command("collStats", "working_set_test"))
    print("Synthetic test complete. No real threat/report data was changed.")

if __name__ == "__main__":
    main()
