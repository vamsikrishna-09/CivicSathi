"""The three sequential workflow stages, as plain Python functions.

1. Issue Analysis  2. Severity & Department Routing  3. Complaint Registration
Stages 1-2 are read-only. Only stage 3 writes to the database, and only after
the citizen explicitly confirms.
"""
import logging
import os
import re
import time

import ai_service
import database
from models import (AUTO_DETECT, CATEGORIES, DEPARTMENTS, PRIORITIES, IssueAnalysis,
                    RoutingResult, validate_complaint)
from utils import save_image

log = logging.getLogger("civicsathi")

# Order matters: on a tie the earlier category wins.
CATEGORY_RULES = [
    ("Pothole / Road Damage", [r"\bpot[- ]?holes?\b", r"\broad damage\b", r"\bbroken roads?\b",
                               r"\bdamaged roads?\b", r"\broad\b.{0,20}\b(caved?|crater|cracked)\b"]),
    ("Blocked Drain", [r"\bblocked drains?\b", r"\bclogged drains?\b", r"\bdrainage block\w*",
                       r"\bdrain\w*", r"\bsewer\w*", r"\bmanholes?\b"]),
    ("Water Leakage", [r"\bleak\w*", r"\bwater pipes?\b", r"\bwater wastage\b", r"\bburst pipes?\b"]),
    ("Broken Streetlight", [r"\bstreet ?lights?\b", r"\bstreet lamps?\b", r"\blamp ?posts?\b",
                            r"\blamp\b.{0,20}\bnot working\b"]),
    ("Garbage / Waste", [r"\bgarbage\b", r"\bwaste\b", r"\btrash\b", r"\brubbish\b", r"\blitter\w*",
                         r"\boverflowing bins?\b", r"\bdump(ed|ing)?\b"]),
]

HIGH_PATTERNS = [r"\baccidents?\b", r"\bdanger\w*", r"\bhazard\w*", r"\binjur\w*", r"\bflood\w*",
                 r"\bburst\b", r"\belectrocut\w*", r"\b(live|exposed) wires?\b", r"\bsparking\b",
                 r"\bswerv\w*", r"\bsinkhole\b", r"\bunsafe\b", r"\bblocking (the )?(road|traffic)\b"]
CATEGORY_HIGH = {  # extra high-severity clues per category
    "Pothole / Road Damage": [r"\b(large|big|huge|deep|massive)\b"],
    "Water Leakage": [r"\b(gushing|heavy|continuous\w*|major|massive)\b"],
}
MEDIUM_PATTERNS = [r"\b(days|weeks?|months?|since|persistent\w*|continuous\w*|repeated\w*|overflow\w*|"
                   r"blocked|clogged|not working|broken|damaged|foul|smell\w*|stink\w*|mosquito\w*|stagnant)\b"]
LOW_PATTERNS = [r"\b(minor|small|slight\w*|little|tiny|cosmetic|occasional\w*)\b"]

IMAGE_NOTE_DEMO = "Image received but not visually analysed. Demo mode uses the text description only."


def _matches(patterns, text):
    found = []
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            found.append(m.group(0))
    return found


def summarize(description):
    """One short sentence taken from the citizen's own words. Nothing is invented."""
    text = " ".join(description.split())
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(first) > 160:
        first = first[:157].rstrip() + "..."
    return f"Citizen reports: {first}"


# ---------- deterministic demo rules ----------

def demo_analyze(description, selected_category=None, has_image=False):
    text = description.lower()
    notes, category, uncertainty = [], "Other", ""
    if selected_category and selected_category != AUTO_DETECT:
        category = selected_category
        notes.append(f"Category chosen by the citizen: {selected_category}.")
    else:
        best = 0
        for name, patterns in CATEGORY_RULES:
            hits = _matches(patterns, text)
            if len(hits) > best:
                best, category, notes = len(hits), name, [f"Matched keyword: '{h}'" for h in hits]
        if best == 0:
            uncertainty = "The category could not be confidently identified, so it is marked Other."
            notes = ["No known issue keywords were found."]
    return IssueAnalysis(category=category, summary=summarize(description), evidence_notes=notes,
                         confidence=None, analysis_mode="DEMO", uncertainty=uncertainty,
                         image_note=IMAGE_NOTE_DEMO if has_image else "")


def demo_route(description, analysis, location=None):
    text = description.lower()
    high = _matches(HIGH_PATTERNS + CATEGORY_HIGH.get(analysis.category, []), text)
    medium = _matches(MEDIUM_PATTERNS, text)
    low = _matches(LOW_PATTERNS, text)
    review = analysis.category == "Other"
    if high:
        priority, review = "High", True
        reason = f"The report mentions '{high[0]}', which can indicate a safety risk or major disruption."
    elif low and not medium:
        priority = "Low"
        reason = f"The report describes a minor or limited issue ('{low[0]}')."
    elif medium:
        priority = "Medium"
        reason = f"The report describes a persistent or significant issue ('{medium[0]}') without a clear immediate hazard."
    else:
        priority, review = "Medium", True
        reason = "The description does not give enough detail to judge severity, so Medium is a preliminary default."
    department = DEPARTMENTS[analysis.category]
    return RoutingResult(
        priority=priority, department=department, priority_reason=reason,
        department_reason=f"{analysis.category} reports are usually handled by {department}. "
                          "This is a recommendation, not an official assignment.",
        human_review=review, analysis_mode="DEMO")


# ---------- validation of AI output (AI can never bypass the schema) ----------

