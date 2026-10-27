"""Analytics use only saved records and keep their totals consistent."""
from __future__ import annotations

START = "2026-04-01"
END = "2027-03-31"


def test_dashboard_metrics(dataset, ctx, session_id):
    metrics = ctx.analytics.dashboard_metrics(session_id, None, START, END, "2026-10-05")
    assert metrics["class_totals"] == {"9": 2, "10": 1}
    assert metrics["total_students"] == 3
    # Alpha 2 present, Beta absent once and on leave once, Gamma 1 present.
    assert metrics["attendance"]["present"] == 3
    assert metrics["attendance"]["absent"] == 1
    assert metrics["attendance"]["leave"] == 1
    assert metrics["attendance"]["percentage"] == 75.0
    assert metrics["marks"]["entered"] == 2
    assert metrics["marks"]["pass_percentage"] == 50.0


def test_dashboard_metrics_for_one_class(dataset, ctx, session_id):
    metrics = ctx.analytics.dashboard_metrics(session_id, "10", START, END, "2026-10-05")
    assert metrics["total_students"] == 1
    assert metrics["attendance"]["present"] == 1
    assert metrics["attendance"]["percentage"] == 100.0
    assert metrics["marks"]["entered"] == 0
    assert metrics["today"]["present"] == 1
    assert metrics["today_saved"] is True


def test_below_threshold_and_support_flags(dataset, ctx, session_id):
    metrics = ctx.analytics.dashboard_metrics(session_id, "9", START, END, "2026-10-05")
    below = {s["full_name"] for s in metrics["below_attendance"]}
    assert below == {"Beta Das"}
    support = {s["full_name"] for s in metrics["support_students"]}
    assert "Beta Das" in support


def test_attendance_pie_matches_service_totals(dataset, ctx, session_id):
    pie = ctx.analytics.attendance_pie(session_id, "9", START, END)
    assert pie["present"] == 2
    assert pie["absent"] == 1
    assert pie["leave"] == 1
    assert pie["percentage"] == 66.67
    assert pie["present"] + pie["absent"] + pie["leave"] == 4


def test_results_pie_matches_exam_statistics(dataset, ctx):
    exam_id = dataset["exam_id"]
    stats = ctx.marks.class_statistics(exam_id)
    pie = ctx.analytics.results_pie(exam_id)
    assert pie["passed"] == stats["passed"] == 1
    assert pie["failed"] == stats["failed"] == 1
    assert pie["absent"] == 0
    assert pie["total"] == 2
    assert pie["pass_percentage"] == 50.0
    assert pie["has_data"] is True


def test_marks_distribution(dataset, ctx):
    distribution = ctx.analytics.marks_distribution(dataset["exam_id"])
    assert distribution["has_data"] is True
    assert distribution["max_marks"] == 100.0
    assert len(distribution["rows"]) == 2


def test_class_comparison(dataset, ctx, session_id):
    rows = ctx.analytics.class_comparison(session_id, START, END)
    assert [row["class_name"] for row in rows] == ["9", "10"]
    nine = rows[0]
    assert nine["students"] == 2
    assert nine["attendance_percentage"] == 66.67
    assert nine["pass_percentage"] == 50.0


def test_monthly_trend(dataset, ctx, session_id):
    trend = ctx.analytics.monthly_trend(session_id, None, START, END)
    assert len(trend) == 1
    assert trend[0]["month"] == "2026-10"


def test_student_performance(dataset, ctx):
    alpha = dataset["students"]["alpha"]
    performance = ctx.analytics.student_performance(alpha, START, END)
    assert performance["student"]["full_name"] == "Alpha Sharma"
    assert performance["attendance"]["percentage"] == 100.0
    assert performance["average_percentage"] == 88.0
    assert performance["needs_support"] is False
    assert performance["attendance_trend"][0]["month"] == "2026-10"


def test_performance_summary_excludes_leave_when_configured(dataset, ctx, session_id):
    summary = ctx.analytics.performance_summary(session_id, "9", START, END)
    assert summary["attendance"]["percentage"] == 66.67
    assert summary["marks"]["entered"] == 2
    beta = next(s for s in summary["students"] if s["full_name"] == "Beta Das")
    assert beta["present"] == 0
    assert beta["absent"] == 1
    assert beta["leave"] == 1
    assert beta["counted"] == 1
    assert beta["attendance_percentage"] == 0.0
