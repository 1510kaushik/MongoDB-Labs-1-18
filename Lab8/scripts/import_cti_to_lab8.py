
import json
import pathlib
import ijson

from bson import json_util
from pymongo import MongoClient, InsertOne
from pymongo.write_concern import WriteConcern

# Backup location, relative to the project root
BACKUP_DIR = pathlib.Path(
    "/work/backups/cyber_threat_intel_20261118_222501"
)

DATABASE_NAME = "cyber_threat_intel"

MONGODB_URI = (
    "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/"
    "?replicaSet=rs0&retryWrites=true&w=majority"
)

BATCH_SIZE = 500


def main():
    if not (BACKUP_DIR / "manifest.json").exists():
        raise FileNotFoundError("Backup manifest not found.")

    manifest = json.loads(
        (BACKUP_DIR / "manifest.json").read_text(encoding="utf-8")
    )

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)

    try:
        client.admin.command("ping")

        hello = client.admin.command("hello")

        if hello.get("setName") != "rs0":
            raise RuntimeError("Connected server is not replica set rs0.")

        if not hello.get("isWritablePrimary"):
            raise RuntimeError("No writable primary is available.")

        print("Connected to Lab 8 replica set.")
        print("Primary:", hello.get("primary"))
        print("MongoDB version:", client.server_info()["version"])

        db = client.get_database(
            DATABASE_NAME,
            write_concern=WriteConcern(w="majority")
        )

        existing = db.list_collection_names()

        if existing:
            raise RuntimeError(
                "Destination database is not empty. "
                f"Existing collections: {existing}. Import stopped."
            )

        print("\nDestination database is empty.")
        print("Starting import...\n")

        # Import documents collection by collection
        for name, details in manifest["collections"].items():

            data_file = BACKUP_DIR / details["data_file"]
            expected = details["document_count"]

            print(f"Importing {name}: expected {expected} documents")

            collection = db[name]
            batch = []
            imported = 0

            with data_file.open("rb") as file:
                for document in ijson.items(file, "item", use_float=True):

                    # Convert Extended JSON into real BSON-compatible values
                    bson_document = json_util.loads(json.dumps(document))

                    batch.append(InsertOne(bson_document))

                    if len(batch) >= BATCH_SIZE:
                        collection.bulk_write(batch, ordered=False)
                        imported += len(batch)
                        batch.clear()

            if batch:
                collection.bulk_write(batch, ordered=False)
                imported += len(batch)

            actual = collection.count_documents({})

            if actual != expected:
                raise RuntimeError(
                    f"Count mismatch in {name}: "
                    f"expected {expected}, found {actual}"
                )

            print(f"Verified {name}: {actual} documents")

        # Restore the original custom index.
        # MongoDB automatically creates the _id index.
        index_file = BACKUP_DIR / "lab71_threats_referenced_indexes.json"

        index_specs = json_util.loads(
            index_file.read_text(encoding="utf-8")
        )

        for spec in index_specs:
            if spec["name"] == "_id_":
                continue

            options = {}

            for key in (
                "unique",
                "sparse",
                "expireAfterSeconds",
                "partialFilterExpression",
                "collation",
                "hidden"
            ):
                if key in spec:
                    options[key] = spec[key]

            db["lab71_threats_referenced"].create_index(
                list(spec["key"].items()),
                name=spec["name"],
                **options
            )

            print("Restored index:", spec["name"])

        print("\nFINAL VERIFICATION")

        total = 0

        for name, details in manifest["collections"].items():
            actual = db[name].count_documents({})
            expected = details["document_count"]

            print(f"{name}: {actual} / {expected}")

            if actual != expected:
                raise RuntimeError(f"Final verification failed: {name}")

            total += actual

        print("\nIMPORT COMPLETED SUCCESSFULLY")
        print("Collections:", len(manifest["collections"]))
        print("Total documents:", total)

    finally:
        client.close()


if __name__ == "__main__":
    main()
