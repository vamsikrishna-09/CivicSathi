"""Shared constants, data models and input validation."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

CATEGORIES = [
    "Pothole / Road Damage",
    "Garbage / Waste",
    "Water Leakage",
    "Blocked Drain",
    "Broken Streetlight",
    "Other",
]
AUTO_DETECT = "Auto-detect"

# Category -> suggested department. This is a recommendation, not an official assignment.
DEPARTMENTS = {
    "Pothole / Road Damage": "Roads & Engineering",
    "Garbage / Waste": "Sanitation",
    "Water Leakage": "Water Supply",
    "Blocked Drain": "Drainage",
    "Broken Streetlight": "Electrical / Street Lighting",
    "Other": "General Civic Services",
}
PRIORITIES = ("Low", "Medium", "High")
STATUSES = ("Submitted", "Acknowledged", "In Progress", "Resolved")
MODES = ("DEMO", "AI")

MAX_DESCRIPTION = 1000
MAX_LOCATION = 200
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXT = (".jpg", ".jpeg", ".png")


@dataclass
class IssueAnalysis:
    category: str
    summary: str
    evidence_notes: list[str] = field(default_factory=list)
    confidence: float | None = None   # None = not calculated (never invented)
    analysis_mode: str = "DEMO"       # must reflect the method actually used
    uncertainty: str = ""
    image_note: str = ""


@dataclass
class RoutingResult:
    priority: str
    department: str
    priority_reason: str
    department_reason: str
    human_review: bool
    analysis_mode: str = "DEMO"


class ValidationError(ValueError):
    """Raised when data fails validation."""


def validate_complaint(description, location, category, consent):
    """Return (cleaned_values, error_messages). Empty error list means valid."""
    errors = []
    desc = (description or "").strip()
    loc = (location or "").strip()
    cat = category or AUTO_DETECT

    if not desc:
        errors.append("Enter a description of the issue.")
    elif len(desc) > MAX_DESCRIPTION:
        errors.append(f"The description is too long. Keep it under {MAX_DESCRIPTION} characters.")
    if not loc:
        errors.append("Enter an approximate public location, such as a road, landmark or locality.")
    elif len(loc) > MAX_LOCATION:
        errors.append(f"The location is too long. Keep it under {MAX_LOCATION} characters.")
    if cat != AUTO_DETECT and cat not in CATEGORIES:
        errors.append("Choose one of the listed categories, or Auto-detect.")
    if not consent:
        errors.append("Consent is required: tick the box to allow this prototype to store your report.")
    return {"description": desc, "location": loc, "category": cat}, errors


def validate_image(filename, data):
    """Return an error message, or None if the image is acceptable."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return "Only JPG/JPEG and PNG images are accepted."
    if not data:
        return "The image file is empty. Choose another image."
    if len(data) > MAX_IMAGE_BYTES:
        return "The image is larger than 5 MB. Choose an image under 5 MB."
    is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpg = data.startswith(b"\xff\xd8\xff")
    if not (is_png or is_jpg):
        return "The file does not look like a valid JPG or PNG image."
    return None


def validate_status(status):
    if status not in STATUSES:
        raise ValueError(f"Invalid status. Allowed values: {', '.join(STATUSES)}.")
    return status
