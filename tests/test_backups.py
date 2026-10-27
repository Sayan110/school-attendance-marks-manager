"""Backup creation, validation and restore safety."""
from __future__ import annotations

import pytest

from app.utils.validators import ValidationError


def test_create_backup_and_validate(dataset, ctx):
    path = ctx.backup.create_backup("manual")
    assert path.exists()
    item = ctx.backup.list_backups()[0]
    assert item["path"] == path
    info = ctx.backup.validate_backup_file(path)
    assert info["valid"] is True
    assert info["counts"]["students"] == 3
    # 2 + 2 rows for Class 9 across two dates, plus 1 row for Class 10.
    assert info["counts"]["attendance"] == 5
    assert info["counts"]["examinations"] == 1


def test_validate_rejects_garbage_file(ctx, tmp_path):
    bad = tmp_path / "not-a-backup.db"
    bad.write_bytes(b"this is not a sqlite database" * 100)
    info = ctx.backup.validate_backup_file(bad)
    assert info["valid"] is False
    assert "not" in info["message"].lower() or "integrity" in info["message"].lower()


def test_validate_rejects_missing_and_tiny_files(ctx, tmp_path):
    missing = tmp_path / "missing.db"
    assert ctx.backup.validate_backup_file(missing)["valid"] is False
    tiny = tmp_path / "tiny.db"
    tiny.write_bytes(b"abc")
    assert ctx.backup.validate_backup_file(tiny)["valid"] is False


def test_restore_replaces_database_and_keeps_safety_copy(dataset, ctx, add_student, session_id):
    backup = ctx.backup.create_backup("manual")
    add_student("99", "Added After Backup")
    assert ctx.students.list_students(session_id)[1] == 4

    result = ctx.backup.restore_backup(backup)
    assert result["restored"] == backup.name
    assert result["safety_backup"].exists()
    assert "before_restore" in result["safety_backup"].name
    assert ctx.students.list_students(session_id)[1] == 3


def test_restore_refuses_the_live_database(ctx):
    with pytest.raises(ValidationError):
        ctx.backup.restore_backup(ctx.db.path)


def test_restore_refuses_invalid_file(ctx, tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"x" * 2048)
    with pytest.raises(ValidationError):
        ctx.backup.restore_backup(bad)


def test_auto_backup_skips_empty_database(ctx):
    assert ctx.backup.auto_backup_if_due() is None


def test_auto_backup_creates_when_due(dataset, ctx):
    path = ctx.backup.auto_backup_if_due()
    assert path is not None
    assert path.exists()
    assert "auto" in path.name
    # A second call in the same window does not create another backup.
    assert ctx.backup.auto_backup_if_due() is None


def test_prune_keeps_configured_number(dataset, ctx):
    ctx.settings.set("backup_retention", "2")
    ctx.backup.create_backup("one")
    ctx.backup.create_backup("two")
    ctx.backup.create_backup("three")
    assert len(ctx.backup.list_backups()) == 2


def test_backup_directory_can_be_changed(ctx, tmp_path):
    target = tmp_path / "custom-backups"
    ctx.backup.set_backup_dir(target)
    assert ctx.backup.backup_dir() == target
    assert target.exists()
    path = ctx.backup.create_backup("custom")
    assert path.parent == target
