import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://127.0.0.1:27018/?directConnection=true"
)

DATABASE_NAME = os.getenv(
    "MONGODB_DATABASE",
    "mongodb_lab10"
)

SERVER_SELECTION_TIMEOUT_MS = 5000