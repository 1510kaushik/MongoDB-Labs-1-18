
import time
from pymongo import MongoClient
from pymongo.errors import PyMongoError

NODES = {
    "mongo1": "mongodb://localhost:27017/?directConnection=true&serverSelectionTimeoutMS=3000",
    "mongo2": "mongodb://localhost:27018/?directConnection=true&serverSelectionTimeoutMS=3000",
    "mongo3": "mongodb://localhost:27019/?directConnection=true&serverSelectionTimeoutMS=3000"
}

last_primary = None

print("Lab 8.2 - MongoDB Failover Monitor")
print("Monitoring replica set: rs0")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        current_primary = None

        for node, uri in NODES.items():
            try:
                client = MongoClient(uri)
                hello = client.admin.command("hello")

                if hello.get("isWritablePrimary"):
                    current_primary = node

                client.close()

            except PyMongoError as error:
                print(f"{node}: Connection issue: {error}")

        if current_primary != last_primary:
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] Primary status changed: {current_primary or 'No primary detected'}")
            last_primary = current_primary

        time.sleep(2)

except KeyboardInterrupt:
    print("\nMonitoring stopped.")
