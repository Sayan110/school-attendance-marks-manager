"""Analytics page: attendance, results and performance charts from saved data."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from app.context import AppContext
from app.ui.common import (
    class_combo,
    current_session_start,
    date_to_iso,
    make_date_edit,
    set_date_edit,
)
from app.ui.icons import make_icon
from app.ui.widgets import (
    InfoCard,
    PageHeader,
    StatCard,
    format_pct,
    palette,
)
from app.ui.theme import chart_colors
from app.utils import dates as date_utils
from app.utils.validators import ValidationError


class ChartCanvas(FigureCanvas):
    def __init__(self, height: float = 3.0, parent: QWidget | None = None) -> None:
        self.figure = Figure(figsize=(5, height), dpi=100, facecolor=palette()["surface"])
        super().__init__(self.figure)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(int(height * 78))
        self.axes = self.figure.add_subplot(111)

    def empty(self, message: str = "No data for this selection yet.") -> None:
        self.figure.clear()
        self.axes = self.figure.add_subplot(111)
        self.axes.axis("off")
        self.axes.text(
            0.5,
            0.54,
            message,
            ha="center",
            va="center",
            color=palette()["text_muted"],
            fontsize=9,
            wrap=True,
        )
        self.draw_idle()


class AnalyticsPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._loading = False
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(12)
        outer.addWidget(
            PageHeader(
                "Analytics",
                "Charts are generated from saved attendance and marks. Empty selections stay empty — "
                "no values are simulated.",
            )
        )
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("small")
        outer.addWidget(self.subtitle)

        filters = QFrame()
        filters.setObjectName("inset")
        frame_layout = QVBoxLayout(filters)
        frame_layout.setContentsMargins(12, 9, 12, 9)
        frame_layout.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Class"))
        self.class_combo = class_combo(include_all=True)
        self.class_combo.currentIndexChanged.connect(self._class_changed)
        row.addWidget(self.class_combo)
        row.addWidget(QLabel("Period"))
        self.preset = QComboBox()
        self.preset.addItems(
            ["This month", "Last 30 days", "This academic session", "Custom range"]
        )
        self.preset.currentIndexChanged.connect(self._preset_changed)
        row.addWidget(self.preset)
        self.start_edit = make_date_edit(date.today().replace(day=1))
        self.end_edit = make_date_edit(date.today())
        self.start_edit.dateChanged.connect(self.refresh)
        self.end_edit.dateChanged.connect(self.refresh)
        row.addWidget(self.start_edit)
        row.addWidget(QLabel("to"))
        row.addWidget(self.end_edit)
        row.addStretch(1)
        frame_layout.addLayout(row)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel("Examination"))
        self.exam_combo = QComboBox()
        self.exam_combo.setMinimumWidth(200)
        self.exam_combo.currentIndexChanged.connect(self.refresh)
        row2.addWidget(self.exam_combo, 1)
        refresh = QPushButton("Refresh charts")
        refresh.setIcon(make_icon("refresh", palette()["text"], 15))
        refresh.clicked.connect(self.refresh)
        row2.addWidget(refresh)
        frame_layout.addLayout(row2)
        outer.addWidget(filters)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self._build_overview()
        self._build_individual()

    def _build_overview(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.cards: dict[str, StatCard] = {}
        for key, label, icon, accent in (
            ("attendance", "Attendance %", "attendance", "info"),
            ("average", "Average CS marks", "marks", "accent"),
            ("pass", "Pass %", "check", "success"),
            ("students", "Students with records", "students", "primary"),
        ):
            card = StatCard(label, "—", "", icon, accent)
            card.setMinimumHeight(98)
            self.cards[key] = card
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        grid_top = QHBoxLayout()
        grid_top.setSpacing(10)
        self.attendance_card = InfoCard("Attendance breakdown")
        self.attendance_chart = ChartCanvas(2.6)
        self.attendance_card.body.addWidget(self.attendance_chart)
        grid_top.addWidget(self.attendance_card, 1)
        self.results_card = InfoCard("Examination results")
        self.results_chart = ChartCanvas(2.6)
        self.results_card.body.addWidget(self.results_chart)
        grid_top.addWidget(self.results_card, 1)
        layout.addLayout(grid_top)

        distribution_card = InfoCard("Marks distribution")
        self.distribution_chart = ChartCanvas(2.5)
        distribution_card.body.addWidget(self.distribution_chart)
        layout.addWidget(distribution_card, 1)

        comparison_card = InfoCard("Class comparison")
        self.comparison_chart = ChartCanvas(2.5)
        comparison_card.body.addWidget(self.comparison_chart)
        layout.addWidget(comparison_card, 1)

        trend_card = InfoCard("Monthly attendance trend")
        self.trend_chart = ChartCanvas(2.5)
        trend_card.body.addWidget(self.trend_chart)
        layout.addWidget(trend_card, 1)

        scroll = _scroll_wrapper(page)
        self.tabs.addTab(scroll, "Overview")

    def _build_individual(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel("Student"))
        self.student_combo = QComboBox()
        self.student_combo.setMinimumWidth(300)
        self.student_combo.currentIndexChanged.connect(self.refresh_individual)
        controls.addWidget(self.student_combo, 1)
        load = QPushButton("Show student")
        load.setIcon(make_icon("refresh", palette()["text"], 15))
        load.clicked.connect(self.refresh_individual)
        controls.addWidget(load)
        layout.addLayout(controls)

        self.student_summary = QLabel("Select a student to see their attendance and exam history.")
        self.student_summary.setObjectName("small")
        self.student_summary.setWordWrap(True)
        layout.addWidget(self.student_summary)

        exam_card = InfoCard("Examination performance")
        self.individual_exam_chart = ChartCanvas(2.6)
        exam_card.body.addWidget(self.individual_exam_chart)
        layout.addWidget(exam_card, 1)

        attendance_card = InfoCard("Monthly attendance")
        self.individual_attendance_chart = ChartCanvas(2.6)
        attendance_card.body.addWidget(self.individual_attendance_chart)
        layout.addWidget(attendance_card, 1)

        history_card = InfoCard("Examination history")
        self.history_label = QLabel("")
        self.history_label.setObjectName("small")
        self.history_label.setWordWrap(True)
        history_card.body.addWidget(self.history_label)
        layout.addWidget(history_card)

        scroll = _scroll_wrapper(page)
        self.tabs.addTab(scroll, "Individual student")

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

    def _class_changed(self) -> None:
        if self._loading:
            return
        self._reload_exams()
        self._reload_students()
        self.refresh()

    def _reload_exams(self) -> None:
        session_id = self.context.session_id
        class_name = self.class_combo.currentData()
        current = self.exam_combo.currentData()
        self.exam_combo.blockSignals(True)
        self.exam_combo.clear()
        if session_id is not None:
            for exam in self.context.marks.list_examinations(session_id, class_name):
                self.exam_combo.addItem(
                    f"{exam['name']} · Class {exam['class_name']}", int(exam["id"])
                )
        index = self.exam_combo.findData(current) if current else -1
        if index >= 0:
            self.exam_combo.setCurrentIndex(index)
        self.exam_combo.blockSignals(False)

    def _reload_students(self) -> None:
        session_id = self.context.session_id
        class_name = self.class_combo.currentData()
        current = self.student_combo.currentData()
        self.student_combo.blockSignals(True)
        self.student_combo.clear()
        if session_id is not None:
            for student in self.context.students.all_students(session_id, class_name):
                self.student_combo.addItem(
                    f"Class {student['class_name']} · {student['roll_no']} · {student['full_name']}",
                    int(student["id"]),
                )
        index = self.student_combo.findData(current) if current else -1
        if index >= 0:
            self.student_combo.setCurrentIndex(index)
        self.student_combo.blockSignals(False)

    def _period(self) -> tuple[str, str]:
        start = date_to_iso(self.start_edit)
        end = date_to_iso(self.end_edit)
        return (end, start) if start > end else (start, end)

    # ---------------------------------------------------------------- refresh
    def refresh(self) -> None:
        self._loading = True
        try:
            self.subtitle.setText(
                f"{self.context.settings.school_name} · {self.context.settings.subject} · "
                f"Session {self.context.settings.active_session_name()}"
            )
            if self.exam_combo.count() == 0:
                self._reload_exams()
            if self.student_combo.count() == 0:
                self._reload_students()
            self._refresh_overview()
            self.refresh_individual()
        finally:
            self._loading = False

    def _refresh_overview(self) -> None:
        session_id = self.context.session_id
        if session_id is None:
            for chart in (
                self.attendance_chart,
                self.results_chart,
                self.distribution_chart,
                self.comparison_chart,
                self.trend_chart,
            ):
                chart.empty("Create an academic session and add records first.")
            return
        start, end = self._period()
        class_name = self.class_combo.currentData()
        try:
            attendance = self.context.analytics.attendance_pie(
                session_id, class_name, start, end
            )
            summary = self.context.analytics.performance_summary(
                session_id, class_name, start, end
            )
        except ValidationError:
            return
        self.cards["attendance"].set_value(
            format_pct(attendance["percentage"]),
            f"{attendance['present']} present of {attendance['counted']} counted",
        )
        marks = summary["marks"]
        self.cards["average"].set_value(
            format_pct(marks["average_percentage"]),
            f"{marks['entered']} marks entered",
        )
        self.cards["pass"].set_value(
            format_pct(marks["pass_percentage"]),
            f"{marks['passed']} passed · {marks['failed']} failed",
        )
        self.cards["students"].set_value(
            len(summary["students"]),
            f"{start} to {end}",
        )
        self._draw_attendance_pie(attendance)
        self._draw_results_pie()
        self._draw_distribution()
        self._draw_comparison(session_id, start, end)
        self._draw_trend(session_id, class_name, start, end)

    # ----------------------------------------------------------------- charts
    def _prepare(self, chart: ChartCanvas) -> None:
        chart.figure.clear()
        chart.figure.set_facecolor(palette()["surface"])
        chart.axes = chart.figure.add_subplot(111)
        chart.axes.set_facecolor(palette()["surface"])
        chart.figure.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.18)

    def _draw_attendance_pie(self, data: dict) -> None:
        colors = chart_colors(palette())
        values = [data["present"], data["absent"], data["leave"]]
        if sum(values) == 0:
            self.attendance_chart.empty("No attendance recorded for this period.")
            return
        self._prepare(self.attendance_chart)
        axes = self.attendance_chart.axes
        wedges, _texts, autotexts = axes.pie(
            values,
            labels=["Present", "Absent", "Leave"],
            colors=[colors[0], colors[3], colors[1]],
            autopct=lambda pct: f"{pct:.0f}%" if pct >= 4 else "",
            startangle=90,
            pctdistance=0.76,
            textprops={"color": palette()["chart_text"], "fontsize": 8},
            wedgeprops={"width": 0.46, "edgecolor": palette()["surface"], "linewidth": 1.4},
        )
        for text in autotexts:
            text.set_color(palette()["surface"])
            text.set_fontweight("bold")
        axes.text(
            0,
            0.06,
            format_pct(data["percentage"]),
            ha="center",
            va="center",
            fontsize=16,
            fontweight="bold",
            color=palette()["text"],
        )
        axes.text(
            0,
            -0.14,
            "attendance",
            ha="center",
            va="center",
            fontsize=8,
            color=palette()["text_muted"],
        )
        axes.set_title(
            f"Present {data['present']} · Absent {data['absent']} · Leave {data['leave']}",
            fontsize=9,
        )
        self.attendance_chart.draw_idle()

    def _draw_results_pie(self) -> None:
        exam_id = self.exam_combo.currentData()
        if not exam_id:
            self.results_chart.empty("Create an examination to see results.")
            return
        data = self.context.analytics.results_pie(int(exam_id))
        if not data.get("has_data"):
            self.results_chart.empty("No marks recorded for this examination.")
            return
        colors = chart_colors(palette())
        labels = ["Passed", "Failed", "Absent", "Exempted", "Pending"]
        values = [
            data["passed"],
            data["failed"],
            data["absent"],
            data["exempted"],
            data["pending"],
        ]
        active = [(label, value) for label, value in zip(labels, values) if value]
        if not active:
            self.results_chart.empty("No marks recorded for this examination.")
            return
        self._prepare(self.results_chart)
        axes = self.results_chart.axes
        palette_slice = [colors[0], colors[3], colors[1], colors[2], colors[5]]
        selected = [palette_slice[index] for index, value in enumerate(values) if value]
        axes.pie(
            [value for _, value in active],
            labels=[label for label, _ in active],
            colors=selected,
            autopct=lambda pct: f"{pct:.0f}%" if pct >= 4 else "",
            startangle=90,
            pctdistance=0.74,
            textprops={"color": palette()["chart_text"], "fontsize": 8},
            wedgeprops={"width": 0.46, "edgecolor": palette()["surface"], "linewidth": 1.4},
        )
        axes.text(
            0,
            0,
            format_pct(data["pass_percentage"]),
            ha="center",
            va="center",
            fontsize=15,
            fontweight="bold",
            color=palette()["text"],
        )
        axes.set_title(
            f"{data['total']} students · {data['passed'] + data['failed']} graded", fontsize=9
        )
        self.results_chart.draw_idle()

    def _draw_distribution(self) -> None:
        exam_id = self.exam_combo.currentData()
        if not exam_id:
            self.distribution_chart.empty("Select an examination with recorded marks.")
            return
        data = self.context.analytics.marks_distribution(int(exam_id))
        if not data.get("has_data"):
            self.distribution_chart.empty("No entered marks for this examination.")
            return
        percentages = [
            row["percentage"]
            for row in data["rows"]
            if row["status"] == "entered" and row["percentage"] is not None
        ]
        bins = list(range(0, 101, 10))
        counts = [0] * 10
        for pct in percentages:
            index = min(9, max(0, int(pct // 10)))
            counts[index] += 1
        self._prepare(self.distribution_chart)
        axes = self.distribution_chart.axes
        colors = chart_colors(palette())
        bars = axes.bar(
            [f"{bins[i]}-{bins[i + 1]}" for i in range(10)],
            counts,
            color=colors[0],
            edgecolor=palette()["surface"],
            linewidth=1,
            width=0.72,
        )
        for bar, count in zip(bars, counts):
            if count:
                axes.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(counts) * 0.02,
                    str(count),
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color=palette()["chart_text"],
                )
        axes.set_ylabel("Students")
        axes.set_xlabel("Percentage band")
        axes.set_title("Distribution of student percentages", fontsize=10)
        axes.grid(axis="y", alpha=0.35)
        axes.set_axisbelow(True)
        self.distribution_chart.draw_idle()

    def _draw_comparison(self, session_id: int, start: str, end: str) -> None:
        data = self.context.analytics.class_comparison(session_id, start, end)
        if not any(row["has_marks"] or row["has_attendance"] for row in data):
            self.comparison_chart.empty("No attendance or marks recorded for this period.")
            return
        self._prepare(self.comparison_chart)
        axes = self.comparison_chart.axes
        colors = chart_colors(palette())
        labels = [f"Class {row['class_name']}" for row in data]
        positions = range(len(data))
        width = 0.24
        series = [
            ("Attendance %", [row["attendance_percentage"] or 0 for row in data], colors[0]),
            ("Average marks %", [row["average_percentage"] or 0 for row in data], colors[1]),
            ("Pass %", [row["pass_percentage"] or 0 for row in data], colors[2]),
        ]
        for index, (label, values, color) in enumerate(series):
            offsets = [p + (index - 1) * width for p in positions]
            bars = axes.bar(offsets, values, width, label=label, color=color)
            for bar, value in zip(bars, values):
                axes.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 1.5,
                    f"{value:.0f}",
                    ha="center",
                    va="bottom",
                    fontsize=7.5,
                    color=palette()["chart_text"],
                )
        axes.set_xticks(list(positions), labels)
        axes.set_ylim(0, 110)
        axes.set_ylabel("Percent")
        axes.set_title("Class 9 vs Class 10", fontsize=10)
        axes.legend(frameon=False, ncol=3, loc="upper center")
        axes.grid(axis="y", alpha=0.3)
        axes.set_axisbelow(True)
        self.comparison_chart.draw_idle()

    def _draw_trend(
        self, session_id: int, class_name: str | None, start: str, end: str
    ) -> None:
        rows = self.context.analytics.monthly_trend(session_id, class_name, start, end)
        if not rows:
            self.trend_chart.empty("No monthly attendance data for this period.")
            return
        self._prepare(self.trend_chart)
        axes = self.trend_chart.axes
        colors = chart_colors(palette())
        labels = []
        for row in rows:
            parsed = date_utils.parse(str(row["month"]) + "-01")
            labels.append(parsed.strftime("%b %Y") if parsed else row["month"])
        values = [row["percentage"] if row["percentage"] is not None else 0 for row in rows]
        axes.plot(
            labels,
            values,
            color=colors[0],
            linewidth=2.2,
            marker="o",
            markersize=5,
            markerfacecolor=palette()["surface"],
            markeredgewidth=2,
        )
        for index, value in enumerate(values):
            axes.annotate(
                f"{value:.0f}%",
                (index, value),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                fontsize=7.5,
                color=palette()["chart_text"],
            )
        axes.set_ylim(0, 108)
        axes.set_ylabel("Attendance %")
        axes.set_title("Monthly attendance percentage", fontsize=10)
        axes.grid(axis="y", alpha=0.3)
        axes.set_axisbelow(True)
        self.trend_chart.draw_idle()

    # --------------------------------------------------------------- individual
    def refresh_individual(self) -> None:
        student_id = self.student_combo.currentData()
        if not student_id:
            self.student_summary.setText("Add students to see individual analytics.")
            self.individual_exam_chart.empty("No student selected.")
            self.individual_attendance_chart.empty("No student selected.")
            self.history_label.setText("")
            return
        start, end = self._period()
        try:
            data = self.context.analytics.student_performance(int(student_id), start, end)
        except (ValidationError, ValueError) as exc:
            self.student_summary.setText(str(exc))
            return
        student = data["student"]
        attendance = data["attendance"]
        average = data["average_percentage"]
        self.student_summary.setText(
            f"Class {student['class_name']} · Roll {student['roll_no']} · {student['full_name']}  |  "
            f"Attendance {format_pct(attendance['percentage'])} "
            f"({attendance['present']} present, {attendance['absent']} absent, "
            f"{attendance['leave']} leave)  |  Average marks {format_pct(average)}"
            + ("  |  Needs support" if data["needs_support"] else "")
        )
        history = data["history"]
        exam_points = [row for row in history if row["percentage"] is not None]
        if not exam_points:
            self.individual_exam_chart.empty("No marks recorded for this student in this period.")
        else:
            self._prepare(self.individual_exam_chart)
            axes = self.individual_exam_chart.axes
            colors = chart_colors(palette())
            labels = [row["name"] for row in exam_points]
            values = [row["percentage"] for row in exam_points]
            axes.plot(
                labels,
                values,
                color=colors[1],
                marker="o",
                linewidth=2,
                markersize=5,
            )
            axes.axhline(
                self.context.settings.performance_threshold,
                color=colors[3],
                linestyle="--",
                linewidth=1.1,
                label=f"Pass threshold {self.context.settings.performance_threshold:g}%",
            )
            for index, value in enumerate(values):
                axes.annotate(
                    f"{value:.0f}%",
                    (index, value),
                    textcoords="offset points",
                    xytext=(0, 8),
                    ha="center",
                    fontsize=7.5,
                    color=palette()["chart_text"],
                )
            axes.set_ylim(0, 108)
            axes.set_ylabel("Percentage")
            axes.set_title("Examination performance", fontsize=10)
            axes.tick_params(axis="x", labelrotation=15)
            axes.legend(frameon=False, fontsize=7.5, loc="lower left")
            axes.grid(axis="y", alpha=0.3)
            axes.set_axisbelow(True)
            self.individual_exam_chart.draw_idle()

        trend = data["attendance_trend"]
        if not trend:
            self.individual_attendance_chart.empty("No attendance recorded in this period.")
        else:
            self._prepare(self.individual_attendance_chart)
            axes = self.individual_attendance_chart.axes
            colors = chart_colors(palette())
            labels = []
            for row in trend:
                parsed = date_utils.parse(str(row["month"]) + "-01")
                labels.append(parsed.strftime("%b %Y") if parsed else row["month"])
            values = [row["percentage"] or 0 for row in trend]
            axes.bar(
                labels,
                values,
                color=colors[0],
                edgecolor=palette()["surface"],
                linewidth=1,
                width=0.6,
            )
            axes.axhline(
                self.context.settings.attendance_threshold,
                color=colors[3],
                linestyle="--",
                linewidth=1.1,
                label=f"Threshold {self.context.settings.attendance_threshold:g}%",
            )
            axes.set_ylim(0, 108)
            axes.set_ylabel("Attendance %")
            axes.set_title("Monthly attendance", fontsize=10)
            axes.legend(frameon=False, fontsize=7.5, loc="lower left")
            axes.grid(axis="y", alpha=0.3)
            axes.set_axisbelow(True)
            self.individual_attendance_chart.draw_idle()

        if not history:
            self.history_label.setText("No examinations exist for this class yet.")
        else:
            lines = []
            for row in history:
                status = row["status"].title()
                if row["total"] is not None:
                    result = "Passed" if row["passed"] else "Failed"
                    lines.append(
                        f"{row['name']} ({row['exam_date'] or 'no date'}): "
                        f"{float(row['total']):g}/{float(row['max_marks']):g} · "
                        f"{format_pct(row['percentage'])} · {result}"
                    )
                else:
                    lines.append(f"{row['name']} ({row['exam_date'] or 'no date'}): {status}")
            self.history_label.setText("\n".join(lines))


def _scroll_wrapper(page: QWidget) -> QWidget:
    from PySide6.QtWidgets import QFrame, QScrollArea

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(page)
    scroll.setStyleSheet("QScrollArea { background: transparent; }")
    return scroll
