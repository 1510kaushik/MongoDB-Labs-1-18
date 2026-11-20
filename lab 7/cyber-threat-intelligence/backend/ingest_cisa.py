import requests
from datetime import datetime, timezone
from pymongo import UpdateOne
from .db import db
from .config import CISA_FEED_URL, CISA_CATALOG_URL

def import_cisa():
    response = requests.get(CISA_FEED_URL, timeout=45, headers={"User-Agent": "Student-CTI-Lab/1.0"})
    response.raise_for_status()
    feed = response.json()
    records = feed.get("vulnerabilities", [])
    now = datetime.now(timezone.utc)
    operations = []
    source = db.sources.find_one_and_update(
        {"source_key": "cisa-kev"},
        {"$set": {"name": "CISA Known Exploited Vulnerabilities Catalog",
                  "url": CISA_CATALOG_URL, "publisher": "Cybersecurity and Infrastructure Security Agency",
                  "source_type": "government_catalog", "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True, return_document=True
    )
    for item in records:
        cve_id = item.get("cveID")
        if not cve_id:
            continue
        document = {
            "cve_id": cve_id,
            "vendor_project": item.get("vendorProject"),
            "product": item.get("product"),
            "vulnerability_name": item.get("vulnerabilityName"),
            "short_description": item.get("shortDescription"),
            "date_added": item.get("dateAdded"),
            "due_date": item.get("dueDate"),
            "known_ransomware_campaign_use": item.get("knownRansomwareCampaignUse"),
            "required_action": item.get("requiredAction"),
            "notes": item.get("notes"),
            "source_id": source["_id"],
            "source": {"name": "CISA KEV", "url": CISA_CATALOG_URL},
            "classification": {
                "category": "Known Exploited Vulnerability",
                "verified_exploitation": True,
                "method": "CISA KEV catalog membership",
                "severity": None,
                "severity_note": "No severity score inferred by this importer."
            },
            "last_imported_at": now
        }
        operations.append(UpdateOne({"cve_id": cve_id}, {"$set": document, "$setOnInsert": {"first_imported_at": now}}, upsert=True))
    if operations:
        result = db.threats.bulk_write(operations, ordered=False)
        inserted, modified = result.upserted_count, result.modified_count
    else:
        inserted = modified = 0
    print(f"Feed release date: {feed.get('dateReleased', 'not provided')}")
    print(f"Records in feed: {len(records)} | inserted: {inserted} | updated: {modified}")
    print(f"Total threats in database: {db.threats.count_documents({})}")
    return {"feed_date": feed.get("dateReleased"), "feed_count": len(records), "inserted": inserted, "modified": modified}

if __name__ == "__main__":
    import_cisa()
