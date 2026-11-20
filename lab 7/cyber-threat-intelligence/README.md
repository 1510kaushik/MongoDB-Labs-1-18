# Cyber Threat Intelligence Platform (MongoDB Labs 7.1 & 7.2)

A student project combining a real-data CTI dashboard with MongoDB schema analysis, BSON-size checks, a 100,000-document working-set test, WiredTiger cache monitoring, and annual-report discovery.

## Important data integrity notes
- The CISA Known Exploited Vulnerabilities (KEV) feed is imported live by `backend/ingest_cisa.py`. It does not ship with fabricated CVE records.
- Annual security report links are discovered from the public `awesome-annual-security-reports` GitHub README by `backend/ingest_reports.py`. This collector stores source links and extracted titles/years, not the full report contents.
- `working_set_test` contains synthetic performance-only documents and is deliberately kept separate from real threat data.
- Severity is not invented from CISA KEV membership. The UI distinguishes CISA KEV membership from a vulnerability severity score.
- You must run the scripts in your own MongoDB environment to produce actual measurements. The project does not claim test results that have not been measured.

## Requirements
- Python 3.10+
- MongoDB Community Server running locally, or a MongoDB connection URI
- Internet access for the real-source importers

## Setup (Windows PowerShell)
```powershell
cd cyber-threat-intelligence
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env if your MongoDB URI differs
python -m backend.ingest_cisa
python -m backend.ingest_reports
python -m backend.schema_analysis
python -m backend.app
```
Open http://127.0.0.1:5000

If PowerShell blocks activation, run `.venv\Scripts\python.exe -m pip install -r requirements.txt`, then use `.venv\Scripts\python.exe -m backend.app`.

## Run Lab 7.2
In a second terminal (same venv):
```powershell
python -m backend.working_set_test
python -m backend.cache_monitor
```
The working-set test drops and recreates ONLY `working_set_test`; it does not drop real threat/report collections. The monitor writes a sample every 10 seconds to `performance_events`. Stop it with Ctrl+C. Run random reads while the monitor is running in another terminal:
```powershell
python -m backend.random_reads
```
Cache metrics depend on MongoDB version and workload. The monitor calculates an interval estimate from counter deltas; treat it as an estimate, not a universal official hit-rate metric.

## Create indexes
Run from the project root:
```powershell
mongosh mongodb://localhost:27017/cyber_threat_intel scripts/create_indexes.js
```
If using a remote URI, run the script in `mongosh` with your URI (do not put credentials in source files).

## API routes
- `GET /api/health`
- `GET /api/threats?q=apache&category=Known Exploited Vulnerability&page=1&limit=20`
- `GET /api/threats/<CVE-ID>`
- `GET /api/reports?q=annual`
- `GET /api/metrics/schema`
- `GET /api/metrics/cache`
- `POST /api/sync/cisa` (refresh CISA feed)
- `POST /api/sync/reports` (refresh annual-report index)

## MongoDB schema decisions (Lab 7.1)
- `threats`: canonical vulnerability facts keyed by unique `cve_id`; small classification object embedded because it is read with the threat.
- `sources`: publisher metadata, stored once.
- `threat_source_links`: references `threat_id`/`source_id`; appropriate for many-to-many threat/source relationships.
- `reports`: metadata and canonical URL only, avoiding large report text duplicated across threat records.
- `schema_metrics`: measured `$bsonSize` summary.
- `working_set_test` and `performance_events`: synthetic performance data/observations only.

Embedding the small `sources` array into each threat can speed up threat detail reads, but duplicates source metadata and makes publisher-wide updates and reverse queries more expensive. The UI/schema uses references for source relationships as the baseline design.

## Data and attribution
- CISA KEV catalog: https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- CISA JSON feed: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
- CTIDigest (manual supplementary research; verify access terms before scraping): https://ctidigest.com/
- Annual security report index: https://github.com/jacobdjwilson/awesome-annual-security-reports

Please follow the source websites' terms and respect rate limits. The GitHub README is a curated index, so report metadata may be incomplete. Verify report dates/titles against the publisher before making claims.

## Submission checklist
1. Import real CISA data and report links.
2. Open the dashboard and test search/classification.
3. Run schema analysis and retain the actual printed BSON metrics.
4. Run the 100k working-set test and cache monitor; record actual observations.
5. Include screenshots of your own running app and outputs in your submission.
6. Zip the project folder after testing. Do not include `.venv`, `.env`, database files, passwords, or caches.
