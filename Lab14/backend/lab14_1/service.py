import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from pymongo.errors import PyMongoError

from ..db import client, db

_previous_cache = None
_cache_lock = threading.Lock()


def _utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cache_hit_ratio(cache):
    global _previous_cache

    requested = cache.get("pages requested from the cache")
    pages_read = cache.get("pages read into cache")

    if requested is None or pages_read is None:
        return None, "unavailable"

    current = {
        "requested": int(requested),
        "read": int(pages_read)
    }

    with _cache_lock:
        previous = _previous_cache
        _previous_cache = current

    if previous is not None:
        requested_delta = current["requested"] - previous["requested"]
        read_delta = current["read"] - previous["read"]

        if requested_delta >= 0 and read_delta >= 0:
            if requested_delta == 0:
                return None, "no new cache requests"
            requested = requested_delta
            pages_read = read_delta
            sample_type = "interval"
        else:
            requested = current["requested"]
            pages_read = current["read"]
            sample_type = "cumulative after counter reset"
    else:
        sample_type = "cumulative initial sample"

    if requested <= 0:
        return None, sample_type

    hits = max(0, requested - pages_read)
    ratio = (hits / requested) * 100

    return round(min(ratio, 100), 2), sample_type


def get_lab14_metrics():
    now = datetime.now(timezone.utc)

    try:
        server = client.admin.command("serverStatus")

        connections = server.get("connections", {})
        opcounters = server.get("opcounters", {})
        cache = (
            server.get("wiredTiger", {})
            .get("cache", {})
        )

        cache_ratio, sample_type = _cache_hit_ratio(cache)

        cache_metrics = {
            "hit_ratio_percent": cache_ratio,
            "sample_type": sample_type,
            "pages_requested": cache.get(
                "pages requested from the cache"
            ),
            "pages_read_into_cache": cache.get(
                "pages read into cache"
            ),
            "bytes_currently_in_cache": cache.get(
                "bytes currently in the cache"
            ),
            "maximum_cache_bytes": cache.get(
                "maximum bytes configured"
            ),
            "pages_written_from_cache": cache.get(
                "pages written from cache"
            )
        }

        replica = None
        members = []
        max_lag = None
        replica_error = None

        try:
            replica = client.admin.command("replSetGetStatus")
            raw_members = replica.get("members", [])

            primary = next(
                (
                    member for member in raw_members
                    if member.get("stateStr") == "PRIMARY"
                ),
                None
            )

            primary_time = (
                _utc(primary.get("optimeDate"))
                if primary else None
            )

            secondary_lags = []

            for member in raw_members:
                state = member.get("stateStr")
                optime = _utc(member.get("optimeDate"))

                lag = None
                if (
                    state == "SECONDARY"
                    and primary_time is not None
                    and optime is not None
                ):
                    lag = max(
                        0,
                        (primary_time - optime).total_seconds()
                    )
                    secondary_lags.append(lag)

                members.append({
                    "name": member.get("name"),
                    "state": state,
                    "health": member.get("health"),
                    "lag_seconds": (
                        round(lag, 3) if lag is not None else None
                    )
                })

            if secondary_lags:
                max_lag = round(max(secondary_lags), 3)

        except PyMongoError as exc:
            replica_error = str(exc)

        warnings = []

        if cache_ratio is not None and cache_ratio < 80:
            warnings.append("Cache hit ratio is below 80%.")

        if max_lag is not None and max_lag > 10:
            warnings.append("Replication lag exceeds 10 seconds.")

        unhealthy = [
            member for member in members
            if member.get("health") != 1
        ]

        if unhealthy:
            warnings.append("One or more replica set members are unhealthy.")

        if replica is not None:
            if not any(m["state"] == "PRIMARY" for m in members):
                warnings.append("No replica set primary was detected.")
        elif replica_error:
            warnings.append("Replica set status is unavailable.")

        return {
            "available": True,
            "lab": "Lab 14.1 - MongoDB Monitoring",
            "status": "warning" if warnings else "success",
            "checked_at": now.isoformat(),
            "database": db.name,
            "mongodb_version": server.get("version"),
            "connections": {
                "current": connections.get("current"),
                "available": connections.get("available"),
                "total_created": connections.get("totalCreated")
            },
            "opcounters": opcounters,
            "cache": cache_metrics,
            "replica_set": {
                "name": replica.get("set") if replica else None,
                "members": members,
                "maximum_secondary_lag_seconds": max_lag,
                "error": replica_error
            },
            "warnings": warnings
        }

    except Exception as exc:
        return {
            "available": False,
            "status": "error",
            "error": str(exc),
            "checked_at": now.isoformat()
        }


def write_metrics_log():
    project_root = Path(__file__).resolve().parents[2]
    log_path = project_root / "metrics.log"

    while True:
        result = get_lab14_metrics()

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result": result
        }

        try:
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(record, default=str) + "\n")

            print(
                "[Lab 14.1]",
                result.get("status"),
                result.get("checked_at")
            )

        except OSError as exc:
            print("[Lab 14.1] Could not write metrics.log:", exc)

        time.sleep(30)
