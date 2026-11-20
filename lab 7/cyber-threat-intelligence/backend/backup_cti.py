from pymongo import MongoClient
from bson import json_util
from pathlib import Path
from datetime import datetime, timezone
import json

client = MongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=5000)
client.admin.command("ping")

db = client["cyber_threat_intel"]
project_root = Path(__file__).resolve().parents[1]
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = project_root / "backups" / f"cyber_threat_intel_{timestamp}"
backup_dir.mkdir(parents=True, exist_ok=False)

manifest = {
    "database": "cyber_threat_intel",
    "server_version": client.server_info()["version"],
    "backup_time_utc": datetime.now(timezone.utc).isoformat(),
    "collections": {}
}

print("Starting backup...")
print("Destination:", backup_dir)

for name in sorted(db.list_collection_names()):
    collection = db[name]
    output_file = backup_dir / f"{name}.json"
    count = 0

    indexes = list(collection.list_indexes())
    index_file = backup_dir / f"{name}_indexes.json"
    index_file.write_text(
        json_util.dumps(indexes, json_options=json_util.CANONICAL_JSON_OPTIONS, indent=2),
        encoding="utf-8"
    )

    with output_file.open("w", encoding="utf-8") as file:
        file.write("[\n")
        cursor = collection.find({}).batch_size(500)

        try:
            for document in cursor:
                if count:
                    file.write(",\n")
                file.write(json_util.dumps(
                    document,
                    json_options=json_util.CANONICAL_JSON_OPTIONS
                ))
                count += 1
        finally:
            cursor.close()

        file.write("\n]\n")

    manifest["collections"][name] = {
        "document_count": count,
        "indexes_file": index_file.name,
        "data_file": output_file.name
    }

    print(f"Backed up {name}: {count} documents")

manifest_file = backup_dir / "manifest.json"
manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

client.close()

print("\nBACKUP COMPLETED")
print("Backup location:", backup_dir)
print("Collections backed up:", len(manifest["collections"]))
