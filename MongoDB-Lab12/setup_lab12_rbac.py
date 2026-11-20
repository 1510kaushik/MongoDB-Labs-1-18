
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure

load_dotenv()

ROOT_USER = os.getenv("MONGO_INITDB_ROOT_USERNAME")
ROOT_PASSWORD = os.getenv("MONGO_INITDB_ROOT_PASSWORD")
ANALYST_PASSWORD = os.getenv("ANALYST_PASSWORD")
HR_PASSWORD = os.getenv("HR_PASSWORD")

if not all([ROOT_USER, ROOT_PASSWORD, ANALYST_PASSWORD, HR_PASSWORD]):
    raise RuntimeError("One or more credentials are missing from .env")

BASE = Path(__file__).resolve().parent
CA_FILE = BASE / "certificates" / "ca" / "ca.crt"
CLIENT_CERT = BASE / "certificates" / "client" / "client.pem"

DB_NAME = "nosql_labs"


def connect(username, password, auth_db):
    uri = (
        f"mongodb://{quote_plus(username)}:{quote_plus(password)}"
        f"@localhost:27131/?authSource={auth_db}"
    )
    return MongoClient(
        uri,
        tls=True,
        tlsCAFile=str(CA_FILE),
        tlsCertificateKeyFile=str(CLIENT_CERT),
        serverSelectionTimeoutMS=5000
    )


def recreate_role(db, role_name, privileges):
    existing = db.command({
        "rolesInfo": role_name,
        "showPrivileges": False
    })

    if existing.get("roles"):
        db.command({"dropRole": role_name})

    db.command({
        "createRole": role_name,
        "privileges": privileges,
        "roles": []
    })


def recreate_user(db, username, password, role_name):
    existing = db.command({"usersInfo": username})

    if existing.get("users"):
        db.command({"dropUser": username})

    db.command({
        "createUser": username,
        "pwd": password,
        "roles": [{"role": role_name, "db": DB_NAME}]
    })


admin_client = connect(ROOT_USER, ROOT_PASSWORD, "admin")

try:
    admin_client.admin.command("ping")
    db = admin_client[DB_NAME]

    print("Connected to MongoDB with administrator credentials.")

    # Create sample employee records.
    employees = db["employees"]

    if employees.count_documents({}) == 0:
        employees.insert_many([
            {
                "employee_id": 101,
                "name": "Aarav",
                "department": "IT",
                "title": "Developer",
                "salary": 65000
            },
            {
                "employee_id": 102,
                "name": "Diya",
                "department": "HR",
                "title": "HR Executive",
                "salary": 55000
            },
            {
                "employee_id": 103,
                "name": "Rohan",
                "department": "Finance",
                "title": "Analyst",
                "salary": 70000
            }
        ])

    print("Employee sample data ready.")

    # Recreate the safe view.
    if "employees_safe" in db.list_collection_names():
        db.drop_collection("employees_safe")

    db.command({
        "create": "employees_safe",
        "viewOn": "employees",
        "pipeline": [
            {
                "$project": {
                    "_id": 1,
                    "employee_id": 1,
                    "name": 1,
                    "department": 1,
                    "title": 1
                }
            }
        ]
    })

    print("Created employees_safe view without salary.")

    # Analyst can only find documents through the safe view.
    recreate_role(
        db,
        "analystViewRole",
        [{
            "resource": {
                "db": DB_NAME,
                "collection": "employees_safe"
            },
            "actions": ["find"]
        }]
    )

    # HR can only find documents in the original employees collection.
    recreate_role(
        db,
        "hrEmployeeReadRole",
        [{
            "resource": {
                "db": DB_NAME,
                "collection": "employees"
            },
            "actions": ["find"]
        }]
    )

    print("Created two collection-scoped roles.")

    recreate_user(
        db, "analyst", ANALYST_PASSWORD, "analystViewRole"
    )

    recreate_user(
        db, "hr_user", HR_PASSWORD, "hrEmployeeReadRole"
    )

    print("Created analyst and hr_user.")

    admin_client.close()

    # Test analyst permissions.
    print("\n--- ANALYST PERMISSION TEST ---")

    with connect("analyst", ANALYST_PASSWORD, DB_NAME) as client:
        analyst_db = client[DB_NAME]

        safe_record = analyst_db.employees_safe.find_one()

        print("Safe view access: SUCCESS")
        print("Returned fields:", list(safe_record.keys()))
        print("Salary visible:", "salary" in safe_record)

        try:
            analyst_db.employees.find_one()
            print("WARNING: Analyst accessed employees collection.")
        except OperationFailure:
            print("Direct employees access: DENIED (expected)")

    # Test HR permissions.
    print("\n--- HR PERMISSION TEST ---")

    with connect("hr_user", HR_PASSWORD, DB_NAME) as client:
        hr_db = client[DB_NAME]

        hr_record = hr_db.employees.find_one()

        print("Employees collection access: SUCCESS")
        print("Returned fields:", list(hr_record.keys()))
        print("Salary visible:", "salary" in hr_record)

        try:
            hr_db.employees.insert_one({
                "employee_id": 999,
                "name": "Unauthorized Test"
            })
            print("WARNING: HR inserted a document.")
        except OperationFailure:
            print("Insert permission: DENIED (expected)")

    print("\nLab 12.1 RBAC and view tests completed.")

finally:
    admin_client.close()
