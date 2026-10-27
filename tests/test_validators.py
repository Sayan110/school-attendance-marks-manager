"""Input validation and date helpers."""
from __future__ import annotations

from datetime import date

import pytest

from app.utils import dates as date_utils
from app.utils.validators import (
    ValidationError,
    clean_text,
    normalize_roll,
    parse_iso_date,
    validate_examination,
    validate_student,
)


def _student(**overrides):
    data = {
        "roll_no": "01",
        "full_name": "Test Student",
        "class_name": "9",
        "section": "a",
        "session_id": 1,
        "guardian_name": "Guardian",
        "contact_no": "9800000000",
        "admission_date": "2026-04-05",
        "status": "active",
    }
    data.update(overrides)
    return data


def test_clean_text_collapses_whitespace_and_truncates():
    assert clean_text("  A   B  ") == "A B"
    assert clean_text(None) == ""
    assert clean_text("abcdef", 4) == "abcd"


def test_normalize_roll_uppercases_letters_only():
    assert normalize_roll("a12") == "A12"
    assert normalize_roll(" 07 ") == "07"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-27", date(2026, 10, 27)),
        ("27-10-2026", date(2026, 10, 27)),
        ("27/10/2026", date(2026, 10, 27)),
        ("2026/10/27", date(2026, 10, 27)),
    ],
)
def test_parse_iso_date_accepts_common_formats(value, expected):
    assert parse_iso_date(value) == expected


def test_parse_iso_date_rejects_garbage():
    with pytest.raises(ValidationError):
        parse_iso_date("not-a-date")


def test_validate_student_normalizes_values():
    values = validate_student(_student(section="b"))
    assert values["roll_no"] == "01"
    assert values["section"] == "B"
    assert values["session_id"] == 1


def test_validate_student_reports_every_missing_field():
    with pytest.raises(ValidationError) as info:
        validate_student({})
    errors = info.value.errors
    assert "roll_no" in errors
    assert "full_name" in errors
    assert "class_name" in errors
    assert "session_id" in errors


def test_validate_student_rejects_bad_class_and_contact():
    with pytest.raises(ValidationError) as info:
        validate_student(_student(class_name="11", contact_no="phone"))
    assert "class_name" in info.value.errors
    assert "contact_no" in info.value.errors


def test_validate_student_rejects_bad_date():
    with pytest.raises(ValidationError) as info:
        validate_student(_student(admission_date="31-02-2026"))
    assert "admission_date" in info.value.errors


def _exam(**overrides):
    data = {
        "name": "Unit Test",
        "class_name": "9",
        "session_id": 1,
        "subject": "Computer Science",
        "max_marks": 100,
        "pass_percent": 33,
        "theory_max": 70,
        "practical_max": 30,
    }
    data.update(overrides)
    return data


def test_validate_examination_defaults_pass_percent_to_33():
    data = _exam()
    data.pop("pass_percent")
    assert validate_examination(data)["pass_percent"] == 33.0


def test_validate_examination_rejects_component_mismatch():
    with pytest.raises(ValidationError) as info:
        validate_examination(_exam(max_marks=100, theory_max=60, practical_max=30))
    assert "max_marks" in info.value.errors


def test_validate_examination_rejects_pass_marks_above_max():
    with pytest.raises(ValidationError) as info:
        validate_examination(_exam(pass_marks=120))
    assert "pass_marks" in info.value.errors


def test_validate_examination_rejects_non_positive_max():
    with pytest.raises(ValidationError) as info:
        validate_examination(_exam(max_marks=0, theory_max=None, practical_max=None))
    assert "max_marks" in info.value.errors


def test_date_helpers_display_and_month_bounds():
    assert date_utils.iso(date(2026, 10, 5)) == "2026-10-05"
    assert date_utils.display("2026-10-05") == "05-10-2026"
    assert "October" in date_utils.display_long("2026-10-05")
    assert date_utils.month_bounds(2026, 10) == (date(2026, 10, 1), date(2026, 10, 31))
