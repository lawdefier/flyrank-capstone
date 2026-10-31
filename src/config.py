"""
Configuration Module for Capstone Platform.
Loads environment variables from .env with fallback defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

PORT = int(os.getenv("PORT", "8000"))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./platform.db")

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "5"))

MOCK_GEO_FAIL_A = os.getenv("MOCK_GEO_FAIL_A", "false").lower() == "true"
MOCK_GEO_FAIL_B = os.getenv("MOCK_GEO_FAIL_B", "false").lower() == "true"
MOCK_EMAIL_FAIL = os.getenv("MOCK_EMAIL_FAIL", "false").lower() == "true"
