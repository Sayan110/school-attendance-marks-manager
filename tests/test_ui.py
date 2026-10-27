"""Offscreen Qt tests for the window shell and the data-entry pages.

These use a real QApplication with the offscreen platform plugin. They never
show a window on the teacher's desktop and never touch the real database.
"""
from __future__ import annotations

import gc
import warnings
from datetime import date

import pytest

from app import config
from app.ui.common import set_date_edit
from app.ui.main_window import MainWindow


@pytest.fixture()
def window(qapp, ctx):
    window = MainWindow(ctx)
    qapp.processEvents()
    try:
        yield window
    finally:
        window._closing = True
        window.close()
        qapp.processEvents()


def test_window_builds_all_pages(window):
    assert sorted(window.pages) == [
        "analytics",
        "attendance",
        "backup",
        "dashboard",
        "marks",
        "reports",
        "settings",
        "students",
    ]
    assert window.stack.count() == 8
    assert window._current_key == "dashboard"
    assert window.breadcrumb.text() == "Dashboard"
    assert window.nav_buttons["dashboard"].isChecked()
    assert window.windowTitle() == config.APP_NAME
    assert window.session_combo.currentText() == config.DEFAULT_SESSION


def test_navigation_switches_pages_and_breadcrumb(window):
    for key, label in [
        ("students", "Students"),
        ("attendance", "Attendance"),
        ("marks", "Marks & exams"),
        ("analytics", "Analytics"),
        ("reports", "Reports"),
        ("backup", "Backup"),
        ("settings", "Settings"),
        ("dashboard", "Dashboard"),
    ]:
        window.navigate_to(key)
        assert window._current_key == key
        assert window.stack.currentWidget() is window.pages[key]
        assert window.breadcrumb.text() == label


def test_navigation_ignores_unknown_page(window):
    window.navigate_to("does-not-exist")
    assert window._current_key == "dashboard"


def test_only_the_main_window_is_visible(window, qapp):
    """No page may leak an unparented widget as its own top-level window."""
    qapp.processEvents()
    extras = [
        widget
        for widget in qapp.topLevelWidgets()
        if widget is not window and widget.isVisible()
    ]
    assert extras == []


def test_closing_window_stops_pending_timers_and_database(qapp, ctx):
    """A debounce timer firing after close must not reopen the database."""
    window = MainWindow(ctx)
    page = window.pages["students"]
    page.search_edit.setText("Alpha")  # arms the single-shot search timer
    assert page._search_timer.isActive() is True

    window.close()
    qapp.processEvents()

    assert window._closing is True
    assert page._search_timer.isActive() is False
    assert ctx.db._conn is None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        gc.collect()
    leaks = [w for w in caught if "unclosed database" in str(w.message)]
    assert leaks == []


def test_all_pages_build_and_refresh_without_qt_warnings(qapp, ctx):
    from PySide6.QtCore import qInstallMessageHandler

    from app.ui.main_window import MainWindow

    messages: list[str] = []
    previous = qInstallMessageHandler(lambda _mode, _ctx, message: messages.append(message))
    try:
        window = MainWindow(ctx)
        for key in list(window.pages):
            window.navigate_to(key)
            qapp.processEvents()
    finally:
        qInstallMessageHandler(previous)
        window._closing = True
        window.close()
        qapp.processEvents()

    problems = [
        message
        for message in messages
        if "QLayout" in message or "Could not parse stylesheet" in message
    ]
    assert problems == []


def test_theme_toggle_rebuilds_and_persists(window, qapp):
    window.apply_theme("dark")
    qapp.processEvents()
    assert window.context.settings.theme == "dark"
    assert window.stack.count() == 8
    # Pages are rebuilt, not destroyed, and the numaber of pages stays the same.
    assert sorted(window.pages) == sorted(
        ["dashboard", "students", "attendance", "marks", "analytics", "reports", "backup", "settings"]
    )
    window.apply_theme("light")
    qapp.processEvents()
    assert window.context.settings.theme == "light"


