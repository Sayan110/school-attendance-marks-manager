"""Backup, validation and restore of the SQLite database."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app import config
from app.database import Database, DatabaseError, SCHEMA_VERSION, utc_now
from app.services.settings_service import SettingsService
from app.utils.validators import ValidationError

REQUIRED_TABLES = {
    "students",
    "academic_sessions",
    "attendance",
    "attendance_batches",
    "examinations",
    "marks",
    "app_settings",
    "grade_rules",
    "holidays",
}


class BackupService:
    def __init__(self, db: Database, settings: SettingsService) -> None:
        self.db = db
        self.settings = settings

    # ------------------------------------------------------------------ paths
    def backup_dir(self) -> Path:
        configured = self.settings.get("backup_directory", "").strip()
        path = Path(configured) if configured else config.default_backup_dir()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def set_backup_dir(self, path: str | Path) -> None:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        self.settings.set("backup_directory", str(target))

    # ---------------------------------------------------------------- create
    def create_backup(self, label: str = "manual") -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(ch for ch in label if ch.isalnum() or ch in ("-", "_"))[:24] or "manual"
        destination = self.backup_dir() / f"school_manager_{timestamp}_{safe_label}.db"
        temp = destination.with_suffix(".db.part")
        try:
            self.db.backup_to(temp)
            info = self.validate_backup_file(temp)
            if not info["valid"]:
                raise ValidationError(info["message"])
            temp.replace(destination)
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)
        self.settings.set("last_backup_at", utc_now())
        self.db.log_activity("backup", "database", None, destination.name)
        self.prune_backups()
        return destination

    def prune_backups(self) -> None:
        retention = self.settings.backup_retention
        backups = sorted(
            self.backup_dir().glob("school_manager_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in backups[retention:]:
            try:
                old.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------ list
    def list_backups(self) -> list[dict[str, Any]]:
        items = []
        for path in sorted(
            self.backup_dir().glob("school_manager_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                stat = path.stat()
                items.append(
                    {
                        "path": path,
                        "name": path.name,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%d-%m-%Y %H:%M"),
                        "modified_ts": stat.st_mtime,
                    }
                )
            except OSError:
                continue
        return items

    @staticmethod
    def validate_backup_file(path: str | Path) -> dict[str, Any]:
        path = Path(path)
        if not path.exists():
            return {"valid": False, "message": "The backup file does not exist.", "counts": {}}
        if path.stat().st_size < 1024:
            return {"valid": False, "message": "The backup file is too small to be valid.", "counts": {}}
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            return {"valid": False, "message": f"Cannot open backup: {exc}", "counts": {}}
        try:
            check = conn.execute("PRAGMA integrity_check").fetchone()
            if not check or check[0] != "ok":
                return {
                    "valid": False,
                    "message": "SQLite integrity check failed for this backup.",
                    "counts": {},
                }
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            missing = REQUIRED_TABLES - tables
            if missing:
                return {
                    "valid": False,
                    "message": "This file is not a School Manager backup (missing tables: "
                    + ", ".join(sorted(missing)) + ").",
                    "counts": {},
                }
            counts = {}
            for table in ("students", "attendance", "examinations", "marks"):
                counts[table] = int(
                    conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
            version = 0
            if "schema_migrations" in tables:
                row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
                version = int(row[0] or 0) if row else 0
            return {
                "valid": True,
                "message": "Backup is valid and can be restored.",
                "counts": counts,
                "schema_version": version,
                "message_extra": (
                    f"Schema v{version} (application expects v{SCHEMA_VERSION})."
                ),
            }
        except sqlite3.Error as exc:
            return {"valid": False, "message": f"Backup validation failed: {exc}", "counts": {}}
        finally:
            conn.close()

    # --------------------------------------------------------------- restore
    def restore_backup(self, source: str | Path) -> dict[str, Any]:
        source = Path(source)
        info = self.validate_backup_file(source)
        if not info["valid"]:
            raise ValidationError(f"Backup cannot be restored. {info['message']}")
        if source.resolve() == self.db.path.resolve():
            raise ValidationError("That is the live database, not a backup.")
        safety = self.create_backup("before_restore")
        db_path = self.db.path
        try:
            self.db.close()
            shutil.copy2(source, db_path)
            # Remove stale WAL/SHM files that belong to the old database.
            for suffix in ("-wal", "-shm"):
                stale = Path(str(db_path) + suffix)
                if stale.exists():
                    stale.unlink(missing_ok=True)
            self.db.connect()
            check = self.db.scalar("PRAGMA integrity_check")
            if check != "ok":
                raise DatabaseError("Integrity check failed after restore.")
        except Exception as exc:
            # Attempt automatic rollback to the safety backup.
            try:
                self.db.close()
                shutil.copy2(safety, db_path)
                for suffix in ("-wal", "-shm"):
                    stale = Path(str(db_path) + suffix)
                    if stale.exists():
                        stale.unlink(missing_ok=True)
                self.db.connect()
            except Exception:  # pragma: no cover - catastrophic disk failure
                pass
            raise ValidationError(
                f"Restore failed and the previous database was put back.\n\n{exc}"
            ) from exc
        self.db.log_activity("restore", "database", None, source.name)
        return {"restored": source.name, "safety_backup": safety, "counts": info["counts"]}

    # ------------------------------------------------------------------- auto
    def auto_backup_if_due(self) -> Path | None:
        days = self.settings.auto_backup_days
        if days <= 0:
            return None
        if int(self.db.scalar("SELECT COUNT(*) FROM students", default=0)) == 0:
            return None
        last = self.settings.get("last_backup_at", "").strip()
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
            except ValueError:
                last_dt = None
            if last_dt and (datetime.now() - last_dt).total_seconds() < days * 86400:
                return None
        return self.create_backup("auto")
