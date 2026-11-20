from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import Depends, HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .config import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS
from .database import db
from .dependencies import get_current_user


def enforce_tenant_rate_limit(
    current_user: dict = Depends(get_current_user)
):
    now = datetime.now(timezone.utc)
    window_seconds = RATE_LIMIT_WINDOW_SECONDS

    window_number = int(now.timestamp()) // window_seconds
    window_start = datetime.fromtimestamp(
        window_number * window_seconds,
        tz=timezone.utc
    )

    tenant_id = ObjectId(current_user["tenant_id"])

    query = {
        "tenant_id": tenant_id,
        "window_start": window_start
    }

    update = {
        "$inc": {"requests": 1},
        "$setOnInsert": {
            "expires_at": window_start + timedelta(
                seconds=window_seconds * 2
            )
        }
    }

    try:
        counter = db.rate_limits.find_one_and_update(
            query,
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
    except DuplicateKeyError:
        # Handles simultaneous first requests for the same tenant/window.
        counter = db.rate_limits.find_one_and_update(
            query,
            {"$inc": {"requests": 1}},
            return_document=ReturnDocument.AFTER
        )

    request_count = counter["requests"]

    if request_count > RATE_LIMIT_REQUESTS:
        reset_at = window_start + timedelta(seconds=window_seconds)
        retry_after = max(
            1,
            int((reset_at - now).total_seconds())
        )

        raise HTTPException(
            status_code=429,
            detail={
                "message": "Tenant rate limit exceeded",
                "limit": RATE_LIMIT_REQUESTS,
                "window_seconds": window_seconds
            },
            headers={"Retry-After": str(retry_after)}
        )

    return {
        "tenant_id": current_user["tenant_id"],
        "requests_used": request_count,
        "limit": RATE_LIMIT_REQUESTS
    }
