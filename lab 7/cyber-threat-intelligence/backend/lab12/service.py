import os
import socket
import ssl
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure


# Load credentials from the separate Lab 12 environment file.
LAB12_ROOT = Path.home() / "Downloads" / "MongoDB-Lab12"
load_dotenv(LAB12_ROOT / ".env")

ROOT_USER = os.getenv("MONGO_INITDB_ROOT_USERNAME")
ROOT_PASSWORD = os.getenv("MONGO_INITDB_ROOT_PASSWORD")

ANALYST_PASSWORD = os.getenv("ANALYST_PASSWORD")
HR_PASSWORD = os.getenv("HR_PASSWORD")
READER_PASSWORD = os.getenv("READER_PASSWORD")
WRITER_PASSWORD = os.getenv("WRITER_PASSWORD")

DB_NAME = "nosql_labs"
MONGO_HOST = "127.0.0.1"
MONGO_PORT = 27131

CA_FILE = LAB12_ROOT / "certificates" / "ca" / "ca.crt"
CLIENT_CERT = LAB12_ROOT / "certificates" / "client" / "client.pem"


def connect(username, password, auth_db):
    if not username or not password:
        raise RuntimeError(f"Credentials are missing for MongoDB user: {username}")

    if not CA_FILE.is_file() or not CLIENT_CERT.is_file():
        raise RuntimeError("Lab 12 TLS certificate files were not found.")

    uri = (
        f"mongodb://{quote_plus(username)}:{quote_plus(password)}"
        f"@{MONGO_HOST}:{MONGO_PORT}/?authSource={auth_db}"
    )

    return MongoClient(
        uri,
        tls=True,
        tlsCAFile=str(CA_FILE),
        tlsCertificateKeyFile=str(CLIENT_CERT),
        serverSelectionTimeoutMS=5000,
    )


def get_tls_details():
    if not CA_FILE.is_file() or not CLIENT_CERT.is_file():
        raise RuntimeError("Lab 12 TLS certificate files were not found.")

    context = ssl.create_default_context(cafile=str(CA_FILE))
    context.check_hostname = False
    context.load_cert_chain(certfile=str(CLIENT_CERT))

    with socket.create_connection(
        (MONGO_HOST, MONGO_PORT), timeout=5
    ) as raw_socket:
        with context.wrap_socket(raw_socket) as tls_socket:
            cipher_info = tls_socket.cipher()

            return {
                "protocol": tls_socket.version(),
                "cipher": cipher_info[0] if cipher_info else "Unknown",
                "cipher_protocol": cipher_info[1] if cipher_info else "Unknown",
                "cipher_bits": cipher_info[2] if cipher_info else None,
            }


def check_tls_connection():
    client = None

    try:
        if not ROOT_USER or not ROOT_PASSWORD:
            raise RuntimeError("Lab 12 administrator credentials are missing.")

        # Verify the actual MongoDB connection using PyMongo.
        client = connect(ROOT_USER, ROOT_PASSWORD, "admin")
        client.admin.command("ping")

        # Read the negotiated TLS protocol and cipher.
        tls_details = get_tls_details()

        return {
            "status": "success",
            "message": "MongoDB TLS connection and client certificate verified.",
            "host": f"{MONGO_HOST}:{MONGO_PORT}",
            "database": DB_NAME,
            **tls_details,
        }

    except Exception as error:
        return {
            "status": "error",
            "message": f"{type(error).__name__}: {error}",
        }

    finally:
        if client:
            client.close()


def test_reader(results):
    if not READER_PASSWORD:
        raise RuntimeError("READER_PASSWORD is missing from the Lab 12 .env file.")

    client = connect("reader", READER_PASSWORD, DB_NAME)

    try:
        db = client[DB_NAME]
        record = db.employees_safe.find_one()

        results["reader"]["safe_view_access"] = "SUCCESS"
        results["reader"]["salary_visible"] = (
            "salary" in record if record else False
        )

        try:
            db.employees.find_one()
            results["reader"]["direct_collection_access"] = "UNEXPECTEDLY ALLOWED"
            results["status"] = "warning"
        except OperationFailure:
            results["reader"]["direct_collection_access"] = "DENIED (EXPECTED)"

        if results["reader"]["salary_visible"]:
            results["status"] = "warning"

    finally:
        client.close()


