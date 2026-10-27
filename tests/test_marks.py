"""Examinations, marks entry, statuses, ranking and pass criteria."""
from __future__ import annotations

import pytest

from app.utils.validators import ValidationError


def make_exam(ctx, session_id, **overrides):
    data = {
        "name": "Unit Test 1",
        "exam_type": "Unit Test",
        "class_name": "9",
        "session_id": session_id,
        "subject": "Computer Science",
        "exam_date": "2026-10-07",
        "max_marks": 100,
        "pass_percent": 33,
        "theory_max": 70,
        "practical_max": 30,
    }
    data.update(overrides)
    return ctx.marks.create_examination(data)


def test_create_and_list_examination(ctx, session_id):
    exam_id = make_exam(ctx, session_id)
    exams = ctx.marks.list_examinations(session_id, "9")
    assert [int(e["id"]) for e in exams] == [exam_id]
    assert ctx.marks.get_examination(exam_id)["name"] == "Unit Test 1"


def test_invalid_component_maximum_is_rejected(ctx, session_id):
    with pytest.raises(ValidationError):
        make_exam(ctx, session_id, theory_max=60, practical_max=30)


def test_marks_entry_statuses_and_component_total(ctx, add_student, session_id):
    one = add_student("01", "One")
    two = add_student("02", "Two")
    three = add_student("03", "Three")
    four = add_student("04", "Four")
    exam_id = make_exam(ctx, session_id)
    counts = ctx.marks.save_marks(
        exam_id,
        [
            {"student_id": one, "status": "entered", "theory": 55, "practical": 25},
            {"student_id": two, "status": "absent"},
            {"student_id": three, "status": "exempted"},
            {"student_id": four, "status": "pending"},
        ],
    )
    assert counts == {"entered": 1, "absent": 1, "exempted": 1, "pending": 1}
    rows = {r["student_id"]: r for r in ctx.marks.result_rows(exam_id)}
    assert rows[one]["total"] == 80.0
    assert rows[one]["percentage"] == 80.0
    assert rows[one]["passed"] is True
    assert rows[two]["total"] is None and rows[two]["passed"] is None
    assert rows[three]["total"] is None
    assert rows[four]["total"] is None and rows[four]["status"] == "pending"


def test_missing_marks_are_never_zero(ctx, add_student, session_id):
    one = add_student("01", "One")
    two = add_student("02", "Two")
    exam_id = make_exam(ctx, session_id, max_marks=50, theory_max=None, practical_max=None)
    ctx.marks.save_marks(
        exam_id,
        [
            {"student_id": one, "status": "entered", "total": 40},
            {"student_id": two, "status": "pending"},
        ],
    )
    stats = ctx.marks.class_statistics(exam_id)
    assert stats["entered"] == 1
    assert stats["pending"] == 1
    assert stats["average"] == 40.0
    assert stats["lowest"] == 40.0
    rows = {r["student_id"]: r for r in stats["rows"]}
    assert rows[two]["total"] is None


def test_ranking_competition_with_ties(ctx, add_student, session_id):
    a = add_student("01", "Aarav Das")
    b = add_student("02", "Bikash Das")
    c = add_student("03", "Chandan Das")
    d = add_student("04", "Deepak Das")
    exam_id = make_exam(ctx, session_id, max_marks=50, theory_max=None, practical_max=None)
    ctx.marks.save_marks(
        exam_id,
        [
            {"student_id": a, "status": "entered", "total": 45},
            {"student_id": b, "status": "entered", "total": 40},
            {"student_id": c, "status": "entered", "total": 40},
            {"student_id": d, "status": "entered", "total": 30},
        ],
    )
    ranks = {r["student_id"]: r["rank"] for r in ctx.marks.result_rows(exam_id)}
    assert ranks == {a: 1, b: 2, c: 2, d: 4}


def test_pass_criteria_from_percentage(ctx, add_student, session_id):
    one = add_student("01", "One")
    two = add_student("02", "Two")
    exam_id = make_exam(ctx, session_id, max_marks=100, theory_max=None, practical_max=None)
    ctx.marks.save_marks(
        exam_id,
        [
            {"student_id": one, "status": "entered", "total": 33},
            {"student_id": two, "status": "entered", "total": 32.9},
        ],
    )
    rows = {r["student_id"]: r for r in ctx.marks.result_rows(exam_id)}
    assert rows[one]["passed"] is True
    assert rows[two]["passed"] is False
    stats = ctx.marks.class_statistics(exam_id)
    assert stats["passed"] == 1 and stats["failed"] == 1
    assert stats["pass_percentage"] == 50.0


def test_pass_percentage_counts_absent_but_excludes_exempt_and_pending(
    ctx, add_student, session_id
):
    a = add_student("01", "Amit Das")
    b = add_student("02", "Bina Das")
    c = add_student("03", "Chandan Das")
    d = add_student("04", "Deepa Das")
    exam_id = make_exam(ctx, session_id, max_marks=50, theory_max=None, practical_max=None)
    ctx.marks.save_marks(
        exam_id,
        [
            {"student_id": a, "status": "entered", "total": 40},
            {"student_id": b, "status": "absent"},
            {"student_id": c, "status": "exempted"},
            {"student_id": d, "status": "pending"},
        ],
    )
    stats = ctx.marks.class_statistics(exam_id)
    # passed / (passed + failed + absent) = 1 / 2
    assert stats["pass_percentage"] == 50.0


