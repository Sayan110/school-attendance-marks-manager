"""Attendance page: mark, edit and summarise Computer Science attendance."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.context import AppContext
from app.database import DatabaseError
from app.ui.common import class_combo, date_to_iso, make_date_edit, set_date_edit
from app.ui.icons import make_icon
from app.ui.widgets import (
    DataTable,
    EmptyState,
    InfoCard,
    StatCard,
    confirm_action,
    error_dialog,
    format_pct,
    info_dialog,
    notify,
    palette,
    set_variant,
)
from app.utils import dates as date_utils
from app.utils.validators import ValidationError

STATUS_OPTIONS = [
    ("Unmarked", None),
    ("Present", "P"),
    ("Absent", "A"),
    ("Leave", "L"),
]


class StudentHistoryDialog(QDialog):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.setWindowTitle("Student attendance history")
        self.resize(760, 560)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        title = QLabel("Student attendance history")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        controls = QHBoxLayout()
        self.class_combo = class_combo()
        self.student_combo = QComboBox()
        self.student_combo.setMinimumWidth(240)
        start = make_date_edit(date_utils.today() - timedelta(days=120))
        end = make_date_edit(date_utils.today())
        self.start_edit, self.end_edit = start, end
        load = QPushButton("Load")
        load.setIcon(make_icon("refresh", palette()["text"], 15))
        load.clicked.connect(self._load)
        controls.addWidget(QLabel("Class"))
        controls.addWidget(self.class_combo)
        controls.addWidget(QLabel("Student"))
        controls.addWidget(self.student_combo, 1)
        controls.addWidget(QLabel("From"))
        controls.addWidget(start)
        controls.addWidget(QLabel("To"))
        controls.addWidget(end)
        controls.addWidget(load)
        layout.addLayout(controls)
        self.summary = QLabel("—")
        self.summary.setObjectName("small")
        layout.addWidget(self.summary)
        self.table = DataTable(["Date", "Weekday", "Status", "Remarks"])
        self.table.apply_widths([100, 110, 100, 380])
        layout.addWidget(self.table, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self.class_combo.currentIndexChanged.connect(self._populate_students)
        self.student_combo.currentIndexChanged.connect(self._load)
        self._populate_students()

    def _populate_students(self) -> None:
        session_id = self.context.session_id
        class_name = self.class_combo.currentData()
        self.student_combo.blockSignals(True)
        self.student_combo.clear()
        if session_id:
            for student in self.context.students.all_students(session_id, class_name):
                self.student_combo.addItem(
                    f"{student['roll_no']} · {student['full_name']}", int(student["id"])
                )
        self.student_combo.blockSignals(False)
        if self.student_combo.count():
            self._load()
        else:
            self.table.set_data([])
            self.summary.setText("No students in this class.")

    def _load(self) -> None:
        student_id = self.student_combo.currentData()
        if not student_id:
            return
        start = date_to_iso(self.start_edit)
        end = date_to_iso(self.end_edit)
        summary = self.context.attendance.student_summary(int(student_id), start, end)
        history = [
            row for row in self.context.attendance.student_history(int(student_id), 3000)
            if start <= row["attendance_date"] <= end
        ]
        self.summary.setText(
            f"Present {summary['present']} · Absent {summary['absent']} · "
            f"Leave {summary['leave']} · Counted {summary['counted']} · "
            f"Attendance {format_pct(summary['percentage'])}  |  "
            f"{date_utils.display(start)} to {date_utils.display(end)}"
        )
        rows = []
        for row in history:
            parsed = date_utils.parse(row["attendance_date"])
            rows.append(
                [
                    date_utils.display(row["attendance_date"]),
                    parsed.strftime("%A") if parsed else "—",
                    {"P": "Present", "A": "Absent", "L": "Leave"}.get(row["status"], row["status"]),
                    row["remarks"] or "",
                ]
            )
        self.table.set_data(rows)


class HolidayDialog(QDialog):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.setWindowTitle("School holidays and non-instructional dates")
        self.resize(760, 520)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        title = QLabel("Holidays and non-instructional dates")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        note = QLabel(
            "Holiday dates are shown as H in monthly registers and are not counted in "
            "attendance percentages. Attendance can still be recorded on a holiday if "
            "the school actually held a session."
        )
        note.setObjectName("small")
        note.setWordWrap(True)
        layout.addWidget(note)
        add_row = QHBoxLayout()
        self.date_edit = make_date_edit(date.today())
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Holiday name, e.g. Independence Day")
        add = QPushButton("Add holiday")
        add.setIcon(make_icon("plus", "#ffffff", 15))
        set_variant(add, "primary")
        add.clicked.connect(self._add)
        delete = QPushButton("Delete selected")
        delete.setIcon(make_icon("trash", palette()["text"], 15))
        delete.clicked.connect(self._delete)
        add_row.addWidget(self.date_edit)
        add_row.addWidget(self.name_edit, 1)
        add_row.addWidget(add)
        add_row.addWidget(delete)
        layout.addLayout(add_row)
        self.table = DataTable(["Date", "Day", "Holiday"])
        self.table.apply_widths([120, 120, 400])
        self.table.setMinimumHeight(260)
        layout.addWidget(self.table, 1)
        close = QPushButton("Done")
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self._load()

    def _load(self) -> None:
        session_id = self.context.session_id
        if not session_id:
            return
        rows = self.context.attendance.holidays(session_id)
        data = []
        ids = []
        for row in rows:
            parsed = date_utils.parse(row["holiday_date"])
            data.append(
                [
                    date_utils.display(row["holiday_date"]),
                    parsed.strftime("%A") if parsed else "—",
                    row["name"],
                ]
            )
            ids.append(int(row["id"]))
        self.table.set_data(data, row_ids=ids)

    def _add(self) -> None:
        session_id = self.context.session_id
        if not session_id:
            return
        try:
            self.context.attendance.add_holiday(
                session_id, date_to_iso(self.date_edit), self.name_edit.text()
            )
        except ValidationError as exc:
            error_dialog(self, "Could not add holiday", str(exc))
            return
        self.name_edit.clear()
        self._load()
        notify(self, "Holiday saved.")

    def _delete(self) -> None:
        holiday_id = self.table.selected_row_id()
        if not holiday_id:
            info_dialog(self, "Select a holiday", "Select a holiday row to delete.")
            return
        if not confirm_action(
            self, "Delete holiday", "Remove this holiday date from the calendar?",
            confirm_text="Delete", danger=True,
        ):
            return
        self.context.attendance.delete_holiday(int(holiday_id))
        self._load()


class AttendancePage(QWidget):
    navigate = Signal(str)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._dirty = False
        self._loading = False
        self._day = None
        self._loaded_class = "9"
        self._loaded_date = date.today().isoformat()
        self._row_widgets: dict[int, tuple[QComboBox, QLineEdit]] = {}
        self._build()
        self.load_day()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("Attendance")
        title.setObjectName("pageTitle")
        titles.addWidget(title)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("pageSubtitle")
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        holidays = QPushButton("Holidays")
        holidays.setIcon(make_icon("attendance", palette()["text"], 15))
        holidays.clicked.connect(self.open_holidays)
        header.addWidget(holidays)
        history = QPushButton("Student history")
        history.setIcon(make_icon("reports", palette()["text"], 15))
        history.clicked.connect(self.open_history)
        header.addWidget(history)
        self.session_badge = QLabel("")
        self.session_badge.setObjectName("sessionBadge")
        header.addWidget(self.session_badge)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)

        # ---------------------------------------------------------- mark tab
        mark_tab = QWidget()
        mark_layout = QVBoxLayout(mark_tab)
        mark_layout.setContentsMargins(14, 14, 14, 14)
        mark_layout.setSpacing(10)

        filter_card = QFrame()
        filter_card.setObjectName("inset")
        filters = QHBoxLayout(filter_card)
        filters.setContentsMargins(12, 9, 12, 9)
        filters.setSpacing(8)
        filters.addWidget(QLabel("Class"))
        self.class_combo = class_combo()
        self.class_combo.currentIndexChanged.connect(self._filter_changed)
        filters.addWidget(self.class_combo)
        filters.addSpacing(6)
        filters.addWidget(QLabel("Date"))
        self.date_edit = make_date_edit(date.today())
        self.date_edit.dateChanged.connect(self._filter_changed)
        filters.addWidget(self.date_edit)
        today_button = QPushButton("Today")
        set_variant(today_button, "ghost")
        today_button.clicked.connect(lambda: self.date_edit.setDate(QDate.currentDate()))
        filters.addWidget(today_button)
        self.saved_badge = QLabel("Not saved")
        self.saved_badge.setProperty("tone", "warning")
        filters.addWidget(self.saved_badge)
        filters.addStretch(1)
        self.holiday_badge = QLabel("")
        self.holiday_badge.setProperty("tone", "warning")
        self.holiday_badge.hide()
        filters.addWidget(self.holiday_badge)
        mark_layout.addWidget(filter_card)

        counts_row = QHBoxLayout()
        counts_row.setSpacing(10)
        self.count_labels: dict[str, QLabel] = {}
        for key, label in (
            ("present", "Present"),
            ("absent", "Absent"),
            ("leave", "Leave"),
            ("unmarked", "Unmarked"),
            ("percentage", "Attendance %"),
        ):
            tile = QFrame()
            tile.setObjectName("card")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(12, 7, 12, 7)
            tile_layout.setSpacing(0)
            title_label = QLabel(label)
            title_label.setObjectName("statHint")
            value_label = QLabel("0")
            value_label.setObjectName("metric")
            tile_layout.addWidget(title_label)
            tile_layout.addWidget(value_label)
            self.count_labels[key] = value_label
            counts_row.addWidget(tile, 1)
        mark_layout.addLayout(counts_row)

        bulk = QHBoxLayout()
        bulk.setSpacing(7)
        for text, status in (("Mark all Present", "P"), ("Mark all Absent", "A"), ("Mark all Leave", "L")):
            button = QPushButton(text)
            set_variant(button, "ghost")
            button.clicked.connect(lambda _=False, s=status: self._mark_all(s))
            bulk.addWidget(button)
        clear_button = QPushButton("Clear all")
        set_variant(clear_button, "ghost")
        clear_button.clicked.connect(lambda: self._mark_all(None))
        bulk.addWidget(clear_button)
        bulk.addStretch(1)
        self.rule_hint = QLabel(
            "Leave is excluded from the attendance denominator. Unmarked students are not saved."
        )
        self.rule_hint.setObjectName("small")
        bulk.addWidget(self.rule_hint)
        mark_layout.addLayout(bulk)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Roll", "Student name", "Section", "Status", "Remarks"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 260)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 150)
        self.table.setMinimumHeight(240)
        mark_layout.addWidget(self.table, 1)

        self.empty = EmptyState(
            "No students to mark",
            "Add active students to this class before recording attendance.",
            icon="students",
            action_text="Go to Students",
        )
        if self.empty.button:
            self.empty.button.clicked.connect(lambda: self.navigate.emit("students"))
        self.empty.hide()
        mark_layout.addWidget(self.empty, 1)

        self.dirty_banner = QFrame()
        self.dirty_banner.setObjectName("card")
        self.dirty_banner.setStyleSheet(
            f"QFrame#card {{ background: {palette()['warning_soft']};"
            f" border: 1px solid {palette()['warning']}; border-radius: 8px; }}"
        )
        dirty_layout = QHBoxLayout(self.dirty_banner)
        dirty_layout.setContentsMargins(10, 5, 8, 5)
        dirty_label = QLabel("Unsaved changes — save before leaving this page.")
        dirty_label.setStyleSheet(f"color: {palette()['warning']}; font-weight: 600;")
        dirty_layout.addWidget(dirty_label)
        dirty_layout.addStretch(1)
        discard = QPushButton("Discard")
        set_variant(discard, "ghost")
        discard.clicked.connect(self.discard_changes)
        dirty_layout.addWidget(discard)
        save_quick = QPushButton("Save now")
        set_variant(save_quick, "primary")
        save_quick.clicked.connect(self.save)
        dirty_layout.addWidget(save_quick)
        self.dirty_banner.hide()
        mark_layout.addWidget(self.dirty_banner)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.save_button = QPushButton("Save attendance")
        self.save_button.setIcon(make_icon("check", "#ffffff", 15))
        set_variant(self.save_button, "primary")
        self.save_button.clicked.connect(self.save)
        bottom.addWidget(self.save_button)
        mark_layout.addLayout(bottom)
        self.tabs.addTab(mark_tab, "Mark attendance")

        # ------------------------------------------------------- summary tab
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        summary_layout.setContentsMargins(14, 14, 14, 14)
        summary_layout.setSpacing(10)
        controls = QFrame()
        controls.setObjectName("inset")
        control_row = QHBoxLayout(controls)
        control_row.setContentsMargins(12, 9, 12, 9)
        control_row.setSpacing(8)
        control_row.addWidget(QLabel("Period"))
        self.period_combo = QComboBox()
        self.period_combo.addItems(["Daily", "Weekly", "Monthly", "Custom range"])
        self.period_combo.currentIndexChanged.connect(self._period_changed)
        control_row.addWidget(self.period_combo)
        self.summary_start = make_date_edit(date.today())
        self.summary_end = make_date_edit(date.today())
        self.summary_start.dateChanged.connect(self.refresh_summary)
        self.summary_end.dateChanged.connect(self.refresh_summary)
        control_row.addWidget(self.summary_start)
        control_row.addWidget(QLabel("to"))
        control_row.addWidget(self.summary_end)
        control_row.addStretch(1)
        refresh = QPushButton("Refresh summary")
        refresh.setIcon(make_icon("refresh", palette()["text"], 15))
        refresh.clicked.connect(self.refresh_summary)
        control_row.addWidget(refresh)
        summary_layout.addWidget(controls)
        self.summary_period_label = QLabel("")
        self.summary_period_label.setObjectName("small")
        summary_layout.addWidget(self.summary_period_label)
        self.summary_cards: dict[str, StatCard] = {}
        summary_cards_row = QHBoxLayout()
        summary_cards_row.setSpacing(10)
        for key, label, icon, accent in (
            ("present", "Present sessions", "check", "success"),
            ("absent", "Absent sessions", "warning", "danger"),
            ("leave", "Leave sessions", "attendance", "warning"),
            ("percentage", "Attendance %", "analytics", "info"),
        ):
            card = StatCard(label, "—", "Recorded sessions only", icon, accent)
            card.setMinimumHeight(100)
            self.summary_cards[key] = card
            summary_cards_row.addWidget(card, 1)
        summary_layout.addLayout(summary_cards_row)
        self.breakdown = DataTable(["Date", "Day", "Present", "Absent", "Leave", "Attendance %", "Note"])
        self.breakdown.apply_widths([110, 110, 80, 80, 70, 110, 200])
        summary_layout.addWidget(self.breakdown, 1)
        summary_note = QLabel(
            "Only dates with saved attendance are listed. Holidays are annotated and are "
            "not counted. Unmarked sessions are never treated as absences."
        )
        summary_note.setObjectName("small")
        summary_note.setWordWrap(True)
        summary_layout.addWidget(summary_note)
        self.tabs.addTab(summary_tab, "Summaries")

        self._status_shortcuts = []
        for key, status in (("P", "P"), ("A", "A"), ("L", "L")):
            shortcut = QShortcut(QKeySequence(key), self.table)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(lambda s=status: self._mark_selected(s))
            self._status_shortcuts.append(shortcut)

    # ------------------------------------------------------------------ data
    def refresh(self) -> None:
        self.subtitle.setText(
            f"{self.context.settings.school_name} · {self.context.settings.subject} · "
            f"Session {self.context.settings.active_session_name()}"
        )
        self.session_badge.setText(f"Session {self.context.settings.active_session_name()}")
        if not self._dirty:
            self.load_day()
        else:
            self.refresh_summary()

    def _filter_changed(self) -> None:
        if self._loading:
            return
        new_class = self.class_combo.currentData() or "9"
        new_date = date_to_iso(self.date_edit)
        if self._dirty:
            if not confirm_action(
                self,
                "Unsaved attendance",
                "You have unsaved attendance changes. Discard them and load another session?",
                confirm_text="Discard and load",
                danger=True,
            ):
                self._loading = True
                index = self.class_combo.findData(self._loaded_class)
                if index >= 0:
                    self.class_combo.setCurrentIndex(index)
                set_date_edit(self.date_edit, self._loaded_date)
                self._loading = False
                return
        self._loaded_class = new_class
        self._loaded_date = new_date
        self.load_day()

    def load_day(self) -> None:
        session_id = self.context.session_id
        if session_id is None:
            return
        class_name = self.class_combo.currentData() or "9"
        on_date = date_to_iso(self.date_edit)
        try:
            day = self.context.attendance.load_day(session_id, class_name, on_date)
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not load attendance", str(exc))
            return
        self._day = day
        self._loading = True
        self.table.setRowCount(0)
        self._row_widgets.clear()
        for row_index, entry in enumerate(day.entries):
            self.table.insertRow(row_index)
            roll_item = QTableWidgetItem(entry.roll_no)
            roll_item.setData(Qt.ItemDataRole.UserRole, entry.student_id)
            name_item = QTableWidgetItem(entry.full_name)
            section_item = QTableWidgetItem(entry.section or "—")
            for column, item in enumerate((roll_item, name_item, section_item)):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_index, column, item)
            combo = QComboBox()
            for label, value in STATUS_OPTIONS:
                combo.addItem(label, value)
            index = max(0, combo.findData(entry.status))
            combo.setCurrentIndex(index)
            self._style_status(combo)
            combo.currentIndexChanged.connect(
                lambda _=0, student_id=entry.student_id, widget=combo: self._status_changed(
                    student_id, widget
                )
            )
            self.table.setCellWidget(row_index, 3, combo)
            remarks = QLineEdit(entry.remarks or "")
            remarks.setPlaceholderText("Optional")
            remarks.textEdited.connect(lambda _text: self._set_dirty(True))
            self.table.setCellWidget(row_index, 4, remarks)
            self._row_widgets[entry.student_id] = (combo, remarks)
        self._loading = False
        self._set_dirty(False)
        self._update_counts()
        self._update_saved_badge()
        has_students = bool(day.entries)
        self.table.setVisible(has_students)
        self.empty.setVisible(not has_students)
        if day.is_holiday:
            self.holiday_badge.setText(f"Holiday · {day.holiday_name}")
            self.holiday_badge.show()
        else:
            self.holiday_badge.hide()
        self.refresh_summary()

    def _style_status(self, combo: QComboBox) -> None:
        status = combo.currentData()
        colors = {
            "P": (palette()["success_soft"], palette()["success"]),
            "A": (palette()["danger_soft"], palette()["danger"]),
            "L": (palette()["warning_soft"], palette()["warning"]),
            None: (palette()["surface_sunken"], palette()["text_muted"]),
        }
        background, foreground = colors.get(status, colors[None])
        combo.setStyleSheet(
            f"QComboBox {{ background: {background}; color: {foreground};"
            f" border: 1px solid {palette()['border']}; border-radius: 6px;"
            f" padding: 4px 8px; font-weight: 600; }}"
        )

    def _status_changed(self, student_id: int, combo: QComboBox) -> None:
        self._style_status(combo)
        if not self._loading:
            self._set_dirty(True)
            self._update_counts()

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self.dirty_banner.setVisible(dirty)
        self._update_saved_badge()

    def _update_counts(self) -> None:
        present = absent = leave = unmarked = 0
        for combo, _ in self._row_widgets.values():
            status = combo.currentData()
            if status == "P":
                present += 1
            elif status == "A":
                absent += 1
            elif status == "L":
                leave += 1
            else:
                unmarked += 1
        percentage = None
        if present + absent:
            percentage = round(present / (present + absent) * 100, 2)
        self.count_labels["present"].setText(str(present))
        self.count_labels["absent"].setText(str(absent))
        self.count_labels["leave"].setText(str(leave))
        self.count_labels["unmarked"].setText(str(unmarked))
        self.count_labels["percentage"].setText(format_pct(percentage))

    def _update_saved_badge(self) -> None:
        if self._dirty:
            self.saved_badge.setText("Unsaved changes")
            self.saved_badge.setProperty("tone", "warning")
        elif self._day and self._day.saved:
            stamp = (self._day.saved_at or "")[:16]
            self.saved_badge.setText(f"Saved {stamp}")
            self.saved_badge.setProperty("tone", "success")
        else:
            self.saved_badge.setText("Not saved")
            self.saved_badge.setProperty("tone", "warning")
        self.saved_badge.style().unpolish(self.saved_badge)
        self.saved_badge.style().polish(self.saved_badge)

    # --------------------------------------------------------------- actions
    def _mark_all(self, status: str | None) -> None:
        if not self._row_widgets:
            return
        self._loading = True
        for combo, _ in self._row_widgets.values():
            index = combo.findData(status)
            if index >= 0:
                combo.setCurrentIndex(index)
            self._style_status(combo)
        self._loading = False
        self._set_dirty(True)
        self._update_counts()

    def _mark_selected(self, status: str) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        student_id = item.data(Qt.ItemDataRole.UserRole)
        widgets = self._row_widgets.get(int(student_id))
        if not widgets:
            return
        combo, _ = widgets
        index = combo.findData(status)
        if index >= 0:
            combo.setCurrentIndex(index)

    def save(self) -> None:
        session_id = self.context.session_id
        if session_id is None or self._day is None:
            return
        class_name = self.class_combo.currentData() or "9"
        on_date = date_to_iso(self.date_edit)
        entries = []
        for student_id, (combo, remarks) in self._row_widgets.items():
            entries.append(
                {
                    "student_id": student_id,
                    "status": combo.currentData(),
                    "remarks": remarks.text(),
                }
            )
        if not any(entry["status"] for entry in entries):
            error_dialog(
                self,
                "Nothing marked",
                "Mark at least one student Present, Absent or Leave before saving. "
                "Unmarked students are not saved and are never counted as absent.",
            )
            return
        overwrite = bool(self._day.saved)
        if overwrite and not confirm_action(
            self,
            "Overwrite saved attendance",
            f"Attendance for Class {class_name} on {date_utils.display(on_date)} is already "
            "saved. Do you want to replace the saved session?",
            confirm_text="Overwrite",
            danger=True,
        ):
            return
        if self._day.is_holiday and not confirm_action(
            self,
            "Holiday date",
            f"{date_utils.display(on_date)} is marked as a holiday "
            f"({self._day.holiday_name}). Save attendance anyway?",
            confirm_text="Save anyway",
        ):
            return
        try:
            counts = self.context.attendance.save_day(
                session_id,
                class_name,
                on_date,
                entries,
                marked_by=self.context.settings.teacher_name,
                overwrite=True,
            )
        except ValidationError as exc:
            error_dialog(self, "Could not save attendance", str(exc))
            return
        except DatabaseError as exc:
            error_dialog(self, "Database error", str(exc))
            return
        notify(
            self,
            f"Attendance saved — {counts.present} present, {counts.absent} absent, "
            f"{counts.leave} leave.",
        )
        self.load_day()

    def discard_changes(self) -> None:
        if not self._dirty:
            return
        if confirm_action(
            self,
            "Discard changes",
            "Discard all unsaved attendance changes for this session?",
            confirm_text="Discard",
            danger=True,
        ):
            self.load_day()

    def has_unsaved_changes(self) -> bool:
        return self._dirty

    def confirm_discard(self, parent: QWidget | None = None) -> bool:
        if not self._dirty:
            return True
        return confirm_action(
            parent or self,
            "Unsaved attendance",
            "Attendance changes have not been saved. Discard them and continue?",
            confirm_text="Discard changes",
            danger=True,
        )

    # -------------------------------------------------------------- summaries
    def _tab_changed(self, index: int) -> None:
        if index == 1:
            self.refresh_summary()

    def _period_changed(self) -> None:
        index = self.period_combo.currentIndex()
        anchor = date_to_iso(self.date_edit)
        parsed = date_utils.parse(anchor) or date.today()
        self.summary_start.blockSignals(True)
        self.summary_end.blockSignals(True)
        self.summary_start.setEnabled(index == 3)
        self.summary_end.setEnabled(index == 3)
        if index == 0:
            set_date_edit(self.summary_start, parsed)
            set_date_edit(self.summary_end, parsed)
        elif index == 1:
            start, end = date_utils.week_bounds(parsed)
            set_date_edit(self.summary_start, start)
            set_date_edit(self.summary_end, end)
        elif index == 2:
            start, end = date_utils.month_bounds(parsed.year, parsed.month)
            set_date_edit(self.summary_start, start)
            set_date_edit(self.summary_end, end)
        self.summary_start.blockSignals(False)
        self.summary_end.blockSignals(False)
        self.refresh_summary()

    def refresh_summary(self) -> None:
        session_id = self.context.session_id
        if session_id is None:
            return
        class_name = self.class_combo.currentData() or "9"
        start = date_to_iso(self.summary_start)
        end = date_to_iso(self.summary_end)
        if start > end:
            start, end = end, start
        summary = self.context.attendance.range_summary(session_id, class_name, start, end)
        self.summary_period_label.setText(
            f"Class {class_name} · {date_utils.display(start)} to {date_utils.display(end)} · "
            f"{summary['sessions']} session day(s) recorded"
        )
        self.summary_cards["present"].set_value(summary["present"])
        self.summary_cards["absent"].set_value(summary["absent"])
        self.summary_cards["leave"].set_value(summary["leave"])
        self.summary_cards["percentage"].set_value(format_pct(summary["percentage"]))
        rows = self.context.attendance.daily_breakdown(session_id, class_name, start, end)
        data = [
            [
                date_utils.display(row["date"]),
                (date_utils.parse(row["date"]) or date.today()).strftime("%A"),
                row["present"],
                row["absent"],
                row["leave"],
                format_pct(row["percentage"]),
                f"Holiday · {row['holiday']}" if row["holiday"] else "",
            ]
            for row in rows
        ]
        self.breakdown.set_data(data)

    def open_history(self) -> None:
        dialog = StudentHistoryDialog(self.context, self)
        dialog.exec()

    def open_holidays(self) -> None:
        dialog = HolidayDialog(self.context, self)
        dialog.exec()
        if not self._dirty:
            self.load_day()
