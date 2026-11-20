from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

import os

ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_FILE, encoding="utf-8-sig")

client = MongoClient(
    os.environ["MONGODB_URI"],
    serverSelectionTimeoutMS=5000
)

db = client[os.environ["MONGODB_DATABASE"]]


def migrate_tenant(tenant_id):
    target_collection = f"tasks_tenant_{tenant_id}"

    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$out": target_collection}
    ]

    # $out replaces the target collection with this tenant's matching data.
    list(db.tasks.aggregate(pipeline, allowDiskUse=True))

    return target_collection


def validate_migration(tenant_id, target_collection):
    source_count = db.tasks.count_documents({
        "tenant_id": tenant_id
    })

    target = db[target_collection]
    target_count = target.count_documents({})

    tenant_ids = target.distinct("tenant_id")

    foreign_documents = target.count_documents({
        "tenant_id": {"$ne": tenant_id}
    })

    valid = (
        source_count == target_count
        and tenant_ids == [tenant_id]
        and foreign_documents == 0
    )

    return {
        "tenant_id": tenant_id,
        "source_count": source_count,
        "target_count": target_count,
        "foreign_documents": foreign_documents,
        "valid": valid
    }


def main():
    tenants = list(
        db.tenants.find({}, {"tenant_id": 1, "_id": 0}).sort("tenant_id", 1)
    )

    if len(tenants) != 5:
        raise RuntimeError(
            f"Expected 5 tenants, found {len(tenants)}"
        )

    source_total = db.tasks.count_documents({})

    if source_total != 500:
        raise RuntimeError(
            f"Expected 500 source tasks, found {source_total}"
        )

    print("Source database:", db.name)
    print("Source collection: tasks")
    print("Source documents:", source_total)

    results = []

    for tenant in tenants:
        tenant_id = tenant["tenant_id"]

        target_collection = migrate_tenant(tenant_id)

        result = validate_migration(
            tenant_id,
            target_collection
        )

        results.append(result)

        print(f"\nTenant: {tenant_id}")
        print("Target collection:", target_collection)
        print("Source documents:", result["source_count"])
        print("Migrated documents:", result["target_count"])
        print("Foreign documents:", result["foreign_documents"])
        print("Validation:", result["valid"])

        if not result["valid"]:
            raise RuntimeError(
                f"Migration validation failed for {tenant_id}"
            )

    migrated_total = sum(r["target_count"] for r in results)

    print("\n--- MIGRATION SUMMARY ---")
    print("Tenants migrated:", len(results))
    print("Original documents:", source_total)
    print("Migrated documents:", migrated_total)
    print("All tenants validated:", all(r["valid"] for r in results))
    print("Migration successful:", migrated_total == source_total)

    if migrated_total != source_total:
        raise RuntimeError("Total document count mismatch")


if __name__ == "__main__":
    try:
        main()
    finally:
        client.close()
