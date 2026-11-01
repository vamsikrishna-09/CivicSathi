import sqlite3

import pytest

import agents
import database
from utils import normalize_tracking_id


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    database.init_db(path)
    return path


def sample(**kw):
    base = dict(description="Pothole", location="Main Rd", category="Pothole / Road Damage", summary="Pothole",
                priority="High", department="Roads & Engineering", priority_reason="r", department_reason="r",
                human_review=True, analysis_mode="DEMO", image_filename=None)
    base.update(kw)
    return base


def test_init_creates_table(db):
    with sqlite3.connect(db) as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert "complaints" in names


def test_insert_and_retrieve(db):
    saved = database.insert_complaint(db, sample())
    assert normalize_tracking_id(saved["tracking_id"]) == saved["tracking_id"]
    assert saved["status"] == "Submitted"
    assert database.get_by_tracking_id(db, saved["tracking_id"])["description"] == "Pothole"


def test_tracking_ids_unique(db):
    ids = {database.insert_complaint(db, sample())["tracking_id"] for _ in range(25)}
    assert len(ids) == 25


def test_collision_is_retried(db, monkeypatch):
    first = database.insert_complaint(db, sample())["tracking_id"]
    seq = iter([first, first, "CS-2026-ZZZZZZ"])
    monkeypatch.setattr(database, "generate_tracking_id", lambda: next(seq))
    assert database.insert_complaint(db, sample())["tracking_id"] == "CS-2026-ZZZZZZ"


def test_unknown_and_hostile_ids_return_none(db):
    database.insert_complaint(db, sample())
    assert database.get_by_tracking_id(db, "CS-2026-NOPE22") is None
    assert database.get_by_tracking_id(db, "x' OR '1'='1") is None


def test_status_update_persists(db):
    tid = database.insert_complaint(db, sample())["tracking_id"]
    assert database.update_status(db, tid, "In Progress") is True
    assert database.get_by_tracking_id(db, tid)["status"] == "In Progress"
    assert database.update_status(db, "CS-2026-NOPE22", "Resolved") is False


def test_invalid_status_rejected(db):
    tid = database.insert_complaint(db, sample())["tracking_id"]
    with pytest.raises(ValueError):
        database.update_status(db, tid, "Done")
    assert database.get_by_tracking_id(db, tid)["status"] == "Submitted"


def test_invalid_values_rejected_on_insert(db):
    for bad in (dict(category="Aliens"), dict(priority="Urgent"), dict(department="Nowhere")):
        with pytest.raises(ValueError):
            database.insert_complaint(db, sample(**bad))
    assert database.list_complaints(db) == []


def test_filters(db):
    database.insert_complaint(db, sample())
    database.insert_complaint(db, sample(category="Garbage / Waste", department="Sanitation", priority="Low"))
    assert len(database.list_complaints(db)) == 2
    assert len(database.list_complaints(db, category="Garbage / Waste")) == 1
    assert len(database.list_complaints(db, priority="High")) == 1
    assert database.list_complaints(db, status="Resolved") == []
    assert database.status_counts(db)["Submitted"] == 2


def test_seed_demo_data_once(db):
    assert database.seed_demo_data(db) == 5
    assert database.seed_demo_data(db) == 0
    assert all(c["is_demo"] and c["description"].startswith("[DEMO DATA]") for c in database.list_complaints(db))


def test_registration_stage_saves_only_when_called(db, tmp_path):
    result = agents.run_analysis("Deep pothole near the bus stop", "Main road")
    assert database.list_complaints(db) == []
    pending = {"description": "Deep pothole near the bus stop", "location": "Main road", "category": "Auto-detect",
               "image": {"name": "../../evil.png", "data": b"\x89PNG\r\n\x1a\nxxxx"}, **result}
    complaint, trace = agents.register_complaint(db, pending, str(tmp_path / "up"))
    assert complaint["status"] == "Submitted" and len(database.list_complaints(db)) == 1
    assert trace[0]["Stage"] == "Complaint Registration"
    assert (tmp_path / "up" / complaint["image_filename"]).exists()
    assert ".." not in complaint["image_filename"]
