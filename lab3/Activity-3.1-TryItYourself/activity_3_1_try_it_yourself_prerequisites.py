"""
Lab 3.1 - "Try it yourself"
Add a requirement to track prerequisites between courses. Decide whether to
embed or reference the prerequisite relationships and justify your choice.

DECISION: REFERENCE (not embed) prerequisites.

Justification
--------------
A course's prerequisites are themselves full course documents that already
live as independent top-level entities in the 'courses' collection, each
with their own lifecycle (title, instructor, schedule, credits can all
change on their own schedule, independent of any course that lists them
as a prerequisite).

If we EMBEDDED full prerequisite course documents inside every course that
requires them:
  - The same course data (e.g. "CS401 - Intro to ML") would be duplicated
    inside every downstream course that requires it (CS402, CS403, ...).
  - If CS401's instructor or schedule changes, every course that embedded a
    copy of it would silently go stale -- there is no single source of
    truth.
  - A course can be a prerequisite for many other courses (many-to-many),
    which is exactly the shape referencing is built for -- embedding works
    best for one-to-few, "always read together" data (like a course's own
    roster), not many-to-many links between peer entities.

So instead we REFERENCE prerequisites: each course stores only a small
array of the *course codes* it depends on (prerequisites: ["CS201", ...]).
This is the standard "one-to-few reference" pattern -- a small, bounded
array of foreign keys stored inline (cheap to read), while the full
prerequisite course document is resolved with a follow-up query / $lookup
only when needed (e.g. to check the prerequisite's title or verify it
still exists).

This script:
  1. Adds a 'prerequisites' field (array of course codes -- a reference,
     not an embedded copy) to the courses collection.
  2. Resolves prerequisites for a course via a follow-up query, proving
     the reference actually points at real course documents.
  3. Also demonstrates resolving prerequisites with $lookup, so the
     app-level "join" is shown both ways.
"""
import json
import os

from bson import json_util
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "nosql_labs_ch3"
HERE = os.path.dirname(os.path.abspath(__file__))


def banner(text, width=70):
    print("\n" + "=" * width)
    print(text)
    print("=" * width)


COURSES = [
    {"title": "Data Structures", "code": "CS201", "instructor": "Dr. Anil Gupta",
     "credits": 4, "schedule": {"days": ["Monday", "Wednesday"], "time": "08:00-09:30", "room": "LH-101"},
     "prerequisites": []},
    {"title": "Algorithms", "code": "CS301", "instructor": "Dr. Meera Joshi",
     "credits": 4, "schedule": {"days": ["Tuesday", "Thursday"], "time": "08:00-09:30", "room": "LH-103"},
     "prerequisites": ["CS201"]},
    {"title": "Introduction to Machine Learning", "code": "CS401", "instructor": "Dr. Priya Sharma",
     "credits": 4, "schedule": {"days": ["Monday", "Wednesday"], "time": "10:00-11:30", "room": "LH-201"},
     "prerequisites": ["CS201", "CS301"]},
    {"title": "Deep Learning with PyTorch", "code": "CS402", "instructor": "Dr. Anil Gupta",
     "credits": 3, "schedule": {"days": ["Tuesday", "Thursday"], "time": "14:00-15:30", "room": "LH-305"},
     "prerequisites": ["CS401"]},
]


def main():
    banner("Lab 3.1 Try It Yourself: Course Prerequisites (Referenced)")

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except ConnectionFailure as exc:
        raise SystemExit(f"[FATAL] Could not connect to MongoDB at {MONGO_URI}: {exc}")

    db = client[DB_NAME]
    if "courses_prerequisites" in db.list_collection_names():
        db.drop_collection("courses_prerequisites")
    col = db["courses_prerequisites"]

    col.insert_many(COURSES)
    print(f"[OK] Inserted {len(COURSES)} courses, each with a 'prerequisites' "
          f"array of REFERENCED course codes (not embedded copies).\n")

    # --- Resolve prerequisites for CS402 via a follow-up query (reference pattern) ---
    print("=== Resolving CS402's prerequisites (follow-up query) ===")
    course = col.find_one({"code": "CS402"})
    print(f"  {course['code']} - {course['title']}")
    print(f"  prerequisites field (references): {course['prerequisites']}")
    prereq_docs = list(col.find({"code": {"$in": course["prerequisites"]}},
                                 {"_id": 0, "code": 1, "title": 1, "instructor": 1}))
    for p in prereq_docs:
        print(f"     -> {p['code']}: {p['title']} (taught by {p['instructor']})")

    # --- Same resolution expressed as a $lookup (self-join on the collection) ---
    print("\n=== Same resolution via $lookup (self-referencing join) ===")
    pipeline = [
        {"$match": {"code": "CS401"}},
        {"$lookup": {
            "from": "courses_prerequisites",
            "localField": "prerequisites",
            "foreignField": "code",
            "as": "prerequisite_details",
        }},
        {"$project": {"_id": 0, "code": 1, "title": 1,
                       "prerequisite_details.code": 1, "prerequisite_details.title": 1}},
    ]
    result = list(col.aggregate(pipeline))[0]
    print(f"  {result['code']} - {result['title']} requires:")
    for p in result["prerequisite_details"]:
        print(f"     -> {p['code']}: {p['title']}")

    # --- Export ---
    docs = list(col.find({}))
    out_path = os.path.join(HERE, "courses_prerequisites_output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, default=json_util.default)
    print(f"\n[OK] Exported {len(docs)} documents -> {out_path}")

    banner("Lab 3.1 Try It Yourself Complete")


if __name__ == "__main__":
    main()
