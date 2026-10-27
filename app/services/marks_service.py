"""Examinations, marks entry, ranking and result analytics."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from app.database import Database, utc_now
from app.services import calculations
from app.utils.validators import (
    ValidationError,
    clean_text,
    validate_examination,
)


class MarksService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------ examinations
    def list_examinations(
        self, session_id: int, class_name: str | None = None
    ) -> list[Any]:
        sql = (
            "SELECT e.*, "
            "(SELECT COUNT(*) FROM marks m WHERE m.examination_id = e.id) AS record_count "
            "FROM examinations e WHERE e.session_id = ?"
        )
        params: list[Any] = [int(session_id)]
        if class_name in ("9", "10"):
            sql += " AND e.class_name = ?"
            params.append(class_name)
        sql += " ORDER BY COALESCE(e.exam_date, ''), e.id"
        return self.db.query(sql, params)

    def get_examination(self, exam_id: int) -> Any:
        return self.db.query_one("SELECT * FROM examinations WHERE id = ?", (int(exam_id),))

    def create_examination(self, data: Mapping[str, Any]) -> int:
        values = validate_examination(data)
        try:
            cursor = self.db.execute(
                "INSERT INTO examinations (name, exam_type, class_name, session_id, subject,"
                " exam_date, max_marks, pass_marks, pass_percent, theory_max, practical_max,"
                " project_max, remarks, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    values["name"], values["exam_type"], values["class_name"],
                    values["session_id"], values["subject"], values["exam_date"],
                    values["max_marks"], values["pass_marks"], values["pass_percent"],
                    values["theory_max"], values["practical_max"], values["project_max"],
                    values["remarks"], utc_now(), utc_now(),
                ),
            )
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
        exam_id = int(cursor.lastrowid)
        self.db.log_activity(
            "create", "examination", exam_id,
            f"{values['name']} — Class {values['class_name']} ({values['max_marks']:g} marks)",
        )
        return exam_id

    def update_examination(self, exam_id: int, data: Mapping[str, Any]) -> None:
        if self.get_examination(exam_id) is None:
            raise ValidationError("This examination no longer exists.")
        values = validate_examination(data)
        try:
            self.db.execute(
                "UPDATE examinations SET name = ?, exam_type = ?, class_name = ?, session_id = ?,"
                " subject = ?, exam_date = ?, max_marks = ?, pass_marks = ?, pass_percent = ?,"
                " theory_max = ?, practical_max = ?, project_max = ?, remarks = ?, updated_at = ?"
                " WHERE id = ?",
                (
                    values["name"], values["exam_type"], values["class_name"],
                    values["session_id"], values["subject"], values["exam_date"],
                    values["max_marks"], values["pass_marks"], values["pass_percent"],
                    values["theory_max"], values["practical_max"], values["project_max"],
                    values["remarks"], utc_now(), int(exam_id),
                ),
            )
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
        self.db.log_activity("update", "examination", exam_id, values["name"])

    def delete_examination(self, exam_id: int) -> None:
        exam = self.get_examination(exam_id)
        if exam is None:
            raise ValidationError("This examination no longer exists.")
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM marks WHERE examination_id = ?", (int(exam_id),))
            conn.execute("DELETE FROM examinations WHERE id = ?", (int(exam_id),))
        self.db.log_activity("delete", "examination", exam_id, exam["name"])

    # ------------------------------------------------------------------ entry
    def exam_roster(self, exam_id: int) -> list[dict[str, Any]]:
        exam = self.get_examination(exam_id)
        if exam is None:
            raise ValidationError("This examination no longer exists.")
        rows = self.db.query(
            "SELECT s.id AS student_id, s.roll_no, s.full_name, s.section,"
            "m.id AS mark_id, m.theory, m.practical, m.project, m.total, m.status, m.remarks "
            "FROM students s LEFT JOIN marks m ON m.student_id = s.id AND m.examination_id = ? "
            "WHERE s.session_id = ? AND s.class_name = ? "
            "AND (s.status = 'active' OR m.id IS NOT NULL) "
            "ORDER BY CAST(s.roll_no AS INTEGER), s.roll_no",
            (int(exam_id), int(exam["session_id"]), exam["class_name"]),
        )
        result = []
        for row in rows:
            result.append(
                {
                    "student_id": int(row["student_id"]),
                    "roll_no": row["roll_no"],
                    "full_name": row["full_name"],
                    "section": row["section"] or "",
                    "mark_id": row["mark_id"],
                    "theory": row["theory"],
                    "practical": row["practical"],
                    "project": row["project"],
                    "total": row["total"],
                    "status": row["status"] or "pending",
                    "remarks": row["remarks"] or "",
                }
            )
        return result

    def save_marks(
        self, exam_id: int, entries: Iterable[Mapping[str, Any]], allow_pending: bool = True
    ) -> dict[str, int]:
        exam = self.get_examination(exam_id)
        if exam is None:
            raise ValidationError("This examination no longer exists.")
        max_marks = float(exam["max_marks"])
        theory_max = exam["theory_max"]
        practical_max = exam["practical_max"]
        project_max = exam["project_max"]
        has_components = any(v is not None for v in (theory_max, practical_max, project_max))
        roster_ids = {int(row["student_id"]) for row in self.exam_roster(exam_id)}
        now = utc_now()
        prepared: list[tuple[int, Any, Any, Any, Any, str, str]] = []
        errors: list[str] = []
        counts = {"entered": 0, "absent": 0, "exempted": 0, "pending": 0}

        def is_blank(value: Any) -> bool:
            return value is None or (isinstance(value, str) and not value.strip())

        def number(value: Any, label: str, field: str) -> float | None:
            if is_blank(value):
                return None
            try:
                return float(str(value).strip())
            except (TypeError, ValueError):
                errors.append(f"{label}: {field} must be a number.")
                return None

        for entry in entries:
            try:
                student_id = int(entry.get("student_id"))
            except (TypeError, ValueError):
                errors.append("A row has an invalid student reference.")
                continue
            if student_id not in roster_ids:
                continue
            status = str(entry.get("status") or "pending").lower()
            if status not in ("pending", "entered", "absent", "exempted"):
                errors.append(f"Student {student_id}: invalid status '{status}'.")
                continue
            remarks = clean_text(entry.get("remarks"), 200)
            label = f"Roll {entry.get('roll_no', student_id)}"

            if status != "entered":
                if status == "pending" and not allow_pending:
                    continue
                prepared.append((student_id, None, None, None, None, status, remarks))
                counts[status] += 1
                continue

            theory_v: float | None = None
            practical_v: float | None = None
            project_v: float | None = None

            if has_components:
                component_fields = (
                    ("theory", "theory marks", theory_max),
                    ("practical", "practical marks", practical_max),
                    ("project", "project marks", project_max),
                )
                values: dict[str, float] = {}
                failed = False
                for key, name, maximum in component_fields:
                    if maximum is None:
                        continue
                    raw = entry.get(key)
                    parsed = number(raw, label, name)
                    if is_blank(raw):
                        errors.append(f"{label}: enter {name} or mark Absent/Exempted.")
                        failed = True
                    elif parsed is None:
                        failed = True
                    elif parsed < 0 or parsed > float(maximum) + 1e-9:
                        errors.append(
                            f"{label}: {name} must be between 0 and {float(maximum):g}."
                        )
                        failed = True
                    else:
                        values[key] = parsed
                if failed:
                    continue
                theory_v = values.get("theory")
                practical_v = values.get("practical")
                project_v = values.get("project")
                total_v: float | None = round(sum(values.values()), 2)
            else:
                raw_total = entry.get("total")
                total_v = number(raw_total, label, "marks")
                if is_blank(raw_total):
                    errors.append(f"{label}: enter marks between 0 and {max_marks:g}.")
                    continue
                if total_v is None:
                    continue
                if total_v < 0 or total_v > max_marks + 1e-9:
                    errors.append(f"{label}: marks must be between 0 and {max_marks:g}.")
                    continue
                total_v = round(total_v, 2)

            if total_v is not None and (total_v < 0 or total_v > max_marks + 1e-9):
                errors.append(f"{label}: total marks must be between 0 and {max_marks:g}.")
                continue
            prepared.append(
                (student_id, theory_v, practical_v, project_v, total_v, status, remarks)
            )
            counts["entered"] += 1

        if errors:
            unique_errors = list(dict.fromkeys(errors))
            raise ValidationError(
                "Some marks could not be saved:\n• " + "\n• ".join(unique_errors[:12]),
                {"rows": " ".join(unique_errors[:12])},
            )
        if not prepared:
            raise ValidationError("There are no marks to save.")

        with self.db.transaction() as conn:
            for row in prepared:
                student_id, theory_v, practical_v, project_v, total_v, status, remarks = row
                conn.execute(
                    "INSERT INTO marks (examination_id, student_id, theory, practical, project,"
                    " total, status, remarks, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(examination_id, student_id) DO UPDATE SET"
                    " theory = excluded.theory, practical = excluded.practical,"
                    " project = excluded.project, total = excluded.total,"
                    " status = excluded.status, remarks = excluded.remarks,"
                    " updated_at = excluded.updated_at",
                    (
                        int(exam_id), student_id, theory_v, practical_v, project_v,
                        total_v, status, remarks or None, now, now,
                    ),
                )
        self.db.log_activity(
            "save", "marks", exam_id,
            f"{exam['name']} — Class {exam['class_name']}: {counts['entered']} entered, "
            f"{counts['absent']} absent, {counts['exempted']} exempted, {counts['pending']} pending",
        )
        return counts

    # ---------------------------------------------------------------- results
    def result_rows(self, exam_id: int) -> list[dict[str, Any]]:
        exam = self.get_examination(exam_id)
        if exam is None:
            raise ValidationError("This examination no longer exists.")
        rows = self.exam_roster(exam_id)
        totals = {
            row["student_id"]: row["total"]
            for row in rows
            if row["status"] == "entered" and row["total"] is not None
        }
        ranks = calculations.competition_ranks(totals, descending=True)
        result = []
        for row in rows:
            total = row["total"] if row["status"] == "entered" else None
            pct = calculations.percentage(total, exam["max_marks"])
            passed = (
                calculations.is_pass(
                    total, exam["max_marks"], exam["pass_marks"], exam["pass_percent"]
                )
                if row["status"] == "entered"
                else None
            )
            result.append(
                {
                    **row,
                    "total": total,
                    "percentage": pct,
                    "passed": passed,
                    "rank": ranks.get(row["student_id"]),
                }
            )
        return result

    def class_statistics(self, exam_id: int) -> dict[str, Any]:
        exam = self.get_examination(exam_id)
        if exam is None:
            raise ValidationError("This examination no longer exists.")
        rows = self.result_rows(exam_id)
        entered = [r for r in rows if r["status"] == "entered" and r["total"] is not None]
        absent = [r for r in rows if r["status"] == "absent"]
        exempted = [r for r in rows if r["status"] == "exempted"]
        pending = [
            r for r in rows
            if r["status"] == "pending"
            or (r["status"] == "entered" and r["total"] is None)
        ]
        passed = [r for r in entered if r["passed"]]
        failed = [r for r in entered if r["passed"] is False]
        summary = calculations.summarize([r["total"] for r in entered])
        percent_summary = calculations.summarize([r["percentage"] for r in entered])
        graded_total = len(passed) + len(failed) + len(absent)
        return {
            "exam": exam,
            "students": len(rows),
            "entered": len(entered),
            "absent": len(absent),
            "exempted": len(exempted),
            "pending": len(pending),
            "passed": len(passed),
            "failed": len(failed),
            "pass_percentage": calculations.rate(len(passed), graded_total),
            "highest": summary["highest"],
            "lowest": summary["lowest"],
            "average": summary["average"],
            "median": summary["median"],
            "average_percentage": percent_summary["average"],
            "max_marks": float(exam["max_marks"]),
            "rows": rows,
        }

    def student_history(self, student_id: int) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT e.*, m.total, m.status AS mark_status, m.theory, m.practical, m.project "
            "FROM examinations e LEFT JOIN marks m ON m.examination_id = e.id AND m.student_id = ? "
            "WHERE e.class_name = (SELECT class_name FROM students WHERE id = ?) "
            "AND e.session_id = (SELECT session_id FROM students WHERE id = ?) "
            "ORDER BY COALESCE(e.exam_date, ''), e.id",
            (int(student_id), int(student_id), int(student_id)),
        )
        result = []
        for row in rows:
            total = row["total"] if row["mark_status"] == "entered" else None
            pct = calculations.percentage(total, row["max_marks"])
            result.append(
                {
                    "exam_id": int(row["id"]),
                    "name": row["name"],
                    "exam_type": row["exam_type"],
                    "exam_date": row["exam_date"],
                    "max_marks": float(row["max_marks"]),
                    "total": total,
                    "percentage": pct,
                    "status": row["mark_status"] or "pending",
                    "passed": (
                        calculations.is_pass(
                            total, row["max_marks"], row["pass_marks"], row["pass_percent"]
                        )
                        if total is not None
                        else None
                    ),
                }
            )
        return result

    def exams_for_class(self, session_id: int, class_name: str) -> list[Any]:
        return self.list_examinations(session_id, class_name)

    def exam_pending_count(self, exam_id: int) -> int:
        exam = self.get_examination(exam_id)
        if exam is None:
            return 0
        active = int(
            self.db.scalar(
                "SELECT COUNT(*) FROM students WHERE session_id = ? AND class_name = ?"
                " AND status = 'active'",
                (int(exam["session_id"]), exam["class_name"]),
                default=0,
            )
        )
        entered = int(
            self.db.scalar(
                "SELECT COUNT(*) FROM marks WHERE examination_id = ?"
                " AND status IN ('entered', 'absent', 'exempted')",
                (int(exam_id),),
                default=0,
            )
        )
        return max(0, active - entered)

    # ----------------------------------------------------------------- import
    def validate_import_rows(
        self, exam_id: int, rows: Iterable[Mapping[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        exam = self.get_examination(exam_id)
        if exam is None:
            raise ValidationError("This examination no longer exists.")
        roster = {str(r["roll_no"]).upper(): r for r in self.exam_roster(exam_id)}
        valid: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, raw in enumerate(rows, start=2):
            data = {str(k).strip().lower(): v for k, v in dict(raw).items()}
            roll = clean_text(data.get("roll_no") or data.get("roll") or "")
            if not roll:
                errors.append({"row": index, "message": "Roll number is required."})
                continue
            student = roster.get(roll.upper())
            if not student:
                errors.append(
                    {"row": index, "message": f"Roll {roll} is not in this examination's class."}
                )
                continue
            if roll.upper() in seen:
                errors.append({"row": index, "message": f"Roll {roll} appears more than once."})
                continue
            seen.add(roll.upper())
            status_raw = clean_text(data.get("status") or "entered").lower()
            status = {
                "present": "entered",
                "p": "entered",
                "absent": "absent",
                "a": "absent",
                "exempted": "exempted",
                "e": "exempted",
                "pending": "pending",
            }.get(status_raw, status_raw)
            entry = {
                "student_id": student["student_id"],
                "roll_no": student["roll_no"],
                "status": status,
                "theory": data.get("theory"),
                "practical": data.get("practical"),
                "project": data.get("project"),
                "total": data.get("total") or data.get("marks"),
                "remarks": data.get("remarks"),
            }
            valid.append(entry)
        return valid, errors

    def import_marks(
        self, exam_id: int, rows: Iterable[Mapping[str, Any]], skip_invalid: bool = True
    ) -> dict[str, Any]:
        valid, errors = self.validate_import_rows(exam_id, rows)
        if errors and not skip_invalid:
            return {"saved": 0, "errors": errors, "cancelled": True}
        if not valid:
            return {"saved": 0, "errors": errors}
        try:
            counts = self.save_marks(exam_id, valid)
        except ValidationError as exc:
            return {"saved": 0, "errors": errors + [{"row": 0, "message": str(exc)}]}
        return {"saved": sum(counts.values()), "errors": errors, "counts": counts}
