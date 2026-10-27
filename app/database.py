"""SQLite database layer: connections, schema migrations, transactions."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from app import config


class DatabaseError(RuntimeError):
    """Raised when a database operation cannot be completed."""


SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS academic_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    start_date  TEXT,
    end_date    TEXT,
    is_active   INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no         TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    class_name      TEXT NOT NULL CHECK (class_name IN ('9', '10')),
    section         TEXT NOT NULL DEFAULT '',
    session_id      INTEGER NOT NULL REFERENCES academic_sessions(id) ON DELETE RESTRICT,
    guardian_name   TEXT,
    contact_no      TEXT,
    admission_date  TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'inactive', 'archived')),
    remarks         TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (session_id, class_name, roll_no)
);
CREATE INDEX IF NOT EXISTS idx_students_session_class
    ON students (session_id, class_name, status);
CREATE INDEX IF NOT EXISTS idx_students_name ON students (full_name);

CREATE TABLE IF NOT EXISTS attendance (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id       INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    session_id       INTEGER NOT NULL REFERENCES academic_sessions(id) ON DELETE RESTRICT,
    class_name       TEXT NOT NULL,
    attendance_date  TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('P', 'A', 'L')),
    remarks          TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    UNIQUE (student_id, attendance_date)
);
CREATE INDEX IF NOT EXISTS idx_attendance_date
    ON attendance (attendance_date, session_id, class_name);
CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance (student_id);

CREATE TABLE IF NOT EXISTS attendance_batches (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER NOT NULL REFERENCES academic_sessions(id) ON DELETE CASCADE,
    class_name       TEXT NOT NULL,
    attendance_date  TEXT NOT NULL,
    saved_at         TEXT NOT NULL,
    saved_by         TEXT,
    UNIQUE (session_id, class_name, attendance_date)
);

CREATE TABLE IF NOT EXISTS examinations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    exam_type       TEXT NOT NULL DEFAULT 'Custom',
    class_name      TEXT NOT NULL CHECK (class_name IN ('9', '10')),
    session_id      INTEGER NOT NULL REFERENCES academic_sessions(id) ON DELETE RESTRICT,
    subject         TEXT NOT NULL DEFAULT 'Computer Science',
    exam_date       TEXT,
    max_marks       REAL NOT NULL CHECK (max_marks > 0),
    pass_marks      REAL,
    pass_percent    REAL,
    theory_max      REAL,
    practical_max   REAL,
    project_max     REAL,
    remarks         TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (name, class_name, session_id, subject)
);
CREATE INDEX IF NOT EXISTS idx_exams_session_class
    ON examinations (session_id, class_name);

CREATE TABLE IF NOT EXISTS marks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    examination_id  INTEGER NOT NULL REFERENCES examinations(id) ON DELETE CASCADE,
    student_id      INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    theory          REAL,
    practical       REAL,
    project         REAL,
    total           REAL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'entered', 'absent', 'exempted')),
    remarks         TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (examination_id, student_id)
);
CREATE INDEX IF NOT EXISTS idx_marks_exam ON marks (examination_id);
CREATE INDEX IF NOT EXISTS idx_marks_student ON marks (student_id);

CREATE TABLE IF NOT EXISTS holidays (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    holiday_date   TEXT NOT NULL,
    name           TEXT NOT NULL,
    session_id     INTEGER REFERENCES academic_sessions(id) ON DELETE CASCADE,
    created_at     TEXT NOT NULL,
    UNIQUE (holiday_date, session_id)
);

CREATE TABLE IF NOT EXISTS grade_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    grade       TEXT NOT NULL,
    min_percent REAL NOT NULL,
    max_percent REAL NOT NULL,
    description TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_id   TEXT,
    details     TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log (created_at);
"""


def utc_now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _migration_001(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_V1)


def _migration_002(conn: sqlite3.Connection) -> None:
    """Seed default academic session, settings and a generic grade scale."""
    now = utc_now()
    conn.execute(
        "INSERT OR IGNORE INTO academic_sessions (name, start_date, end_date, is_active, created_at)"
        " VALUES (?, ?, ?, 1, ?)",
        (config.DEFAULT_SESSION, config.DEFAULT_SESSION_START, config.DEFAULT_SESSION_END, now),
    )
    row = conn.execute(
        "SELECT id FROM academic_sessions WHERE name = ?", (config.DEFAULT_SESSION,)
    ).fetchone()
    session_id = row[0] if row else None

    defaults = dict(config.DEFAULT_SETTINGS)
    if session_id is not None:
        defaults["active_session_id"] = str(session_id)
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )

    # Generic, fully configurable scale. NOT an official SEBA grading policy.
    grades = [
        ("A+", 90.0, 100.0, "Outstanding", 1),
        ("A", 80.0, 89.99, "Very good", 2),
        ("B", 70.0, 79.99, "Good", 3),
        ("C", 60.0, 69.99, "Above average", 4),
        ("D", 50.0, 59.99, "Average", 5),
        ("E", 33.0, 49.99, "Needs improvement", 6),
        ("F", 0.0, 32.99, "Not passed (as per configured pass mark)", 7),
    ]
    existing = conn.execute("SELECT COUNT(*) FROM grade_rules").fetchone()[0]
    if existing == 0:
        conn.executemany(
            "INSERT INTO grade_rules (grade, min_percent, max_percent, description, sort_order)"
            " VALUES (?, ?, ?, ?, ?)",
            grades,
        )


