"""
Activity 6.2 - Covered Query

Objective:
Implement a covered query and use explain() to verify
that the FETCH stage is eliminated.

A covered query is a query where:
1. All fields used in the query are in the index.
2. All fields returned by the projection are in the index.
3. _id is excluded from the result unless _id is part of the index.

Expected result:
- IXSCAN is used.
- FETCH stage is eliminated.
- totalDocsExamined should be 0.
"""

import sys
import os

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from config.connection import get_db, reset_collection, banner


# ============================================================
# FIND STAGES IN QUERY PLAN
# ============================================================

def find_stages(obj):
    """
    Recursively find all stages in a MongoDB query plan.
    """

    stages = []

    if isinstance(obj, dict):

        if "stage" in obj:
            stages.append(obj["stage"])

        for value in obj.values():

            stages.extend(
                find_stages(value)
            )

    elif isinstance(obj, list):

        for item in obj:

            stages.extend(
                find_stages(item)
            )

    return stages


# ============================================================
# FIND INDEX NAME
# ============================================================

def find_index_name(obj):
    """
    Recursively find the index name from a query plan.
    """

    if isinstance(obj, dict):

        if "indexName" in obj:
            return obj["indexName"]

        for value in obj.values():

            result = find_index_name(value)

            if result:
                return result

    elif isinstance(obj, list):

        for item in obj:

            result = find_index_name(item)

            if result:
                return result

    return None


# ============================================================
# DISPLAY EXPLAIN RESULTS
# ============================================================

def display_explain(plan):

    print("\n" + "=" * 70)
    print("EXPLAIN RESULTS")
    print("=" * 70)

    query_planner = plan.get(
        "queryPlanner",
        {}
    )

    winning_plan = query_planner.get(
        "winningPlan",
        {}
    )

    execution_stats = plan.get(
        "executionStats",
        {}
    )

    # --------------------------------------------------------
    # Stages
    # --------------------------------------------------------

    stages = find_stages(
        winning_plan
    )

    print(
        "\nQuery Plan Stages:"
    )

    if stages:

        for stage in stages:
            print(
                "  ->",
                stage
            )

    else:

        print(
            "  No stages found"
        )

    # --------------------------------------------------------
    # Index
    # --------------------------------------------------------

    index_name = find_index_name(
        winning_plan
    )

    if index_name:

        print(
            "\nIndex Used:",
            index_name
        )

    else:

        print(
            "\nIndex Used: None detected"
        )

    # --------------------------------------------------------
    # Execution statistics
    # --------------------------------------------------------

    docs_examined = execution_stats.get(
        "totalDocsExamined",
        "N/A"
    )

    keys_examined = execution_stats.get(
        "totalKeysExamined",
        "N/A"
    )

    returned = execution_stats.get(
        "nReturned",
        "N/A"
    )

    execution_time = execution_stats.get(
        "executionTimeMillis",
        "N/A"
    )

    print(
        "\nDocuments Examined:",
        docs_examined
    )

    print(
        "Keys Examined:",
        keys_examined
    )

    print(
        "Documents Returned:",
        returned
    )

    print(
        "Execution Time:",
        execution_time,
        "ms"
    )

    # --------------------------------------------------------
    # Covered query verification
    # --------------------------------------------------------

    print(
        "\n" + "-" * 70
    )

    if "FETCH" not in stages and docs_examined == 0:

        print(
            "SUCCESS: Covered query confirmed!"
        )

        print(
            "FETCH stage: NOT PRESENT"
        )

        print(
            "Documents examined: 0"
        )

        print(
            "MongoDB answered the query directly from the index."
        )

    elif "FETCH" not in stages:

        print(
            "FETCH stage: NOT PRESENT"
        )

        print(
            "The query plan does not contain FETCH."
        )

    else:

        print(
            "FETCH stage: PRESENT"
        )

        print(
            "The query is NOT fully covered."
        )

    print(
        "-" * 70
    )


# ============================================================
# MAIN
# ============================================================

