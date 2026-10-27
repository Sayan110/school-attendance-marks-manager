"""Attendance: unmarked vs absent, duplicates, overwrite, leave policy, holidays."""
from __future__ import annotations

import pytest

from app.services.attendance_service import AlreadySavedError
from app.utils.validators import ValidationError


def test_roll_call_starts_unmarked_not_absent(ctx, add_student, session_id):
    add_student("01", "One")
    add_student("02", "Two")
    day = ctx.attendance.load_day(session_id, "9", "2026-10-05")
    assert [e.status for e in day.entries] == [None, None]
    assert day.counts.unmarked == 2
    assert day.counts.absent == 0
    assert day.counts.percentage is None
    assert day.saved is False


def test_save_day_counts_and_saved_flag(ctx, add_student, session_id):
    one = add_student("01", "One")
    two = add_student("02", "Two")
    counts = ctx.attendance.save_day(
        session_id,
        "9",
        "2026-10-05",
        [
            {"student_id": one, "status": "P", "remarks": "On time"},
            {"student_id": two, "status": "A"},
        ],
    )
    assert counts.present == 1 and counts.absent == 1
    assert counts.percentage == 50.0
    day = ctx.attendance.load_day(session_id, "9", "2026-10-05")
    assert day.saved is True
    assert day.counts.present == 1
    assert day.entries[0].remarks == "On time"


def test_saving_same_day_twice_requires_overwrite(ctx, add_student, session_id):
    one = add_student("01", "One")
    two = add_student("02", "Two")
    entries = [
        {"student_id": one, "status": "P"},
        {"student_id": two, "status": "P"},
    ]
    ctx.attendance.save_day(session_id, "9", "2026-10-05", entries)
    with pytest.raises(AlreadySavedError):
        ctx.attendance.save_day(session_id, "9", "2026-10-05", entries)
    updated = ctx.attendance.save_day(
        session_id,
        "9",
        "2026-10-05",
        [
            {"student_id": one, "status": "A"},
            {"student_id": two, "status": "P"},
        ],
        overwrite=True,
    )
    assert updated.present == 1 and updated.absent == 1


def test_unmarked_students_are_not_saved_and_previous_status_is_cleared(
    ctx, add_student, session_id
):
    one = add_student("01", "One")
    two = add_student("02", "Two")
    ctx.attendance.save_day(
        session_id,
        "9",
        "2026-10-05",
        [
            {"student_id": one, "status": "P"},
            {"student_id": two, "status": "A"},
        ],
    )
    ctx.attendance.save_day(
        session_id,
        "9",
        "2026-10-05",
        [
            {"student_id": one, "status": "P"},
            {"student_id": two, "status": None},
        ],
        overwrite=True,
    )
    day = ctx.attendance.load_day(session_id, "9", "2026-10-05")
    statuses = {e.student_id: e.status for e in day.entries}
    assert statuses[two] is None
    assert ctx.attendance.existing_count(session_id, "9", "2026-10-05") == 1


def test_save_requires_at_least_one_marked_student(ctx, add_student, session_id):
    one = add_student("01", "One")
    with pytest.raises(ValidationError):
        ctx.attendance.save_day(
            session_id, "9", "2026-10-05", [{"student_id": one, "status": None}]
        )


def test_invalid_status_and_foreign_student_are_rejected(ctx, add_student, session_id):
    one = add_student("01", "One", "9")
    other = add_student("01", "Other", "10")
    with pytest.raises(ValidationError):
        ctx.attendance.save_day(
            session_id, "9", "2026-10-05", [{"student_id": one, "status": "X"}]
        )
    with pytest.raises(ValidationError):
        ctx.attendance.save_day(
            session_id, "9", "2026-10-05", [{"student_id": other, "status": "P"}]
        )


