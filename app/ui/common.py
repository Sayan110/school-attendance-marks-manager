"""Shared page helpers."""
from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QComboBox, QDateEdit, QLabel, QWidget

from app import config
from app.services.settings_service import SettingsService
from app.ui.widgets import format_pct


def make_date_edit(value: date | None = None) -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd-MM-yyyy")
    edit.setDate(QDate(value or date.today()))
    edit.setMinimumWidth(118)
    return edit


def date_to_iso(edit: QDateEdit) -> str:
    return edit.date().toString("yyyy-MM-dd")


def set_date_edit(edit: QDateEdit, value: date | str | None) -> None:
    if value is None:
        return
    if isinstance(value, str):
        parsed = QDate.fromString(value, "yyyy-MM-dd")
    else:
        parsed = QDate(value.year, value.month, value.day)
    if parsed.isValid():
        edit.setDate(parsed)


def populate_sessions(
    combo: QComboBox, settings: SettingsService, select_id: int | None = None
) -> None:
    combo.blockSignals(True)
    current = select_id or settings.active_session_id()
    combo.clear()
    for session in settings.sessions():
        combo.addItem(session["name"], int(session["id"]))
    if current is not None:
        index = combo.findData(int(current))
        if index >= 0:
            combo.setCurrentIndex(index)
    combo.blockSignals(False)


def class_combo(include_all: bool = False) -> QComboBox:
    combo = QComboBox()
    if include_all:
        combo.addItem("All Classes", None)
    combo.addItem("Class 9", "9")
    combo.addItem("Class 10", "10")
    combo.setMinimumWidth(118)
    return combo


def current_session_start(settings: SettingsService) -> date:
    session = settings.get_session(settings.active_session_id())
    if session and session["start_date"]:
        parsed = QDate.fromString(session["start_date"], "yyyy-MM-dd")
        if parsed.isValid():
            return parsed.toPython()
    return date(date.today().year, 4, 1)


def muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("small")
    label.setWordWrap(True)
    return label


def pct_text(value: Any) -> str:
    return format_pct(value)


def hint_for_period(start: str, end: str) -> str:
    return f"{start} to {end}"