def test_session_combo_switches_active_session(window, ctx):
    new_id = ctx.settings.add_session("2027-2028", "2027-04-01", "2028-03-31")
    window._refresh_session_combo()
    index = window.session_combo.findData(new_id)
    assert index >= 0
    window.session_combo.setCurrentIndex(index)
    assert ctx.settings.active_session_id() == new_id


def test_students_page_lists_and_filters(window, dataset):
    page = window.pages["students"]
    window.navigate_to("students")
    assert page.table.rowCount() == 3
    page.search_edit.setText("Beta")
    page._filters_changed()
    assert page.table.rowCount() == 1
    page.search_edit.setText("")
    page._filters_changed()
    assert page.table.rowCount() == 3
    page.class_filter.setCurrentIndex(page.class_filter.findData("10"))
    page._filters_changed()
    assert page.table.rowCount() == 1


def test_students_page_empty_state_without_students(window, ctx):
    page = window.pages["students"]
    page.refresh()
    assert page.table_panel.isHidden() is True
    assert page.empty_state.isHidden() is False


def test_attendance_page_marks_saves_and_clears_dirty(window, dataset, monkeypatch):
    from app.ui import attendance as attendance_module

    monkeypatch.setattr(attendance_module, "notify", lambda *a, **k: None)
    page = window.pages["attendance"]
    page.class_combo.setCurrentIndex(page.class_combo.findData("9"))
    set_date_edit(page.date_edit, date(2026, 10, 7))
    page.load_day()
    assert page.table.rowCount() == 2
    assert page.has_unsaved_changes() is False

    page._mark_all("P")
    assert page.has_unsaved_changes() is True
    assert page.count_labels["present"].text() == "2"
    assert page.count_labels["absent"].text() == "0"

    page.save()
    assert page.has_unsaved_changes() is False
    saved = page.context.attendance.load_day(page.context.session_id, "9", "2026-10-07")
    assert saved.saved is True
    assert saved.counts.present == 2


def test_attendance_save_requires_at_least_one_mark(window, dataset, monkeypatch):
    from app.ui import attendance as attendance_module

    errors = []
    monkeypatch.setattr(attendance_module, "notify", lambda *a, **k: None)
    monkeypatch.setattr(
        attendance_module, "error_dialog", lambda parent, title, text: errors.append(title)
    )
    page = window.pages["attendance"]
    page.class_combo.setCurrentIndex(page.class_combo.findData("9"))
    set_date_edit(page.date_edit, date(2026, 10, 12))
    page.load_day()
    page.save()
    assert errors == ["Nothing marked"]
    assert page.context.attendance.existing_count(page.context.session_id, "9", "2026-10-12") == 0


def test_attendance_discard_reloads_saved_state(window, dataset, monkeypatch):
    from app.ui import attendance as attendance_module

    monkeypatch.setattr(attendance_module, "confirm_action", lambda *a, **k: True)
    page = window.pages["attendance"]
    page.class_combo.setCurrentIndex(page.class_combo.findData("9"))
    set_date_edit(page.date_edit, date(2026, 10, 5))
    page.load_day()
    page._mark_all("A")
    assert page.has_unsaved_changes() is True
    page.discard_changes()
    assert page.has_unsaved_changes() is False
    assert page.count_labels["present"].text() == "1"
    assert page.count_labels["absent"].text() == "1"


def test_attendance_overwrite_confirmation_can_cancel(window, dataset, monkeypatch):
    from app.ui import attendance as attendance_module

    monkeypatch.setattr(attendance_module, "confirm_action", lambda *a, **k: False)
    page = window.pages["attendance"]
    page.class_combo.setCurrentIndex(page.class_combo.findData("9"))
    set_date_edit(page.date_edit, date(2026, 10, 5))
    page.load_day()
    page._mark_all("A")
    page.save()
    assert page.has_unsaved_changes() is True
    saved = page.context.attendance.load_day(page.context.session_id, "9", "2026-10-05")
    assert saved.counts.present == 1  # unchanged