def test_leave_exclusion_setting_changes_percentage(ctx, add_student, session_id):
    one = add_student("01", "One")
    two = add_student("02", "Two")
    ctx.attendance.save_day(
        session_id,
        "9",
        "2026-10-05",
        [
            {"student_id": one, "status": "P"},
            {"student_id": two, "status": "L"},
        ],
    )
    assert ctx.settings.leave_excluded is True
    assert ctx.attendance.day_summary(session_id, "9", "2026-10-05").percentage == 100.0

    ctx.settings.set("leave_excluded_from_percentage", "0")
    ctx.settings.reload()
    assert ctx.settings.leave_excluded is False
    assert ctx.attendance.day_summary(session_id, "9", "2026-10-05").percentage == 50.0
    assert ctx.attendance.student_summary(one)["percentage"] == 100.0

    ctx.settings.set("leave_excluded_from_percentage", "1")
    ctx.settings.reload()


def test_range_summary_and_daily_breakdown(ctx, add_student, session_id):
    one = add_student("01", "One")
    two = add_student("02", "Two")
    ctx.attendance.save_day(
        session_id,
        "9",
        "2026-10-05",
        [{"student_id": one, "status": "P"}, {"student_id": two, "status": "A"}],
    )
    ctx.attendance.save_day(
        session_id,
        "9",
        "2026-10-06",
        [{"student_id": one, "status": "P"}, {"student_id": two, "status": "P"}],
    )
    summary = ctx.attendance.range_summary(session_id, "9", "2026-10-01", "2026-10-31")
    assert summary["present"] == 3
    assert summary["absent"] == 1
    assert summary["sessions"] == 2
    assert summary["percentage"] == 75.0
    breakdown = ctx.attendance.daily_breakdown(session_id, "9", "2026-10-01", "2026-10-31")
    assert [row["date"] for row in breakdown] == ["2026-10-05", "2026-10-06"]
    assert breakdown[0]["percentage"] == 50.0


def test_holidays_are_stored_and_flagged(ctx, session_id):
    holiday_id = ctx.attendance.add_holiday(session_id, "2026-10-02", "Gandhi Jayanti")
    day = ctx.attendance.load_day(session_id, "9", "2026-10-02")
    assert day.is_holiday is True
    assert day.holiday_name == "Gandhi Jayanti"
    assert ctx.attendance.holiday_dates(session_id, "2026-10-01", "2026-10-31") == {"2026-10-02"}
    ctx.attendance.delete_holiday(holiday_id)
    assert ctx.attendance.holiday_for(session_id, "2026-10-02") is None


def test_student_history_and_class_summary(ctx, add_student, session_id):
    one = add_student("01", "One")
    two = add_student("02", "Two")
    ctx.attendance.save_day(
        session_id,
        "9",
        "2026-10-05",
        [{"student_id": one, "status": "P"}, {"student_id": two, "status": "A"}],
    )
    history = ctx.attendance.student_history(one)
    assert history[0]["attendance_date"] == "2026-10-05"
    assert history[0]["status"] == "P"
    rows = ctx.attendance.class_summary(session_id, "9", "2026-10-01", "2026-10-31")
    assert len(rows) == 2
    assert rows[0]["percentage"] == 100.0
    assert rows[1]["percentage"] == 0.0


def test_monthly_trend_and_register(ctx, add_student, session_id):
    one = add_student("01", "One")
    ctx.attendance.save_day(
        session_id, "9", "2026-10-05", [{"student_id": one, "status": "P"}]
    )
    trend = ctx.attendance.monthly_trend(session_id, "9", "2026-04-01", "2027-03-31")
    assert trend[0]["month"] == "2026-10"
    assert trend[0]["percentage"] == 100.0
    register = ctx.attendance.monthly_register(session_id, "9", 2026, 10)
    assert register["students"][0]["present"] == 1
    assert register["days"] == 31


def test_archived_student_keeps_historical_attendance(ctx, add_student, session_id):
    one = add_student("01", "One")
    ctx.attendance.save_day(
        session_id, "9", "2026-10-05", [{"student_id": one, "status": "P"}]
    )
    ctx.students.archive(one)
    day = ctx.attendance.load_day(session_id, "9", "2026-10-05")
    assert [e.full_name for e in day.entries] == ["One"]
    assert day.counts.present == 1
