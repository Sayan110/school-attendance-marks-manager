"""Examinations and Computer Science marks entry."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.context import AppContext
from app.database import DatabaseError
from app.services import calculations, io_service
from app.ui.common import class_combo, date_to_iso, make_date_edit, set_date_edit
from app.ui.icons import make_icon
from app.ui.widgets import (
    DataTable,
    EmptyState,
    PageHeader,
    StatCard,
    confirm_action,
    error_dialog,
    format_pct,
    notify,
    palette,
    set_variant,
)
from app.utils.validators import ValidationError

STATUS_OPTIONS = [
    ("Pending", "pending"),
    ("Entered", "entered"),
    ("Absent", "absent"),
    ("Exempted", "exempted"),
]


class ExaminationDialog(QDialog):
    """Create or edit an examination with configurable components."""

    def __init__(
        self,
        context: AppContext,
        exam: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.exam = exam
        self.setWindowTitle("Edit examination" if exam else "New examination")
        self.setMinimumWidth(520)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(10)
        title = QLabel("Edit examination" if exam else "New examination")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(8)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Unit Test 1")
        form.addRow("Examination name *", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(list(config.EXAM_TYPES))
        self.type_combo.setEditable(True)
        form.addRow("Examination type", self.type_combo)

        self.class_combo = class_combo()
        form.addRow("Class *", self.class_combo)

        self.date_edit = make_date_edit(date.today())
        form.addRow("Examination date", self.date_edit)

        self.max_edit = QLineEdit()
        self.max_edit.setPlaceholderText("e.g. 100")
        form.addRow("Maximum marks *", self.max_edit)

        self.pass_percent_edit = QLineEdit()
        self.pass_percent_edit.setPlaceholderText("Default 33")
        form.addRow("Pass percentage", self.pass_percent_edit)

        self.pass_marks_edit = QLineEdit()
        self.pass_marks_edit.setPlaceholderText("Optional; overrides pass percentage")
        form.addRow("Passing marks", self.pass_marks_edit)

        components = QFrame()
        components.setObjectName("inset")
        component_layout = QVBoxLayout(components)
        component_layout.setContentsMargins(12, 10, 12, 10)
        component_layout.setSpacing(6)
        comp_label = QLabel(
            "Optional components. If you use any component maximum, the components must add "
            "up to the overall maximum marks."
        )
        comp_label.setObjectName("small")
        comp_label.setWordWrap(True)
        component_layout.addWidget(comp_label)
        fields = QHBoxLayout()
        fields.setSpacing(8)
        self.theory_edit = QLineEdit()
        self.theory_edit.setPlaceholderText("Theory max")
        self.practical_edit = QLineEdit()
        self.practical_edit.setPlaceholderText("Practical max")
        self.project_edit = QLineEdit()
        self.project_edit.setPlaceholderText("Project max")
        for label, widget in (
            ("Theory", self.theory_edit),
            ("Practical", self.practical_edit),
            ("Project", self.project_edit),
        ):
            column = QVBoxLayout()
            column.setSpacing(3)
            column.addWidget(QLabel(label))
            column.addWidget(widget)
            fields.addLayout(column)
        component_layout.addLayout(fields)
        form.addRow("Components", components)

        self.remarks_edit = QLineEdit()
        self.remarks_edit.setPlaceholderText("Optional notes for this examination")
        form.addRow("Remarks", self.remarks_edit)
        layout.addLayout(form)

        note = QLabel(
            "Marks above the maximum are rejected; a blank mark is never converted to zero. "
            "Pass criteria and grades are teacher-configured, not an official SEBA policy."
        )
        note.setObjectName("small")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save examination")
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("variant", "primary")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if exam:
            self._populate(exam)

    def _populate(self, exam) -> None:
        self.name_edit.setText(str(exam["name"]))
        index = self.type_combo.findText(str(exam["exam_type"]))
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        else:
            self.type_combo.setCurrentText(str(exam["exam_type"]))
        class_index = self.class_combo.findData(str(exam["class_name"]))
        if class_index >= 0:
            self.class_combo.setCurrentIndex(class_index)
        if exam["exam_date"]:
            set_date_edit(self.date_edit, exam["exam_date"])
        self.max_edit.setText(f"{float(exam['max_marks']):g}")
        if exam["pass_percent"] is not None:
            self.pass_percent_edit.setText(f"{float(exam['pass_percent']):g}")
        if exam["pass_marks"] is not None:
            self.pass_marks_edit.setText(f"{float(exam['pass_marks']):g}")
        for field, key in (
            (self.theory_edit, "theory_max"),
            (self.practical_edit, "practical_max"),
            (self.project_edit, "project_max"),
        ):
            if exam[key] is not None:
                field.setText(f"{float(exam[key]):g}")
        self.remarks_edit.setText(exam["remarks"] or "")

    def _save(self) -> None:
        data = {
            "name": self.name_edit.text(),
            "exam_type": self.type_combo.currentText(),
            "class_name": self.class_combo.currentData(),
            "session_id": self.context.session_id,
            "subject": self.context.settings.subject,
            "exam_date": date_to_iso(self.date_edit),
            "max_marks": self.max_edit.text().strip(),
            "pass_percent": self.pass_percent_edit.text().strip(),
            "pass_marks": self.pass_marks_edit.text().strip(),
            "theory_max": self.theory_edit.text().strip() or None,
            "practical_max": self.practical_edit.text().strip() or None,
            "project_max": self.project_edit.text().strip() or None,
            "remarks": self.remarks_edit.text(),
        }
        try:
            if self.exam:
                self.context.marks.update_examination(int(self.exam["id"]), data)
                message = "Examination updated."
            else:
                self.context.marks.create_examination(data)
                message = "Examination created."
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not save examination", str(exc))
            return
        self.saved_message = message
        self.accept()


class MarksPage(QWidget):
    navigate = Signal(str)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._loading = False
        self._dirty = False
        self._exam = None
        self._rows: list[dict] = []
        self._widgets: dict[int, dict[str, QWidget]] = {}
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(12)
        outer.addWidget(
            PageHeader(
                "Marks & examinations",
                "Record Computer Science marks with configurable maxima, components and pass criteria.",
            )
        )
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("small")
        outer.addWidget(self.subtitle)

        filters = QFrame()
        filters.setObjectName("inset")
        row = QHBoxLayout(filters)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(8)
        row.addWidget(QLabel("Class"))
        self.class_combo = class_combo()
        self.class_combo.currentIndexChanged.connect(self._class_changed)
        row.addWidget(self.class_combo)
        row.addSpacing(4)
        row.addWidget(QLabel("Examination"))
        self.exam_combo = QComboBox()
        self.exam_combo.setMinimumWidth(280)
        self.exam_combo.currentIndexChanged.connect(self._exam_changed)
        row.addWidget(self.exam_combo, 1)
        self.new_button = QPushButton("New")
        self.new_button.setIcon(make_icon("plus", palette()["text"], 15))
        self.new_button.clicked.connect(self._new_exam)
        row.addWidget(self.new_button)
        self.edit_button = QPushButton("Edit")
        self.edit_button.setIcon(make_icon("edit", palette()["text"], 15))
        self.edit_button.clicked.connect(self._edit_exam)
        row.addWidget(self.edit_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.setIcon(make_icon("trash", palette()["text"], 15))
        self.delete_button.clicked.connect(self._delete_exam)
        row.addWidget(self.delete_button)
        outer.addWidget(filters)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.cards: dict[str, StatCard] = {}
        for key, label, icon, accent in (
            ("students", "Students", "students", "primary"),
            ("entered", "Marks entered", "marks", "info"),
            ("average", "Average marks", "analytics", "accent"),
            ("pass", "Pass %", "check", "success"),
            ("pending", "Pending", "warning", "warning"),
        ):
            card = StatCard(label, "—", "", icon, accent)
            card.setMinimumHeight(100)
            self.cards[key] = card
            cards.addWidget(card, 1)
        outer.addLayout(cards)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)

        # ------------------------------------------------------------ entry tab
        entry_tab = QWidget()
        entry_layout = QVBoxLayout(entry_tab)
        entry_layout.setContentsMargins(12, 12, 12, 12)
        entry_layout.setSpacing(8)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.import_button = QPushButton("Import Excel/CSV")
        self.import_button.setIcon(make_icon("import", palette()["text"], 15))
        self.import_button.clicked.connect(self._import_marks)
        actions.addWidget(self.import_button)
        self.template_button = QPushButton("Download template")
        self.template_button.setIcon(make_icon("export", palette()["text"], 15))
        self.template_button.clicked.connect(self._download_template)
        actions.addWidget(self.template_button)
        self.export_button = QPushButton("Export Excel")
        self.export_button.setIcon(make_icon("export", palette()["text"], 15))
        self.export_button.clicked.connect(self._export_excel)
        actions.addWidget(self.export_button)
        self.csv_button = QPushButton("Export CSV")
        self.csv_button.clicked.connect(self._export_csv)
        actions.addWidget(self.csv_button)
        actions.addStretch(1)
        self.dirty_label = QLabel("")
        self.dirty_label.setProperty("tone", "warning")
        self.dirty_label.hide()
        actions.addWidget(self.dirty_label)
        self.save_button = QPushButton("Save marks")
        self.save_button.setIcon(make_icon("check", "#ffffff", 15))
        set_variant(self.save_button, "primary")
        self.save_button.clicked.connect(self.save)
        actions.addWidget(self.save_button)
        entry_layout.addLayout(actions)

        hint = QLabel(
            "Enter marks only for students whose status is Entered. Absent and Exempted are "
            "recorded distinctly; Pending stays blank. Missing marks are never treated as zero."
        )
        hint.setObjectName("small")
        hint.setWordWrap(True)
        entry_layout.addWidget(hint)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            [
                "Roll",
                "Student name",
                "Section",
                "Status",
                "Theory",
                "Practical",
                "Project",
                "Total",
                "%",
                "Result",
                "Rank",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        for index, width in enumerate((55, 190, 55, 120, 80, 80, 80, 80, 70, 80, 55)):
            self.table.setColumnWidth(index, width)
        self.table.setMinimumHeight(240)
        entry_layout.addWidget(self.table, 1)

        self.remarks_row = QHBoxLayout()
        self.remarks_row.setSpacing(12)
        self.remarks_row.addWidget(QLabel("Remarks for selected student"))
        self.remarks_edit = QLineEdit()
        self.remarks_edit.setPlaceholderText("Select a student row, then type a remark")
        self.remarks_edit.setEnabled(False)
        self.remarks_edit.textEdited.connect(self._remarks_changed)
        self.remarks_row.addWidget(self.remarks_edit, 1)
        entry_layout.addLayout(self.remarks_row)

        self.empty = EmptyState(
            "No examination selected",
            "Create an examination for this class to start entering marks.",
            icon="marks",
            action_text="Create examination",
        )
        if self.empty.button:
            self.empty.button.clicked.connect(self._new_exam)
        self.empty.hide()
        entry_layout.addWidget(self.empty, 1)
        self.tabs.addTab(entry_tab, "Marks entry")

        # ---------------------------------------------------------- results tab
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        results_layout.setContentsMargins(12, 12, 12, 12)
        results_layout.setSpacing(8)
        result_actions = QHBoxLayout()
        result_actions.addWidget(
            QLabel(
                "Ranks use standard competition ranking: ties share a rank and the next rank skips."
            )
        )
        result_actions.addStretch(1)
        result_refresh = QPushButton("Refresh results")
        result_refresh.setIcon(make_icon("refresh", palette()["text"], 15))
        result_refresh.clicked.connect(self.refresh_results)
        result_actions.addWidget(result_refresh)
        results_layout.addLayout(result_actions)
        self.result_table = DataTable(
            ["Rank", "Roll", "Student", "Status", "Total", "Percentage", "Result", "Grade"]
        )
        self.result_table.apply_widths([60, 70, 220, 100, 80, 100, 100, 80])
        results_layout.addWidget(self.result_table, 1)
        self.result_note = QLabel("")
        self.result_note.setObjectName("small")
        self.result_note.setWordWrap(True)
        results_layout.addWidget(self.result_note)
        self.tabs.addTab(results_tab, "Results")

        self.table.itemSelectionChanged.connect(self._selection_changed)

    # ---------------------------------------------------------------- refresh
    def refresh(self) -> None:
        self.subtitle.setText(
            f"{self.context.settings.school_name} · {self.context.settings.subject} · "
            f"Session {self.context.settings.active_session_name()}"
        )
        if self.context.session_id is None:
            return
        self._reload_exams()

    def _class_changed(self) -> None:
        if self._loading:
            return
        if self._dirty and not self.confirm_discard():
            return
        self._reload_exams()

    def _reload_exams(self) -> None:
        self._loading = True
        try:
            session_id = self.context.session_id
            class_name = self.class_combo.currentData() or "9"
            self.exam_combo.clear()
            if session_id is None:
                self.exam_combo.addItem("No active session", None)
                self.exam_combo.setEnabled(False)
                return
            exams = self.context.marks.list_examinations(session_id, class_name)
            for exam in exams:
                label = str(exam["name"])
                if exam["exam_date"]:
                    label += f" · {exam['exam_date']}"
                self.exam_combo.addItem(label, int(exam["id"]))
            if not exams:
                self.exam_combo.addItem("No examinations yet", None)
            self.exam_combo.setEnabled(bool(exams))
        finally:
            self._loading = False
        self._exam_changed()

    def _exam_changed(self) -> None:
        if self._loading:
            return
        if self._dirty and not self.confirm_discard():
            return
        exam_id = self.exam_combo.currentData()
        self._exam = self.context.marks.get_examination(int(exam_id)) if exam_id else None
        self._dirty = False
        self._update_dirty()
        self.load_marks()

    # ------------------------------------------------------------------- load
    def load_marks(self) -> None:
        self.table.setRowCount(0)
        self._widgets.clear()
        self._rows = []
        if self._exam is None:
            self.table.hide()
            self.empty.show()
            self.tabs.setTabEnabled(1, False)
            self._update_cards(None)
            return
        self.empty.hide()
        self.table.show()
        self.tabs.setTabEnabled(1, True)
        try:
            rows = self.context.marks.exam_roster(int(self._exam["id"]))
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not load marks", str(exc))
            return
        self._rows = rows
        self._loading = True
        try:
            has_components = any(
                self._exam[key] is not None
                for key in ("theory_max", "practical_max", "project_max")
            )
            self.table.setColumnHidden(4, not (has_components and self._exam["theory_max"] is not None))
            self.table.setColumnHidden(5, not (has_components and self._exam["practical_max"] is not None))
            self.table.setColumnHidden(6, not (has_components and self._exam["project_max"] is not None))
            for row_index, row in enumerate(rows):
                self.table.insertRow(row_index)
                roll = QTableWidgetItem(str(row["roll_no"]))
                roll.setData(Qt.ItemDataRole.UserRole, int(row["student_id"]))
                name = QTableWidgetItem(str(row["full_name"]))
                section = QTableWidgetItem(row["section"] or "—")
                total_item = QTableWidgetItem(
                    f"{float(row['total']):g}" if row["total"] is not None else "—"
                )
                percent = calculations.percentage(
                    row["total"] if row["status"] == "entered" else None,
                    self._exam["max_marks"],
                )
                pct_item = QTableWidgetItem(format_pct(percent))
                result_item = QTableWidgetItem(self._result_text(row, percent))
                rank_item = QTableWidgetItem("—")
                for column, item in (
                    (0, roll),
                    (1, name),
                    (2, section),
                    (7, total_item),
                    (8, pct_item),
                    (9, result_item),
                    (10, rank_item),
                ):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row_index, column, item)
                status = QComboBox()
                for label, value in STATUS_OPTIONS:
                    status.addItem(label, value)
                index = status.findData(row["status"] or "pending")
                status.setCurrentIndex(max(0, index))
                self._style_status(status)
                status.currentIndexChanged.connect(
                    lambda _=0, sid=int(row["student_id"]): self._status_changed(sid)
                )
                self.table.setCellWidget(row_index, 3, status)
                widgets: dict[str, QWidget] = {"status": status}
                for key, column in (("theory", 4), ("practical", 5), ("project", 6), ("total", 7)):
                    if key == "total" and has_components:
                        continue
                    edit = QLineEdit()
                    edit.setPlaceholderText("—")
                    edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    if row.get(key) is not None:
                        edit.setText(f"{float(row[key]):g}")
                    edit.textEdited.connect(
                        lambda _t, sid=int(row["student_id"]): self._entry_changed(sid)
                    )
                    edit.editingFinished.connect(self._update_row_totals)
                    self.table.setCellWidget(row_index, column, edit)
                    widgets[key] = edit
                self._widgets[int(row["student_id"])] = widgets
        finally:
            self._loading = False
        self._dirty = False
        self._update_dirty()
        self._update_cards(None)
        self.refresh_results()

    def _result_text(self, row: dict, percent: float | None) -> str:
        if row["status"] == "absent":
            return "Absent"
        if row["status"] == "exempted":
            return "Exempted"
        if row["status"] != "entered" or row["total"] is None:
            return "Pending"
        passed = calculations.is_pass(
            row["total"],
            self._exam["max_marks"],
            self._exam["pass_marks"],
            self._exam["pass_percent"],
        )
        return "Passed" if passed else "Failed"

    def _style_status(self, combo: QComboBox) -> None:
        colors = {
            "entered": (palette()["success_soft"], palette()["success"]),
            "absent": (palette()["danger_soft"], palette()["danger"]),
            "exempted": (palette()["info_soft"], palette()["info"]),
            "pending": (palette()["surface_sunken"], palette()["text_muted"]),
        }
        background, foreground = colors.get(combo.currentData(), colors["pending"])
        combo.setStyleSheet(
            f"QComboBox {{ background: {background}; color: {foreground};"
            f" border: 1px solid {palette()['border']}; border-radius: 6px;"
            f" padding: 4px 8px; font-weight: 600; }}"
        )

    def _status_changed(self, student_id: int) -> None:
        widgets = self._widgets.get(int(student_id))
        if not widgets:
            return
        status = widgets["status"].currentData()
        self._style_status(widgets["status"])
        for key in ("theory", "practical", "project", "total"):
            if key in widgets:
                widgets[key].setEnabled(status == "entered")
        if not self._loading:
            self._set_dirty(True)
            self._update_row_totals()
            self.remarks_edit.setEnabled(True)

    def _entry_changed(self, student_id: int) -> None:
        if not self._loading:
            self._set_dirty(True)
            self._update_row_totals()

    def _update_row_totals(self) -> None:
        if self._exam is None:
            return
        for row, record in enumerate(self._rows):
            sid = int(record["student_id"])
            widgets = self._widgets.get(sid)
            if not widgets:
                continue
            status = widgets["status"].currentData()
            total = None
            if status == "entered":
                parts = []
                for key in ("theory", "practical", "project"):
                    if key in widgets:
                        text = widgets[key].text().strip()
                        if text:
                            try:
                                parts.append(float(text))
                            except ValueError:
                                parts = []
                                break
                if "total" in widgets:
                    text = widgets["total"].text().strip()
                    try:
                        total = float(text) if text else None
                    except ValueError:
                        total = None
                elif len(parts) == sum(
                    1 for key in ("theory", "practical", "project") if key in widgets
                ):
                    total = round(sum(parts), 2)
                if total is not None and not (0 <= total <= float(self._exam["max_marks"])):
                    total = None
            total_item = self.table.item(row, 7)
            if total_item:
                total_item.setText(f"{total:g}" if total is not None else "—")
            pct = calculations.percentage(total, self._exam["max_marks"])
            pct_item = self.table.item(row, 8)
            if pct_item:
                pct_item.setText(format_pct(pct))
            result_item = self.table.item(row, 9)
            if result_item:
                result_item.setText(
                    self._result_text({**record, "status": status, "total": total}, pct)
                )

    def _selection_changed(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._rows)):
            self.remarks_edit.setEnabled(False)
            return
        record = self._rows[row]
        self.remarks_edit.setEnabled(True)
        self.remarks_edit.blockSignals(True)
        self.remarks_edit.setText(record.get("remarks") or "")
        self.remarks_edit.blockSignals(False)
        self._remark_student_id = int(record["student_id"])

    def _remarks_changed(self, text: str) -> None:
        if not hasattr(self, "_remark_student_id"):
            return
        for record in self._rows:
            if int(record["student_id"]) == self._remark_student_id:
                record["remarks"] = text
                break
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._update_dirty()

    def _update_dirty(self) -> None:
        self.dirty_label.setVisible(self._dirty)
        self.dirty_label.setText("Unsaved marks changes")

    # ------------------------------------------------------------------- save
    def save(self) -> None:
        if self._exam is None:
            return
        entries = []
        for record in self._rows:
            sid = int(record["student_id"])
            widgets = self._widgets.get(sid)
            if not widgets:
                continue
            entry = {
                "student_id": sid,
                "roll_no": record["roll_no"],
                "status": widgets["status"].currentData(),
                "remarks": record.get("remarks") or "",
            }
            for key in ("theory", "practical", "project", "total"):
                if key in widgets:
                    entry[key] = widgets[key].text().strip()
            entries.append(entry)
        try:
            counts = self.context.marks.save_marks(int(self._exam["id"]), entries)
        except ValidationError as exc:
            error_dialog(self, "Could not save marks", str(exc))
            return
        except DatabaseError as exc:
            error_dialog(self, "Database error", str(exc))
            return
        notify(
            self,
            f"Marks saved — {counts['entered']} entered, {counts['absent']} absent, "
            f"{counts['exempted']} exempted, {counts['pending']} pending.",
        )
        self.load_marks()

    def has_unsaved_changes(self) -> bool:
        return self._dirty

    def confirm_discard(self, parent: QWidget | None = None) -> bool:
        if not self._dirty:
            return True
        return confirm_action(
            parent or self,
            "Unsaved marks",
            "Marks changes have not been saved. Discard them and continue?",
            confirm_text="Discard changes",
            danger=True,
        )

    # -------------------------------------------------------------- statistics
    def _update_cards(self, stats: dict | None) -> None:
        if stats is None and self._exam is not None:
            try:
                stats = self.context.marks.class_statistics(int(self._exam["id"]))
            except (ValidationError, DatabaseError):
                stats = None
        if not stats:
            for card in self.cards.values():
                card.set_value("—")
            return
        self.cards["students"].set_value(
            stats["students"],
            f"{stats['absent']} absent · {stats['exempted']} exempted",
        )
        self.cards["entered"].set_value(
            stats["entered"], f"of {stats['students']} students"
        )
        self.cards["average"].set_value(
            format_pct(stats["average_percentage"]),
            f"Average total {stats['average'] if stats['average'] is not None else '—'} "
            f"of {stats['max_marks']:g}",
        )
        self.cards["pass"].set_value(
            format_pct(stats["pass_percentage"]),
            f"{stats['passed']} passed · {stats['failed']} failed",
        )
        self.cards["pending"].set_value(
            stats["pending"], "Never counted as zero"
        )

    def refresh_results(self) -> None:
        if self._exam is None:
            self.result_table.set_data([])
            return
        try:
            stats = self.context.marks.class_statistics(int(self._exam["id"]))
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not load results", str(exc))
            return
        rules = self.context.settings.grade_rules()
        rows = []
        for record in sorted(
            stats["rows"],
            key=lambda r: (r["rank"] is None, r["rank"] or 0, str(r["roll_no"])),
        ):
            if record["status"] == "absent":
                result = "Absent"
            elif record["status"] == "exempted":
                result = "Exempted"
            elif record["status"] != "entered" or record["total"] is None:
                result = "Pending"
            else:
                result = "Passed" if record["passed"] else "Failed"
            rows.append(
                [
                    record["rank"] if record["rank"] is not None else "—",
                    record["roll_no"],
                    record["full_name"],
                    record["status"].title(),
                    f"{float(record['total']):g}" if record["total"] is not None else "—",
                    format_pct(record["percentage"]),
                    result,
                    calculations.grade_for(record["percentage"], rules),
                ]
            )
        self.result_table.set_data(rows)
        self._update_cards(stats)
        self.result_note.setText(
            f"{self._exam['name']} · Class {self._exam['class_name']} · "
            f"Maximum {float(self._exam['max_marks']):g} · "
            f"{self._exam_pass_note()} · Grades are teacher-configured, not an official SEBA policy."
        )

    def _exam_pass_note(self) -> str:
        if self._exam["pass_marks"] is not None:
            return f"Passing marks {float(self._exam['pass_marks']):g}"
        if self._exam["pass_percent"] is not None:
            return f"Pass percentage {float(self._exam['pass_percent']):g}%"
        return "Pass criteria not set"

    # -------------------------------------------------------------- exam CRUD
    def _new_exam(self) -> None:
        if self.context.session_id is None:
            return
        dialog = ExaminationDialog(self.context, parent=self)
        if dialog.exec():
            self._reload_exams()
            notify(self, getattr(dialog, "saved_message", "Examination created."))

    def _edit_exam(self) -> None:
        if self._exam is None:
            return
        dialog = ExaminationDialog(self.context, self._exam, parent=self)
        if dialog.exec():
            self._reload_exams()
            notify(self, getattr(dialog, "saved_message", "Examination updated."))

    def _delete_exam(self) -> None:
        if self._exam is None:
            return
        stats = self.context.marks.class_statistics(int(self._exam["id"]))
        if not confirm_action(
            self,
            "Delete examination",
            f"Delete “{self._exam['name']}” and all {stats['students']} recorded marks? "
            "This cannot be undone.",
            confirm_text="Delete examination",
            danger=True,
        ):
            return
        try:
            self.context.marks.delete_examination(int(self._exam["id"]))
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not delete examination", str(exc))
            return
        self._reload_exams()
        notify(self, "Examination deleted.", "info")

    # ----------------------------------------------------------------- import
    def _import_marks(self) -> None:
        if self._exam is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import marks",
            "",
            "Spreadsheets (*.xlsx *.xlsm *.xls *.csv);;All files (*.*)",
        )
        if not path:
            return
        try:
            rows = io_service.read_table_file(path)
        except (ValidationError, OSError) as exc:
            error_dialog(self, "Could not read file", str(exc))
            return
        if not rows:
            error_dialog(self, "Empty file", "The selected file contains no data rows.")
            return
        result = self.context.marks.import_marks(int(self._exam["id"]), rows)
        self.load_marks()
        if result.get("errors"):
            detail = "\n".join(
                f"Row {item.get('row', '?')}: {item.get('message', '')}"
                for item in result["errors"][:10]
            )
            QMessageBox.warning(
                self,
                "Import completed with issues",
                f"Saved {result.get('saved', 0)} rows.\n\n{detail}",
            )
        else:
            notify(self, f"Imported {result.get('saved', 0)} mark records.")

    def _download_template(self) -> None:
        if self._exam is None:
            return
        default = f"marks_class{self._exam['class_name']}_{str(self._exam['name']).replace(' ', '_')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save marks template", default, "Excel workbook (*.xlsx)"
        )
        if not path:
            return
        try:
            roster = self.context.marks.exam_roster(int(self._exam["id"]))
            io_service.write_marks_template(
                path,
                roster,
                self._exam["theory_max"],
                self._exam["practical_max"],
                self._exam["project_max"],
            )
        except (ValidationError, OSError) as exc:
            error_dialog(self, "Could not save template", str(exc))
            return
        notify(self, "Template saved. Fill marks, then use Import Excel/CSV.")

    def _export_rows(self) -> tuple[list[str], list[list]]:
        headers = ["Rank", "Roll", "Student", "Status", "Total", "Percentage", "Result", "Grade"]
        rows = []
        for index in range(self.result_table.rowCount()):
            rows.append(
                [
                    self.result_table.item(index, column).text()
                    if self.result_table.item(index, column)
                    else ""
                    for column in range(8)
                ]
            )
        return headers, rows

    def _export_excel(self) -> None:
        if self._exam is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export marks to Excel", f"marks_class{self._exam['class_name']}.xlsx",
            "Excel workbook (*.xlsx)",
        )
        if not path:
            return
        headers, rows = self._export_rows()
        try:
            io_service.export_excel(
                path,
                headers,
                rows,
                sheet_name="Marks",
                title=f"{self._exam['name']} — Class {self._exam['class_name']}",
                subtitle_lines=[
                    self.context.settings.school_name,
                    f"{self.context.settings.subject} · {self._exam_pass_note()}",
                ],
            )
        except (ValidationError, OSError, DatabaseError) as exc:
            error_dialog(self, "Could not export", str(exc))
            return
        notify(self, f"Marks exported to {Path(path).name}.")

    def _export_csv(self) -> None:
        if self._exam is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export marks to CSV", f"marks_class{self._exam['class_name']}.csv",
            "CSV file (*.csv)",
        )
        if not path:
            return
        headers, rows = self._export_rows()
        try:
            io_service.export_csv(
                path,
                headers,
                rows,
            )
        except (ValidationError, OSError) as exc:
            error_dialog(self, "Could not export", str(exc))
            return
        notify(self, f"Marks exported to {Path(path).name}.")
