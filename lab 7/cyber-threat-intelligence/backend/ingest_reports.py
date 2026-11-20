
import re
import requests
from datetime import datetime, timezone
from pymongo import UpdateOne
from pymongo import ReturnDocument

from .db import db
from .config import REPORTS_README_URL, REPORTS_REPO_URL


LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', re.I)
YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')


def clean_title(title):
    return re.sub(r'[*_`#]', '', title).strip()


def sync_reports():
    response = requests.get(
        REPORTS_README_URL,
        timeout=45,
        headers={"User-Agent": "Student-CTI-Lab/1.0"}
    )
    response.raise_for_status()

    readme = response.text
    now = datetime.now(timezone.utc)

    source = db.sources.find_one_and_update(
        {"source_key": "annual-security-reports-github"},
        {
            "$set": {
                "name": "Awesome Annual Security Reports",
                "url": REPORTS_REPO_URL,
                "publisher": "Community-maintained GitHub repository",
                "source_type": "report_index",
                "updated_at": now
            },
            "$setOnInsert": {
                "created_at": now
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

    ops = []
    seen = set()

    for line in readme.splitlines():
        for title, url in LINK_RE.findall(line):
            url = url.rstrip(".,;")

            if "github.com/jacobdjwilson/awesome-annual-security-reports" in url.lower():
                continue

            if url in seen:
                continue

            seen.add(url)

            normalized_title = clean_title(title)

            year_matches = re.findall(
                r'\b(?:19|20)\d{2}\b',
                normalized_title + " " + line
            )

            report_data = {
                "title": normalized_title[:500],
                "url": url,
                "year": int(year_matches[0]) if year_matches else None,
                "source_id": source["_id"],
                "source_name": source["name"],
                "discovered_from": REPORTS_REPO_URL
            }

            ops.append(
                UpdateOne(
                    {"url": url},
                    {
                        "$set": report_data,
                        "$setOnInsert": {
                            "first_discovered_at": now
                        }
                    },
                    upsert=True
                )
            )

    inserted = 0
    modified = 0

    if ops:
        result = db.reports.bulk_write(ops, ordered=False)
        inserted = result.upserted_count
        modified = result.modified_count

    print(f"Unique external links scanned: {len(seen)}")
    print(f"New report/link records: {inserted} | updated: {modified}")
    print(f"Total report records: {db.reports.count_documents({})}")

    return {
        "scanned": len(seen),
        "inserted": inserted,
        "modified": modified
    }


if __name__ == "__main__":
    sync_reports()
