import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo import MongoClient

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

ROOT_USER = os.getenv("MONGO_INITDB_ROOT_USERNAME")
ROOT_PASSWORD = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
READER_PASSWORD = os.getenv("READER_PASSWORD")
WRITER_PASSWORD = os.getenv("WRITER_PASSWORD")

DB_NAME = "nosql_labs"
CA_FILE = BASE / "certificates" / "ca" / "ca.crt"
CLIENT_CERT = BASE / "certificates" / "client" / "client.pem"

if not all([ROOT_USER, ROOT_PASSWORD, READER_PASSWORD, WRITER_PASSWORD]):
    raise RuntimeError("Missing required credentials in .env")

if not CA_FILE.is_file() or not CLIENT_CERT.is_file():
    raise RuntimeError("TLS certificate files are missing")


def connect(username, password, auth_db):
    uri = (
        f"mongodb://{quote_plus(username)}:{quote_plus(password)}"
        f"@127.0.0.1:27131/?authSource={auth_db}"
    )
    return MongoClient(
        uri,
        tls=True,
        tlsCAFile=str(CA_FILE),
        tlsCertificateKeyFile=str(CLIENT_CERT),
        serverSelectionTimeoutMS=5000,
    )


def ensure_role(db, name, privileges):
    existing = db.command({"rolesInfo": name})
    if existing.get("roles"):
        print(f"Role already exists; preserving it: {name}")
        return

    db.command({
        "createRole": name,
        "privileges": privileges,
        "roles": [],
    })
    print(f"Created role: {name}")


def ensure_user(db, username, password, role):
    existing = db.command({"usersInfo": username})
    if existing.get("users"):
        print(f"User already exists; preserving it: {username}")
        return

    db.command({
        "createUser": username,
        "pwd": password,
        "roles": [{"role": role, "db": DB_NAME}],
    })
    print(f"Created user: {username}")


client = connect(ROOT_USER, ROOT_PASSWORD, "admin")

try:
    client.admin.command("ping")
    db = client[DB_NAME]

    ensure_role(
        db,
        "readerViewRole",
        [{
            "resource": {"db": DB_NAME, "collection": "employees_safe"},
            "actions": ["find"],
        }],
    )

    ensure_role(
        db,
        "writerEmployeeRole",
        [{
            "resource": {"db": DB_NAME, "collection": "employees"},
            "actions": ["find", "insert", "update"],
        }],
    )

    ensure_user(db, "reader", READER_PASSWORD, "readerViewRole")
    ensure_user(db, "writer", WRITER_PASSWORD, "writerEmployeeRole")

    print("\nReader and Writer role setup completed.")
    print("Existing Analyst and HR accounts were not modified.")

finally:
    client.close()
