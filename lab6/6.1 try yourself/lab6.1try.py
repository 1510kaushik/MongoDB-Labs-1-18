"""
Activity 6.1 - Measure Actual Index Usage

Uses MongoDB $indexStats aggregation stage to measure
how frequently each index is actually used.
"""

import sys
import os

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from config.connection import get_db, banner


# ============================================================
# RUN QUERIES MULTIPLE TIMES
# ============================================================

def run_queries_multiple_times(collection, repetitions=10):

    print("\n" + "=" * 70)
    print("RUNNING QUERIES MULTIPLE TIMES")
    print("=" * 70)

    for i in range(repetitions):

        print(f"Running query set {i + 1}/{repetitions}")

        # ----------------------------------------------------
        # Query 1
        # Category + price sorting
        # Uses idx_category_price
        # ----------------------------------------------------

        list(
            collection.find(
                {
                    "category": "Electronics"
                }
            ).sort(
                [
                    ("price", 1)
                ]
            )
        )

        # ----------------------------------------------------
        # Query 2
        # Price range
        # Uses idx_price
        # ----------------------------------------------------

        list(
            collection.find(
                {
                    "price": {
                        "$gte": 1000,
                        "$lte": 10000
                    }
                }
            )
        )

        # ----------------------------------------------------
        # Query 3
        # Tag search
        # Uses idx_tags
        # ----------------------------------------------------

        list(
            collection.find(
                {
                    "tags": "wireless"
                }
            )
        )

        # ----------------------------------------------------
        # Query 4
        # Name search
        # Uses idx_name
        # ----------------------------------------------------

        list(
            collection.find(
                {
                    "name": {
                        "$regex": "^Product 1"
                    }
                }
            )
        )

        # ----------------------------------------------------
        # Query 5
        # Category + rating
        # Uses idx_category_rating
        # ----------------------------------------------------

        list(
            collection.find(
                {
                    "category": "Clothing",
                    "rating": {
                        "$gte": 4
                    }
                }
            )
        )

    print(
        "\n[OK] All queries executed multiple times."
    )


# ============================================================
# CHECK INDEX USAGE
# ============================================================

def check_index_usage(collection):

    print("\n" + "=" * 70)
    print("INDEX USAGE USING $indexStats")
    print("=" * 70)

    # --------------------------------------------------------
    # Run $indexStats
    # --------------------------------------------------------

    stats = list(
        collection.aggregate(
            [
                {
                    "$indexStats": {}
                }
            ]
        )
    )

    if not stats:

        print(
            "\nNo index statistics available."
        )

        return

    # --------------------------------------------------------
    # Display results
    # --------------------------------------------------------

    for stat in stats:

        index_name = stat.get(
            "name",
            "Unknown"
        )

        accesses = stat.get(
            "accesses",
            {}
        )

        operations = accesses.get(
            "ops",
            0
        )

        since = accesses.get(
            "since",
            "Unknown"
        )

        print(
            f"\nIndex Name : {index_name}"
        )

        print(
            f"Operations : {operations}"
        )

        print(
            f"Since      : {since}"
        )

    # --------------------------------------------------------
    # Sort indexes by usage
    # --------------------------------------------------------

    stats.sort(
        key=lambda x: x.get(
            "accesses",
            {}
        ).get(
            "ops",
            0
        ),
        reverse=True
    )

    print("\n" + "=" * 70)
    print("INDEX USAGE RANKING")
    print("=" * 70)

    for position, stat in enumerate(
        stats,
        start=1
    ):

        name = stat.get(
            "name",
            "Unknown"
        )

        operations = stat.get(
            "accesses",
            {}
        ).get(
            "ops",
            0
        )

        print(
            f"{position}. {name:<30} "
            f"Used {operations} times"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    banner(
        "Activity 6.1: $indexStats"
    )

    # --------------------------------------------------------
    # Connect to database
    # --------------------------------------------------------

    db = get_db(
        "nosql_labs"
    )

    collection = db["products"]

    print(
        "[OK] Connected to products collection."
    )

    # --------------------------------------------------------
    # Check whether documents exist
    # --------------------------------------------------------

    count = collection.count_documents({})

    print(
        f"[INFO] Documents in collection: {count}"
    )

    if count == 0:

        print(
            "\nERROR: Products collection is empty."
        )

        print(
            "Run Lab 6.1 first to create the products."
        )

        return

    # --------------------------------------------------------
    # Run queries repeatedly
    # --------------------------------------------------------

    run_queries_multiple_times(
        collection,
        repetitions=10
    )

    # --------------------------------------------------------
    # Check actual index usage
    # --------------------------------------------------------

    check_index_usage(
        collection
    )

    # --------------------------------------------------------
    # Complete
    # --------------------------------------------------------

    banner(
        "Activity 6.1 Complete"
    )


if __name__ == "__main__":
    main()