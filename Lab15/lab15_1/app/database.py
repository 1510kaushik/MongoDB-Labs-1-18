from pymongo import MongoClient, ASCENDING, DESCENDING
from .config import MONGODB_URI, MONGODB_DATABASE

client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=5000,
    appname="Lab15MultiTenantAPI"
)

db = client[MONGODB_DATABASE]


def check_connection():
    return client.admin.command("ping")


def ensure_indexes():
    db.tenants.create_index(
        [("slug", ASCENDING)],
        unique=True,
        name="tenant_slug_unique"
    )

    db.users.create_index(
        [("tenant_id", ASCENDING), ("email", ASCENDING)],
        unique=True,
        name="tenant_email_unique"
    )

    db.tasks.create_index(
        [("tenant_id", ASCENDING), ("created_at", DESCENDING)],
        name="tenant_created_at"
    )

    db.tasks.create_index(
        [("tenant_id", ASCENDING), ("status", ASCENDING)],
        name="tenant_status"
    )

    db.rate_limits.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
        name="rate_limit_ttl"
    )

    db.rate_limits.create_index(
        [("tenant_id", ASCENDING), ("window_start", ASCENDING)],
        unique=True,
        name="tenant_window_unique"
    )

    return {
        "tenants": list(db.tenants.index_information().keys()),
        "users": list(db.users.index_information().keys()),
        "tasks": list(db.tasks.index_information().keys()),
        "rate_limits": list(db.rate_limits.index_information().keys())
    }
