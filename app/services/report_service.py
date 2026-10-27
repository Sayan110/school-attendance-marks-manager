"""Builds structured report documents used by PDF, Excel and on-screen preview."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from app.database import Database
from app.services import calculations
from app.services.analytics_service import AnalyticsService
from app.services.attendance_service import AttendanceService
from app.services.marks_service import MarksService
from app.services.settings_service import SettingsService
from app.services.student_service import StudentService
from app.utils import dates as date_utils
from app.utils.validators import ValidationError


def dash(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def pct(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return f"{float(value):.2f}%"


def num(value: Any, digits: int = 2) -> str:
    if value is None or value == "":
        return "—"
    number = float(value)
    if abs(number - round(number)) < 1e-9:
        return f"{number:.0f}"
    return f"{number:.{digits}f}"


@dataclass
class ReportTable:
    headers: list[str]
    rows: list[list[Any]] = field(default_factory=list)
    widths: list[float] | None = None
    title: str = ""
    align: list[str] | None = None
    empty_message: str = "No records match this report."


@dataclass
class ReportDocument:
    key: str
    title: str
    school: str
    subtitle: str
    meta: list[tuple[str, str]]
    summary: list[tuple[str, str]]
    tables: list[ReportTable]
    notes: list[str]
    generated_at: str
    landscape: bool = False
    filename_stem: str = "report"
    board: str = "SEBA Board, Assam"
    subject: str = "Computer Science"
    classes: str = "Classes 9 & 10"

    @property
    def letterhead_line(self) -> str:
        parts = [self.board, self.subject, self.classes]
        return "  •  ".join(part for part in parts if part)

    @property
    def has_tables(self) -> bool:
        return any(table.rows for table in self.tables)


REPORT_TYPES: list[tuple[str, str]] = [
    ("daily_attendance", "Daily attendance register"),
    ("monthly_attendance", "Monthly attendance register"),
    ("student_attendance", "Individual student attendance report"),
    ("class_attendance", "Class attendance summary"),
    ("marksheet", "Examination marksheet"),
    ("student_progress", "Individual student progress report"),
    ("class_performance", "Class performance report"),
    ("support_report", "Failed-student and academic-support report"),
    ("below_threshold", "Students below attendance threshold"),
    ("session_summary", "Academic session summary"),
]

REPORT_LABELS = dict(REPORT_TYPES)


class ReportService:
    def __init__(
        self,
        db: Database,
        settings: SettingsService,
        students: StudentService,
        attendance: AttendanceService,
        marks: MarksService,
        analytics: AnalyticsService,
    ) -> None:
        self.db = db
        self.settings = settings
        self.students = students
        self.attendance = attendance
        self.marks = marks
        self.analytics = analytics

    # ---------------------------------------------------------------- helpers
    def _session(self, session_id: int) -> Any:
        session = self.settings.get_session(session_id)
        if session is None:
            raise ValidationError("Select a valid academic session.")
        return session

    def _meta(
        self,
        session_id: int,
        class_name: str | None = None,
        period: str = "",
        extra: list[tuple[str, str]] | None = None,
    ) -> list[tuple[str, str]]:
        session = self._session(session_id)
        meta = [
            ("Academic session", session["name"]),
            ("Subject", self.settings.subject),
            ("Teacher", self.settings.teacher_name or "—"),
            ("Class", f"Class {class_name}" if class_name else "Class 9 & Class 10"),
        ]
        if period:
            meta.append(("Reporting period", period))
        if extra:
            meta.extend(extra)
        return meta

    @staticmethod
    def _period(start: str, end: str) -> str:
        return f"{date_utils.display(start)} to {date_utils.display(end)}"

    def _student(self, student_id: int) -> Any:
        student = self.students.get(student_id)
        if student is None:
            raise ValidationError("The selected student no longer exists.")
        return student

    @staticmethod
    def _result_label(row: Mapping[str, Any]) -> str:
        status = row.get("status")
        if status == "absent":
            return "Absent"
        if status == "exempted":
            return "Exempted"
        if status == "pending" or row.get("total") is None:
            return "Pending"
        if row.get("passed") is True:
            return "Passed"
        if row.get("passed") is False:
            return "Failed"
        return "Pending"

    def _pass_text(self, exam: Any) -> str:
        if exam["pass_marks"] is not None:
            return f"Passing marks: {num(exam['pass_marks'])} out of {num(exam['max_marks'])}"
        if exam["pass_percent"] is not None:
            return f"Pass criterion: {num(exam['pass_percent'])}% of {num(exam['max_marks'])} marks"
        return "Pass criterion: not configured"

    def _grade(self, percent: float | None, rules: list[Any]) -> str:
        return calculations.grade_for(percent, rules)

    def _generated(self) -> str:
        return datetime.now().strftime("%d-%m-%Y %H:%M")

    @staticmethod
    def _leave_note() -> str:
        return (
            "Attendance rule: Attendance % = Present sessions ÷ counted sessions × 100. "
            "Leave sessions are excluded from the denominator; unmarked sessions are never "
            "treated as absences."
        )

    def _base_document(
        self, key: str, title: str, subtitle: str, meta: list[tuple[str, str]]
    ) -> ReportDocument:
        return ReportDocument(
            key=key,
            title=title,
            school=self.settings.school_name,
            subtitle=subtitle,
            meta=meta,
            summary=[],
            tables=[],
            notes=[],
            generated_at=self._generated(),
            filename_stem=key,
            board=self.settings.board,
            subject=self.settings.subject,
            classes="Classes 9 & 10",
        )

    # -------------------------------------------------------------- 1. daily
    def daily_attendance(self, session_id: int, class_name: str, on_date: str) -> ReportDocument:
        day = self.attendance.load_day(session_id, class_name, on_date)
        counts = day.counts
        doc = self._base_document(
            "daily_attendance",
            "Daily Attendance Register",
            f"{self.settings.subject} • Class {class_name} • {date_utils.display(on_date)}",
            self._meta(session_id, class_name, date_utils.display_long(on_date)),
        )
        doc.filename_stem = f"attendance_daily_class{class_name}_{on_date}"
        doc.summary = [
            ("Present", str(counts.present)),
            ("Absent", str(counts.absent)),
            ("Leave", str(counts.leave)),
            ("Unmarked", str(counts.unmarked)),
            ("Attendance %", pct(counts.percentage)),
        ]
        doc.tables = [
            ReportTable(
                headers=["Roll", "Student name", "Section", "Status", "Remarks"],
                rows=[
                    [
                        entry.roll_no,
                        entry.full_name,
                        dash(entry.section),
                        {"P": "Present", "A": "Absent", "L": "Leave"}.get(entry.status, "Unmarked"),
                        entry.remarks or "",
                    ]
                    for entry in day.entries
                ],
                widths=[60, 220, 60, 90, 170],
                align=["left", "left", "center", "center", "left"],
                empty_message="No students are enrolled in this class for the session.",
            )
        ]
        doc.notes = [self._leave_note()]
        if day.is_holiday:
            doc.notes.insert(0, f"This date is recorded as a holiday: {day.holiday_name}.")
        doc.notes.append(
            "Status shown as 'Unmarked' was not saved and is not counted as an absence."
        )
        return doc

    # ------------------------------------------------------------ 2. monthly
    def monthly_attendance(
        self, session_id: int, class_name: str, year: int, month: int
    ) -> ReportDocument:
        register = self.attendance.monthly_register(session_id, class_name, year, month)
        days = register["days"]
        holidays = register["holidays"]
        doc = self._base_document(
            "monthly_attendance",
            "Monthly Attendance Register",
            f"{self.settings.subject} • Class {class_name} • {register['label']}",
            self._meta(session_id, class_name, register["label"]),
        )
        doc.landscape = True
        doc.filename_stem = f"attendance_monthly_class{class_name}_{year}_{month:02d}"
        total_p = sum(row["present"] for row in register["students"])
        total_a = sum(row["absent"] for row in register["students"])
        total_l = sum(row["leave"] for row in register["students"])
        doc.summary = [
            ("Students", str(len(register["students"]))),
            ("Present", str(total_p)),
            ("Absent", str(total_a)),
            ("Leave", str(total_l)),
            (
                "Attendance %",
                pct(calculations.attendance_percentage(total_p, total_a, total_l, self.settings.leave_excluded)),
            ),
        ]
        headers = ["Roll", "Student"] + [str(day) for day in range(1, days + 1)] + ["P", "A", "L", "%"]
        rows = []
        for student in register["students"]:
            marks = student["marks"]
            row: list[Any] = [student["roll_no"], student["full_name"]]
            for day in range(1, days + 1):
                iso = f"{year:04d}-{month:02d}-{day:02d}"
                if iso in holidays:
                    row.append("H")
                else:
                    row.append(marks.get(iso, ""))
            row.extend(
                [student["present"], student["absent"], student["leave"], pct(student["percentage"])]
            )
            rows.append(row)
        widths = [28, 105] + [14] * days + [20, 20, 20, 32]
        doc.tables = [
            ReportTable(
                headers=headers,
                rows=rows,
                widths=widths,
                align=["left", "left"] + ["center"] * (days + 4),
                empty_message="No students are enrolled in this class for the session.",
            )
        ]
        if holidays:
            doc.notes.append(
                "Holidays / non-instructional dates: "
                + ", ".join(f"{date_utils.display(d)} ({name})" for d, name in sorted(holidays.items()))
            )
        doc.notes.append("H = holiday / non-instructional date (not counted). Blank = no session recorded.")
        doc.notes.append(self._leave_note())
        return doc

    # ---------------------------------------------------- 3. student attendance
    def student_attendance(
        self, student_id: int, start: str, end: str
    ) -> ReportDocument:
        student = self._student(student_id)
        summary = self.attendance.student_summary(student_id, start, end)
        history = [
            row
            for row in self.attendance.student_history(student_id, 2000)
            if start <= row["attendance_date"] <= end
        ]
        doc = self._base_document(
            "student_attendance",
            "Individual Student Attendance Report",
            f"{student['full_name']} • Class {student['class_name']} • {self._period(start, end)}",
            self._meta(
                student["session_id"],
                student["class_name"],
                self._period(start, end),
                [
                    ("Student", student["full_name"]),
                    ("Roll number", student["roll_no"]),
                    ("Section", student["section"] or "—"),
                ],
            ),
        )
        doc.filename_stem = f"attendance_student_{student['roll_no']}_{start}_{end}"
        doc.summary = [
            ("Present", str(summary["present"])),
            ("Absent", str(summary["absent"])),
            ("Leave", str(summary["leave"])),
            ("Counted sessions", str(summary["counted"])),
            ("Attendance %", pct(summary["percentage"])),
        ]
        rows = [
            [
                date_utils.display(row["attendance_date"]),
                date_utils.parse(row["attendance_date"]).strftime("%A")
                if date_utils.parse(row["attendance_date"])
                else "—",
                {"P": "Present", "A": "Absent", "L": "Leave"}.get(row["status"], row["status"]),
                row["remarks"] or "",
            ]
            for row in history
        ]
        doc.tables = [
            ReportTable(
                headers=["Date", "Weekday", "Status", "Remarks"],
                rows=rows,
                widths=[90, 110, 100, 240],
                empty_message="No attendance was recorded for this student in the selected period.",
            )
        ]
        doc.notes = [self._leave_note()]
        threshold = self.settings.attendance_threshold
        if summary["percentage"] is not None and summary["percentage"] < threshold:
            doc.notes.append(
                f"Attention: attendance is below the configured threshold of {threshold:g}%."
            )
        return doc

    # ------------------------------------------------------ 4. class attendance
    def class_attendance(
        self, session_id: int, class_name: str, start: str, end: str
    ) -> ReportDocument:
        rows_data = self.attendance.class_summary(session_id, class_name, start, end)
        totals = {
            "p": sum(r["present"] for r in rows_data),
            "a": sum(r["absent"] for r in rows_data),
            "l": sum(r["leave"] for r in rows_data),
        }
        overall = calculations.attendance_percentage(totals["p"], totals["a"], totals["l"], self.settings.leave_excluded)
        threshold = self.settings.attendance_threshold
        below = [r for r in rows_data if r["percentage"] is not None and r["percentage"] < threshold]
        doc = self._base_document(
            "class_attendance",
            "Class Attendance Summary",
            f"{self.settings.subject} • Class {class_name} • {self._period(start, end)}",
            self._meta(session_id, class_name, self._period(start, end)),
        )
        doc.filename_stem = f"attendance_class{class_name}_{start}_{end}"
        doc.summary = [
            ("Students", str(len(rows_data))),
            ("Present", str(totals["p"])),
            ("Absent", str(totals["a"])),
            ("Leave", str(totals["l"])),
            ("Class attendance %", pct(overall)),
            ("Below threshold", f"{len(below)} (below {threshold:g}%)"),
        ]
        doc.tables = [
            ReportTable(
                headers=["Roll", "Student name", "Section", "Present", "Absent", "Leave", "Counted", "Attendance %"],
                rows=[
                    [
                        r["roll_no"], r["full_name"], dash(r["section"]), r["present"],
                        r["absent"], r["leave"], r["counted"], pct(r["percentage"]),
                    ]
                    for r in rows_data
                ],
                widths=[60, 210, 60, 60, 60, 50, 60, 90],
                align=["left", "left", "center", "center", "center", "center", "center", "center"],
                empty_message="No active students in this class for the session.",
            )
        ]
        doc.notes = [self._leave_note()]
        if below:
            doc.notes.append(
                "Below threshold: " + ", ".join(f"{r['full_name']} ({pct(r['percentage'])})" for r in below)
            )
        return doc

    # -------------------------------------------------------------- 5. marksheet
    def marksheet(self, exam_id: int) -> ReportDocument:
        exam = self.marks.get_examination(exam_id)
        if exam is None:
            raise ValidationError("The selected examination no longer exists.")
        stats = self.marks.class_statistics(exam_id)
        rules = self.settings.grade_rules()
        components = [
            ("Theory", exam["theory_max"], "theory"),
            ("Practical", exam["practical_max"], "practical"),
            ("Project", exam["project_max"], "project"),
        ]
        active_components = [c for c in components if c[1] is not None]
        headers = ["Roll", "Student name"]
        if active_components:
            headers += [c[0] for c in active_components]
            headers += ["Total", "Max", "%"]
        else:
            headers += ["Marks", "Max", "%"]
        headers += ["Result", "Rank", "Grade", "Remarks"]
        rows = []
        for row in stats["rows"]:
            values: list[Any] = [row["roll_no"], row["full_name"]]
            if active_components:
                values += [num(row[c[2]]) if row["status"] == "entered" else "—" for c in active_components]
                values += [
                    num(row["total"]) if row["total"] is not None else "—",
                    num(stats["max_marks"]),
                    pct(row["percentage"]),
                ]
            else:
                values += [
                    num(row["total"]) if row["total"] is not None else "—",
                    num(stats["max_marks"]),
                    pct(row["percentage"]),
                ]
            values += [
                self._result_label(row),
                dash(row["rank"]),
                self._grade(row["percentage"], rules),
                row["remarks"] or "",
            ]
            rows.append(values)
        doc = self._base_document(
            "marksheet",
            f"Examination Marksheet — {exam['name']}",
            f"{self.settings.subject} • Class {exam['class_name']} • {exam['exam_type']}",
            self._meta(
                int(exam["session_id"]),
                exam["class_name"],
                date_utils.display_long(exam["exam_date"]) if exam["exam_date"] else "Date not set",
                [("Examination", exam["name"]), ("Maximum marks", num(exam["max_marks"]))],
            ),
        )
        doc.filename_stem = f"marksheet_class{exam['class_name']}_{exam['id']}"
        doc.landscape = len(headers) > 7
        doc.summary = [
            ("Students", str(stats["students"])),
            ("Marks entered", str(stats["entered"])),
            ("Passed", str(stats["passed"])),
            ("Failed", str(stats["failed"])),
            ("Absent", str(stats["absent"])),
            ("Pending", str(stats["pending"])),
            ("Pass %", pct(stats["pass_percentage"])),
            ("Average %", pct(stats["average_percentage"])),
        ]
        widths = [45, 190] + [55] * (len(headers) - 2)
        doc.tables = [
            ReportTable(
                headers=headers,
                rows=rows,
                widths=widths,
                align=["left", "left"] + ["center"] * (len(headers) - 2),
                empty_message="No students are enrolled in this class for this examination.",
            )
        ]
        doc.notes = [
            f"Maximum marks: {num(exam['max_marks'])}. {self._pass_text(exam)}.",
            "A missing mark is shown as Pending/— and is never converted to zero.",
            "Rank is calculated within this examination and class using entered marks only. "
            "Tied marks share a rank and the next rank is skipped (1, 2, 2, 4).",
            "Grades use the teacher-configured scale in Settings; this is not an official SEBA grading policy.",
            "Pass % = passed ÷ (passed + failed + absent); exempted and pending results are excluded.",
        ]
        return doc

    # ------------------------------------------------------- 6. student progress
    def student_progress(self, student_id: int, start: str, end: str) -> ReportDocument:
        student = self._student(student_id)
        performance = self.analytics.student_performance(student_id, start, end)
        history = [
            h for h in performance["history"]
            if not h["exam_date"] or start <= h["exam_date"] <= end
        ]
        rules = self.settings.grade_rules()
        doc = self._base_document(
            "student_progress",
            "Individual Student Progress Report",
            f"{student['full_name']} • Class {student['class_name']} • {self._period(start, end)}",
            self._meta(
                student["session_id"],
                student["class_name"],
                self._period(start, end),
                [
                    ("Student", student["full_name"]),
                    ("Roll number", student["roll_no"]),
                    ("Section", student["section"] or "—"),
                ],
            ),
        )
        doc.filename_stem = f"progress_{student['roll_no']}_{start}_{end}"
        attendance = performance["attendance"]
        doc.summary = [
            ("Examinations", str(len([h for h in history if h["total"] is not None]))),
            ("Average marks %", pct(performance["average_percentage"])),
            ("Attendance %", pct(attendance["percentage"])),
            ("Present", str(attendance["present"])),
            ("Absent", str(attendance["absent"])),
            ("Leave", str(attendance["leave"])),
        ]
        doc.tables = [
            ReportTable(
                headers=["Examination", "Date", "Max", "Obtained", "%", "Result", "Grade"],
                rows=[
                    [
                        h["name"],
                        date_utils.display(h["exam_date"]),
                        num(h["max_marks"]),
                        num(h["total"]) if h["total"] is not None else "—",
                        pct(h["percentage"]),
                        self._result_label(h),
                        self._grade(h["percentage"], rules),
                    ]
                    for h in history
                ],
                widths=[190, 75, 50, 65, 60, 70, 60],
                align=["left", "center", "center", "center", "center", "center", "center"],
                empty_message="No examinations were recorded for this student in the selected period.",
            )
        ]
        weak = [
            h for h in history
            if h["percentage"] is not None and h["percentage"] < self.settings.performance_threshold
        ]
        if weak:
            doc.notes.append(
                "Areas needing improvement (below the configured performance threshold "
                f"of {self.settings.performance_threshold:g}%): "
                + ", ".join(f"{h['name']} ({pct(h['percentage'])})" for h in weak)
                + "."
            )
        if attendance["percentage"] is not None and attendance["percentage"] < self.settings.attendance_threshold:
            doc.notes.append(
                f"Attendance is below the configured threshold of {self.settings.attendance_threshold:g}%."
            )
        if not weak and (attendance["percentage"] is None or attendance["percentage"] >= self.settings.attendance_threshold):
            doc.notes.append("No threshold breaches were detected in this period.")
        doc.notes.append(self._leave_note())
        return doc

    # ------------------------------------------------------- 7. class performance
    def class_performance(
        self, session_id: int, class_name: str, start: str, end: str
    ) -> ReportDocument:
        summary = self.analytics.performance_summary(session_id, class_name, start, end)
        exams = [
            e for e in self.marks.list_examinations(session_id, class_name)
            if not e["exam_date"] or start <= e["exam_date"] <= end
        ]
        exam_rows = []
        for exam in exams:
            stats = self.marks.class_statistics(int(exam["id"]))
            exam_rows.append(
                [
                    exam["name"],
                    dash(exam["exam_type"]),
                    date_utils.display(exam["exam_date"]),
                    num(exam["max_marks"]),
                    stats["entered"],
                    stats["passed"],
                    stats["failed"],
                    stats["absent"],
                    stats["pending"],
                    pct(stats["pass_percentage"]),
                    pct(stats["average_percentage"]),
                ]
            )
        students = summary["students"]
        doc = self._base_document(
            "class_performance",
            "Class Performance Report",
            f"{self.settings.subject} • Class {class_name} • {self._period(start, end)}",
            self._meta(session_id, class_name, self._period(start, end)),
        )
        doc.filename_stem = f"performance_class{class_name}_{start}_{end}"
        doc.landscape = True
        doc.summary = [
            ("Students", str(len(students))),
            ("Average marks %", pct(summary["marks"]["average_percentage"])),
            ("Pass %", pct(summary["marks"]["pass_percentage"])),
            ("Attendance %", pct(summary["attendance"]["percentage"])),
            ("Highest %", pct(summary["marks"]["highest_percentage"])),
            ("Lowest %", pct(summary["marks"]["lowest_percentage"])),
            ("Needs support", str(len(summary["support_students"]))),
        ]
        doc.tables = [
            ReportTable(
                title="Examination overview",
                headers=["Examination", "Type", "Date", "Max", "Entered", "Passed", "Failed", "Absent", "Pending", "Pass %", "Average %"],
                rows=exam_rows,
                widths=[150, 80, 55, 35, 45, 45, 45, 45, 45, 50, 55],
                align=["left", "left", "center"] + ["center"] * 8,
                empty_message="No examinations were recorded in this period.",
            ),
            ReportTable(
                title="Student performance",
                headers=["Roll", "Student name", "Exams", "Average %", "Attendance %", "Support"],
                rows=[
                    [
                        s["roll_no"], s["full_name"], s["exam_count"],
                        pct(s["average_percentage"]), pct(s["attendance_percentage"]),
                        "Yes — " + "; ".join(s["support_reasons"]) if s["needs_support"] else "No",
                    ]
                    for s in students
                ],
                widths=[45, 150, 45, 65, 75, 250],
                align=["left", "left", "center", "center", "center", "left"],
                empty_message="No active students in this class.",
            ),
        ]
        doc.notes = [
            "Average marks % is the mean of percentage scores across entered examinations.",
            "Pass % counts absentees as not passed; exempted and pending results are excluded.",
            self._leave_note(),
        ]
        return doc

    # ------------------------------------------------------ 8. support report
    def support_report(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> ReportDocument:
        summary = self.analytics.performance_summary(session_id, class_name, start, end)
        failures = []
        for exam in self.marks.list_examinations(session_id, class_name):
            if exam["exam_date"] and not (start <= exam["exam_date"] <= end):
                continue
            stats = self.marks.class_statistics(int(exam["id"]))
            threshold = calculations.effective_pass_marks(
                exam["max_marks"], exam["pass_marks"], exam["pass_percent"]
            )
            for row in stats["rows"]:
                if row["passed"] is False:
                    failures.append(
                        [
                            exam["name"],
                            dash(exam["exam_type"]),
                            row["roll_no"],
                            row["full_name"],
                            num(row["total"]),
                            num(exam["max_marks"]),
                            pct(row["percentage"]),
                            num(threshold) if threshold is not None else "—",
                        ]
                    )
        support = summary["support_students"]
        doc = self._base_document(
            "support_report",
            "Failed-Student and Academic-Support Report",
            f"{self.settings.subject} • {'Class ' + class_name if class_name else 'Classes 9 & 10'} • {self._period(start, end)}",
            self._meta(session_id, class_name, self._period(start, end)),
        )
        doc.filename_stem = f"support_{class_name or 'all'}_{start}_{end}"
        doc.landscape = True
        doc.summary = [
            ("Failed results", str(len(failures))),
            ("Students needing support", str(len(support))),
            ("Performance threshold", f"{self.settings.performance_threshold:g}%"),
            ("Attendance threshold", f"{self.settings.attendance_threshold:g}%"),
        ]
        doc.tables = [
            ReportTable(
                title="Failed results",
                headers=["Examination", "Type", "Roll", "Student name", "Obtained", "Max", "%", "Pass mark"],
                rows=failures,
                widths=[150, 80, 40, 150, 50, 40, 50, 55],
                align=["left", "left", "left", "left"] + ["center"] * 4,
                empty_message="No failed examination results were recorded in this period.",
            ),
            ReportTable(
                title="Academic support list",
                headers=["Roll", "Student name", "Class", "Average %", "Attendance %", "Reasons"],
                rows=[
                    [
                        s["roll_no"], s["full_name"], s["class_name"],
                        pct(s["average_percentage"]), pct(s["attendance_percentage"]),
                        "; ".join(s["support_reasons"]) or "Below configured threshold",
                    ]
                    for s in support
                ],
                widths=[40, 140, 40, 60, 70, 270],
                align=["left", "left", "center", "center", "center", "left"],
                empty_message="No student is below the configured support thresholds.",
            ),
        ]
        doc.notes = [
            "Support flags are calculated from actual saved marks and attendance only.",
            "A blank or pending exam is not counted as a failure.",
            self._leave_note(),
        ]
        return doc

    # ----------------------------------------------------- 9. below threshold
    def below_threshold(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> ReportDocument:
        summary = self.analytics.performance_summary(session_id, class_name, start, end)
        below = summary["below_attendance"]
        threshold = self.settings.attendance_threshold
        doc = self._base_document(
            "below_threshold",
            "Students Below Attendance Threshold",
            f"{self.settings.subject} • {'Class ' + class_name if class_name else 'Classes 9 & 10'} • {self._period(start, end)}",
            self._meta(session_id, class_name, self._period(start, end)),
        )
        doc.filename_stem = f"below_attendance_{class_name or 'all'}_{start}_{end}"
        doc.summary = [
            ("Threshold", f"{threshold:g}%"),
            ("Students below threshold", str(len(below))),
            ("Students evaluated", str(len(summary["students"]))),
        ]
        doc.tables = [
            ReportTable(
                headers=["Roll", "Student name", "Class", "Present", "Absent", "Leave", "Attendance %", "Shortfall"],
                rows=[
                    [
                        s["roll_no"], s["full_name"], s["class_name"], s["present"],
                        s["absent"], s["leave"], pct(s["attendance_percentage"]),
                        f"{max(0, threshold - (s['attendance_percentage'] or 0)):.2f} pp",
                    ]
                    for s in sorted(below, key=lambda r: r["attendance_percentage"])
                ],
                widths=[50, 180, 45, 55, 55, 55, 80, 75],
                align=["left", "left", "center"] + ["center"] * 5,
                empty_message="No student is below the configured attendance threshold.",
            )
        ]
        doc.notes = [
            f"Configured attendance threshold: {threshold:g}%. Change it in Settings.",
            "Only sessions with recorded attendance are counted.",
            self._leave_note(),
        ]
        return doc

    # -------------------------------------------------------- 10. session summary
    def session_summary(self, session_id: int, start: str, end: str) -> ReportDocument:
        session = self._session(session_id)
        comparison = self.analytics.class_comparison(session_id, start, end)
        counts = self.students.count_by_class(session_id)
        exams = self.marks.list_examinations(session_id)
        attendance = self.analytics._attendance_counts(session_id, None, start, end)
        doc = self._base_document(
            "session_summary",
            "Academic Session Summary",
            f"{self.settings.subject} • {session['name']} • {self._period(start, end)}",
            self._meta(session_id, None, self._period(start, end)),
        )
        doc.filename_stem = f"session_summary_{session['name'].replace('-', '_')}"
        doc.landscape = True
        doc.summary = [
            ("Class 9 students", str(counts["9"])),
            ("Class 10 students", str(counts["10"])),
            ("Attendance %", pct(attendance["percentage"])),
            ("Exam sessions", str(len(exams))),
        ]
        exam_rows = []
        for exam in exams:
            stats = self.marks.class_statistics(int(exam["id"]))
            exam_rows.append(
                [
                    exam["name"], exam["class_name"], dash(exam["exam_type"]),
                    date_utils.display(exam["exam_date"]), num(exam["max_marks"]),
                    stats["entered"], stats["passed"], stats["failed"], stats["absent"],
                    stats["pending"], pct(stats["pass_percentage"]), pct(stats["average_percentage"]),
                ]
            )
        doc.tables = [
            ReportTable(
                title="Class overview",
                headers=["Class", "Students", "Average marks %", "Pass %", "Attendance %"],
                rows=[
                    [
                        f"Class {c['class_name']}", c["students"], pct(c["average_percentage"]),
                        pct(c["pass_percentage"]), pct(c["attendance_percentage"]),
                    ]
                    for c in comparison
                ],
                widths=[80, 80, 120, 80, 100],
                align=["left"] + ["center"] * 4,
            ),
            ReportTable(
                title="Examinations",
                headers=["Examination", "Class", "Type", "Date", "Max", "Entered", "Passed", "Failed", "Absent", "Pending", "Pass %", "Average %"],
                rows=exam_rows,
                widths=[140, 45, 75, 55, 35, 45, 45, 45, 45, 45, 50, 55],
                align=["left", "center", "left", "center"] + ["center"] * 8,
                empty_message="No examinations have been created for this session.",
            ),
        ]
        monthly = self.analytics.monthly_trend(session_id, None, start, end)
        doc.tables.append(
            ReportTable(
                title="Attendance by month (all classes)",
                headers=["Month", "Sessions", "Present", "Absent", "Leave", "Attendance %"],
                rows=[
                    [
                        m["month"], m["sessions"], m["present"], m["absent"],
                        m["leave"], pct(m["percentage"]),
                    ]
                    for m in monthly
                ],
                widths=[80, 70, 70, 70, 70, 90],
                align=["left"] + ["center"] * 5,
                empty_message="No attendance has been recorded in this session.",
            )
        )
        doc.notes = [
            "All figures are calculated from records saved in the local database.",
            "Grades and pass criteria are teacher-configured, not an official SEBA policy.",
            self._leave_note(),
        ]
        return doc

    # ---------------------------------------------------------------- dispatch
    def build(self, key: str, **params: Any) -> ReportDocument:
        builders = {
            "daily_attendance": self.daily_attendance,
            "monthly_attendance": self.monthly_attendance,
            "student_attendance": self.student_attendance,
            "class_attendance": self.class_attendance,
            "marksheet": self.marksheet,
            "student_progress": self.student_progress,
            "class_performance": self.class_performance,
            "support_report": self.support_report,
            "below_threshold": self.below_threshold,
            "session_summary": self.session_summary,
        }
        if key not in builders:
            raise ValidationError(f"Unknown report type: {key}")
        return builders[key](**params)
