"""Configuration, read from environment variables. Never hardcode secrets here."""
import os

try:  # python-dotenv is optional; real environment variables always work.
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()   # optional
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip()       # optional
DEMO_MODE = _flag("CIVICSATHI_DEMO_MODE", "true")          # demo is the default
DB_PATH = os.getenv("CIVICSATHI_DB_PATH", "").strip() or "civicsathi.db"
UPLOAD_DIR = os.getenv("CIVICSATHI_UPLOAD_DIR", "").strip() or "uploads"
