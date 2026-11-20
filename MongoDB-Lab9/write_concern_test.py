import json
from service import run_benchmark

if __name__ == "__main__":
    print("Starting Lab 9.1 Write Concern Benchmark...")

    try:
        results = run_benchmark(1000)
        print(json.dumps(results, indent=4))
        print("\nBenchmark completed successfully.")

    except Exception as error:
        print(f"\nBenchmark failed: {error}")
