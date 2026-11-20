from pathlib import Path
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent / ".env", encoding="utf-8-sig")

import os

client = MongoClient(
    os.environ["MONGODB_URI"],
    serverSelectionTimeoutMS=5000
)

db = client[os.environ["MONGODB_DATABASE"]]

# This script only resets the isolated migration database collections.
db.tasks.delete_many({})
db.tenants.delete_many({})

now = datetime.now(timezone.utc)

tenants = [
    {
        "tenant_id": f"tenant_{i:03d}",
        "tenant_name": f"Company {i}",
        "created_at": now
    }
    for i in range(1, 6)
]

db.tenants.insert_many(tenants)

statuses = ["pending", "in_progress", "completed"]
priorities = ["low", "medium", "high"]

tasks = []

for tenant_number in range(1, 6):
    tenant_id = f"tenant_{tenant_number:03d}"

    for task_number in range(1, 101):
        tasks.append({
            "id": f"{tenant_id}_task_{task_number:03d}",
            "tenant_id": tenant_id,
            "title": f"Task {task_number} for {tenant_id}",
            "status": statuses[(task_number - 1) % len(statuses)],
            "priority": priorities[(task_number - 1) % len(priorities)],
            "created_at": now - timedelta(minutes=task_number)
        })

result = db.tasks.insert_many(tasks)

print("Database:", db.name)
print("Tenants created:", db.tenants.count_documents({}))
print("Tasks inserted:", len(result.inserted_ids))
print("\nTask counts by tenant:")

for tenant in tenants:
    tenant_id = tenant["tenant_id"]
    count = db.tasks.count_documents({"tenant_id": tenant_id})
    print(f"{tenant_id}: {count}")

total = db.tasks.count_documents({})
print("\nTotal task documents:", total)
print("Seed validation:", total == 500 and all(
    db.tasks.count_documents({"tenant_id": t["tenant_id"]}) == 100
    for t in tenants
))

client.close()

