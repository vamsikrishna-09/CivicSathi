"""SQLite persistence. All user values go through parameterised queries."""
import os
import sqlite3
from contextlib import closing

from models import CATEGORIES, PRIORITIES, STATUSES, DEPARTMENTS, validate_status
from utils import generate_tracking_id, utc_now


def _in(values):
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)  # fixed constants only


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_id TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    location TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ({_in(CATEGORIES)})),
    summary TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ({_in(PRIORITIES)})),
    department TEXT NOT NULL,
    priority_reason TEXT NOT NULL,
    department_reason TEXT NOT NULL,
    human_review INTEGER NOT NULL DEFAULT 0,
    analysis_mode TEXT NOT NULL CHECK (analysis_mode IN ('DEMO', 'AI')),
    status TEXT NOT NULL CHECK (status IN ({_in(STATUSES)})),
    image_filename TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_FIELDS = ("description", "location", "category", "summary", "priority", "department",
           "priority_reason", "department_reason", "human_review", "analysis_mode",
           "image_filename", "is_demo")


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _to_dict(row):
    if row is None:
        return None
    d = dict(row)
    d["human_review"] = bool(d["human_review"])
    d["is_demo"] = bool(d["is_demo"])
    return d


def init_db(db_path):
    folder = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(folder, exist_ok=True)
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(SCHEMA)


def insert_complaint(db_path, fields, max_attempts=5):
    """Insert a complaint with status 'Submitted'; return the saved record.

    The tracking ID is generated here; a UNIQUE collision triggers a retry.
    Values are validated so AI output cannot bypass the supported schema.
    """
    if fields.get("category") not in CATEGORIES:
        raise ValueError("Unsupported category.")
    if fields.get("priority") not in PRIORITIES:
        raise ValueError("Unsupported priority.")
    if fields.get("department") not in DEPARTMENTS.values():
        raise ValueError("Unsupported department.")
    values = [fields.get(k) for k in _FIELDS]
    values[_FIELDS.index("human_review")] = int(bool(fields.get("human_review")))
    values[_FIELDS.index("is_demo")] = int(bool(fields.get("is_demo")))
    now = utc_now()
    sql = (f"INSERT INTO complaints (tracking_id, {', '.join(_FIELDS)}, status, created_at, updated_at) "
           f"VALUES (?, {', '.join('?' for _ in _FIELDS)}, 'Submitted', ?, ?)")
    for _ in range(max_attempts):
        tracking_id = generate_tracking_id()
        try:
            with closing(_connect(db_path)) as conn, conn:
                conn.execute(sql, [tracking_id, *values, now, now])
            return get_by_tracking_id(db_path, tracking_id)
        except sqlite3.IntegrityError as exc:
            if "tracking_id" not in str(exc):
                raise
    raise RuntimeError("Could not generate a unique tracking ID.")


def get_by_tracking_id(db_path, tracking_id):
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT * FROM complaints WHERE tracking_id = ?", (tracking_id,)).fetchone()
    return _to_dict(row)


def list_complaints(db_path, category=None, priority=None, status=None):
    clauses, params = [], []
    for column, value in (("category", category), ("priority", priority), ("status", status)):
        if value and value != "All":
            clauses.append(f"{column} = ?")  # column names are fixed above
            params.append(value)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(f"SELECT * FROM complaints{where} ORDER BY created_at DESC, id DESC", params).fetchall()
    return [_to_dict(r) for r in rows]


def update_status(db_path, tracking_id, status):
    """Update a status. Returns False if the tracking ID does not exist."""
    validate_status(status)
    with closing(_connect(db_path)) as conn, conn:
        cur = conn.execute("UPDATE complaints SET status = ?, updated_at = ? WHERE tracking_id = ?",
                           (status, utc_now(), tracking_id))
    return cur.rowcount > 0


def delete_complaint(db_path, tracking_id):
    """Delete a complaint by tracking ID. Returns True if deleted."""
    with closing(_connect(db_path)) as conn, conn:
        cur = conn.execute(
            "DELETE FROM complaints WHERE tracking_id = ?",
            (tracking_id,)
        )
    return cur.rowcount > 0

def status_counts(db_path):
    with closing(_connect(db_path)) as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM complaints GROUP BY status").fetchall()
    counts = {s: 0 for s in STATUSES}
    counts.update({r["status"]: r["n"] for r in rows})
    return counts


_SAMPLES = [
    ("Large pothole near a public bus stop causing vehicles to swerve", "Near the main bus stop, central area", "Pothole / Road Damage", "High"),
    ("Garbage overflowing from a public waste bin", "Market road, east locality", "Garbage / Waste", "Medium"),
    ("Water continuously leaking from a roadside pipe", "Lake view road junction", "Water Leakage", "High"),
    ("Drain blocked with waste after rainfall", "Near the primary school gate", "Blocked Drain", "Medium"),
    ("Streetlight not working on a public road", "Park avenue, near the community hall", "Broken Streetlight", "Medium"),
]


def seed_demo_data(db_path):
    """Add five fictional, clearly labelled sample complaints (once). Returns how many were added."""
    with closing(_connect(db_path)) as conn:
        if conn.execute("SELECT COUNT(*) FROM complaints WHERE is_demo = 1").fetchone()[0]:
            return 0
    for text, location, category, priority in _SAMPLES:
        insert_complaint(db_path, {
            "description": f"[DEMO DATA] {text}", "location": location, "category": category,
            "summary": f"Citizen reports: {text}", "priority": priority,
            "department": DEPARTMENTS[category],
            "priority_reason": "Fictional sample record.", "department_reason": "Fictional sample record.",
            "human_review": False, "analysis_mode": "DEMO", "image_filename": None, "is_demo": True,
        })
    return len(_SAMPLES)
