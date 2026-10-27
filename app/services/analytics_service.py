"""Aggregated statistics for the dashboard and analytics pages."""
from __future__ import annotations

from typing import Any

from app.database import Database
from app.services import calculations
from app.services.attendance_service import AttendanceService
from app.services.marks_service import MarksService
from app.services.settings_service import SettingsService
from app.utils import dates as date_utils


class AnalyticsService:
    def __init__(
        self,
        db: Database,
        settings: SettingsService,
        attendance: AttendanceService,
        marks: MarksService,
    ) -> None:
        self.db = db
        self.settings = settings
        self.attendance = attendance
        self.marks = marks

    # ---------------------------------------------------------------- helpers
    def _attendance_counts(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> dict[str, Any]:
        clauses = ["s.session_id = ?", "a.attendance_date BETWEEN ? AND ?"]
        params: list[Any] = [int(session_id), start, end]
        if class_name in ("9", "10"):
            clauses.append("s.class_name = ?")
            params.append(class_name)
        row = self.db.query_one(
            "SELECT "
            "SUM(CASE WHEN a.status = 'P' THEN 1 ELSE 0 END) AS p,"
            "SUM(CASE WHEN a.status = 'A' THEN 1 ELSE 0 END) AS a,"
            "SUM(CASE WHEN a.status = 'L' THEN 1 ELSE 0 END) AS l,"
            "COUNT(DISTINCT a.attendance_date) AS days "
            "FROM attendance a JOIN students s ON s.id = a.student_id "
            f"WHERE {' AND '.join(clauses)}",
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
            "counted": p + a + (0 if self.settings.leave_excluded else l),
            "percentage": calculations.attendance_percentage(p, a, l, self.settings.leave_excluded),
            "has_data": (p + a + l) > 0,
        }

    def _mark_records(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> list[Any]:
        clauses = ["e.session_id = ?", "(e.exam_date IS NULL OR e.exam_date BETWEEN ? AND ?)"]
        params: list[Any] = [int(session_id), start, end]
        if class_name in ("9", "10"):
            clauses.append("e.class_name = ?")
            params.append(class_name)
        return self.db.query(
            "SELECT m.id, m.student_id, m.total, m.status AS mark_status, m.theory, m.practical,"
            " m.project, e.id AS exam_id, e.name AS exam_name, e.exam_type, e.exam_date,"
            " e.max_marks, e.pass_marks, e.pass_percent, e.class_name, s.full_name, s.roll_no "
            "FROM marks m JOIN examinations e ON e.id = m.examination_id "
            "JOIN students s ON s.id = m.student_id "
            f"WHERE {' AND '.join(clauses)}",
            params,
        )

    def _mark_totals(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> dict[str, Any]:
        records = self._mark_records(session_id, class_name, start, end)
        entered = [r for r in records if r["mark_status"] == "entered" and r["total"] is not None]
        absent = [r for r in records if r["mark_status"] == "absent"]
        exempted = [r for r in records if r["mark_status"] == "exempted"]
        passed = 0
        failed = 0
        percentages = []
        raw_percentages = []
        for row in entered:
            pct = calculations.percentage(row["total"], row["max_marks"])
            percentages.append(pct)
            if pct is not None:
                raw_percentages.append(pct)
            verdict = calculations.is_pass(
                row["total"], row["max_marks"], row["pass_marks"], row["pass_percent"]
            )
            if verdict:
                passed += 1
            elif verdict is False:
                failed += 1
        summary = calculations.summarize(percentages)
        graded = passed + failed + len(absent)
        return {
            "records": records,
            "entered": len(entered),
            "absent": len(absent),
            "exempted": len(exempted),
            "passed": passed,
            "failed": failed,
            "pass_percentage": calculations.rate(passed, graded),
            "average_percentage": summary["average"],
            "highest_percentage": summary["highest"],
            "lowest_percentage": summary["lowest"],
            "median_percentage": summary["median"],
            "marks_average": summary["average"],
            "percentages": raw_percentages,
        }

    def student_aggregates(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> list[dict[str, Any]]:
        """Per-student attendance and average marks used for support / thresholds."""
        clauses = ["s.session_id = ?", "s.status = 'active'"]
        params: list[Any] = [int(session_id)]
        if class_name in ("9", "10"):
            clauses.append("s.class_name = ?")
            params.append(class_name)
        students = self.db.query(
            "SELECT s.id, s.roll_no, s.full_name, s.class_name, s.section FROM students s "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY s.class_name, CAST(s.roll_no AS INTEGER), s.roll_no",
            params,
        )
        att_rows = self.db.query(
            "SELECT a.student_id,"
            "SUM(CASE WHEN a.status = 'P' THEN 1 ELSE 0 END) AS p,"
            "SUM(CASE WHEN a.status = 'A' THEN 1 ELSE 0 END) AS a,"
            "SUM(CASE WHEN a.status = 'L' THEN 1 ELSE 0 END) AS l "
            "FROM attendance a JOIN students s ON s.id = a.student_id "
            f"WHERE {' AND '.join(clauses)} AND a.attendance_date BETWEEN ? AND ? "
            "GROUP BY a.student_id",
            params + [start, end],
        )
        attendance_map = {
            int(row["student_id"]): (int(row["p"] or 0), int(row["a"] or 0), int(row["l"] or 0))
            for row in att_rows
        }
        mark_rows = self._mark_records(session_id, class_name, start, end)
        mark_map: dict[int, list[float]] = {}
        for row in mark_rows:
            if row["mark_status"] != "entered" or row["total"] is None:
                continue
            pct = calculations.percentage(row["total"], row["max_marks"])
            if pct is not None:
                mark_map.setdefault(int(row["student_id"]), []).append(pct)
        threshold_att = self.settings.attendance_threshold
        threshold_perf = self.settings.performance_threshold
        result = []
        for student in students:
            p, a, l = attendance_map.get(int(student["id"]), (0, 0, 0))
            att_pct = calculations.attendance_percentage(p, a, l, self.settings.leave_excluded)
            marks_list = mark_map.get(int(student["id"]), [])
            avg = round(sum(marks_list) / len(marks_list), 2) if marks_list else None
            reasons = []
            if att_pct is not None and att_pct < threshold_att:
                reasons.append(f"Attendance {att_pct:.1f}% below {threshold_att:g}%")
            if avg is not None and avg < threshold_perf:
                reasons.append(f"Average {avg:.1f}% below {threshold_perf:g}%")
            result.append(
                {
                    "student_id": int(student["id"]),
                    "roll_no": student["roll_no"],
                    "full_name": student["full_name"],
                    "class_name": student["class_name"],
                    "section": student["section"] or "",
                    "present": p,
                    "absent": a,
                    "leave": l,
                    "counted": p + a + (0 if self.settings.leave_excluded else l),
                    "attendance_percentage": att_pct,
                    "exam_count": len(marks_list),
                    "average_percentage": avg,
                    "needs_support": bool(reasons),
                    "support_reasons": reasons,
                }
            )
        return result

    # -------------------------------------------------------------- dashboard
    def dashboard_metrics(
        self,
        session_id: int,
        class_name: str | None,
        start: str,
        end: str,
        on_date: str | None = None,
    ) -> dict[str, Any]:
        on_date = on_date or date_utils.today().isoformat()
        counts = self.db.query(
            "SELECT class_name, COUNT(*) AS total FROM students "
            "WHERE session_id = ? AND status = 'active' GROUP BY class_name",
            (int(session_id),),
        )
        class_totals = {row["class_name"]: int(row["total"]) for row in counts}
        if class_name in ("9", "10"):
            day = self.attendance.day_summary(session_id, class_name, on_date)
            today_counts = day.as_dict()
        else:
            # All classes: aggregate today's records without double counting.
            row = self.db.query_one(
                "SELECT "
                "SUM(CASE WHEN a.status = 'P' THEN 1 ELSE 0 END) AS p,"
                "SUM(CASE WHEN a.status = 'A' THEN 1 ELSE 0 END) AS a,"
                "SUM(CASE WHEN a.status = 'L' THEN 1 ELSE 0 END) AS l "
                "FROM attendance a JOIN students s ON s.id = a.student_id "
                "WHERE s.session_id = ? AND a.attendance_date = ?",
                (int(session_id), on_date),
            )
            p = int(row["p"] or 0) if row else 0
            a = int(row["a"] or 0) if row else 0
            l = int(row["l"] or 0) if row else 0
            today_counts = {
                "present": p,
                "absent": a,
                "leave": l,
                "percentage": calculations.attendance_percentage(p, a, l, self.settings.leave_excluded),
            }
        marks = self._mark_totals(session_id, class_name, start, end)
        students = self.student_aggregates(session_id, class_name, start, end)
        below_attendance = [
            s for s in students
            if s["attendance_percentage"] is not None
            and s["attendance_percentage"] < self.settings.attendance_threshold
        ]
        support = [s for s in students if s["needs_support"]]
        total_students = (
            sum(class_totals.values()) if class_name not in ("9", "10")
            else class_totals.get(class_name, 0)
        )
        return {
            "session_id": int(session_id),
            "class_name": class_name,
            "start": start,
            "end": end,
            "on_date": on_date,
            "class_totals": {"9": class_totals.get("9", 0), "10": class_totals.get("10", 0)},
            "total_students": total_students,
            "today": today_counts,
            "today_saved": self.attendance.existing_count(
                session_id, class_name, on_date
            ) > 0 if class_name in ("9", "10") else None,
            "attendance": self._attendance_counts(session_id, class_name, start, end),
            "marks": {k: v for k, v in marks.items() if k not in ("records", "percentages")},
            "below_attendance": below_attendance,
            "support_students": support,
            "attendance_threshold": self.settings.attendance_threshold,
            "performance_threshold": self.settings.performance_threshold,
            "has_students": total_students > 0,
            "recent_activity": self.db.recent_activity(12),
        }

    # ----------------------------------------------------------------- charts
    def attendance_pie(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> dict[str, Any]:
        return self._attendance_counts(session_id, class_name, start, end)

    def results_pie(self, exam_id: int) -> dict[str, Any]:
        stats = self.marks.class_statistics(exam_id)
        return {
            "passed": stats["passed"],
            "failed": stats["failed"],
            "absent": stats["absent"],
            "exempted": stats["exempted"],
            "pending": stats["pending"],
            "total": stats["students"],
            "has_data": stats["entered"] > 0 or stats["absent"] > 0 or stats["exempted"] > 0,
            "pass_percentage": stats["pass_percentage"],
        }

    def marks_distribution(self, exam_id: int) -> dict[str, Any]:
        exam = self.marks.get_examination(exam_id)
        if exam is None:
            return {"exam": None, "rows": [], "max_marks": 0}
        rows = self.marks.result_rows(exam_id)
        return {
            "exam": exam,
            "rows": rows,
            "max_marks": float(exam["max_marks"]),
            "has_data": any(r["status"] == "entered" for r in rows),
        }

    def class_comparison(
        self, session_id: int, start: str, end: str
    ) -> list[dict[str, Any]]:
        result = []
        for class_name in ("9", "10"):
            attendance = self._attendance_counts(session_id, class_name, start, end)
            marks = self._mark_totals(session_id, class_name, start, end)
            student_count = int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM students WHERE session_id = ? AND class_name = ?"
                    " AND status = 'active'",
                    (int(session_id), class_name),
                    default=0,
                )
            )
            result.append(
                {
                    "class_name": class_name,
                    "students": student_count,
                    "average_percentage": marks["average_percentage"],
                    "pass_percentage": marks["pass_percentage"],
                    "attendance_percentage": attendance["percentage"],
                    "has_marks": marks["entered"] > 0,
                    "has_attendance": attendance["has_data"],
                }
            )
        return result

    def monthly_trend(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> list[dict[str, Any]]:
        return self.attendance.monthly_trend(session_id, class_name, start, end)

    def student_performance(self, student_id: int, start: str, end: str) -> dict[str, Any]:
        student = self.db.query_one("SELECT * FROM students WHERE id = ?", (int(student_id),))
        if student is None:
            raise ValueError("Student not found.")
        history = self.marks.student_history(student_id)
        attendance = self.attendance.student_summary(student_id, start, end)
        trend = self.db.query(
            "SELECT substr(attendance_date, 1, 7) AS month,"
            "SUM(CASE WHEN status = 'P' THEN 1 ELSE 0 END) AS p,"
            "SUM(CASE WHEN status = 'A' THEN 1 ELSE 0 END) AS a,"
            "SUM(CASE WHEN status = 'L' THEN 1 ELSE 0 END) AS l "
            "FROM attendance WHERE student_id = ? AND attendance_date BETWEEN ? AND ? "
            "GROUP BY month ORDER BY month",
            (int(student_id), start, end),
        )
        percentages = [h["percentage"] for h in history if h["percentage"] is not None]
        average = round(sum(percentages) / len(percentages), 2) if percentages else None
        weak_exams = [h for h in history if h["percentage"] is not None and h["percentage"] < self.settings.performance_threshold]
        return {
            "student": student,
            "history": history,
            "attendance": attendance,
            "attendance_trend": [
                {
                    "month": row["month"],
                    "percentage": calculations.attendance_percentage(
                        int(row["p"]), int(row["a"]), int(row["l"]), self.settings.leave_excluded
                    ),
                }
                for row in trend
            ],
            "average_percentage": average,
            "weak_exams": weak_exams,
            "needs_support": (
                (average is not None and average < self.settings.performance_threshold)
                or (
                    attendance["percentage"] is not None
                    and attendance["percentage"] < self.settings.attendance_threshold
                )
            ),
        }

    def performance_summary(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> dict[str, Any]:
        marks = self._mark_totals(session_id, class_name, start, end)
        attendance = self._attendance_counts(session_id, class_name, start, end)
        students = self.student_aggregates(session_id, class_name, start, end)
        return {
            "marks": {k: v for k, v in marks.items() if k not in ("records", "percentages")},
            "attendance": attendance,
            "students": students,
            "below_attendance": [
                s for s in students
                if s["attendance_percentage"] is not None
                and s["attendance_percentage"] < self.settings.attendance_threshold
            ],
            "support_students": [s for s in students if s["needs_support"]],
            "attendance_threshold": self.settings.attendance_threshold,
            "performance_threshold": self.settings.performance_threshold,
        }
