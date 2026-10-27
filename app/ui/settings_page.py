"""Settings page: school identity, sessions, thresholds, grades and theme."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.context import AppContext
from app.database import DatabaseError
from app.ui.common import date_to_iso, make_date_edit, set_date_edit
from app.ui.icons import make_icon
from app.ui.widgets import (
    PageHeader,
    confirm_action,
    error_dialog,
    info_dialog,
    notify,
    palette,
    set_variant,
)
from app.utils.validators import ValidationError


class SessionDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        session: object | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Academic session")
        self.setModal(True)
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(10)
        title = QLabel("Academic session")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        form = QFormLayout()
        form.setSpacing(8)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. 2026-2027")
        form.addRow("Session name *", self.name_edit)
        self.start_edit = make_date_edit(QDate.currentDate().toPython())
        self.end_edit = make_date_edit(
            QDate.currentDate().addYears(1).addDays(-1).toPython()
        )
        form.addRow("Start date", self.start_edit)
        form.addRow("End date", self.end_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save session")
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("variant", "primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if session:
            self.name_edit.setText(str(session["name"]))
            if session["start_date"]:
                set_date_edit(self.start_edit, session["start_date"])
            if session["end_date"]:
                set_date_edit(self.end_edit, session["end_date"])


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    session_changed = Signal(int)
    settings_saved = Signal()

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(12)
        outer.addWidget(
            PageHeader(
                "Settings",
                "School identity, academic sessions, attendance and pass rules, grade scale, "
                "theme and backups.",
            )
        )
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self._build_school_tab()
        self._build_rules_tab()
        self._build_grades_tab()
        self._build_theme_tab()

    def _scroll(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout = page.layout()
        if layout is None:
            layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        scroll.setWidget(page)
        return scroll

    def _build_school_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        identity = QFrame()
        identity.setObjectName("card")
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(16, 14, 16, 14)
        identity_layout.setSpacing(8)
        title = QLabel("School and teacher")
        title.setObjectName("cardTitle")
        identity_layout.addWidget(title)
        form = QFormLayout()
        form.setSpacing(8)
        self.school_edit = QLineEdit()
        form.addRow("School name *", self.school_edit)
        self.teacher_edit = QLineEdit()
        self.teacher_edit.setPlaceholderText("Teacher name shown on reports")
        form.addRow("Teacher name", self.teacher_edit)
        self.designation_edit = QLineEdit()
        form.addRow("Designation", self.designation_edit)
        self.subject_edit = QLineEdit()
        form.addRow("Subject", self.subject_edit)
        self.board_edit = QLineEdit()
        form.addRow("Board", self.board_edit)
        identity_layout.addLayout(form)
        save_identity = QPushButton("Save school details")
        save_identity.setIcon(make_icon("check", "#ffffff", 15))
        set_variant(save_identity, "primary")
        save_identity.clicked.connect(self._save_identity)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(save_identity)
        identity_layout.addLayout(row)
        layout.addWidget(identity)

        sessions = QFrame()
        sessions.setObjectName("card")
        sessions_layout = QVBoxLayout(sessions)
        sessions_layout.setContentsMargins(16, 14, 16, 14)
        sessions_layout.setSpacing(8)
        sessions_title = QLabel("Academic sessions")
        sessions_title.setObjectName("cardTitle")
        sessions_layout.addWidget(sessions_title)
        note = QLabel(
            "The active session filters students, attendance, examinations and reports across "
            "the whole application."
        )
        note.setObjectName("small")
        note.setWordWrap(True)
        sessions_layout.addWidget(note)
        self.session_table = QTableWidget(0, 4)
        self.session_table.setHorizontalHeaderLabels(["Session", "Start", "End", "Active"])
        self.session_table.verticalHeader().setVisible(False)
        self.session_table.verticalHeader().setDefaultSectionSize(34)
        self.session_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.session_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.session_table.horizontalHeader().setStretchLastSection(True)
        for index, width in enumerate((160, 120, 120, 80)):
            self.session_table.setColumnWidth(index, width)
        self.session_table.setMinimumHeight(180)
        # Keep the action buttons above the fold; the table scrolls when a
        # school keeps many historical sessions.
        self.session_table.setMaximumHeight(260)
        sessions_layout.addWidget(self.session_table)
        buttons = QHBoxLayout()
        add = QPushButton("Add session")
        add.setIcon(make_icon("plus", palette()["text"], 15))
        add.clicked.connect(self._add_session)
        buttons.addWidget(add)
        edit = QPushButton("Edit session")
        edit.setIcon(make_icon("edit", palette()["text"], 15))
        edit.clicked.connect(self._edit_session)
        buttons.addWidget(edit)
        activate = QPushButton("Set active session")
        activate.setIcon(make_icon("check", "#ffffff", 15))
        set_variant(activate, "primary")
        activate.clicked.connect(self._activate_session)
        buttons.addWidget(activate)
        buttons.addStretch(1)
        sessions_layout.addLayout(buttons)
        layout.addWidget(sessions)
        layout.addStretch(1)
        self.tabs.addTab(self._scroll(page), "School & sessions")

    def _build_rules_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)
        title = QLabel("Attendance and performance rules")
        title.setObjectName("cardTitle")
        card_layout.addWidget(title)
        form = QFormLayout()
        form.setSpacing(10)
        self.attendance_threshold = QDoubleSpinBox()
        self.attendance_threshold.setRange(0, 100)
        self.attendance_threshold.setDecimals(1)
        self.attendance_threshold.setSuffix("%")
        form.addRow("Attendance warning threshold", self.attendance_threshold)
        self.performance_threshold = QDoubleSpinBox()
        self.performance_threshold.setRange(0, 100)
        self.performance_threshold.setDecimals(1)
        self.performance_threshold.setSuffix("%")
        form.addRow("Marks support threshold", self.performance_threshold)
        self.default_pass = QDoubleSpinBox()
        self.default_pass.setRange(0, 100)
        self.default_pass.setDecimals(1)
        self.default_pass.setSuffix("%")
        form.addRow("Default pass percentage", self.default_pass)
        self.leave_check = QCheckBox(
            "Exclude Leave from the attendance percentage denominator"
        )
        form.addRow("Leave handling", self.leave_check)
        card_layout.addLayout(form)
        explanation = QLabel(
            "Attendance % = present ÷ counted sessions × 100. When Leave is excluded, counted "
            "sessions are Present + Absent. When it is included, counted sessions are Present + "
            "Absent + Leave. Unmarked sessions are never counted as absences. Pass percentages "
            "count absentees as not passed and exclude exempted or pending students."
        )
        explanation.setObjectName("small")
        explanation.setWordWrap(True)
        card_layout.addWidget(explanation)
        save = QPushButton("Save rules")
        save.setIcon(make_icon("check", "#ffffff", 15))
        set_variant(save, "primary")
        save.clicked.connect(self._save_rules)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(save)
        card_layout.addLayout(row)
        layout.addWidget(card)
        layout.addStretch(1)
        self.tabs.addTab(self._scroll(page), "Rules")

    def _build_grades_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        note = QLabel(
            "Grade rules are fully configurable by the teacher. They are not an official SEBA "
            "grade scale; the default seed is a generic A+ to F scale."
        )
        note.setObjectName("small")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.grade_table = QTableWidget(0, 4)
        self.grade_table.setHorizontalHeaderLabels(["Grade", "Minimum %", "Maximum %", "Description"])
        self.grade_table.verticalHeader().setVisible(False)
        self.grade_table.verticalHeader().setDefaultSectionSize(34)
        self.grade_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.grade_table.horizontalHeader().setStretchLastSection(True)
        for index, width in enumerate((90, 110, 110, 330)):
            self.grade_table.setColumnWidth(index, width)
        self.grade_table.setMinimumHeight(280)
        layout.addWidget(self.grade_table)
        buttons = QHBoxLayout()
        add = QPushButton("Add grade")
        add.setIcon(make_icon("plus", palette()["text"], 15))
        add.clicked.connect(self._add_grade_row)
        buttons.addWidget(add)
        remove = QPushButton("Remove selected")
        remove.setIcon(make_icon("trash", palette()["text"], 15))
        remove.clicked.connect(self._remove_grade_row)
        buttons.addWidget(remove)
        reset = QPushButton("Reset to default scale")
        reset.clicked.connect(self._reset_grades)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        save = QPushButton("Save grade scale")
        save.setIcon(make_icon("check", "#ffffff", 15))
        set_variant(save, "primary")
        save.clicked.connect(self._save_grades)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self.tabs.addTab(self._scroll(page), "Grades")

    def _build_theme_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)
        title = QLabel("Appearance")
        title.setObjectName("cardTitle")
        card_layout.addWidget(title)
        note = QLabel(
            "Theme changes apply immediately and are remembered for the next launch. Pages are "
            "rebuilt so icons and charts keep the correct contrast."
        )
        note.setObjectName("small")
        note.setWordWrap(True)
        card_layout.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(QLabel("Theme"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.currentIndexChanged.connect(self._theme_selected)
        row.addWidget(self.theme_combo)
        row.addStretch(1)
        card_layout.addLayout(row)
        layout.addWidget(card)
        note2 = QLabel(
            "Use the Backup page in the sidebar to create, validate and restore database backups."
        )
        note2.setObjectName("small")
        note2.setWordWrap(True)
        layout.addWidget(note2)
        layout.addStretch(1)
        self.tabs.addTab(self._scroll(page), "Appearance")

    # ---------------------------------------------------------------- refresh
    def refresh(self) -> None:
        settings = self.context.settings
        self.school_edit.setText(settings.school_name)
        self.teacher_edit.setText(settings.teacher_name)
        self.designation_edit.setText(settings.get("teacher_designation", ""))
        self.subject_edit.setText(settings.subject)
        self.board_edit.setText(settings.board)
        self.attendance_threshold.setValue(settings.attendance_threshold)
        self.performance_threshold.setValue(settings.performance_threshold)
        self.default_pass.setValue(settings.get_float("default_pass_percent", 33))
        self.leave_check.setChecked(settings.leave_excluded)
        self.theme_combo.blockSignals(True)
        index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self.theme_combo.blockSignals(False)
        self._load_sessions()
        self._load_grades()

    def _load_sessions(self) -> None:
        self.session_table.setRowCount(0)
        active_id = self.context.session_id
        for row, session in enumerate(self.context.settings.sessions()):
            self.session_table.insertRow(row)
            values = [
                str(session["name"]),
                session["start_date"] or "—",
                session["end_date"] or "—",
                "Active" if active_id == int(session["id"]) else "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, int(session["id"]))
                if column == 3 and value:
                    item.setForeground(Qt.GlobalColor.darkGreen)
                self.session_table.setItem(row, column, item)

    def _load_grades(self) -> None:
        self.grade_table.setRowCount(0)
        for row, rule in enumerate(self.context.settings.grade_rules()):
            self.grade_table.insertRow(row)
            values = [
                str(rule["grade"]),
                f"{float(rule['min_percent']):g}",
                f"{float(rule['max_percent']):g}",
                rule["description"] or "",
            ]
            for column, value in enumerate(values):
                self.grade_table.setItem(row, column, QTableWidgetItem(value))

    # ------------------------------------------------------------------ saves
    def _save_identity(self) -> None:
        school = self.school_edit.text().strip()
        if not school:
            error_dialog(self, "School name required", "Enter the school name.")
            return
        try:
            self.context.settings.set_many(
                {
                    "school_name": school,
                    "teacher_name": self.teacher_edit.text().strip(),
                    "teacher_designation": self.designation_edit.text().strip(),
                    "subject": self.subject_edit.text().strip() or config.DEFAULT_SUBJECT,
                    "board": self.board_edit.text().strip() or config.SCHOOL_BOARD,
                }
            )
        except DatabaseError as exc:
            error_dialog(self, "Could not save settings", str(exc))
            return
        self.settings_saved.emit()
        notify(self, "School details saved.")

    def _save_rules(self) -> None:
        try:
            self.context.settings.set_many(
                {
                    "attendance_threshold": f"{self.attendance_threshold.value():g}",
                    "performance_threshold": f"{self.performance_threshold.value():g}",
                    "default_pass_percent": f"{self.default_pass.value():g}",
                    "leave_excluded_from_percentage": "1" if self.leave_check.isChecked() else "0",
                }
            )
        except DatabaseError as exc:
            error_dialog(self, "Could not save rules", str(exc))
            return
        self.settings_saved.emit()
        notify(self, "Attendance and pass rules saved.")

    def _save_grades(self) -> None:
        rules = []
        for row in range(self.grade_table.rowCount()):
            grade = self._cell(row, 0)
            if not grade:
                continue
            rules.append(
                {
                    "grade": grade,
                    "min_percent": self._cell(row, 1),
                    "max_percent": self._cell(row, 2),
                    "description": self._cell(row, 3),
                }
            )
        try:
            self.context.settings.save_grade_rules(rules)
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not save grade scale", str(exc))
            return
        self._load_grades()
        self.settings_saved.emit()
        notify(self, "Grade scale saved.")

    def _reset_grades(self) -> None:
        if not confirm_action(
            self,
            "Reset grade scale",
            "Replace the current grade rules with the generic default A+ to F scale?",
            confirm_text="Reset grades",
            danger=True,
        ):
            return
        self.context.settings.reset_grade_rules()
        self._load_grades()
        notify(self, "Default grade scale restored.", "info")

    def _cell(self, row: int, column: int) -> str:
        item = self.grade_table.item(row, column)
        return item.text().strip() if item else ""

    def _add_grade_row(self) -> None:
        row = self.grade_table.rowCount()
        self.grade_table.insertRow(row)
        for column, value in enumerate(("", "0", "0", "")):
            self.grade_table.setItem(row, column, QTableWidgetItem(value))
        self.grade_table.setCurrentCell(row, 0)

    def _remove_grade_row(self) -> None:
        row = self.grade_table.currentRow()
        if row >= 0:
            self.grade_table.removeRow(row)

    # --------------------------------------------------------------- sessions
    def _selected_session(self):
        row = self.session_table.currentRow()
        if row < 0:
            return None
        item = self.session_table.item(row, 0)
        if item is None:
            return None
        return self.context.settings.get_session(int(item.data(Qt.ItemDataRole.UserRole)))

    def _add_session(self) -> None:
        dialog = SessionDialog(self)
        if not dialog.exec():
            return
        try:
            self.context.settings.add_session(
                dialog.name_edit.text(),
                date_to_iso(dialog.start_edit),
                date_to_iso(dialog.end_edit),
            )
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not add session", str(exc))
            return
        self._load_sessions()
        notify(self, "Academic session added.")

    def _edit_session(self) -> None:
        session = self._selected_session()
        if session is None:
            info_dialog(self, "Select a session", "Select a session row first.")
            return
        dialog = SessionDialog(self, session)
        if not dialog.exec():
            return
        try:
            self.context.settings.update_session(
                int(session["id"]),
                dialog.name_edit.text(),
                date_to_iso(dialog.start_edit),
                date_to_iso(dialog.end_edit),
            )
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not update session", str(exc))
            return
        self._load_sessions()
        self.settings_saved.emit()
        notify(self, "Academic session updated.")

    def _activate_session(self) -> None:
        session = self._selected_session()
        if session is None:
            info_dialog(self, "Select a session", "Select a session row first.")
            return
        try:
            self.context.settings.set_active_session(int(session["id"]))
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not activate session", str(exc))
            return
        self._load_sessions()
        self.session_changed.emit(int(session["id"]))
        notify(self, f"Active session is now {session['name']}.")

    # ------------------------------------------------------------------ theme
    def _theme_selected(self) -> None:
        name = self.theme_combo.currentData()
        if not name:
            return
        self.context.settings.set("theme", name)
        self.theme_changed.emit(str(name))
