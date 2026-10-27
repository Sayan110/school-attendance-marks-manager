"""Data written in one session must still be there after a restart.

The app closes its ``AppContext`` and reopens the same SQLite file on the next
launch, so these tests close a context and build a brand-new one against the
same data directory - the same thing the teacher's second launch does.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SVSM_DATA_DIR", str(tmp_path / "svsm-data"))
    monkeypatch.delenv("SVSM_DB_PATH", raising=False)
    return tmp_path / "svsm-data"


def _new_context():
    from app.context import AppContext

    context = AppContext()
    context.settings.reload()
    return context


def test_students_attendance_and_settings_survive_a_restart(data_dir):
    first = _new_context()
    session_id = int(first.session_id)
    student_id = first.students.create(
        {
            "roll_no": "07",
            "full_name": "Persisted Pupil",
            "class_name": "9",
            "section": "A",
            "session_id": session_id,
            "guardian_name": "Guardian",
            "contact_no": "9800000007",
            "admission_date": "2026-04-05",
            "status": "active",
            "remarks": "saved before restart",
        }
    )
    first.attendance.save_day(
        session_id,
        "9",
        "2026-10-05",
        [{"student_id": student_id, "status": "P"}],
    )
    first.settings.set("attendance_threshold", "81")
    first.close()

    second = _new_context()
    try:
        assert second.session_id == session_id
        rows, total = second.students.list_students(session_id, search="Persisted")
        assert total == 1
        assert rows[0]["id"] == student_id
        assert rows[0]["remarks"] == "saved before restart"

        assert second.attendance.is_saved(session_id, "9", "2026-10-05") is True
        counts = second.attendance.day_summary(session_id, "9", "2026-10-05")
        assert counts.present == 1
        assert counts.absent == 0

        assert second.settings.get("attendance_threshold") == "81"
    finally:
        second.close()


def test_marks_survive_a_restart(data_dir):
    first = _new_context()
    session_id = int(first.session_id)
    student_id = first.students.create(
        {
            "roll_no": "08",
            "full_name": "Marked Pupil",
            "class_name": "9",
            "section": "A",
            "session_id": session_id,
            "guardian_name": "Guardian",
            "contact_no": "9800000008",
            "admission_date": "2026-04-05",
            "status": "active",
            "remarks": "",
        }
    )
    exam_id = first.marks.create_examination(
        {
            "name": "Restart Test",
            "exam_type": "Unit Test",
            "class_name": "9",
            "session_id": session_id,
            "subject": "Computer Science",
            "exam_date": "2026-10-09",
            "max_marks": 50,
            "pass_percent": 33,
        }
    )
    first.marks.save_marks(
        exam_id, [{"student_id": student_id, "status": "entered", "total": 41}]
    )
    first.close()

    second = _new_context()
    try:
        rows = second.marks.result_rows(exam_id)
        saved = [row for row in rows if int(row["student_id"]) == student_id]
        assert len(saved) == 1
        assert saved[0]["status"] == "entered"
        assert float(saved[0]["total"]) == 41.0
    finally:
        second.close()
