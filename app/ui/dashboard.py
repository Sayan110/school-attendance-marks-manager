"""Dashboard page: live school-wide statistics from the local database."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.context import AppContext
from app.ui.common import (
    class_combo,
    current_session_start,
    date_to_iso,
    make_date_edit,
    populate_sessions,
    set_date_edit,
)
from app.ui.icons import make_icon, school_logo
from app.ui.widgets import (
    DataTable,
    EmptyState,
    InfoCard,
    ScrollPage,
    StatCard,
    clear_layout,
    format_pct,
    palette,
    set_variant,
)


class DashboardPage(ScrollPage):
    navigate = Signal(str)
    session_change_requested = Signal(int)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._loading = False
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        header_row = QHBoxLayout()
        header = QVBoxLayout()
        header.setSpacing(1)
        title = QLabel("Dashboard")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        self.welcome = QLabel("Live overview of attendance and Computer Science performance.")
        self.welcome.setObjectName("pageSubtitle")
        header.addWidget(self.welcome)
        header_row.addLayout(header)
        header_row.addStretch(1)
        today = QLabel(date.today().strftime("%A, %d %B %Y"))
        today.setObjectName("dateBadge")
        header_row.addWidget(today)
        self.layout.addLayout(header_row)

        # Filters -----------------------------------------------------------
        self.filter_card = QFrame()
        self.filter_card.setObjectName("card")
        filters = QHBoxLayout(self.filter_card)
        filters.setContentsMargins(14, 11, 14, 11)
        filters.setSpacing(10)

        filters.addWidget(self._label("Session"))
        self.session_combo = QComboBox()
        self.session_combo.setMinimumWidth(126)
        populate_sessions(self.session_combo, self.context.settings)
        self.session_combo.currentIndexChanged.connect(self._session_changed)
        filters.addWidget(self.session_combo)

        filters.addWidget(self._label("Class"))
        self.class_combo = class_combo(include_all=True)
        self.class_combo.currentIndexChanged.connect(self._filters_changed)
        filters.addWidget(self.class_combo)

        filters.addWidget(self._label("Period"))
        self.preset = QComboBox()
        self.preset.addItems(["This month", "Last 30 days", "This academic session", "Custom range"])
        self.preset.setMinimumWidth(150)
        self.preset.currentIndexChanged.connect(self._preset_changed)
        filters.addWidget(self.preset)

        self.start_edit = make_date_edit(date.today().replace(day=1))
        self.end_edit = make_date_edit(date.today())
        self.start_edit.dateChanged.connect(self._filters_changed)
        self.end_edit.dateChanged.connect(self._filters_changed)
        filters.addWidget(self.start_edit)
        filters.addWidget(QLabel("to"))
        filters.addWidget(self.end_edit)
        filters.addStretch(1)
        refresh_button = QPushButton("Refresh")
        refresh_button.setIcon(make_icon("refresh", palette()["text"], 15))
        refresh_button.clicked.connect(self.refresh)
        filters.addWidget(refresh_button)
        self.layout.addWidget(self.filter_card)

        self.rule_note = QLabel(
            "Attendance % = present ÷ counted sessions. Leave is excluded from the denominator "
            "and unmarked sessions are never counted as absences."
        )
        self.rule_note.setObjectName("small")
        self.rule_note.setWordWrap(True)
        self.layout.addWidget(self.rule_note)

        # Empty state -------------------------------------------------------
        self.empty = EmptyState(
            "No students yet",
            "Add Class 9 or Class 10 students (or import a CSV/Excel file) to start recording "
            "attendance and Computer Science marks. This dashboard will populate itself from "
            "your saved records — no statistics are pre-filled.",
            icon="students",
            action_text="Add your first student",
        )
        if self.empty.button:
            self.empty.button.clicked.connect(lambda: self.navigate.emit("students"))
        self.layout.addWidget(self.empty)
        self.empty.hide()

        # Body --------------------------------------------------------------
        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)

        self.cards: dict[str, StatCard] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        card_specs = [
            ("class9", "Class 9 students", "students", "primary", "Active students"),
            ("class10", "Class 10 students", "students", "primary", "Active students"),
            ("present", "Present today", "check", "success", "Recorded today"),
            ("absent", "Absent today", "warning", "danger", "Recorded today"),
            ("leave", "On leave today", "attendance", "warning", "Recorded today"),
            ("attendance", "Attendance %", "attendance", "info", "Selected period"),
            ("average", "Average CS marks", "marks", "accent", "Selected period"),
            ("pass", "Pass %", "check", "success", "Selected period"),
            ("support", "Needs support", "students", "warning", "Marks or attendance"),
            ("below", "Below attendance threshold", "warning", "danger", "Selected period"),
        ]
        for index, (key, label, icon, accent, hint) in enumerate(card_specs):
            card = StatCard(label, "—", hint, icon, accent)
            self.cards[key] = card
            grid.addWidget(card, index // 5, index % 5)
        for column in range(5):
            grid.setColumnStretch(column, 1)
        body_layout.addLayout(grid)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        self.activity_card = InfoCard("Recent activity")
        self.activity_card.setMinimumHeight(260)
        self.activity_box = self.activity_card.body
        bottom.addWidget(self.activity_card, 1)

        self.attention_card = InfoCard("Students needing attention")
        self.attention_table = DataTable(
            ["Roll", "Student", "Class", "Attendance", "Avg marks", "Reason"]
        )
        self.attention_table.setMinimumHeight(220)
        self.attention_table.apply_widths([55, 150, 55, 85, 80, 190])
        self.attention_card.body.addWidget(self.attention_table)
        self.attention_empty = QLabel("No student is below the configured thresholds.")
        self.attention_empty.setObjectName("small")
        self.attention_empty.setWordWrap(True)
        self.attention_empty.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.attention_card.body.addWidget(self.attention_empty)
        bottom.addWidget(self.attention_card, 1)
        body_layout.addLayout(bottom)

        self.layout.addWidget(self.body)
        self.layout.addStretch(1)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("small")
        label.setStyleSheet("font-weight: 600;")
        return label

    # ---------------------------------------------------------------- filters
    def _preset_changed(self) -> None:
        if self._loading:
            return
        today = date.today()
        index = self.preset.currentIndex()
        self.start_edit.blockSignals(True)
        self.end_edit.blockSignals(True)
        if index == 0:
            set_date_edit(self.start_edit, today.replace(day=1))
            set_date_edit(self.end_edit, today)
            custom = False
        elif index == 1:
            set_date_edit(self.start_edit, today - timedelta(days=29))
            set_date_edit(self.end_edit, today)
            custom = False
        elif index == 2:
            set_date_edit(self.start_edit, current_session_start(self.context.settings))
            set_date_edit(self.end_edit, today)
            custom = False
        else:
            custom = True
        self.start_edit.blockSignals(False)
        self.end_edit.blockSignals(False)
        self.start_edit.setEnabled(custom)
        self.end_edit.setEnabled(custom)
        self.refresh()

    def _filters_changed(self) -> None:
        if self._loading:
            return
        self.refresh()

    def _session_changed(self) -> None:
        if self._loading:
            return
        session_id = self.session_combo.currentData()
        if session_id:
            self.session_change_requested.emit(int(session_id))

    # ---------------------------------------------------------------- refresh
    def refresh(self) -> None:
        self._loading = True
        try:
            populate_sessions(self.session_combo, self.context.settings)
            session_id = self.context.session_id
            if session_id is None:
                self.body.hide()
                self.empty.show()
                self.empty.setVisible(True)
                return
            self.welcome.setText(
                f"{self.context.settings.school_name} · {self.context.settings.subject} · "
                f"Session {self.context.settings.active_session_name()}"
            )
            start = date_to_iso(self.start_edit)
            end = date_to_iso(self.end_edit)
            if start > end:
                start, end = end, start
            class_name = self.class_combo.currentData()
            metrics = self.context.analytics.dashboard_metrics(
                session_id, class_name, start, end
            )
            counts = metrics["class_totals"]
            self.cards["class9"].set_value(counts["9"], "Active students · Class 9")
            self.cards["class10"].set_value(counts["10"], "Active students · Class 10")
            today_counts = metrics["today"]
            today_label = date.today().strftime("%d-%m-%Y")
            self.cards["present"].set_value(
                today_counts["present"], f"Recorded {today_label}"
            )
            self.cards["absent"].set_value(
                today_counts["absent"], f"Recorded {today_label}"
            )
            self.cards["leave"].set_value(
                today_counts["leave"], f"Recorded {today_label}"
            )
            attendance = metrics["attendance"]
            self.cards["attendance"].set_value(
                format_pct(attendance["percentage"]),
                f"{attendance['present']} present of {attendance['counted']} counted",
            )
            marks = metrics["marks"]
            self.cards["average"].set_value(
                format_pct(marks["average_percentage"]),
                f"{marks['entered']} marks entered · {metrics['start']} to {metrics['end']}",
            )
            self.cards["pass"].set_value(
                format_pct(marks["pass_percentage"]),
                f"{marks['passed']} passed · {marks['failed']} failed · {marks['absent']} absent",
            )
            self.cards["support"].set_value(
                len(metrics["support_students"]),
                f"Below {self.context.settings.performance_threshold:g}% marks "
                f"or {self.context.settings.attendance_threshold:g}% attendance",
            )
            self.cards["below"].set_value(
                len(metrics["below_attendance"]),
                f"Below {self.context.settings.attendance_threshold:g}% attendance",
            )
            self._tone_cards(attendance["percentage"], marks["pass_percentage"])
            if metrics["has_students"]:
                self.empty.hide()
                self.body.show()
            else:
                self.body.hide()
                self.empty.show()
            self._fill_attention(metrics["support_students"])
            self._fill_activity(metrics["recent_activity"])
        finally:
            self._loading = False

    def _tone_cards(self, attendance: float | None, pass_pct: float | None) -> None:
        threshold = self.context.settings.attendance_threshold
        card = self.cards["attendance"]
        if attendance is None:
            card.set_tone("text_muted")
        elif attendance >= threshold:
            card.set_tone("success")
        elif attendance >= threshold - 10:
            card.set_tone("warning")
        else:
            card.set_tone("danger")
        pass_card = self.cards["pass"]
        if pass_pct is None:
            pass_card.set_tone("text_muted")
        elif pass_pct >= 80:
            pass_card.set_tone("success")
        elif pass_pct >= 50:
            pass_card.set_tone("warning")
        else:
            pass_card.set_tone("danger")

    def _fill_attention(self, students: list[dict]) -> None:
        ordered = sorted(
            students,
            key=lambda s: (
                s["attendance_percentage"] if s["attendance_percentage"] is not None else 101,
                s["average_percentage"] if s["average_percentage"] is not None else 101,
            ),
        )[:10]
        rows = [
            [
                s["roll_no"],
                s["full_name"],
                s["class_name"],
                format_pct(s["attendance_percentage"]),
                format_pct(s["average_percentage"]),
                "; ".join(s["support_reasons"]),
            ]
            for s in ordered
        ]
        self.attention_table.set_data(rows, row_ids=[s["student_id"] for s in ordered])
        self.attention_table.setVisible(bool(rows))
        self.attention_empty.setVisible(not rows)

    def _fill_activity(self, activity: list) -> None:
        clear_layout(self.activity_box)
        if not activity:
            empty = QLabel("No activity recorded yet. Save attendance or marks to see it here.")
            empty.setObjectName("small")
            empty.setWordWrap(True)
            self.activity_box.addWidget(empty)
            self.activity_box.addStretch(1)
            return
        icons = {
            "attendance": "attendance",
            "marks": "marks",
            "student": "students",
            "examination": "reports",
            "backup": "backup",
            "database": "backup",
            "holiday": "attendance",
            "academic_session": "settings",
            "grade_rules": "settings",
        }
        for row in activity[:9]:
            item = QWidget()
            layout = QHBoxLayout(item)
            layout.setContentsMargins(0, 3, 0, 3)
            layout.setSpacing(9)
            icon = QLabel()
            icon.setFixedSize(26, 26)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setPixmap(
                make_icon(
                    icons.get(row["entity"], "info"), palette()["primary"], 15
                ).pixmap(15, 15)
            )
            icon.setStyleSheet(f"background: {palette()['surface_alt']}; border-radius: 7px;")
            layout.addWidget(icon)
            details = row["details"] or row["action"].title()
            text = QLabel(str(details))
            text.setWordWrap(True)
            text.setStyleSheet("font-size: 8.6pt;")
            layout.addWidget(text, 1)
            stamp = QLabel(self._format_time(row["created_at"]))
            stamp.setObjectName("small")
            stamp.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            layout.addWidget(stamp)
            self.activity_box.addWidget(item)
        self.activity_box.addStretch(1)

    @staticmethod
    def _format_time(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(str(value))
            return parsed.strftime("%d-%m %H:%M")
        except ValueError:
            return str(value)[:16]