def test_out_of_range_component_rejects_whole_save(ctx, add_student, session_id):
    one = add_student("01", "One")
    exam_id = make_exam(ctx, session_id)
    with pytest.raises(ValidationError):
        ctx.marks.save_marks(
            exam_id,
            [{"student_id": one, "status": "entered", "theory": 71, "practical": 10}],
        )
    assert ctx.marks.exam_roster(exam_id)[0]["status"] == "pending"


def test_component_blank_is_an_error(ctx, add_student, session_id):
    one = add_student("01", "One")
    exam_id = make_exam(ctx, session_id)
    with pytest.raises(ValidationError) as info:
        ctx.marks.save_marks(
            exam_id, [{"student_id": one, "status": "entered", "theory": 50}]
        )
    assert "practical" in str(info.value).lower()


def test_total_marks_only_exam_validates_range(ctx, add_student, session_id):
    one = add_student("01", "One")
    exam_id = make_exam(ctx, session_id, max_marks=50, theory_max=None, practical_max=None)
    with pytest.raises(ValidationError):
        ctx.marks.save_marks(
            exam_id, [{"student_id": one, "status": "entered", "total": 51}]
        )
    ctx.marks.save_marks(exam_id, [{"student_id": one, "status": "entered", "total": 50}])
    assert ctx.marks.result_rows(exam_id)[0]["total"] == 50.0


def test_pending_only_save_is_rejected_when_pending_is_skipped(
    ctx, add_student, session_id
):
    one = add_student("01", "One")
    exam_id = make_exam(ctx, session_id, max_marks=50, theory_max=None, practical_max=None)
    assert ctx.marks.exam_pending_count(exam_id) == 1
    with pytest.raises(ValidationError):
        ctx.marks.save_marks(
            exam_id, [{"student_id": one, "status": "pending"}], allow_pending=False
        )
    # Nothing was written, so the student is still pending.
    assert ctx.marks.exam_roster(exam_id)[0]["status"] == "pending"


def test_pending_rows_are_saved_when_allowed(ctx, add_student, session_id):
    one = add_student("01", "One")
    exam_id = make_exam(ctx, session_id, max_marks=50, theory_max=None, practical_max=None)
    counts = ctx.marks.save_marks(exam_id, [{"student_id": one, "status": "pending"}])
    assert counts["pending"] == 1
    roster = ctx.marks.exam_roster(exam_id)
    assert roster[0]["status"] == "pending"
    assert roster[0]["total"] is None


def test_exam_pending_count(ctx, add_student, session_id):
    one = add_student("01", "One")
    two = add_student("02", "Two")
    exam_id = make_exam(ctx, session_id, max_marks=50, theory_max=None, practical_max=None)
    assert ctx.marks.exam_pending_count(exam_id) == 2
    ctx.marks.save_marks(exam_id, [{"student_id": one, "status": "absent"}])
    assert ctx.marks.exam_pending_count(exam_id) == 1


def test_import_validation_and_apply(ctx, add_student, session_id):
    add_student("01", "One")
    add_student("02", "Two")
    exam_id = make_exam(ctx, session_id, max_marks=50, theory_max=None, practical_max=None)
    rows = [
        {"roll_no": "01", "status": "entered", "total": "40"},
        {"roll_no": "01", "status": "entered", "total": "30"},
        {"roll_no": "99", "status": "entered", "total": "10"},
        {"roll_no": "02", "status": "absent"},
    ]
    valid, errors = ctx.marks.validate_import_rows(exam_id, rows)
    assert len(valid) == 2
    assert len(errors) == 2
    result = ctx.marks.import_marks(exam_id, rows)
    assert result["saved"] == 2
    rows_after = {r["roll_no"]: r for r in ctx.marks.result_rows(exam_id)}
    assert rows_after["01"]["total"] == 40.0
    assert rows_after["02"]["status"] == "absent"


def test_delete_examination_removes_marks(ctx, add_student, session_id):
    one = add_student("01", "One")
    exam_id = make_exam(ctx, session_id, max_marks=50, theory_max=None, practical_max=None)
    ctx.marks.save_marks(exam_id, [{"student_id": one, "status": "entered", "total": 45}])
    ctx.marks.delete_examination(exam_id)
    assert ctx.marks.get_examination(exam_id) is None
    assert ctx.db.scalar("SELECT COUNT(*) FROM marks", default=0) == 0


def test_student_history_lists_exams_with_status(ctx, add_student, session_id):
    one = add_student("01", "One")
    exam_id = make_exam(ctx, session_id, max_marks=50, theory_max=None, practical_max=None)
    ctx.marks.save_marks(exam_id, [{"student_id": one, "status": "entered", "total": 44}])
    history = ctx.marks.student_history(one)
    assert history[0]["name"] == "Unit Test 1"
    assert history[0]["percentage"] == 88.0
    assert history[0]["passed"] is True