def _check_ai_analysis(raw, has_image):
    if not isinstance(raw, dict):
        raise ValueError("AI analysis must be a dict.")
    if raw.get("category") not in CATEGORIES:
        raise ValueError("AI returned an unsupported category.")
    summary = str(raw.get("summary", "")).strip()
    if not summary or len(summary) > 500:
        raise ValueError("AI returned an invalid summary.")
    notes = raw.get("evidence_notes", [])
    if not isinstance(notes, list) or not all(isinstance(n, str) for n in notes):
        raise ValueError("AI returned invalid evidence notes.")
    conf = raw.get("confidence")
    if conf is not None and (isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1):
        raise ValueError("AI returned an invalid confidence.")
    if raw.get("image_analysed") is True:
        image_note = "The image was analysed by the AI service."
    else:
        image_note = "Image received but not visually analysed." if has_image else ""
    return IssueAnalysis(category=raw["category"], summary=summary, evidence_notes=notes,
                         confidence=conf, analysis_mode="AI", image_note=image_note)


def _check_ai_routing(raw):
    if not isinstance(raw, dict):
        raise ValueError("AI routing must be a dict.")
    if raw.get("priority") not in PRIORITIES:
        raise ValueError("AI returned an unsupported priority.")
    if raw.get("department") not in DEPARTMENTS.values():
        raise ValueError("AI returned an unsupported department.")
    reasons = [str(raw.get("priority_reason", "")).strip(), str(raw.get("department_reason", "")).strip()]
    if not all(reasons) or not isinstance(raw.get("human_review"), bool):
        raise ValueError("AI returned incomplete routing details.")
    return RoutingResult(priority=raw["priority"], department=raw["department"], priority_reason=reasons[0],
                         department_reason=reasons[1], human_review=raw["human_review"], analysis_mode="AI")


# ---------- workflow stages ----------

def _trace(stage, mode, inp, out, started, note=""):
    return {"Stage": stage, "Mode": mode, "Status": "completed", "Input": inp,
            "Output": out + (f" {note}" if note else ""),
            "Time (ms)": round((time.perf_counter() - started) * 1000, 1)}


def issue_analysis_stage(description, selected_category=None, has_image=False):
    started, note, result = time.perf_counter(), "", None
    try:
        raw = ai_service.analyze_issue(description, selected_category, has_image or None)
        if raw is not None:
            result = _check_ai_analysis(raw, has_image)
    except Exception:
        log.warning("AI analysis failed; using demo rules.")
        note = "AI analysis was unavailable or invalid, so demo rules were used."
    if result is None:
        result = demo_analyze(description, selected_category, has_image)
    entry = _trace("Issue Analysis", result.analysis_mode, f"{len(description)} characters of text",
                   f"Category: {result.category}.", started, note)
    return result, entry


def routing_stage(description, analysis, location=None):
    started, note, result = time.perf_counter(), "", None
    try:
        raw = ai_service.assess_severity_and_route(description, analysis, location)
        if raw is not None:
            result = _check_ai_routing(raw)
    except Exception:
        log.warning("AI routing failed; using demo rules.")
        note = "AI routing was unavailable or invalid, so demo rules were used."
    if result is None:
        result = demo_route(description, analysis, location)
    entry = _trace("Severity & Department Routing", result.analysis_mode, f"Category: {analysis.category}",
                   f"Priority: {result.priority}; department: {result.department}.", started, note)
    return result, entry


def run_analysis(description, location, selected_category=None, has_image=False):
    """Stages 1 and 2. Read-only: nothing is stored."""
    analysis, t1 = issue_analysis_stage(description, selected_category, has_image)
    routing, t2 = routing_stage(description, analysis, location)
    return {"analysis": analysis, "routing": routing, "trace": [t1, t2]}


def register_complaint(db_path, pending, upload_dir="uploads"):
    """Stage 3. Call only after the citizen clicked 'Register complaint'.

    `pending` holds description, location, category, analysis, routing and optional image.
    Returns (saved_complaint, [trace_entry]). Raises on failure, so callers never report
    success for a complaint that was not saved.
    """
    started = time.perf_counter()
    _, errors = validate_complaint(pending["description"], pending["location"], pending["category"], True)
    if errors:
        raise ValueError(errors[0])
    analysis, routing = pending["analysis"], pending["routing"]
    image, image_name = pending.get("image"), None
    if image:
        image_name = save_image(image["data"], image["name"], upload_dir)
    fields = {
        "description": pending["description"], "location": pending["location"],
        "category": analysis.category, "summary": analysis.summary, "priority": routing.priority,
        "department": routing.department, "priority_reason": routing.priority_reason,
        "department_reason": routing.department_reason, "human_review": routing.human_review,
        "analysis_mode": "AI" if "AI" in (analysis.analysis_mode, routing.analysis_mode) else "DEMO",
        "image_filename": image_name,
    }
    try:
        complaint = database.insert_complaint(db_path, fields)
    except Exception:
        if image_name:  # do not leave an orphaned upload behind
            try:
                os.remove(os.path.join(upload_dir, image_name))
            except OSError:
                pass
        raise
    entry = {"Stage": "Complaint Registration", "Mode": fields["analysis_mode"], "Status": "completed",
             "Input": "Citizen confirmed the reviewed result", "Output": f"Saved with tracking ID {complaint['tracking_id']}.",
             "Time (ms)": round((time.perf_counter() - started) * 1000, 1)}
    return complaint, [entry]
