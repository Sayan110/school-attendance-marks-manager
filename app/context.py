"""Application context: owns the database and service instances."""
from __future__ import annotations

from pathlib import Path

from app.database import Database
from app.services.analytics_service import AnalyticsService
from app.services.attendance_service import AttendanceService
from app.services.backup_service import BackupService
from app.services.marks_service import MarksService
from app.services.settings_service import SettingsService
from app.services.student_service import StudentService


class AppContext:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db = Database(db_path)
        self.db.connect()
        self.settings = SettingsService(self.db)
        self.students = StudentService(self.db)
        self.attendance = AttendanceService(self.db, self.settings)
        self.marks = MarksService(self.db)
        self.analytics = AnalyticsService(
            self.db, self.settings, self.attendance, self.marks
        )
        self.backup = BackupService(self.db, self.settings)
        # Imported lazily to keep startup fast and avoid a circular import.
        from app.services.report_service import ReportService

        self.reports = ReportService(
            self.db, self.settings, self.students, self.attendance, self.marks, self.analytics
        )

    # ------------------------------------------------------------------ state
    @property
    def session_id(self) -> int | None:
        return self.settings.active_session_id()

    @property
    def session_name(self) -> str:
        return self.settings.active_session_name()

    def close(self) -> None:
        self.db.close()
