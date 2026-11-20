
from backend.db import db
import sys
import json
import time
from pathlib import Path
from copy import deepcopy
from datetime import datetime

# Make project root accessible
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# ==========================================
# LAB 7.1: EMBEDDING VS REFERENCING
# ==========================================

print("\nStarting Lab 7.1 experiment...")

# Original collections (read-only)
threats = db["threats"]
sources = db["sources"]

# Experimental collections
referenced = db["lab71_threats_referenced"]
embedded = db["lab71_threats_embedded"]
experiment_sources = db["lab71_sources"]

# Read original data
source_documents = list(sources.find())
threat_documents = list(threats.find())

if not source_documents or not threat_documents:
    raise RuntimeError("Original threats or sources collection is empty.")

# Map source IDs to source documents
source_map = {
    source["_id"]: {
        key: value
        for key, value in source.items()
        if key != "_id"
    }
    for source in source_documents
}

reference_docs = []
embedded_docs = []

# Prepare both document designs
for original in threat_documents:

    threat = deepcopy(original)
    source_id = threat.get("source_id")

    # Only compare records with a valid source reference
    if source_id not in source_map:
        continue

    source_info = source_map[source_id]

    # DESIGN A: REFERENCING
    ref_doc = deepcopy(threat)
    ref_doc.pop("source", None)
    ref_doc["source_id"] = source_id

    # DESIGN B: EMBEDDING
    emb_doc = deepcopy(threat)
    emb_doc.pop("source_id", None)
    emb_doc["source"] = deepcopy(source_info)

    reference_docs.append(ref_doc)
    embedded_docs.append(emb_doc)

if not reference_docs:
    raise RuntimeError("No threats with valid source_id references found.")

# Clear only experiment collections
referenced.delete_many({})
embedded.delete_many({})
experiment_sources.delete_many({})

# Insert experimental data
experiment_sources.insert_many(deepcopy(source_documents))
referenced.insert_many(reference_docs)
embedded.insert_many(embedded_docs)

# Create index for source reference
referenced.create_index("source_id")

print("Experimental documents inserted successfully.")


# ==========================================
# QUERY FUNCTIONS
# ==========================================

sample_id = reference_docs[0]["_id"]


def reference_query():

    return list(
        referenced.aggregate([
            {"$match": {"_id": sample_id}},
            {
                "$lookup": {
                    "from": "lab71_sources",
                    "localField": "source_id",
                    "foreignField": "_id",
                    "as": "source"
                }
            },
            {
                "$unwind": {
                    "path": "$source",
                    "preserveNullAndEmptyArrays": True
                }
            }
        ])
    )


def embedded_query():

    return embedded.find_one({"_id": sample_id})


# ==========================================
# PERFORMANCE TEST
# ==========================================

ITERATIONS = 500

# Warm-up
for _ in range(20):
    reference_query()
    embedded_query()

# Referencing benchmark
start = time.perf_counter()

for _ in range(ITERATIONS):
    reference_query()

reference_total = time.perf_counter() - start

# Embedding benchmark
start = time.perf_counter()

for _ in range(ITERATIONS):
    embedded_query()

embedded_total = time.perf_counter() - start

reference_avg = reference_total / ITERATIONS * 1000
embedded_avg = embedded_total / ITERATIONS * 1000


# ==========================================
# BSON SIZE TEST
# ==========================================

reference_result = list(
    referenced.aggregate([
        {"$match": {"_id": sample_id}},
        {"$project": {"size": {"$bsonSize": "$$ROOT"}}}
    ])
)

embedded_result = list(
    embedded.aggregate([
        {"$match": {"_id": sample_id}},
        {"$project": {"size": {"$bsonSize": "$$ROOT"}}}
    ])
)

reference_size = reference_result[0]["size"]
embedded_size = embedded_result[0]["size"]


# ==========================================
# SAVE RESULTS
# ==========================================

results = {
    "experiment": "Lab 7.1 Embedding vs Referencing",
    "measured_at": datetime.now().isoformat(),
    "original_threat_count": len(threat_documents),
    "compared_threat_count": len(reference_docs),
    "source_count": len(source_documents),
    "iterations": ITERATIONS,
    "referencing_total_seconds": round(reference_total, 6),
    "embedding_total_seconds": round(embedded_total, 6),
    "referencing_average_ms": round(reference_avg, 6),
    "embedding_average_ms": round(embedded_avg, 6),
    "referencing_bson_bytes": reference_size,
    "embedding_bson_bytes": embedded_size
}

results_folder = PROJECT_ROOT / "results"
results_folder.mkdir(exist_ok=True)

output_file = results_folder / "lab71_embedding_vs_referencing.json"

with open(output_file, "w", encoding="utf-8") as file:
    json.dump(results, file, indent=4)


# ==========================================
# DISPLAY RESULTS
# ==========================================

print("\n========== LAB 7.1 RESULTS ==========")

print("Original threats:", len(threat_documents))
print("Compared threats:", len(reference_docs))
print("Source documents:", len(source_documents))

print("\n--- Query Performance ---")
print("Iterations:", ITERATIONS)
print(f"Referencing total: {reference_total:.4f} seconds")
print(f"Embedding total:   {embedded_total:.4f} seconds")
print(f"Referencing average: {reference_avg:.4f} ms")
print(f"Embedding average:   {embedded_avg:.4f} ms")

print("\n--- BSON Document Size ---")
print(f"Referenced document: {reference_size} bytes")
print(f"Embedded document:   {embedded_size} bytes")

print("\nResults saved to:")
print(output_file)

print("\nLab 7.1 experiment completed successfully!")