def main():

    banner(
        "Activity 6.2: Covered Query"
    )

    # --------------------------------------------------------
    # Connect to MongoDB
    # --------------------------------------------------------

    print(
        "\nConnecting to MongoDB..."
    )

    db = get_db(
        "nosql_labs"
    )

    print(
        "[OK] Connected to MongoDB."
    )

    # --------------------------------------------------------
    # Use products collection from Lab 6.1
    # --------------------------------------------------------

    col = db[
        "products"
    ]

    count = col.count_documents({})

    print(
        f"[INFO] Products collection contains "
        f"{count:,} documents."
    )

    # --------------------------------------------------------
    # If products collection doesn't exist
    # --------------------------------------------------------

    if count == 0:

        print(
            "\nERROR: products collection is empty."
        )

        print(
            "Please run Lab 6.1 first."
        )

        return

    # ========================================================
    # CREATE COVERING INDEX
    # ========================================================

    banner(
        "CREATING COVERING INDEX"
    )

    # This index contains BOTH fields that we need:
    #
    # sensor_id -> query field
    # reading   -> returned field
    #
    # Therefore MongoDB can answer the query directly
    # from the index.

    index_name = col.create_index(
        [
            ("sensor_id", 1),
            ("reading", 1)
        ],
        name="idx_covered_sensor_reading"
    )

    print(
        "[OK] Created index:",
        index_name
    )

    # ========================================================
    # COVERED QUERY
    # ========================================================

    banner(
        "COVERED QUERY"
    )

    query = {
        "sensor_id": "SENSOR-0050"
    }

    # IMPORTANT:
    #
    # We return only fields contained in the index.
    #
    # _id is automatically returned by MongoDB unless
    # explicitly excluded.
    #
    # Therefore we use "_id": 0.

    projection = {
        "_id": 0,
        "sensor_id": 1,
        "reading": 1
    }

    print(
        "\nQuery:"
    )

    print(
        query
    )

    print(
        "\nProjection:"
    )

    print(
        projection
    )

    # ========================================================
    # RUN THE QUERY
    # ========================================================

    print(
        "\nRunning covered query..."
    )

    results = list(
        col.find(
            query,
            projection
        ).limit(10)
    )

    print(
        f"\nReturned {len(results)} documents."
    )

    print(
        "\nSample results:"
    )

    for document in results[:5]:

        print(
            document
        )

    # ========================================================
    # RUN EXPLAIN
    # ========================================================

    banner(
        "EXPLAIN: COVERED QUERY"
    )

    find_command = {
        "find": col.name,
        "filter": query,
        "projection": projection
    }

    plan = col.database.command(
        "explain",
        find_command,
        verbosity="executionStats"
    )

    # ========================================================
    # DISPLAY RESULTS
    # ========================================================

    display_explain(
        plan
    )

    # ========================================================
    # COMPARE WITH NON-COVERED QUERY
    # ========================================================

    banner(
        "COMPARISON: NON-COVERED QUERY"
    )

    print(
        """
Now we run a similar query but request a field
that is NOT contained in the index.

The index contains:
    sensor_id
    reading

The following query also requests:
    status

Therefore MongoDB must fetch the original document.
"""
    )

    noncovered_projection = {
        "_id": 0,
        "sensor_id": 1,
        "reading": 1,
        "status": 1
    }

    noncovered_command = {
        "find": col.name,
        "filter": query,
        "projection": noncovered_projection
    }

    noncovered_plan = col.database.command(
        "explain",
        noncovered_command,
        verbosity="executionStats"
    )

    print(
        "\nNon-covered query:"
    )

    print(
        query
    )

    print(
        "\nProjection:"
    )

    print(
        noncovered_projection
    )

    display_explain(
        noncovered_plan
    )

    # ========================================================
    # FINAL EXPLANATION
    # ========================================================

    banner(
        "ACTIVITY 6.2 CONCLUSION"
    )

    print(
        """
Covered Query:
--------------

Query:
    { sensor_id: "SENSOR-0050" }

Projection:
    {
        _id: 0,
        sensor_id: 1,
        reading: 1
    }

Index:
    {
        sensor_id: 1,
        reading: 1
    }

All required fields are present in the index.

Therefore MongoDB can return the result directly
from the index without reading the original documents.

Expected explain() result:

    IXSCAN
    No FETCH
    totalDocsExamined = 0


Non-Covered Query:
------------------

When a field that is not contained in the index
is requested, MongoDB must access the original
documents.

Expected result:

    IXSCAN
    FETCH

Therefore:

Covered Query
    -> Reads only the index
    -> No FETCH
    -> totalDocsExamined = 0

Non-Covered Query
    -> Uses the index
    -> Fetches the documents
    -> FETCH stage is present
"""
    )

    banner(
        "Activity 6.2 Complete"
    )


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()