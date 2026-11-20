from pymongo import MongoClient
from .config import MONGODB_URI, DATABASE_NAME

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
db = client[DATABASE_NAME]

def check_connection():
    client.admin.command("ping")
    return True
