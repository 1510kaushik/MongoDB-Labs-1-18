from backend.db import db, client, verify_connection

try:
    print("Checking Lab 10 MongoDB connection...")
    result = verify_connection()

    print("\nCONNECTION SUCCESSFUL")
    for key, value in result.items():
        print(f"{key}: {value}")

    print("\nCollections:", db.list_collection_names())

except Exception as error:
    print("\nCONNECTION FAILED:", error)

finally:
    client.close()