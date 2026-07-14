import os
from dotenv import load_dotenv

# Load environment variables from .env in the same directory
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

class Config:
    # SQLite replaces Postgres
    DATA_DIR = os.environ.get("AGENTOS_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(DATA_DIR, 'agentos.db')}")
    # diskcache replaces Redis
    CACHE_DIR = os.environ.get("AGENTOS_CACHE_DIR", os.path.join(DATA_DIR, "cache"))
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "72"))
    REFRESH_EXPIRY_DAYS = int(os.environ.get("REFRESH_EXPIRY_DAYS", "30"))
    PORT = int(os.environ.get("PORT", "8000"))
    DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
    RATE_LIMIT_DEFAULT = int(os.environ.get("RATE_LIMIT_DEFAULT", "60"))
    RATE_LIMIT_AUTH = int(os.environ.get("RATE_LIMIT_AUTH", "10"))
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))
