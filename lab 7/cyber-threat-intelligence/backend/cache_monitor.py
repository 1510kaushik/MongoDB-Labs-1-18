
import time
from datetime import datetime, timezone

from .db import db, client
from .ingest_reports import sync_reports


def find_number(cache, *needles):
    for key, value in cache.items():
        normalized = key.lower()
        if all(n.lower() in normalized for n in needles):
            if isinstance(value, (int, float)):
                return value
    return None


def sample_cache():
    status = client.admin.command("serverStatus")
    cache = status.get("wiredTiger", {}).get("cache", {})

    requested = find_number(cache, "pages requested from the cache")
    read = find_number(cache, "pages read into cache")
    current = find_number(cache, "bytes currently in the cache")
    maximum = find_number(cache, "maximum bytes configured")

    return requested, read, current, maximum


def check_new_reports():
    """Fetch the external annual security reports index and sync new links."""
    print("\nChecking external annual security reports index...")

    result = sync_reports()

    print(
        f"Reports scanned: {result['scanned']} | "
        f"New records: {result['inserted']} | "
        f"Updated records: {result['modified']}"
    )

    return result


def main():
    print("Sampling WiredTiger cache metrics every 10 seconds. Ctrl+C to stop.")

    previous_requested = None
    previous_read = None

    try:
        while True:
            try:
                requested, read, current, maximum = sample_cache()
                now = datetime.now(timezone.utc)

                hit_ratio = None

                if (
                    requested is not None
                    and read is not None
                    and previous_requested is not None
                    and previous_read is not None
                ):
                    delta_requested = requested - previous_requested
                    delta_read = read - previous_read

                    if delta_requested > 0:
                        hit_ratio = max(
                            0.0,
                            min(1.0, 1 - delta_read / delta_requested)
                        )

                utilization = (
                    current / maximum
                    if current is not None and maximum
                    else None
                )

                db.performance_events.insert_one({
                    "timestamp": now,
                    "cache_bytes": current,
                    "max_cache_bytes": maximum,
                    "cache_utilization": utilization,
                    "pages_requested_cumulative": requested,
                    "pages_read_into_cache_cumulative": read,
                    "interval_hit_ratio_estimate": hit_ratio,
                    "metric_note": (
                        "Approximation from WiredTiger counter deltas."
                    )
                })

                print({
                    "timestamp": now.isoformat(),
                    "cache_bytes": current,
                    "max_cache_bytes": maximum,
                    "cache_utilization": (
                        round(utilization, 4)
                        if utilization is not None else None
                    ),
                    "interval_hit_ratio_estimate": (
                        round(hit_ratio, 4)
                        if hit_ratio is not None
                        else "warming up / counters unavailable"
                    )
                })

                check_new_reports()

                previous_requested = requested
                previous_read = read

            except Exception as exc:
                print("Monitor sample failed:", exc)

            time.sleep(10)

    except KeyboardInterrupt:
        print("Cache and report monitor stopped.")


if __name__ == "__main__":
    main()
