import pytest

import agents
import ai_service
from models import CATEGORIES, DEPARTMENTS, PRIORITIES

CASES = [
    ("There is a large pothole near the bus stop.", "Pothole / Road Damage"),
    ("Garbage is piling up near the market.", "Garbage / Waste"),
    ("A water pipe is leaking on the main road.", "Water Leakage"),
    ("The blocked drain near the school smells bad.", "Blocked Drain"),
    ("The streetlight on 5th street is not working.", "Broken Streetlight"),
    ("The park bench needs a fresh coat of paint.", "Other"),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_keyword_classification(text, expected):
    assert agents.demo_analyze(text).category == expected


def test_drain_with_waste_prefers_drain():
    assert agents.demo_analyze("Drain blocked with waste after rainfall").category == "Blocked Drain"


def test_selected_category_is_respected():
    assert agents.demo_analyze("Something odd", "Water Leakage").category == "Water Leakage"


def test_priority_always_supported():
    for text, _ in CASES:
        result = agents.run_analysis(text, "Main road")
        assert result["routing"].priority in PRIORITIES


def test_unclear_severity_defaults_to_medium_with_review():
    result = agents.run_analysis("There is a pothole.", "Main road")["routing"]
    assert result.priority == "Medium" and result.human_review is True


def test_high_and_low_priority():
    assert agents.run_analysis("Deep pothole causing accidents", "x")["routing"].priority == "High"
    assert agents.run_analysis("A minor pothole on a quiet lane", "x")["routing"].priority == "Low"


def test_department_mapping():
    for category in CATEGORIES:
        analysis = agents.demo_analyze("anything", category)
        assert agents.demo_route("anything", analysis).department == DEPARTMENTS[category]


def test_demo_output_labelled_demo_and_trace():
    result = agents.run_analysis("Large pothole near the bus stop", "Main road")
    assert result["analysis"].analysis_mode == "DEMO" and result["routing"].analysis_mode == "DEMO"
    assert [t["Mode"] for t in result["trace"]] == ["DEMO", "DEMO"]
    assert result["analysis"].confidence is None


def test_image_is_not_claimed_as_analysed():
    note = agents.run_analysis("pothole", "x", has_image=True)["analysis"].image_note.lower()
    assert "not visually analysed" in note
    assert agents.run_analysis("pothole", "x")["analysis"].image_note == ""


def test_valid_ai_output_is_labelled_ai(monkeypatch):
    monkeypatch.setattr(ai_service, "analyze_issue", lambda *a, **k: {
        "category": "Water Leakage", "summary": "Pipe leak", "evidence_notes": ["leak"], "confidence": 0.8})
    result = agents.run_analysis("pipe is leaking", "x", has_image=True)
    assert result["analysis"].analysis_mode == "AI"
    assert "not visually analysed" in result["analysis"].image_note.lower()


@pytest.mark.parametrize("bad", [{"category": "Nonsense", "summary": "x"}, "not a dict",
                                 {"category": "Other", "summary": ""},
                                 {"category": "Other", "summary": "ok", "confidence": 5}])
def test_malformed_ai_output_falls_back(monkeypatch, bad):
    monkeypatch.setattr(ai_service, "analyze_issue", lambda *a, **k: bad)
    result = agents.run_analysis("pothole on road", "x")
    assert result["analysis"].analysis_mode == "DEMO"
    assert "demo rules were used" in result["trace"][0]["Output"]


def test_ai_exception_falls_back(monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("slow")
    monkeypatch.setattr(ai_service, "analyze_issue", boom)
    monkeypatch.setattr(ai_service, "assess_severity_and_route", boom)
    result = agents.run_analysis("garbage everywhere", "x")
    assert result["analysis"].analysis_mode == "DEMO" and result["routing"].analysis_mode == "DEMO"


def test_analysis_does_not_touch_database(tmp_path):
    import database
    db = str(tmp_path / "t.db")
    database.init_db(db)
    agents.run_analysis("pothole", "x")
    assert database.list_complaints(db) == []
