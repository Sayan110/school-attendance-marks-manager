"""Settings, academic sessions and grade rules."""
from __future__ import annotations

import pytest

from app import config
from app.utils.validators import ValidationError


def test_school_defaults_are_seeded(ctx):
    assert ctx.settings.school_name == config.SCHOOL_NAME
    assert ctx.settings.subject == "Computer Science"
    assert ctx.settings.board == "SEBA Board, Assam"
    assert ctx.settings.attendance_threshold == 75.0
    assert ctx.settings.performance_threshold == 33.0
    assert ctx.settings.leave_excluded is True
    assert ctx.settings.theme == "light"


def test_values_roundtrip_and_type_coercion(ctx):
    ctx.settings.set_many(
        {
            "attendance_threshold": "80.5",
            "performance_threshold": "40",
            "leave_excluded_from_percentage": "0",
            "theme": "dark",
            "school_name": "  SHIKSHA VIKASH ENGLISH HIGH SCHOOL  ",
        }
    )
    assert ctx.settings.attendance_threshold == 80.5
    assert ctx.settings.performance_threshold == 40.0
    assert ctx.settings.leave_excluded is False
    assert ctx.settings.theme == "dark"
    assert ctx.settings.school_name == "SHIKSHA VIKASH ENGLISH HIGH SCHOOL"


def test_bad_numbers_fall_back_to_defaults(ctx):
    ctx.settings.set_many({"attendance_threshold": "not-a-number"})
    assert ctx.settings.attendance_threshold == 75.0


def test_reload_clears_cached_values(ctx):
    assert ctx.settings.subject == "Computer Science"  # loads and caches the value
    ctx.db.execute(
        "UPDATE app_settings SET value = 'Information Technology' WHERE key = 'subject'"
    )
    assert ctx.settings.subject == "Computer Science"  # still served from cache
    ctx.settings.reload()
    assert ctx.settings.subject == "Information Technology"


def test_default_session_is_active(ctx, session_id):
    assert ctx.settings.active_session_name() == config.DEFAULT_SESSION
    session = ctx.settings.get_session(session_id)
    assert session["name"] == config.DEFAULT_SESSION
    assert session["is_active"] == 1


def test_add_session_and_switch_active(ctx):
    new_id = ctx.settings.add_session("2027-2028", "2027-04-01", "2028-03-31")
    assert new_id in [int(row["id"]) for row in ctx.settings.sessions()]
    ctx.settings.set_active_session(new_id)
    assert ctx.settings.active_session_id() == new_id
    active = [row["id"] for row in ctx.settings.sessions() if row["is_active"] == 1]
    assert active == [new_id]


def test_switch_to_missing_session_is_rejected(ctx):
    with pytest.raises(ValidationError):
        ctx.settings.set_active_session(9999)


def test_session_validation(ctx):
    with pytest.raises(ValidationError):
        ctx.settings.add_session("")
    with pytest.raises(ValidationError):
        ctx.settings.add_session("2028-2029", "2028-04-01", "2027-03-31")
    with pytest.raises(ValidationError):
        ctx.settings.add_session(config.DEFAULT_SESSION)
    with pytest.raises(ValidationError):
        ctx.settings.add_session("Bad Date", "not-a-date")


def test_update_session(ctx, session_id):
    ctx.settings.update_session(session_id, "2026-2027", "2026-04-01", "2027-03-31")
    session = ctx.settings.get_session(session_id)
    assert session["start_date"] == "2026-04-01"
    assert session["end_date"] == "2027-03-31"
    with pytest.raises(ValidationError):
        ctx.settings.update_session(session_id, "", "2026-04-01", "2027-03-31")


def test_grade_rules_are_seeded_and_ordered(ctx):
    rules = ctx.settings.grade_rules()
    assert [rule["grade"] for rule in rules] == ["A+", "A", "B", "C", "D", "E", "F"]
    assert rules[0]["min_percent"] == 90
    assert rules[-1]["min_percent"] == 0


def test_grade_rule_validation(ctx):
    with pytest.raises(ValidationError):
        ctx.settings.save_grade_rules([])
    with pytest.raises(ValidationError):
        ctx.settings.save_grade_rules([{"grade": "A", "min_percent": 50, "max_percent": 40}])
    with pytest.raises(ValidationError):
        ctx.settings.save_grade_rules([{"grade": "A", "min_percent": 0, "max_percent": 101}])
    with pytest.raises(ValidationError):
        ctx.settings.save_grade_rules([{"grade": "", "min_percent": 0, "max_percent": 100}])
    assert len(ctx.settings.grade_rules()) == 7


def test_grade_rule_replacement_and_reset(ctx):
    ctx.settings.save_grade_rules(
        [
            {"grade": "P", "min_percent": 40, "max_percent": 100, "description": "Pass"},
            {"grade": "F", "min_percent": 0, "max_percent": 39.99, "description": "Fail"},
        ]
    )
    assert [rule["grade"] for rule in ctx.settings.grade_rules()] == ["P", "F"]
    ctx.settings.reset_grade_rules()
    assert len(ctx.settings.grade_rules()) == 7


def test_activity_log_records_changes(ctx, session_id):
    before = ctx.db.scalar("SELECT COUNT(*) FROM audit_log", default=0)
    ctx.settings.update_session(session_id, "2026-2027", "2026-04-05", "2027-03-31")
    after = ctx.db.scalar("SELECT COUNT(*) FROM audit_log", default=0)
    assert after > before
