import os
from dotenv import load_dotenv

load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("MONGODB_DATABASE", "cyber_threat_intel")
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
CISA_FEED_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
REPORTS_README_URL = "https://raw.githubusercontent.com/jacobdjwilson/awesome-annual-security-reports/main/README.md"
REPORTS_REPO_URL = "https://github.com/jacobdjwilson/awesome-annual-security-reports"
CISA_CATALOG_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
