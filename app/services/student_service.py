"""Student records: CRUD, search, filtering, archival and import."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from app.database import Database, utc_now
from app.services import calculations
from app.utils.validators import (
    ValidationError,
    clean_text,
    normalize_roll,
    validate_student,
)

SORT_COLUMNS = {
    "roll_no": "CAST(s.roll_no AS INTEGER), s.roll_no",
    "full_name": "s.full_name COLLATE NOCASE",
    "class_name": "s.class_name",
    "section": "s.section",
    "status": "s.status",
    "created_at": "s.created_at",
}


class StudentService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ read
    def list_students(
        self,
        session_id: int,
        class_name: str | None = None,
        section: str | None = None,
        search: str = "",
        status: str = "active",
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "roll_no",
        sort_dir: str = "asc",
    ) -> tuple[list[Any], int]:
        where = ["s.session_id = ?"]
        params: list[Any] = [int(session_id)]
        if class_name in ("9", "10"):
            where.append("s.class_name = ?")
            params.append(class_name)
        if section:
            where.append("s.section = ?")
            params.append(section)
        if status and status != "all":
            where.append("s.status = ?")
            params.append(status)
        else:
            where.append("s.status != 'archived'")
        search = clean_text(search)
        if search:
            where.append(
                "(s.full_name LIKE ? COLLATE NOCASE OR s.roll_no LIKE ? COLLATE NOCASE "
                "OR COALESCE(s.guardian_name,'') LIKE ? COLLATE NOCASE)"
            )
            term = f"%{search}%"
            params.extend([term, term, term])
        clause = " AND ".join(where)
        order = SORT_COLUMNS.get(sort_by, SORT_COLUMNS["roll_no"])
        direction = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
        total = int(
            self.db.scalar(f"SELECT COUNT(*) FROM students s WHERE {clause}", params, default=0)
        )
        page_size = max(1, min(int(page_size), 500))
        page = max(1, int(page))
        offset = (page - 1) * page_size
        rows = self.db.query(
            f"SELECT s.*, ses.name AS session_name FROM students s "
            f"JOIN academic_sessions ses ON ses.id = s.session_id "
            f"WHERE {clause} ORDER BY {order} {direction} LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )
        return rows, total

    def all_students(
        self,
        session_id: int,
        class_name: str | None = None,
        status: str = "active",
    ) -> list[Any]:
        where = ["s.session_id = ?"]
        params: list[Any] = [int(session_id)]
        if class_name in ("9", "10"):
            where.append("s.class_name = ?")
            params.append(class_name)
        if status == "all":
            where.append("s.status != 'archived'")
        else:
            where.append("s.status = ?")
            params.append(status)
        return self.db.query(
            "SELECT s.* FROM students s WHERE " + " AND ".join(where) +
            " ORDER BY s.class_name, CAST(s.roll_no AS INTEGER), s.roll_no",
            params,
        )

    def get(self, student_id: int) -> Any:
        return self.db.query_one(
            "SELECT s.*, ses.name AS session_name FROM students s "
            "JOIN academic_sessions ses ON ses.id = s.session_id WHERE s.id = ?",
            (int(student_id),),
        )

    def count_by_class(self, session_id: int, status: str = "active") -> dict[str, int]:
        rows = self.db.query(
            "SELECT class_name, COUNT(*) AS total FROM students "
            "WHERE session_id = ? AND status = ? GROUP BY class_name",
            (int(session_id), status),
        )
        counts = {"9": 0, "10": 0}
        for row in rows:
            counts[row["class_name"]] = int(row["total"])
        return counts

    def sections(self, session_id: int, class_name: str | None = None) -> list[str]:
        sql = (
            "SELECT DISTINCT section FROM students WHERE session_id = ? "
            "AND status = 'active' AND section <> ''"
        )
        params: list[Any] = [int(session_id)]
        if class_name in ("9", "10"):
            sql += " AND class_name = ?"
            params.append(class_name)
        sql += " ORDER BY section"
        return [row["section"] for row in self.db.query(sql, params)]

    def roll_exists(
        self, session_id: int, class_name: str, roll_no: str, exclude_id: int | None = None
    ) -> bool:
        sql = (
            "SELECT COUNT(*) FROM students WHERE session_id = ? AND class_name = ? "
            "AND UPPER(roll_no) = UPPER(?)"
        )
        params: list[Any] = [int(session_id), class_name, normalize_roll(roll_no)]
        if exclude_id is not None:
            sql += " AND id <> ?"
            params.append(int(exclude_id))
        return int(self.db.scalar(sql, params, default=0)) > 0

    # ----------------------------------------------------------------- write
    def create(self, data: Mapping[str, Any]) -> int:
        values = validate_student(data)
        if self.roll_exists(values["session_id"], values["class_name"], values["roll_no"]):
            raise ValidationError(
                f"Roll number {values['roll_no']} already exists in Class "
                f"{values['class_name']} for this academic session.",
                {"roll_no": "Duplicate roll number for this class and session."},
            )
        now = utc_now()
        try:
            cursor = self.db.execute(
                "INSERT INTO students (roll_no, full_name, class_name, section, session_id,"
                " guardian_name, contact_no, admission_date, status, remarks, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    values["roll_no"],
                    values["full_name"],
                    values["class_name"],
                    values["section"],
                    values["session_id"],
                    values["guardian_name"],
                    values["contact_no"],
                    values["admission_date"],
                    values["status"],
                    values["remarks"],
                    now,
                    now,
                ),
            )
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
        student_id = int(cursor.lastrowid)
        self.db.log_activity(
            "create", "student", student_id,
            f"{values['full_name']} (Class {values['class_name']}, Roll {values['roll_no']})",
        )
        return student_id

    def update(self, student_id: int, data: Mapping[str, Any]) -> None:
        existing = self.get(student_id)
        if existing is None:
            raise ValidationError("This student no longer exists.")
        values = validate_student(data)
        if self.roll_exists(
            values["session_id"], values["class_name"], values["roll_no"], exclude_id=student_id
        ):
            raise ValidationError(
                f"Roll number {values['roll_no']} already exists in Class "
                f"{values['class_name']} for this academic session.",
                {"roll_no": "Duplicate roll number for this class and session."},
            )
        try:
            self.db.execute(
                "UPDATE students SET roll_no = ?, full_name = ?, class_name = ?, section = ?,"
                " session_id = ?, guardian_name = ?, contact_no = ?, admission_date = ?,"
                " status = ?, remarks = ?, updated_at = ? WHERE id = ?",
                (
                    values["roll_no"],
                    values["full_name"],
                    values["class_name"],
                    values["section"],
                    values["session_id"],
                    values["guardian_name"],
                    values["contact_no"],
                    values["admission_date"],
                    values["status"],
                    values["remarks"],
                    utc_now(),
                    int(student_id),
                ),
            )
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
        self.db.log_activity(
            "update", "student", student_id, f"{values['full_name']} (Roll {values['roll_no']})"
        )

    def set_status(self, student_id: int, status: str) -> None:
        if status not in ("active", "inactive", "archived"):
            raise ValidationError("Invalid student status.")
        student = self.get(student_id)
        if student is None:
            raise ValidationError("This student no longer exists.")
        self.db.execute(
            "UPDATE students SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), int(student_id)),
        )
        self.db.log_activity(status, "student", student_id, student["full_name"])

    def archive(self, student_id: int) -> None:
        self.set_status(student_id, "archived")

    def restore(self, student_id: int) -> None:
        self.set_status(student_id, "active")

    def record_counts(self, student_id: int) -> dict[str, int]:
        return {
            "attendance": int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM attendance WHERE student_id = ?",
                    (int(student_id),),
                    default=0,
                )
            ),
            "marks": int(
                self.db.scalar(
                    "SELECT COUNT(*) FROM marks WHERE student_id = ?",
                    (int(student_id),),
                    default=0,
                )
            ),
        }

    def delete_permanently(self, student_id: int) -> None:
        student = self.get(student_id)
        if student is None:
            raise ValidationError("This student no longer exists.")
        counts = self.record_counts(student_id)
        if counts["attendance"] or counts["marks"]:
            raise ValidationError(
                "This student has attendance or marks records and cannot be deleted "
                "permanently. Archive the student instead to preserve data integrity."
            )
        self.db.execute("DELETE FROM students WHERE id = ?", (int(student_id),))
        self.db.log_activity("delete", "student", student_id, student["full_name"])

    # ---------------------------------------------------------------- import
    def validate_import_rows(
        self, session_id: int, rows: Iterable[Mapping[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Validate import rows without writing anything.

        Returns (valid_rows, errors). Each error carries row number + message.
        """
        valid: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        if not rows:
            return valid, [{"row": 0, "message": "The file contains no data rows."}]
        for index, raw in enumerate(rows, start=2):  # header occupies row 1
            data = dict(raw)
            data["session_id"] = session_id
            try:
                values = validate_student(data)
            except ValidationError as exc:
                errors.append({"row": index, "message": str(exc), "fields": exc.errors})
                continue
            key = (values["class_name"], normalize_roll(values["roll_no"]).upper())
            if key in seen:
                errors.append(
                    {"row": index, "message": "Duplicate roll number inside the import file."}
                )
                continue
            if self.roll_exists(values["session_id"], values["class_name"], values["roll_no"]):
                errors.append(
                    {
                        "row": index,
                        "message": (
                            f"Roll {values['roll_no']} already exists in Class "
                            f"{values['class_name']} for this session."
                        ),
                    }
                )
                continue
            seen.add(key)
            values["_row"] = index
            valid.append(values)
        return valid, errors

    def import_students(
        self, session_id: int, rows: Iterable[Mapping[str, Any]], skip_invalid: bool = True
    ) -> dict[str, Any]:
        valid, errors = self.validate_import_rows(session_id, rows)
        if errors and not skip_invalid:
            return {"imported": 0, "errors": errors, "cancelled": True}
        if not valid:
            return {"imported": 0, "errors": errors}
        now = utc_now()
        with self.db.transaction() as conn:
            for values in valid:
                conn.execute(
                    "INSERT INTO students (roll_no, full_name, class_name, section, session_id,"
                    " guardian_name, contact_no, admission_date, status, remarks, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        values["roll_no"],
                        values["full_name"],
                        values["class_name"],
                        values["section"],
                        values["session_id"],
                        values["guardian_name"],
                        values["contact_no"],
                        values["admission_date"],
                        values["status"],
                        values["remarks"],
                        now,
                        now,
                    ),
                )
        self.db.log_activity(
            "import", "student", None, f"{len(valid)} students imported from file"
        )
        return {"imported": len(valid), "errors": errors}

    # ---------------------------------------------------------------- helpers
    def attendance_snapshot(self, student_id: int, exclude_leave: bool = True) -> dict[str, Any]:
        row = self.db.query_one(
            "SELECT "
            "SUM(CASE WHEN status = 'P' THEN 1 ELSE 0 END) AS present,"
            "SUM(CASE WHEN status = 'A' THEN 1 ELSE 0 END) AS absent,"
            "SUM(CASE WHEN status = 'L' THEN 1 ELSE 0 END) AS leave_count "
            "FROM attendance WHERE student_id = ?",
            (int(student_id),),
        )
        present = int(row["present"] or 0) if row else 0
        absent = int(row["absent"] or 0) if row else 0
        leave = int(row["leave_count"] or 0) if row else 0
        return {
            "present": present,
            "absent": absent,
            "leave": leave,
            "percentage": calculations.attendance_percentage(
                present, absent, leave, exclude_leave
            ),
        }
