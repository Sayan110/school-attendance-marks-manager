"""Shared validation helpers. Raises ValidationError with field-level messages."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Mapping

from app import config


class ValidationError(ValueError):
    def __init__(self, message: str, errors: Mapping[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.errors = dict(errors or {})

    def __str__(self) -> str:
        return self.message


def clean_text(value: Any, max_length: int | None = None) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if max_length is not None and len(text) > max_length:
        text = text[:max_length].strip()
    return text


def normalize_roll(value: Any) -> str:
    """Roll numbers are stored upper-case so 'a12' and 'A12' cannot both exist."""
    return clean_text(value, 30).upper()


def parse_iso_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"'{text}' is not a valid date. Use YYYY-MM-DD.")


def parse_number(value: Any, field: str, errors: dict[str, str]) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        errors[field] = "Enter a valid number."
        return None
    if number != number or number in (float("inf"), float("-inf")):
        errors[field] = "Enter a valid number."
        return None
    return number


def validate_student(data: Mapping[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    roll_no = normalize_roll(data.get("roll_no"))
    full_name = clean_text(data.get("full_name"), 120)
    class_name = clean_text(data.get("class_name"))
    section = clean_text(data.get("section"), 10).upper()
    guardian = clean_text(data.get("guardian_name"), 120)
    contact = clean_text(data.get("contact_no"), 25)
    remarks = clean_text(data.get("remarks"), 500)
    status = clean_text(data.get("status") or "active").lower()

    if not roll_no:
        errors["roll_no"] = "Roll / admission number is required."
    if not full_name:
        errors["full_name"] = "Full name is required."
    elif len(full_name) < 2:
        errors["full_name"] = "Full name is too short."
    if class_name not in config.CLASSES:
        errors["class_name"] = "Select Class 9 or Class 10."
    if not data.get("session_id"):
        errors["session_id"] = "Academic session is required."
    else:
        try:
            int(data["session_id"])
        except (TypeError, ValueError):
            errors["session_id"] = "Academic session is invalid."
    if status not in ("active", "inactive", "archived"):
        errors["status"] = "Status must be active, inactive or archived."
    if contact and not re.fullmatch(r"[0-9+\-() ]{5,25}", contact):
        errors["contact_no"] = "Use digits, spaces, +, - or parentheses only."
    admission_raw = data.get("admission_date")
    admission = None
    if admission_raw:
        try:
            admission = parse_iso_date(admission_raw)
        except ValidationError:
            errors["admission_date"] = "Enter a valid admission date (YYYY-MM-DD)."

    if errors:
        raise ValidationError("Please correct the highlighted fields.", errors)

    return {
        "roll_no": roll_no,
        "full_name": full_name,
        "class_name": class_name,
        "section": section,
        "session_id": int(data["session_id"]),
        "guardian_name": guardian or None,
        "contact_no": contact or None,
        "admission_date": admission.isoformat() if admission else None,
        "status": status,
        "remarks": remarks or None,
    }


def validate_examination(data: Mapping[str, Any]) -> dict[str, Any]:
    errors: dict[str, str] = {}
    name = clean_text(data.get("name"), 120)
    exam_type = clean_text(data.get("exam_type")) or "Custom"
    class_name = clean_text(data.get("class_name"))
    subject = clean_text(data.get("subject") or config.DEFAULT_SUBJECT, 60)
    remarks = clean_text(data.get("remarks"), 500)

    if not name:
        errors["name"] = "Examination name is required."
    if class_name not in config.CLASSES:
        errors["class_name"] = "Select Class 9 or Class 10."
    if not data.get("session_id"):
        errors["session_id"] = "Academic session is required."
    if not subject:
        errors["subject"] = "Subject is required."

    max_marks = parse_number(data.get("max_marks"), "max_marks", errors)
    if max_marks is None or max_marks <= 0:
        errors["max_marks"] = "Maximum marks must be greater than zero."
    pass_percent = parse_number(data.get("pass_percent"), "pass_percent", errors)
    if pass_percent is not None and not (0 <= pass_percent <= 100):
        errors["pass_percent"] = "Pass percentage must be between 0 and 100."
    pass_marks = parse_number(data.get("pass_marks"), "pass_marks", errors)
    if pass_marks is not None and max_marks is not None and not (0 <= pass_marks <= max_marks):
        errors["pass_marks"] = "Passing marks cannot exceed maximum marks."

    theory = parse_number(data.get("theory_max"), "theory_max", errors)
    practical = parse_number(data.get("practical_max"), "practical_max", errors)
    project = parse_number(data.get("project_max"), "project_max", errors)
    for field, value in (("theory_max", theory), ("practical_max", practical), ("project_max", project)):
        if value is not None and value < 0:
            errors[field] = "Component maximum cannot be negative."
    components = [v for v in (theory, practical, project) if v is not None]
    if components and max_marks is not None and abs(sum(components) - max_marks) > 0.01:
        errors["max_marks"] = (
            "Component maximums must add up to the overall maximum marks "
            f"({sum(components):g} vs {max_marks:g})."
        )
    if pass_percent is None and pass_marks is None and not errors.get("max_marks"):
        pass_percent = 33.0
    exam_date = None
    if data.get("exam_date"):
        try:
            exam_date = parse_iso_date(data.get("exam_date"))
        except ValidationError:
            errors["exam_date"] = "Enter a valid examination date."

    if errors:
        raise ValidationError("Please correct the highlighted fields.", errors)

    return {
        "name": name,
        "exam_type": exam_type,
        "class_name": class_name,
        "session_id": int(data["session_id"]),
        "subject": subject,
        "exam_date": exam_date.isoformat() if exam_date else None,
        "max_marks": float(max_marks),
        "pass_marks": float(pass_marks) if pass_marks is not None else None,
        "pass_percent": float(pass_percent) if pass_percent is not None else None,
        "theory_max": theory,
        "practical_max": practical,
        "project_max": project,
        "remarks": remarks or None,
    }
