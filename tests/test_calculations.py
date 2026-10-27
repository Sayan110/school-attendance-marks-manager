"""Pure calculation helpers."""
from __future__ import annotations

import pytest

from app.services import calculations


def test_attendance_excludes_leave_by_default():
    assert calculations.attendance_percentage(3, 0, 2) == 100.0


def test_attendance_can_include_leave_in_denominator():
    assert calculations.attendance_percentage(3, 0, 2, exclude_leave=False) == 60.0


def test_attendance_with_nothing_counted_is_none_not_zero():
    assert calculations.attendance_percentage(0, 0, 0) is None
    assert calculations.attendance_percentage(0, 0, 4) is None  # only Leave
    assert calculations.attendance_percentage(0, 0, 4, exclude_leave=False) == 0.0


def test_attendance_rounds_to_two_places():
    assert calculations.attendance_percentage(1, 2) == 33.33


def test_effective_pass_marks_prefers_absolute_marks():
    assert calculations.effective_pass_marks(100, pass_marks=40, pass_percent=33) == 40.0
    assert calculations.effective_pass_marks(100, pass_percent=33) == 33.0
    assert calculations.effective_pass_marks(100) is None


def test_is_pass_returns_none_for_missing_marks():
    assert calculations.is_pass(None, 100, pass_percent=33) is None
    assert calculations.is_pass(33, 100, pass_percent=33) is True
    assert calculations.is_pass(32.9, 100, pass_percent=33) is False
    assert calculations.is_pass(50, 100) is None  # no pass rule configured


def test_percentage_handles_zero_and_none():
    assert calculations.percentage(50, 100) == 50.0
    assert calculations.percentage(None, 100) is None
    assert calculations.percentage(50, 0) is None


def test_competition_ranking_ties_skip_next_rank():
    ranks = calculations.competition_ranks({"a": 90, "b": 80, "c": 80, "d": 70})
    assert ranks == {"a": 1, "b": 2, "c": 2, "d": 4}


def test_competition_ranking_omits_missing_values():
    ranks = calculations.competition_ranks({"a": 90, "b": None, "c": 70})
    assert ranks == {"a": 1, "c": 2}


def test_competition_ranking_ascending():
    ranks = calculations.competition_ranks({"a": 90, "b": 70}, descending=False)
    assert ranks == {"b": 1, "a": 2}


def test_summarize_skips_missing_values():
    summary = calculations.summarize([10, None, 20, 30])
    assert summary["count"] == 3
    assert summary["highest"] == 30
    assert summary["lowest"] == 10
    assert summary["average"] == 20.0
    assert summary["median"] == 20.0
    assert summary["total"] == 60.0


def test_summarize_empty_is_safe():
    summary = calculations.summarize([])
    assert summary["count"] == 0
    assert summary["average"] is None


@pytest.mark.parametrize(
    ("percent", "expected"),
    [(100, "A+"), (90, "A+"), (89.99, "A"), (80, "A"), (70, "B"), (60, "C"), (50, "D"), (33, "E"), (32.99, "F"), (0, "F")],
)
def test_grade_boundaries(percent, expected, ctx):
    rules = ctx.settings.grade_rules()
    assert calculations.grade_for(percent, rules) == expected


def test_grade_for_missing_percentage():
    assert calculations.grade_for(None, []) == "—"


def test_rate_and_percent_change():
    assert calculations.rate(1, 4) == 25.0
    assert calculations.rate(1, 0) is None
    assert calculations.percent_change(120, 100) == 20.0
    assert calculations.percent_change(50, None) is None
    assert calculations.percent_change(50, 0) is None


def test_support_flag_uses_either_threshold():
    assert calculations.support_flag(20, 90, 33, 75) is True
    assert calculations.support_flag(60, 50, 33, 75) is True
    assert calculations.support_flag(60, 90, 33, 75) is False
    assert calculations.support_flag(None, None, 33, 75) is False
