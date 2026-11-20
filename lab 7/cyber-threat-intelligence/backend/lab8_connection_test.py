from pymongo import MongoClient

client = MongoClient(
    "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rs0",
    serverSelectionTimeoutMS=10000
)

hello = client.admin.command("hello")

print("Replica set:", hello.get("setName"))
print("Primary:", hello.get("primary"))
print("Threat count:", client.cyber_threat_intel.threats.count_documents({}))

client.close()