MIGRATIONS: list[tuple[int, Any]] = [
    (1, _migration_001),
    (2, _migration_002),
]
SCHEMA_VERSION = MIGRATIONS[-1][0]


class Database:
    """Thin, thread-safe-enough wrapper around a single SQLite connection.

    All UI access happens on the Qt main thread. A re-entrant lock protects
    background backup operations that may touch the connection.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else config.database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ setup
    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        try:
            conn = sqlite3.connect(str(self.path), timeout=20)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA busy_timeout = 10000")
            self._conn = conn
            self.migrate()
            return conn
        except sqlite3.Error as exc:  # pragma: no cover - platform dependent
            self._conn = None
            raise DatabaseError(
                f"Could not open the database at {self.path}.\n\n{exc}"
            ) from exc

    def migrate(self) -> None:
        conn = self.conn
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {
            row[0]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for version, migration in MIGRATIONS:
            if version in applied:
                continue
            try:
                # Each migration is written to be safely re-runnable
                # (CREATE IF NOT EXISTS / INSERT OR IGNORE).
                migration(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, utc_now()),
                )
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise DatabaseError(
                    f"Database migration {version} failed: {exc}"
                ) from exc

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.commit()
                    self._conn.execute("PRAGMA optimize")
                except sqlite3.Error:
                    pass
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    # ------------------------------------------------------------- primitives
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.conn
        with self._lock:
            try:
                conn.execute("BEGIN")
                yield conn
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
                raise

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> sqlite3.Cursor:
        with self._lock:
            try:
                cur = self.conn.execute(sql, tuple(params or ()))
                self.conn.commit()
                return cur
            except sqlite3.Error as exc:
                try:
                    self.conn.rollback()
                except sqlite3.Error:
                    pass
                raise DatabaseError(self._friendly_error(exc)) from exc

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        with self._lock:
            try:
                self.conn.executemany(sql, [tuple(r) for r in rows])
                self.conn.commit()
            except sqlite3.Error as exc:
                self.conn.rollback()
                raise DatabaseError(self._friendly_error(exc)) from exc

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[sqlite3.Row]:
        with self._lock:
            try:
                return self.conn.execute(sql, tuple(params or ())).fetchall()
            except sqlite3.Error as exc:
                raise DatabaseError(self._friendly_error(exc)) from exc

    def query_one(
        self, sql: str, params: Sequence[Any] | None = None
    ) -> sqlite3.Row | None:
        with self._lock:
            try:
                return self.conn.execute(sql, tuple(params or ())).fetchone()
            except sqlite3.Error as exc:
                raise DatabaseError(self._friendly_error(exc)) from exc

    def scalar(self, sql: str, params: Sequence[Any] | None = None, default: Any = None) -> Any:
        row = self.query_one(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value

    def log_activity(
        self,
        action: str,
        entity: str,
        entity_id: Any = None,
        details: str = "",
    ) -> None:
        try:
            self.execute(
                "INSERT INTO audit_log (created_at, action, entity, entity_id, details)"
                " VALUES (?, ?, ?, ?, ?)",
                (utc_now(), action, entity, None if entity_id is None else str(entity_id), details),
            )
        except DatabaseError:
            # Audit logging must never break a user operation.
            pass

    def recent_activity(self, limit: int = 12) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (int(limit),)
        )

    @staticmethod
    def _friendly_error(exc: sqlite3.Error) -> str:
        text = str(exc)
        if "UNIQUE constraint failed" in text:
            if "students" in text:
                return (
                    "A student with this roll number already exists in the same class "
                    "and academic session."
                )
            if "attendance" in text:
                return "Attendance for this student and date already exists."
            if "marks" in text:
                return "Marks for this student and examination already exist."
            if "academic_sessions" in text:
                return "An academic session with this name already exists."
            if "examinations" in text:
                return "An examination with this name already exists for the class and session."
            return "This record already exists. Duplicate entries are not allowed."
        if "FOREIGN KEY constraint failed" in text:
            return "This record is still referenced by other data and cannot be removed."
        if "CHECK constraint failed" in text:
            return "One of the values is not allowed. Please review the form and try again."
        return f"Database error: {text}"

    def backup_to(self, destination: str | Path) -> Path:
        """Create a consistent copy of the database using SQLite's backup API."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(destination))
            try:
                self.conn.backup(target)
                target.execute("PRAGMA integrity_check")
            finally:
                target.close()
        return destination

    def table_counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for table in ("students", "attendance", "examinations", "marks", "holidays"):
            result[table] = int(self.scalar(f"SELECT COUNT(*) FROM {table}", default=0))
        return result