def test_writer(results):
    if not WRITER_PASSWORD:
        raise RuntimeError("WRITER_PASSWORD is missing from the Lab 12 .env file.")

    client = connect("writer", WRITER_PASSWORD, DB_NAME)

    try:
        db = client[DB_NAME]
        record = db.employees.find_one()

        results["writer"]["employee_collection_access"] = "SUCCESS"
        results["writer"]["salary_visible"] = (
            "salary" in record if record else False
        )

        # This selector is deliberately impossible, so no employee is changed.
        try:
            db.employees.update_one(
                {"employee_id": -999999},
                {"$set": {"dashboard_permission_test": True}},
                upsert=False,
            )
            results["writer"]["update_permission"] = "ALLOWED"
        except OperationFailure:
            results["writer"]["update_permission"] = "DENIED (UNEXPECTED)"
            results["status"] = "warning"

        try:
            db.employees.delete_one({"employee_id": -999999})
            results["writer"]["delete_permission"] = "UNEXPECTEDLY ALLOWED"
            results["status"] = "warning"
        except OperationFailure:
            results["writer"]["delete_permission"] = "DENIED (EXPECTED)"

    finally:
        client.close()


def test_analyst(results):
    if not ANALYST_PASSWORD:
        raise RuntimeError("ANALYST_PASSWORD is missing from the Lab 12 .env file.")

    client = connect("analyst", ANALYST_PASSWORD, DB_NAME)

    try:
        db = client[DB_NAME]
        record = db.employees_safe.find_one()

        results["analyst"]["safe_view_access"] = "SUCCESS"
        results["analyst"]["salary_visible"] = (
            "salary" in record if record else False
        )

        try:
            db.employees.find_one()
            results["analyst"]["direct_collection_access"] = "UNEXPECTEDLY ALLOWED"
            results["status"] = "warning"
        except OperationFailure:
            results["analyst"]["direct_collection_access"] = "DENIED (EXPECTED)"

        if results["analyst"]["salary_visible"]:
            results["status"] = "warning"

    finally:
        client.close()


def test_hr(results):
    if not HR_PASSWORD:
        raise RuntimeError("HR_PASSWORD is missing from the Lab 12 .env file.")

    client = connect("hr_user", HR_PASSWORD, DB_NAME)

    try:
        db = client[DB_NAME]
        record = db.employees.find_one()

        results["hr"]["employee_collection_access"] = "SUCCESS"
        results["hr"]["salary_visible"] = (
            "salary" in record if record else False
        )

        # HR is not permitted to insert. Use a unique test record and
        # remove it with the administrator if the permission is misconfigured.
        test_record = {
            "employee_id": -987654321,
            "name": "Temporary Lab 12 Permission Test",
        }

        try:
            db.employees.insert_one(test_record)
            results["hr"]["insert_permission"] = "UNEXPECTEDLY ALLOWED"
            results["status"] = "warning"

            admin_client = connect(ROOT_USER, ROOT_PASSWORD, "admin")
            try:
                admin_client[DB_NAME].employees.delete_one(test_record)
            finally:
                admin_client.close()

        except OperationFailure:
            results["hr"]["insert_permission"] = "DENIED (EXPECTED)"

        if record and "salary" not in record:
            results["status"] = "warning"

    finally:
        client.close()


def run_rbac_tests():
    results = {
        "status": "success",
        "reader": {},
        "writer": {},
        "analyst": {},
        "hr": {},
    }

    test_reader(results)
    test_writer(results)
    test_analyst(results)
    test_hr(results)

    return results


def get_lab12_status():
    return {
        "lab": "Lab 12",
        "tls": check_tls_connection(),
    }