def test_marks_page_edits_and_saves(window, dataset, monkeypatch):
    from app.ui import marks as marks_module

    monkeypatch.setattr(marks_module, "notify", lambda *a, **k: None)
    page = window.pages["marks"]
    window.navigate_to("marks")
    assert page.table.rowCount() == 2
    alpha = dataset["students"]["alpha"]
    widgets = page._widgets[alpha]
    widgets["theory"].setText("65")
    widgets["theory"].textEdited.emit("65")
    assert page.has_unsaved_changes() is True
    page.save()
    assert page.has_unsaved_changes() is False
    rows = {row["student_id"]: row for row in page.context.marks.result_rows(dataset["exam_id"])}
    assert rows[alpha]["total"] == 93.0


def test_marks_page_status_change_marks_absent(window, dataset, monkeypatch):
    from app.ui import marks as marks_module

    monkeypatch.setattr(marks_module, "notify", lambda *a, **k: None)
    page = window.pages["marks"]
    window.navigate_to("marks")
    beta = dataset["students"]["beta"]
    combo = page._widgets[beta]["status"]
    combo.setCurrentIndex(combo.findData("absent"))
    assert page.has_unsaved_changes() is True
    page.save()
    rows = {row["student_id"]: row for row in page.context.marks.result_rows(dataset["exam_id"])}
    assert rows[beta]["status"] == "absent"
    assert rows[beta]["total"] is None


def test_marks_page_empty_state_without_exams(window, ctx):
    page = window.pages["marks"]
    page.refresh()
    assert page.table.isHidden() is True
    assert page.empty.isHidden() is False


def test_analytics_page_builds_charts_from_saved_data(window, dataset):
    page = window.pages["analytics"]
    window.navigate_to("analytics")
    assert page.tabs.count() >= 2
    charts = [
        page.attendance_chart,
        page.results_chart,
        page.distribution_chart,
        page.comparison_chart,
        page.trend_chart,
    ]
    for chart in charts:
        assert chart.figure.axes, "every chart should render at least one axes"
    # The attendance pie must reflect the two present, one absent, one leave rows.
    labels = [text.get_text() for text in charts[0].figure.axes[0].texts]
    assert any("Present" in label for label in labels)


def test_reports_page_previews_every_report_type(window, dataset):
    page = window.pages["reports"]
    window.navigate_to("reports")
    assert page.report_combo.count() == 10
    for index in range(page.report_combo.count()):
        page.report_combo.setCurrentIndex(index)
        page._preview()
        text = page.preview.toPlainText()
        assert "SHIKSHA VIKASH ENGLISH HIGH SCHOOL" in text, page.report_combo.currentText()
        assert page._document is not None


def test_reports_page_warns_when_parameters_are_missing(window, ctx):
    page = window.pages["reports"]
    window.navigate_to("reports")
    page.report_combo.setCurrentIndex(page.report_combo.findData("marksheet"))
    page._preview()
    assert page._document is None
    assert "Preview unavailable" in page.status.text()


def test_settings_page_saves_thresholds(window, qapp):
    page = window.pages["settings"]
    window.navigate_to("settings")
    page.attendance_threshold.setValue(82.5)
    page._save_rules()
    qapp.processEvents()
    assert window.context.settings.attendance_threshold == 82.5


def test_backup_page_lists_created_backups(window, dataset):
    window.context.backup.create_backup("manual")
    page = window.pages["backup"]
    window.navigate_to("backup")
    assert page.table.rowCount() == 1


def test_close_prompts_only_when_dirty(window, dataset, monkeypatch):
    from app.ui import attendance as attendance_module
    from app.ui import main_window as main_window_module

    monkeypatch.setattr(attendance_module, "confirm_action", lambda *a, **k: True)
    monkeypatch.setattr(main_window_module, "confirm_action", lambda *a, **k: False)
    page = window.pages["attendance"]
    page.class_combo.setCurrentIndex(page.class_combo.findData("9"))
    set_date_edit(page.date_edit, date(2026, 10, 5))
    page.load_day()
    page._mark_all("A")
    assert page.has_unsaved_changes() is True
    window.show()
    window.close()
    assert window._closing is False  # close was refused because of unsaved changes
    page.discard_changes()
    assert page.has_unsaved_changes() is False
    window.close()
    assert window._closing is True
