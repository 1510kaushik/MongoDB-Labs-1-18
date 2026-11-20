from pymongo import MongoClient
from backend.config import (
    MONGODB_URI,
    DATABASE_NAME,
    SERVER_SELECTION_TIMEOUT_MS
)

client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS
)

db = client[DATABASE_NAME]


def verify_connection():
    hello = client.admin.command("hello")

    if not hello.get("setName"):
        raise RuntimeError("MongoDB replica set not detected")

    if not hello.get("isWritablePrimary"):
        raise RuntimeError("Connected node is not primary")

    return {
        "connected": True,
        "replica_set": hello.get("setName"),
        "node": hello.get("me"),
        "primary": hello.get("primary"),
        "database": DATABASE_NAME
    }