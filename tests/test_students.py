"""Student records: uniqueness, search, archive and permanent deletion."""
from __future__ import annotations

import pytest

from app.utils.validators import ValidationError


def test_create_and_get(ctx, session_id):
    student_id = ctx.students.create(
        {
            "roll_no": "01",
            "full_name": "Rituparna Das",
            "class_name": "9",
            "section": "A",
            "session_id": session_id,
            "guardian_name": "Guardian",
            "contact_no": "9800000000",
            "admission_date": "2026-04-05",
        }
    )
    student = ctx.students.get(student_id)
    assert student["full_name"] == "Rituparna Das"
    assert student["session_name"] == "2026-2027"


def test_duplicate_roll_in_same_class_is_rejected(ctx, session_id):
    base = {
        "full_name": "One",
        "class_name": "9",
        "session_id": session_id,
        "section": "A",
    }
    ctx.students.create({**base, "roll_no": "05"})
    with pytest.raises(ValidationError) as info:
        ctx.students.create({**base, "roll_no": "05", "full_name": "Two"})
    assert "roll_no" in info.value.errors


def test_same_roll_in_other_class_is_allowed(ctx, session_id):
    ctx.students.create(
        {"roll_no": "05", "full_name": "Class 9", "class_name": "9", "session_id": session_id}
    )
    ctx.students.create(
        {"roll_no": "05", "full_name": "Class 10", "class_name": "10", "session_id": session_id}
    )
    rows, total = ctx.students.list_students(session_id)
    assert total == 2


def test_roll_exists_is_case_insensitive(ctx, add_student, session_id):
    add_student("A1", "Letter Roll")
    # normalize_roll upper-cases every roll number, so a1 and A1 are the same.
    assert ctx.students.roll_exists(session_id, "9", "a1") is True


def test_update_and_duplicate_check(ctx, add_student):
    first = add_student("01", "First")
    second = add_student("02", "Second")
    data = {
        "roll_no": "02",
        "full_name": "First Renamed",
        "class_name": "9",
        "section": "A",
        "session_id": ctx.session_id,
    }
    with pytest.raises(ValidationError):
        ctx.students.update(first, data)
    data["roll_no"] = "03"
    ctx.students.update(first, data)
    assert ctx.students.get(first)["full_name"] == "First Renamed"


def test_archive_hides_from_active_list_and_restore(ctx, add_student, session_id):
    student_id = add_student("01", "Archive Me")
    ctx.students.archive(student_id)
    active, total = ctx.students.list_students(session_id)
    assert total == 0
    archived, archived_total = ctx.students.list_students(session_id, status="archived")
    assert archived_total == 1
    ctx.students.restore(student_id)
    active, total = ctx.students.list_students(session_id)
    assert total == 1


def test_search_matches_name_roll_and_guardian(ctx, add_student, session_id):
    add_student("01", "Rituparna Das")
    add_student("02", "Anurag Bora", guardian_name="Guardian of Anurag")
    rows, total = ctx.students.list_students(session_id, search="ritu")
    assert total == 1 and rows[0]["full_name"] == "Rituparna Das"
    rows, total = ctx.students.list_students(session_id, search="02")
    assert total == 1 and rows[0]["full_name"] == "Anurag Bora"
    rows, total = ctx.students.list_students(session_id, search="Anurag")
    assert total == 1 and rows[0]["guardian_name"] == "Guardian of Anurag"


def test_filter_by_class_and_section(ctx, add_student, session_id):
    add_student("01", "Amit Das", "9", "A")
    add_student("02", "Bina Das", "9", "B")
    add_student("01", "Chandan Das", "10", "A")
    rows, total = ctx.students.list_students(session_id, class_name="10")
    assert total == 1 and rows[0]["full_name"] == "Chandan Das"
    rows, total = ctx.students.list_students(session_id, class_name="9", section="B")
    assert total == 1 and rows[0]["full_name"] == "Bina Das"


def test_sorting_and_pagination(ctx, add_student, session_id):
    for index in range(1, 8):
        add_student(f"{index:02d}", f"Student {index}")
    page1, total = ctx.students.list_students(session_id, page=1, page_size=3)
    page2, _ = ctx.students.list_students(session_id, page=2, page_size=3)
    assert total == 7
    assert [r["roll_no"] for r in page1] == ["01", "02", "03"]
    assert [r["roll_no"] for r in page2] == ["04", "05", "06"]
    desc, _ = ctx.students.list_students(session_id, sort_by="full_name", sort_dir="desc")
    assert desc[0]["full_name"] == "Student 7"


def test_count_by_class_and_sections(ctx, add_student):
    add_student("01", "Amit Das", "9", "A")
    add_student("02", "Bina Das", "9", "B")
    add_student("01", "Chandan Das", "10", "A")
    assert ctx.students.count_by_class(ctx.session_id) == {"9": 2, "10": 1}
    assert ctx.students.sections(ctx.session_id, "9") == ["A", "B"]


def test_permanent_delete_is_blocked_when_records_exist(ctx, add_student, session_id):
    student_id = add_student("01", "Has Records")
    ctx.attendance.save_day(
        session_id, "9", "2026-10-05", [{"student_id": student_id, "status": "P"}]
    )
    with pytest.raises(ValidationError) as info:
        ctx.students.delete_permanently(student_id)
    assert "Archive" in str(info.value)


def test_permanent_delete_without_records(ctx, add_student, session_id):
    student_id = add_student("01", "Clean")
    ctx.students.delete_permanently(student_id)
    assert ctx.students.get(student_id) is None
    assert ctx.students.list_students(session_id)[1] == 0


def test_import_validation_flags_duplicates_inside_file(ctx, session_id):
    rows = [
        {"roll_no": "01", "full_name": "One", "class_name": "9"},
        {"roll_no": "01", "full_name": "One Again", "class_name": "9"},
        {"roll_no": "02", "full_name": "", "class_name": "9"},
    ]
    valid, errors = ctx.students.validate_import_rows(session_id, rows)
    assert len(valid) == 1
    assert len(errors) == 2


def test_import_skips_invalid_and_reports_errors(ctx, session_id):
    ctx.students.create(
        {"roll_no": "01", "full_name": "Existing", "class_name": "9", "session_id": session_id}
    )
    result = ctx.students.import_students(
        session_id,
        [
            {"roll_no": "01", "full_name": "Duplicate", "class_name": "9"},
            {"roll_no": "02", "full_name": "New Student", "class_name": "9"},
        ],
    )
    assert result["imported"] == 1
    assert len(result["errors"]) == 1


def test_import_cancel_when_invalid_and_not_skipping(ctx, session_id):
    result = ctx.students.import_students(
        session_id,
        [{"roll_no": "", "full_name": "", "class_name": "9"}],
        skip_invalid=False,
    )
    assert result["imported"] == 0
    assert result["cancelled"] is True
