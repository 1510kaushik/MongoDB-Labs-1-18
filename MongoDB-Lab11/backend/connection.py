from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .config import MONGOS_URI, DATABASE_NAME

client = MongoClient(
    MONGOS_URI,
    serverSelectionTimeoutMS=5000
)

db = client[DATABASE_NAME]


def check_connection():
    try:
        result = client.admin.command("ping")
        return {
            "connected": True,
            "message": "MongoDB Mongos connection successful",
            "ping": result.get("ok")
        }
    except PyMongoError as error:
        return {
            "connected": False,
            "message": str(error)
        }
