"""Small helpers: tracking IDs, safe file names, timestamps."""
import datetime as dt
import os
import re
import secrets
import uuid

# No 0/O/1/I so IDs are easy to read out loud.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_TRACKING_RE = re.compile(r"^CS-\d{4}-[A-Z0-9]{6}$")


def generate_tracking_id(year=None):
    year = year or dt.datetime.now(dt.timezone.utc).year
    return f"CS-{year}-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def normalize_tracking_id(raw):
    """Return an upper-cased valid tracking ID, or None if malformed."""
    value = (raw or "").strip().upper()
    return value if _TRACKING_RE.match(value) else None


def safe_image_name(original):
    """Random server-side name. The user's filename is never used as a path."""
    ext = ".png" if os.path.splitext(original or "")[1].lower() == ".png" else ".jpg"
    return uuid.uuid4().hex + ext


def save_image(data, original_name, folder):
    os.makedirs(folder, exist_ok=True)
    name = safe_image_name(original_name)
    with open(os.path.join(folder, name), "wb") as fh:
        fh.write(data)
    return name


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def format_time(iso):
    try:
        return dt.datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M UTC")
    except (TypeError, ValueError):
        return str(iso or "")
