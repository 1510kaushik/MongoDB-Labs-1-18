
from pathlib import Path
from pymongo import MongoClient
from pymongo.errors import PyMongoError

base = Path(__file__).resolve().parent
ca_file = base / "certificates" / "ca" / "ca.crt"

client = MongoClient(
    "mongodb://localhost:27131/?directConnection=true",
    tls=True,
    tlsCAFile=str(ca_file),
    serverSelectionTimeoutMS=5000
)

try:
    client.admin.command("ping")
    print("WARNING: Connection succeeded without a client certificate.")
except PyMongoError:
    print("SUCCESS: Connection rejected without a client certificate.")
finally:
    client.close()
