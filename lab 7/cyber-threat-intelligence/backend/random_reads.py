
import random
import time
from .db import db


def main():
    collection = db["working_set_test"]
    count = collection.count_documents({})

    if count == 0:
        print("No working-set records. Run python -m backend.working_set_test first.")
        return

    total_reads = min(500, count)
    ids = random.sample(range(count), total_reads)
    successful_reads = 0

    start = time.perf_counter()

    for doc_id in ids:
        result = collection.find_one({"_id": doc_id}, {"payload": 0})
        if result is not None:
            successful_reads += 1

    elapsed = time.perf_counter() - start

    print(f"Documents in working set: {count}")
    print(f"Random reads attempted: {total_reads}")
    print(f"Successful reads: {successful_reads}")
    print(f"Elapsed time: {elapsed:.3f} seconds")
    print(f"Read throughput: {successful_reads / elapsed:.2f} reads/second")


if __name__ == "__main__":
    main()
