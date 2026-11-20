from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure
import os

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

CA = BASE / "certificates" / "ca" / "ca.crt"
CERT = BASE / "certificates" / "client" / "client.pem"
DB = "nosql_labs"

def connect(user, password):
    uri = (
        f"mongodb://{quote_plus(user)}:{quote_plus(password)}"
        f"@127.0.0.1:27131/?authSource={DB}"
    )
    return MongoClient(
        uri, tls=True, tlsCAFile=str(CA),
        tlsCertificateKeyFile=str(CERT),
        serverSelectionTimeoutMS=5000
    )

for username, key in [("reader", "READER_PASSWORD"), ("writer", "WRITER_PASSWORD")]:
    print(f"\n--- {username.upper()} TEST ---")
    client = connect(username, os.getenv(key))
    try:
        db = client[DB]

        try:
            record = (
                db.employees_safe.find_one()
                if username == "reader"
                else db.employees.find_one()
            )
            print("Read access: SUCCESS" if record else "Read query succeeded; collection is empty")
            if record:
                print("Salary visible:", "salary" in record)
        except OperationFailure as e:
            print("Read access: DENIED", e.code)

        try:
            db.employees.delete_one({"employee_id": -999999})
            print("Delete permission: ALLOWED")
        except OperationFailure:
            print("Delete permission: DENIED (EXPECTED)")

        if username == "reader":
            try:
                db.employees.find_one()
                print("Direct collection access: UNEXPECTEDLY ALLOWED")
            except OperationFailure:
                print("Direct collection access: DENIED (EXPECTED)")

    finally:
        client.close()
