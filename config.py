"""Configuration from environment variables or Streamlit secrets.
Never hardcode secrets here.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _setting(name: str, default: str = "") -> str:
    """Read from environment first, then Streamlit Cloud secrets."""
    value = os.getenv(name)

    if value is not None and value.strip():
        return value.strip()

    try:
        import streamlit as st
        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return default


def _flag(name: str, default: str) -> bool:
    return _setting(name, default).lower() in {
        "1", "true", "yes", "on"
    }


GEMINI_API_KEY = _setting("GEMINI_API_KEY")
GEMINI_MODEL = _setting("GEMINI_MODEL")

DEMO_MODE = _flag("CIVICSATHI_DEMO_MODE", "true")

DB_PATH = _setting("CIVICSATHI_DB_PATH") or "civicsathi.db"
UPLOAD_DIR = _setting("CIVICSATHI_UPLOAD_DIR") or "uploads"