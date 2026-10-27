"""Shared pytest fixtures.

Every test gets its own SQLite database inside a temporary directory. The
teacher's real database under %LOCALAPPDATA% is never opened.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Qt must be told to use the offscreen platform before PySide6 is imported.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def qapp():
    """One QApplication per session, torn down deterministically.

    Without the explicit teardown PySide6 aborts the interpreter at exit
    (access violation) because widgets outlive the application object.
    """
    from PySide6.QtWidgets import QApplication

    from app.ui.shutdown import shutdown_qt

    app = QApplication.instance() or QApplication([])
    yield app
    shutdown_qt(app)


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("SVSM_DATA_DIR", str(tmp_path / "svsm-data"))
    monkeypatch.delenv("SVSM_DB_PATH", raising=False)
    from app.context import AppContext

    context = AppContext()
    context.settings.reload()
    try:
        yield context
    finally:
        context.close()


@pytest.fixture()
def session_id(ctx) -> int:
    value = ctx.session_id
    assert value is not None
    return int(value)


@pytest.fixture()
def add_student(ctx, session_id):
    def _add(roll, name, class_name="9", section="A", **extra):
        data = {
            "roll_no": roll,
            "full_name": name,
            "class_name": class_name,
            "section": section,
            "session_id": session_id,
            "guardian_name": f"Guardian of {name.split()[0]}",
            "contact_no": "9800000000",
            "admission_date": "2026-04-05",
            "status": "active",
            "remarks": "",
        }
        data.update(extra)
        return ctx.students.create(data)

    return _add


@pytest.fixture()
def dataset(ctx, session_id, add_student):
    """Two Class 9 students, one Class 10 student, attendance and one exam."""
    s1 = add_student("01", "Alpha Sharma", "9")
    s2 = add_student("02", "Beta Das", "9", section="B")
    s3 = add_student("01", "Gamma Bora", "10")

    ctx.attendance.save_day(
        session_id,
        "9",
        "2026-10-05",
        [
            {"student_id": s1, "status": "P"},
            {"student_id": s2, "status": "A"},
        ],
    )
    ctx.attendance.save_day(
        session_id,
        "9",
        "2026-10-06",
        [
            {"student_id": s1, "status": "P"},
            {"student_id": s2, "status": "L"},
        ],
    )
    ctx.attendance.save_day(
        session_id,
        "10",
        "2026-10-05",
        [{"student_id": s3, "status": "P"}],
    )

    exam = ctx.marks.create_examination(
        {
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
    )
    ctx.marks.save_marks(
        exam,
        [
            {"student_id": s1, "status": "entered", "theory": 60, "practical": 28},
            {"student_id": s2, "status": "entered", "theory": 20, "practical": 10},
        ],
    )
    return {
        "students": {"alpha": s1, "beta": s2, "gamma": s3},
        "exam_id": exam,
    }
