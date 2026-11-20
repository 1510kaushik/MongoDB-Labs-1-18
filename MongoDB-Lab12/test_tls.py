
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

username = os.getenv("MONGO_INITDB_ROOT_USERNAME")
password = os.getenv("MONGO_INITDB_ROOT_PASSWORD")

if not username or not password:
    raise RuntimeError("MongoDB credentials missing from .env")

base = Path(__file__).resolve().parent

ca_file = base / "certificates" / "ca" / "ca.crt"
client_file = base / "certificates" / "client" / "client.pem"

uri = (
    f"mongodb://{quote_plus(username)}:{quote_plus(password)}"
    "@localhost:27131/?authSource=admin"
)

print("Testing MongoDB TLS connection with client certificate...")

try:
    client = MongoClient(
        uri,
        tls=True,
        tlsCAFile=str(ca_file),
        tlsCertificateKeyFile=str(client_file),
        serverSelectionTimeoutMS=5000
    )

    print("Server response:", client.admin.command("ping"))
    print("Database connection successful!")
    print("TLS and client certificate verification successful.")

    client.close()

except PyMongoError as error:
    print("TLS connection failed:")
    print(type(error).__name__, error)
