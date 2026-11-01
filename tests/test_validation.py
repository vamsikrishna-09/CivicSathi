import pytest

from models import MAX_DESCRIPTION, MAX_IMAGE_BYTES, MAX_LOCATION, validate_complaint, validate_image
from utils import normalize_tracking_id, safe_image_name

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
JPG = b"\xff\xd8\xff" + b"0" * 20


def test_valid_input():
    clean, errors = validate_complaint("  pothole  ", " Main Rd ", "Auto-detect", True)
    assert errors == [] and clean["description"] == "pothole" and clean["location"] == "Main Rd"


@pytest.mark.parametrize("desc,loc,consent", [("", "Main Rd", True), ("   ", "Main Rd", True),
                                              ("pothole", "", True), ("pothole", "  ", True),
                                              ("pothole", "Main Rd", False)])
def test_required_fields_and_consent(desc, loc, consent):
    assert validate_complaint(desc, loc, "Auto-detect", consent)[1]


def test_length_limits_and_bad_category():
    assert validate_complaint("x" * (MAX_DESCRIPTION + 1), "a", "Auto-detect", True)[1]
    assert validate_complaint("x", "a" * (MAX_LOCATION + 1), "Auto-detect", True)[1]
    assert validate_complaint("x", "a", "Made up", True)[1]


def test_image_accepted():
    assert validate_image("a.png", PNG) is None
    assert validate_image("a.JPG", JPG) is None


@pytest.mark.parametrize("name,data", [("a.gif", PNG), ("a.exe", b"MZ"), ("a", PNG), ("a.png", b""),
                                       ("a.png", PNG + b"0" * MAX_IMAGE_BYTES), ("a.png", b"not an image")])
def test_image_rejected(name, data):
    assert validate_image(name, data)


def test_exactly_5mb_is_allowed():
    assert validate_image("a.png", PNG + b"0" * (MAX_IMAGE_BYTES - len(PNG))) is None


def test_unsafe_filenames_not_used():
    name = safe_image_name("../../etc/passwd.png")
    assert "/" not in name and "\\" not in name and ".." not in name and name.endswith(".png")
    assert safe_image_name("x.jpeg").endswith(".jpg")
    assert safe_image_name("a.png") != safe_image_name("a.png")


def test_tracking_id_normalisation():
    assert normalize_tracking_id(" cs-2026-ab12cd ") == "CS-2026-AB12CD"
    assert normalize_tracking_id("hello") is None
    assert normalize_tracking_id("") is None
