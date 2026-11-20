import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

MONGOS_URI = os.getenv(
    "LAB11_MONGOS_URI",
    "mongodb://localhost:27120"
)

DATABASE_NAME = os.getenv(
    "LAB11_DATABASE",
    "mongodb_lab11"
)

FLASK_HOST = os.getenv("LAB11_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("LAB11_PORT", "5011"))
