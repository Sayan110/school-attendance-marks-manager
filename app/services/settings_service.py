"""Application settings and academic session management."""
from __future__ import annotations

from typing import Any, Iterable

from app import config
from app.database import Database, utc_now
from app.utils.validators import ValidationError, clean_text, parse_iso_date


class SettingsService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._cache: dict[str, str] = {}
        self._loaded = False

    # ---------------------------------------------------------------- values
    def _load(self) -> None:
        if self._loaded:
            return
        rows = self.db.query("SELECT key, value FROM app_settings")
        self._cache = {row["key"]: row["value"] for row in rows}
        self._loaded = True

    def get(self, key: str, default: str | None = None) -> str:
        self._load()
        if key in self._cache:
            return self._cache[key]
        if default is not None:
            return default
        return config.DEFAULT_SETTINGS.get(key, "")

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(float(self.get(key, str(default))))
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.get(key, str(default)))
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, "1" if default else "0").strip().lower()
        return value in ("1", "true", "yes", "on")

    def set(self, key: str, value: Any) -> None:
        text = "" if value is None else str(value)
        self.db.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
            " updated_at = excluded.updated_at",
            (key, text, utc_now()),
        )
        self._cache[key] = text

    def set_many(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            self.set(key, value)

    def reload(self) -> None:
        """Drop the in-memory cache, e.g. after restoring a backup."""
        self._cache = {}
        self._loaded = False

    # -------------------------------------------------------------- shortcuts
    @property
    def school_name(self) -> str:
        return self.get("school_name", config.SCHOOL_NAME).strip() or config.SCHOOL_NAME

    @property
    def teacher_name(self) -> str:
        return self.get("teacher_name", "").strip()

    @property
    def subject(self) -> str:
        return self.get("subject", config.DEFAULT_SUBJECT).strip() or config.DEFAULT_SUBJECT

    @property
    def board(self) -> str:
        return self.get("board", config.SCHOOL_BOARD)

    @property
    def attendance_threshold(self) -> float:
        return self.get_float("attendance_threshold", 75.0)

    @property
    def performance_threshold(self) -> float:
        return self.get_float("performance_threshold", 33.0)

    @property
    def leave_excluded(self) -> bool:
        return self.get_bool("leave_excluded_from_percentage", True)

    @property
    def theme(self) -> str:
        return self.get("theme", "light")

    @property
    def auto_backup_days(self) -> int:
        return self.get_int("auto_backup_days", 7)

    @property
    def backup_retention(self) -> int:
        return max(1, self.get_int("backup_retention", 20))

    # ---------------------------------------------------------------- sessions
    def sessions(self) -> list[Any]:
        return self.db.query(
            "SELECT * FROM academic_sessions ORDER BY name DESC"
        )

    def session_names(self) -> list[str]:
        return [row["name"] for row in self.sessions()]

    def get_session(self, session_id: int | None) -> Any:
        if not session_id:
            return None
        return self.db.query_one(
            "SELECT * FROM academic_sessions WHERE id = ?", (int(session_id),)
        )

    def active_session_id(self) -> int | None:
        value = self.get("active_session_id", "")
        if value:
            try:
                session_id = int(value)
                if self.get_session(session_id):
                    return session_id
            except ValueError:
                pass
        row = self.db.query_one(
            "SELECT id FROM academic_sessions ORDER BY is_active DESC, name DESC LIMIT 1"
        )
        return int(row["id"]) if row else None

    def active_session_name(self) -> str:
        session = self.get_session(self.active_session_id())
        return session["name"] if session else config.DEFAULT_SESSION

    def set_active_session(self, session_id: int) -> None:
        if self.get_session(session_id) is None:
            raise ValidationError("That academic session no longer exists.")
        self.db.execute("UPDATE academic_sessions SET is_active = 0")
        self.db.execute(
            "UPDATE academic_sessions SET is_active = 1 WHERE id = ?", (int(session_id),)
        )
        self.set("active_session_id", int(session_id))

    def add_session(self, name: str, start_date: str = "", end_date: str = "") -> int:
        name = clean_text(name, 20)
        if not name:
            raise ValidationError("Academic session name is required.")
        start = parse_iso_date(start_date) if start_date else None
        end = parse_iso_date(end_date) if end_date else None
        if start and end and end < start:
            raise ValidationError("Session end date cannot be before the start date.")
        try:
            cursor = self.db.execute(
                "INSERT INTO academic_sessions (name, start_date, end_date, is_active, created_at)"
                " VALUES (?, ?, ?, 0, ?)",
                (name, start.isoformat() if start else None, end.isoformat() if end else None, utc_now()),
            )
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
        new_id = int(cursor.lastrowid)
        self.db.log_activity("create", "academic_session", new_id, name)
        return new_id

    def update_session(self, session_id: int, name: str, start_date: str, end_date: str) -> None:
        name = clean_text(name, 20)
        if not name:
            raise ValidationError("Academic session name is required.")
        start = parse_iso_date(start_date) if start_date else None
        end = parse_iso_date(end_date) if end_date else None
        if start and end and end < start:
            raise ValidationError("Session end date cannot be before the start date.")
        try:
            self.db.execute(
                "UPDATE academic_sessions SET name = ?, start_date = ?, end_date = ? WHERE id = ?",
                (name, start.isoformat() if start else None, end.isoformat() if end else None, int(session_id)),
            )
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
        self.db.log_activity("update", "academic_session", session_id, name)

    # ------------------------------------------------------------------ grades
    def grade_rules(self) -> list[Any]:
        return self.db.query("SELECT * FROM grade_rules ORDER BY sort_order, min_percent DESC")

    def save_grade_rules(self, rules: Iterable[dict[str, Any]]) -> None:
        cleaned = []
        for index, rule in enumerate(rules):
            grade = clean_text(rule.get("grade"), 8)
            if not grade:
                raise ValidationError("Every grade needs a label.")
            try:
                low = float(rule.get("min_percent"))
                high = float(rule.get("max_percent"))
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    f"Grade {grade}: minimum and maximum percentage must be numbers."
                ) from exc
            if not (0 <= low <= 100 and 0 <= high <= 100):
                raise ValidationError(f"Grade {grade}: percentages must be between 0 and 100.")
            if high < low:
                raise ValidationError(f"Grade {grade}: maximum cannot be below minimum.")
            cleaned.append((grade, low, high, clean_text(rule.get("description"), 120), index))
        if not cleaned:
            raise ValidationError("Add at least one grade rule.")
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM grade_rules")
            conn.executemany(
                "INSERT INTO grade_rules (grade, min_percent, max_percent, description, sort_order)"
                " VALUES (?, ?, ?, ?, ?)",
                cleaned,
            )
        self.db.log_activity("update", "grade_rules", None, f"{len(cleaned)} rules")

    def reset_grade_rules(self) -> None:
        defaults = [
            {"grade": "A+", "min_percent": 90, "max_percent": 100, "description": "Outstanding"},
            {"grade": "A", "min_percent": 80, "max_percent": 89.99, "description": "Very good"},
            {"grade": "B", "min_percent": 70, "max_percent": 79.99, "description": "Good"},
            {"grade": "C", "min_percent": 60, "max_percent": 69.99, "description": "Above average"},
            {"grade": "D", "min_percent": 50, "max_percent": 59.99, "description": "Average"},
            {"grade": "E", "min_percent": 33, "max_percent": 49.99, "description": "Needs improvement"},
            {"grade": "F", "min_percent": 0, "max_percent": 32.99, "description": "Below pass mark"},
        ]
        self.save_grade_rules(defaults)
