"""Attendance recording, editing, registers and holiday handling."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping

from app.database import Database, utc_now
from app.services import calculations
from app.services.settings_service import SettingsService
from app.utils import dates as date_utils
from app.utils.validators import ValidationError, clean_text, parse_iso_date


class AlreadySavedError(ValidationError):
    """Raised when a saved attendance session would be overwritten."""


@dataclass
class AttendanceCounts:
    present: int = 0
    absent: int = 0
    leave: int = 0
    unmarked: int = 0
    percentage: float | None = None
    exclude_leave: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "absent": self.absent,
            "leave": self.leave,
            "unmarked": self.unmarked,
            "percentage": self.percentage,
            "exclude_leave": self.exclude_leave,
        }


@dataclass
class RosterEntry:
    student_id: int
    roll_no: str
    full_name: str
    section: str
    status: str | None = None
    remarks: str = ""


@dataclass
class DayAttendance:
    session_id: int
    class_name: str
    on_date: str
    entries: list[RosterEntry] = field(default_factory=list)
    saved: bool = False
    saved_at: str | None = None
    is_holiday: bool = False
    holiday_name: str = ""
    exclude_leave: bool = True

    @property
    def counts(self) -> AttendanceCounts:
        present = sum(1 for e in self.entries if e.status == "P")
        absent = sum(1 for e in self.entries if e.status == "A")
        leave = sum(1 for e in self.entries if e.status == "L")
        unmarked = sum(1 for e in self.entries if e.status is None)
        return AttendanceCounts(
            present=present,
            absent=absent,
            leave=leave,
            unmarked=unmarked,
            percentage=calculations.attendance_percentage(
                present, absent, leave, self.exclude_leave
            ),
            exclude_leave=self.exclude_leave,
        )


class AttendanceService:
    def __init__(self, db: Database, settings: SettingsService | None = None) -> None:
        self.db = db
        self.settings = settings

    @property
    def exclude_leave(self) -> bool:
        """Whether Leave days are removed from the attendance percentage.

        The setting is documented in the Settings page. Leave is always a
        distinct status and is never treated as Absent.
        """
        if self.settings is None:
            return True
        return self.settings.leave_excluded

    # ------------------------------------------------------------------ load
    def roster(self, session_id: int, class_name: str) -> list[Any]:
        return self.db.query(
            "SELECT id, roll_no, full_name, section FROM students "
            "WHERE session_id = ? AND class_name = ? AND status = 'active' "
            "ORDER BY CAST(roll_no AS INTEGER), roll_no",
            (int(session_id), class_name),
        )

    def load_day(
        self,
        session_id: int,
        class_name: str,
        on_date: str | date,
        exclude_leave: bool | None = None,
    ) -> DayAttendance:
        if exclude_leave is None:
            exclude_leave = self.exclude_leave
        iso_date = date_utils.iso(parse_iso_date(on_date))
        if not iso_date:
            raise ValidationError("Select a valid attendance date.")
        roster = self.roster(session_id, class_name)
        saved_rows = {
            int(row["student_id"]): row
            for row in self.db.query(
                "SELECT a.* FROM attendance a JOIN students s ON s.id = a.student_id "
                "WHERE a.attendance_date = ? AND s.session_id = ? AND s.class_name = ?",
                (iso_date, int(session_id), class_name),
            )
        }
        batch = self.db.query_one(
            "SELECT * FROM attendance_batches WHERE session_id = ? AND class_name = ?"
            " AND attendance_date = ?",
            (int(session_id), class_name, iso_date),
        )
        entries = [
            RosterEntry(
                student_id=int(row["id"]),
                roll_no=row["roll_no"],
                full_name=row["full_name"],
                section=row["section"] or "",
                status=(saved_rows[int(row["id"])]["status"] if int(row["id"]) in saved_rows else None),
                remarks=(saved_rows[int(row["id"])]["remarks"] or "" if int(row["id"]) in saved_rows else ""),
            )
            for row in roster
        ]
        entry_ids = {e.student_id for e in entries}
        # Historical records for archived/inactive students remain visible.
        for student_id, row in saved_rows.items():
            if student_id in entry_ids:
                continue
            student = self.db.query_one(
                "SELECT id, roll_no, full_name, section, status FROM students WHERE id = ?",
                (student_id,),
            )
            if student:
                entries.append(
                    RosterEntry(
                        student_id=int(student["id"]),
                        roll_no=student["roll_no"],
                        full_name=student["full_name"],
                        section=student["section"] or "",
                        status=row["status"],
                        remarks=row["remarks"] or "",
                    )
                )
        holiday = self.holiday_for(session_id, iso_date)
        counts_valid = AttendanceCounts(exclude_leave=exclude_leave)
        if entries:
            present = sum(1 for e in entries if e.status == "P")
            absent = sum(1 for e in entries if e.status == "A")
            leave = sum(1 for e in entries if e.status == "L")
            counts_valid = AttendanceCounts(
                present=present,
                absent=absent,
                leave=leave,
                unmarked=sum(1 for e in entries if e.status is None),
                percentage=calculations.attendance_percentage(
                    present, absent, leave, exclude_leave
                ),
                exclude_leave=exclude_leave,
            )
        return DayAttendance(
            session_id=int(session_id),
            class_name=class_name,
            on_date=iso_date,
            entries=sorted(entries, key=lambda e: (len(e.roll_no), e.roll_no)),
            saved=batch is not None,
            saved_at=batch["saved_at"] if batch else None,
            is_holiday=holiday is not None,
            holiday_name=holiday["name"] if holiday else "",
            exclude_leave=exclude_leave,
        )

    def is_saved(self, session_id: int, class_name: str, on_date: str) -> bool:
        return (
            self.db.query_one(
                "SELECT id FROM attendance_batches WHERE session_id = ? AND class_name = ?"
                " AND attendance_date = ?",
                (int(session_id), class_name, date_utils.iso(parse_iso_date(on_date))),
            )
            is not None
        )

    def existing_count(self, session_id: int, class_name: str, on_date: str) -> int:
        return int(
            self.db.scalar(
                "SELECT COUNT(*) FROM attendance a JOIN students s ON s.id = a.student_id "
                "WHERE a.attendance_date = ? AND s.session_id = ? AND s.class_name = ?",
                (date_utils.iso(parse_iso_date(on_date)), int(session_id), class_name),
                default=0,
            )
        )

    # ------------------------------------------------------------------ save
    def save_day(
        self,
        session_id: int,
        class_name: str,
        on_date: str | date,
        entries: Iterable[Mapping[str, Any] | RosterEntry],
        marked_by: str = "",
        overwrite: bool = False,
    ) -> AttendanceCounts:
        iso_date = date_utils.iso(parse_iso_date(on_date))
        if not iso_date:
            raise ValidationError("Select a valid attendance date.")
        if class_name not in ("9", "10"):
            raise ValidationError("Select Class 9 or Class 10.")
        saved = self.is_saved(session_id, class_name, iso_date)
        if saved and not overwrite:
            raise AlreadySavedError(
                "Attendance for this class and date has already been saved. "
                "Confirm that you want to overwrite the existing session."
            )
        roster_ids = {
            int(row["id"]) for row in self.roster(session_id, class_name)
        }
        parsed: list[tuple[int, str, str]] = []
        unmarked_ids: list[int] = []
        for entry in entries:
            if isinstance(entry, RosterEntry):
                student_id = entry.student_id
                status = entry.status
                remarks = entry.remarks
                if entry.status is None:
                    remarks = ""
            else:
                student_id = int(entry.get("student_id"))
                status = entry.get("status")
                remarks = clean_text(entry.get("remarks"), 200)
            if student_id not in roster_ids:
                raise ValidationError(
                    "One of the students does not belong to this class and session. "
                    "Reload the roster and try again."
                )
            if status in (None, ""):
                unmarked_ids.append(student_id)
                continue
            if status not in ("P", "A", "L"):
                raise ValidationError("Each student must be Present, Absent or Leave.")
            parsed.append((student_id, status, remarks))
        if not parsed and not unmarked_ids:
            raise ValidationError("There are no students to record attendance for.")
        if not parsed:
            raise ValidationError(
                "Mark at least one student before saving. Unmarked students are not saved."
            )
        now = utc_now()
        with self.db.transaction() as conn:
            for student_id, status, remarks in parsed:
                conn.execute(
                    "INSERT INTO attendance (student_id, session_id, class_name, attendance_date,"
                    " status, remarks, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(student_id, attendance_date) DO UPDATE SET"
                    " status = excluded.status, remarks = excluded.remarks,"
                    " class_name = excluded.class_name, session_id = excluded.session_id,"
                    " updated_at = excluded.updated_at",
                    (student_id, int(session_id), class_name, iso_date, status, remarks or None, now, now),
                )
            # A cleared status removes the previous record (unmarked != absent).
            for student_id in unmarked_ids:
                conn.execute(
                    "DELETE FROM attendance WHERE student_id = ? AND attendance_date = ?",
                    (student_id, iso_date),
                )
            conn.execute(
                "INSERT INTO attendance_batches (session_id, class_name, attendance_date, saved_at, saved_by)"
                " VALUES (?, ?, ?, ?, ?) ON CONFLICT(session_id, class_name, attendance_date)"
                " DO UPDATE SET saved_at = excluded.saved_at, saved_by = excluded.saved_by",
                (int(session_id), class_name, iso_date, now, marked_by or None),
            )
        present = sum(1 for _, status, _ in parsed if status == "P")
        absent = sum(1 for _, status, _ in parsed if status == "A")
        leave = sum(1 for _, status, _ in parsed if status == "L")
        self.db.log_activity(
            "save", "attendance", None,
            f"Class {class_name} {iso_date}: {present} present, {absent} absent, {leave} leave",
        )
        return AttendanceCounts(
            present=present,
            absent=absent,
            leave=leave,
            unmarked=len(unmarked_ids),
            percentage=calculations.attendance_percentage(present, absent, leave, self.exclude_leave),
            exclude_leave=self.exclude_leave,
        )

    # -------------------------------------------------------------- summaries
    def day_summary(self, session_id: int, class_name: str, on_date: str) -> AttendanceCounts:
        row = self.db.query_one(
            "SELECT "
            "SUM(CASE WHEN a.status = 'P' THEN 1 ELSE 0 END) AS p,"
            "SUM(CASE WHEN a.status = 'A' THEN 1 ELSE 0 END) AS a,"
            "SUM(CASE WHEN a.status = 'L' THEN 1 ELSE 0 END) AS l "
            "FROM attendance a JOIN students s ON s.id = a.student_id "
            "WHERE s.session_id = ? AND s.class_name = ? AND a.attendance_date = ?",
            (int(session_id), class_name, on_date),
        )
        p = int(row["p"] or 0) if row else 0
        a = int(row["a"] or 0) if row else 0
        l = int(row["l"] or 0) if row else 0
        return AttendanceCounts(
            present=p,
            absent=a,
            leave=l,
            percentage=calculations.attendance_percentage(p, a, l, self.exclude_leave),
        )

    def range_summary(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> dict[str, Any]:
        clauses = ["a.attendance_date BETWEEN ? AND ?"]
        params: list[Any] = [start, end]
        if class_name in ("9", "10"):
            clauses.append("s.class_name = ?")
            params.append(class_name)
        if session_id:
            clauses.append("s.session_id = ?")
            params.append(int(session_id))
        where = " AND ".join(clauses)
        row = self.db.query_one(
            "SELECT "
            "SUM(CASE WHEN a.status = 'P' THEN 1 ELSE 0 END) AS p,"
            "SUM(CASE WHEN a.status = 'A' THEN 1 ELSE 0 END) AS a,"
            "SUM(CASE WHEN a.status = 'L' THEN 1 ELSE 0 END) AS l,"
            "COUNT(DISTINCT a.attendance_date) AS days "
            f"FROM attendance a JOIN students s ON s.id = a.student_id WHERE {where}",
            params,
        )
        p = int(row["p"] or 0) if row else 0
        a = int(row["a"] or 0) if row else 0
        l = int(row["l"] or 0) if row else 0
        return {
            "present": p,
            "absent": a,
            "leave": l,
            "sessions": int(row["days"] or 0) if row else 0,
            "percentage": calculations.attendance_percentage(p, a, l, self.exclude_leave),
        }

    def daily_breakdown(
        self, session_id: int, class_name: str, start: str, end: str
    ) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT a.attendance_date AS d,"
            "SUM(CASE WHEN a.status = 'P' THEN 1 ELSE 0 END) AS p,"
            "SUM(CASE WHEN a.status = 'A' THEN 1 ELSE 0 END) AS a,"
            "SUM(CASE WHEN a.status = 'L' THEN 1 ELSE 0 END) AS l "
            "FROM attendance a JOIN students s ON s.id = a.student_id "
            "WHERE s.session_id = ? AND s.class_name = ? AND a.attendance_date BETWEEN ? AND ? "
            "GROUP BY a.attendance_date ORDER BY a.attendance_date",
            (int(session_id), class_name, start, end),
        )
        holidays = {h["holiday_date"]: h["name"] for h in self.holidays(session_id, start, end)}
        result = []
        for row in rows:
            p, a, l = int(row["p"]), int(row["a"]), int(row["l"])
            result.append(
                {
                    "date": row["d"],
                    "present": p,
                    "absent": a,
                    "leave": l,
                    "percentage": calculations.attendance_percentage(p, a, l, self.exclude_leave),
                    "holiday": holidays.get(row["d"], ""),
                }
            )
        return result

    def student_history(self, student_id: int, limit: int = 500) -> list[Any]:
        return self.db.query(
            "SELECT * FROM attendance WHERE student_id = ? ORDER BY attendance_date DESC LIMIT ?",
            (int(student_id), int(limit)),
        )

    def student_summary(self, student_id: int, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        sql = (
            "SELECT "
            "SUM(CASE WHEN status = 'P' THEN 1 ELSE 0 END) AS p,"
            "SUM(CASE WHEN status = 'A' THEN 1 ELSE 0 END) AS a,"
            "SUM(CASE WHEN status = 'L' THEN 1 ELSE 0 END) AS l "
            "FROM attendance WHERE student_id = ?"
        )
        params: list[Any] = [int(student_id)]
        if start and end:
            sql += " AND attendance_date BETWEEN ? AND ?"
            params.extend([start, end])
        row = self.db.query_one(sql, params)
        p = int(row["p"] or 0) if row else 0
        a = int(row["a"] or 0) if row else 0
        l = int(row["l"] or 0) if row else 0
        return {
            "present": p,
            "absent": a,
            "leave": l,
            "counted": p + a + (0 if self.exclude_leave else l),
            "percentage": calculations.attendance_percentage(p, a, l, self.exclude_leave),
        }

    def class_summary(self, session_id: int, class_name: str, start: str, end: str) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT s.id, s.roll_no, s.full_name, s.section,"
            "SUM(CASE WHEN a.status = 'P' THEN 1 ELSE 0 END) AS p,"
            "SUM(CASE WHEN a.status = 'A' THEN 1 ELSE 0 END) AS a,"
            "SUM(CASE WHEN a.status = 'L' THEN 1 ELSE 0 END) AS l "
            "FROM students s LEFT JOIN attendance a ON a.student_id = s.id "
            "AND a.attendance_date BETWEEN ? AND ? "
            "WHERE s.session_id = ? AND s.class_name = ? AND s.status = 'active' "
            "GROUP BY s.id ORDER BY CAST(s.roll_no AS INTEGER), s.roll_no",
            (start, end, int(session_id), class_name),
        )
        result = []
        for row in rows:
            p, a, l = int(row["p"] or 0), int(row["a"] or 0), int(row["l"] or 0)
            result.append(
                {
                    "student_id": int(row["id"]),
                    "roll_no": row["roll_no"],
                    "full_name": row["full_name"],
                    "section": row["section"] or "",
                    "present": p,
                    "absent": a,
                    "leave": l,
                    "counted": p + a + (0 if self.exclude_leave else l),
                    "percentage": calculations.attendance_percentage(p, a, l, self.exclude_leave),
                }
            )
        return result

    def monthly_trend(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> list[dict[str, Any]]:
        clauses = ["a.attendance_date BETWEEN ? AND ?"]
        params: list[Any] = [start, end]
        if class_name in ("9", "10"):
            clauses.append("s.class_name = ?")
            params.append(class_name)
        if session_id:
            clauses.append("s.session_id = ?")
            params.append(int(session_id))
        rows = self.db.query(
            "SELECT substr(a.attendance_date, 1, 7) AS month,"
            "SUM(CASE WHEN a.status = 'P' THEN 1 ELSE 0 END) AS p,"
            "SUM(CASE WHEN a.status = 'A' THEN 1 ELSE 0 END) AS a,"
            "SUM(CASE WHEN a.status = 'L' THEN 1 ELSE 0 END) AS l,"
            "COUNT(DISTINCT a.attendance_date) AS days "
            "FROM attendance a JOIN students s ON s.id = a.student_id "
            f"WHERE {' AND '.join(clauses)} GROUP BY month ORDER BY month",
            params,
        )
        result = []
        for row in rows:
            p, a, l = int(row["p"]), int(row["a"]), int(row["l"])
            result.append(
                {
                    "month": row["month"],
                    "present": p,
                    "absent": a,
                    "leave": l,
                    "sessions": int(row["days"]),
                    "percentage": calculations.attendance_percentage(p, a, l, self.exclude_leave),
                }
            )
        return result

    def monthly_register(
        self, session_id: int, class_name: str, year: int, month: int
    ) -> dict[str, Any]:
        start, end = date_utils.month_bounds(year, month)
        students = self.roster(session_id, class_name)
        rows = self.db.query(
            "SELECT a.student_id, a.attendance_date, a.status FROM attendance a "
            "JOIN students s ON s.id = a.student_id "
            "WHERE s.session_id = ? AND s.class_name = ? AND a.attendance_date BETWEEN ? AND ?",
            (int(session_id), class_name, start.isoformat(), end.isoformat()),
        )
        marks: dict[int, dict[str, str]] = {}
        for row in rows:
            marks.setdefault(int(row["student_id"]), {})[row["attendance_date"]] = row["status"]
        holidays = {
            h["holiday_date"]: h["name"] for h in self.holidays(session_id, start.isoformat(), end.isoformat())
        }
        register_rows = []
        for student in students:
            student_marks = marks.get(int(student["id"]), {})
            p = sum(1 for v in student_marks.values() if v == "P")
            a = sum(1 for v in student_marks.values() if v == "A")
            l = sum(1 for v in student_marks.values() if v == "L")
            register_rows.append(
                {
                    "student_id": int(student["id"]),
                    "roll_no": student["roll_no"],
                    "full_name": student["full_name"],
                    "section": student["section"] or "",
                    "marks": student_marks,
                    "present": p,
                    "absent": a,
                    "leave": l,
                    "percentage": calculations.attendance_percentage(p, a, l, self.exclude_leave),
                }
            )
        return {
            "year": year,
            "month": month,
            "label": date_utils.month_label(year, month),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": date_utils.days_in_month(year, month),
            "students": register_rows,
            "holidays": holidays,
            "session_id": int(session_id),
            "class_name": class_name,
        }

    # ---------------------------------------------------------------- holidays
    def holidays(self, session_id: int, start: str | None = None, end: str | None = None) -> list[Any]:
        sql = "SELECT * FROM holidays WHERE session_id = ?"
        params: list[Any] = [int(session_id)]
        if start and end:
            sql += " AND holiday_date BETWEEN ? AND ?"
            params.extend([start, end])
        sql += " ORDER BY holiday_date"
        return self.db.query(sql, params)

    def holiday_for(self, session_id: int, on_date: str) -> Any:
        return self.db.query_one(
            "SELECT * FROM holidays WHERE session_id = ? AND holiday_date = ?",
            (int(session_id), on_date),
        )

    def add_holiday(self, session_id: int, on_date: str, name: str) -> int:
        parsed = parse_iso_date(on_date)
        if not parsed:
            raise ValidationError("Select a valid holiday date.")
        name = clean_text(name, 120)
        if not name:
            raise ValidationError("Enter a name for the holiday.")
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO holidays (holiday_date, name, session_id, created_at)"
                " VALUES (?, ?, ?, ?) ON CONFLICT(holiday_date, session_id)"
                " DO UPDATE SET name = excluded.name",
                (parsed.isoformat(), name, int(session_id), utc_now()),
            )
        self.db.log_activity("create", "holiday", None, f"{parsed.isoformat()} {name}")
        row = self.holiday_for(session_id, parsed.isoformat())
        return int(row["id"]) if row else 0

    def delete_holiday(self, holiday_id: int) -> None:
        self.db.execute("DELETE FROM holidays WHERE id = ?", (int(holiday_id),))
        self.db.log_activity("delete", "holiday", holiday_id, "")

    def holiday_dates(self, session_id: int, start: str, end: str) -> set[str]:
        return {row["holiday_date"] for row in self.holidays(session_id, start, end)}
