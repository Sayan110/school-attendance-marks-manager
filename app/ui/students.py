"""Student management page: CRUD, search, filters, import and export."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.context import AppContext
from app.database import DatabaseError
from app.services import io_service
from app.ui.common import class_combo, make_date_edit, populate_sessions
from app.ui.icons import make_icon
from app.ui.widgets import (
    DataTable,
    EmptyState,
    Pager,
    confirm_action,
    error_dialog,
    info_dialog,
    notify,
    palette,
    set_variant,
)
from app.utils import dates as date_utils
from app.utils.validators import ValidationError


class StudentDialog(QDialog):
    def __init__(
        self,
        context: AppContext,
        student: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.student = student
        self.setWindowTitle("Edit student" if student else "Add student")
        self.setMinimumWidth(560)
        self.setModal(True)
        self._build()
        if student:
            self._fill(student)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = QLabel("Edit student details" if self.student else "Add a new student")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            f"{self.context.settings.school_name} · {self.context.settings.subject}"
        )
        subtitle.setObjectName("small")
        layout.addWidget(subtitle)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f"color: {palette()['danger']}; background: {palette()['danger_soft']};"
            " border-radius: 7px; padding: 7px 9px;"
        )
        self.error_label.hide()
        layout.addWidget(self.error_label)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        self.roll_edit = QLineEdit()
        self.roll_edit.setPlaceholderText("e.g. 12")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Full name as in the school register")
        self.class_combo = class_combo()
        self.section_edit = QLineEdit()
        self.section_edit.setPlaceholderText("Optional, e.g. A")
        self.session_combo = QComboBox()
        populate_sessions(self.session_combo, self.context.settings)
        self.guardian_edit = QLineEdit()
        self.guardian_edit.setPlaceholderText("Optional")
        self.contact_edit = QLineEdit()
        self.contact_edit.setPlaceholderText("Optional phone number")
        self.admission_check = QCheckBox("Record admission date")
        self.admission_check.setChecked(True)
        self.admission_edit = make_date_edit(date.today())
        admission_row = QWidget()
        admission_layout = QHBoxLayout(admission_row)
        admission_layout.setContentsMargins(0, 0, 0, 0)
        admission_layout.setSpacing(8)
        admission_layout.addWidget(self.admission_check)
        admission_layout.addWidget(self.admission_edit, 1)
        self.status_combo = QComboBox()
        self.status_combo.addItem("Active", "active")
        self.status_combo.addItem("Inactive", "inactive")
        self.remarks_edit = QPlainTextEdit()
        self.remarks_edit.setPlaceholderText("Optional notes")
        self.remarks_edit.setFixedHeight(64)

        form.addRow("Roll / admission no. *", self.roll_edit)
        form.addRow("Full name *", self.name_edit)
        form.addRow("Class *", self.class_combo)
        form.addRow("Section", self.section_edit)
        form.addRow("Academic session *", self.session_combo)
        form.addRow("Parent / guardian", self.guardian_edit)
        form.addRow("Contact number", self.contact_edit)
        form.addRow("Admission date", admission_row)
        form.addRow("Status", self.status_combo)
        form.addRow("Remarks", self.remarks_edit)
        layout.addLayout(form)

        self.admission_check.toggled.connect(self.admission_edit.setEnabled)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Save student")
        set_variant(save, "primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self.roll_edit.setFocus()

    def _fill(self, student: dict) -> None:
        self.roll_edit.setText(str(student.get("roll_no") or ""))
        self.name_edit.setText(str(student.get("full_name") or ""))
        index = self.class_combo.findData(str(student.get("class_name")))
        if index >= 0:
            self.class_combo.setCurrentIndex(index)
        self.section_edit.setText(str(student.get("section") or ""))
        session_index = self.session_combo.findData(int(student.get("session_id") or 0))
        if session_index >= 0:
            self.session_combo.setCurrentIndex(session_index)
        self.guardian_edit.setText(str(student.get("guardian_name") or ""))
        self.contact_edit.setText(str(student.get("contact_no") or ""))
        if student.get("admission_date"):
            self.admission_check.setChecked(True)
            parsed = QDate.fromString(str(student["admission_date"]), "yyyy-MM-dd")
            if parsed.isValid():
                self.admission_edit.setDate(parsed)
        else:
            self.admission_check.setChecked(False)
            self.admission_edit.setEnabled(False)
        status_index = self.status_combo.findData(str(student.get("status") or "active"))
        if status_index >= 0:
            self.status_combo.setCurrentIndex(status_index)
        self.remarks_edit.setPlainText(str(student.get("remarks") or ""))

    def _data(self) -> dict:
        return {
            "roll_no": self.roll_edit.text(),
            "full_name": self.name_edit.text(),
            "class_name": self.class_combo.currentData(),
            "section": self.section_edit.text(),
            "session_id": self.session_combo.currentData(),
            "guardian_name": self.guardian_edit.text(),
            "contact_no": self.contact_edit.text(),
            "admission_date": (
                self.admission_edit.date().toString("yyyy-MM-dd")
                if self.admission_check.isChecked()
                else ""
            ),
            "status": self.status_combo.currentData(),
            "remarks": self.remarks_edit.toPlainText(),
        }

    def _save(self) -> None:
        self.error_label.hide()
        for field in (self.roll_edit, self.name_edit, self.contact_edit):
            field.setProperty("invalid", False)
            field.style().unpolish(field)
            field.style().polish(field)
        try:
            if self.student:
                self.context.students.update(int(self.student["id"]), self._data())
            else:
                self.context.students.create(self._data())
        except ValidationError as exc:
            message = str(exc)
            if exc.errors:
                message += "\n" + "\n".join(f"• {value}" for value in exc.errors.values())
            self.error_label.setText(message)
            self.error_label.show()
            mapping = {
                "roll_no": self.roll_edit,
                "full_name": self.name_edit,
                "contact_no": self.contact_edit,
            }
            for field, widget in mapping.items():
                if field in exc.errors:
                    widget.setProperty("invalid", True)
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
            return
        except DatabaseError as exc:
            error_dialog(self, "Could not save student", str(exc))
            return
        self.accept()


class ImportStudentsDialog(QDialog):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.rows: list[dict] = []
        self.valid_rows: list[dict] = []
        self.errors: list[dict] = []
        self.setWindowTitle("Import students")
        self.resize(920, 620)
        self.setModal(True)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        title = QLabel("Import students from Excel or CSV")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        note = QLabel(
            "Choose a .xlsx, .xls or .csv file. Required columns: roll_no, full_name, "
            "class_name (9 or 10). The academic session is selected below. "
            "Existing students are never overwritten."
        )
        note.setWordWrap(True)
        note.setObjectName("small")
        layout.addWidget(note)

        top = QHBoxLayout()
        self.session_combo = QComboBox()
        populate_sessions(self.session_combo, self.context.settings)
        top.addWidget(QLabel("Academic session"))
        top.addWidget(self.session_combo)
        choose = QPushButton("Choose file…")
        choose.setIcon(make_icon("import", palette()["text"], 15))
        choose.clicked.connect(self._choose_file)
        top.addWidget(choose)
        self.file_label = QLabel("No file selected")
        self.file_label.setObjectName("small")
        top.addWidget(self.file_label, 1)
        template = QPushButton("Download template")
        template.clicked.connect(self._download_template)
        top.addWidget(template)
        layout.addLayout(top)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.tabs = QStackedWidget()
        self.preview = DataTable(["Row", "Roll", "Full name", "Class", "Section", "Guardian", "Status"])
        self.preview.setMinimumHeight(280)
        self.error_table = DataTable(["Row", "Problem"])
        self.error_table.setMinimumHeight(280)
        self.tabs.addWidget(self.preview)
        self.tabs.addWidget(self.error_table)
        self.tab_buttons = QHBoxLayout()
        self.valid_button = QPushButton("Valid rows (0)")
        self.valid_button.setCheckable(True)
        self.valid_button.setChecked(True)
        self.valid_button.clicked.connect(lambda: self._show_tab(0))
        self.error_button = QPushButton("Errors (0)")
        self.error_button.setCheckable(True)
        self.error_button.clicked.connect(lambda: self._show_tab(1))
        self.tab_buttons.addWidget(self.valid_button)
        self.tab_buttons.addWidget(self.error_button)
        self.tab_buttons.addStretch(1)
        layout.addLayout(self.tab_buttons)
        layout.addWidget(self.tabs, 1)

        self.import_button = QPushButton("Import students")
        set_variant(self.import_button, "primary")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        bottom.addWidget(self.import_button)
        layout.addLayout(bottom)

    def _show_tab(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        self.valid_button.setChecked(index == 0)
        self.error_button.setChecked(index == 1)

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select student import file",
            str(config.default_export_dir()),
            "Spreadsheets (*.xlsx *.xlsm *.xls *.csv);;All files (*.*)",
        )
        if not path:
            return
        self.file_label.setText(Path(path).name)
        try:
            raw_rows = io_service.read_table_file(path)
        except ValidationError as exc:
            error_dialog(self, "Could not read file", str(exc))
            return
        self.rows = [io_service.normalize_student_row(row) for row in raw_rows]
        self._validate()

    def _validate(self) -> None:
        session_id = self.session_combo.currentData()
        if not session_id:
            error_dialog(self, "No session", "Select an academic session first.")
            return
        self.valid_rows, self.errors = self.context.students.validate_import_rows(
            int(session_id), self.rows
        )
        preview_rows = [
            [
                row["_row"], row["roll_no"], row["full_name"], row["class_name"],
                row["section"], row["guardian_name"] or "", row["status"],
            ]
            for row in self.valid_rows
        ]
        self.preview.set_data(preview_rows)
        self.preview.apply_widths([50, 70, 210, 60, 60, 180, 80])
        self.error_table.set_data(
            [[error["row"], error["message"]] for error in self.errors]
        )
        self.error_table.apply_widths([60, 760])
        self.valid_button.setText(f"Valid rows ({len(self.valid_rows)})")
        self.error_button.setText(f"Errors ({len(self.errors)})")
        self.import_button.setEnabled(bool(self.valid_rows))
        if self.errors:
            self.status_label.setStyleSheet(
                f"color: {palette()['warning']}; background: {palette()['warning_soft']};"
                " border-radius: 7px; padding: 7px 9px;"
            )
            self.status_label.setText(
                f"{len(self.valid_rows)} row(s) can be imported. {len(self.errors)} row(s) "
                "have problems and will be skipped. Review the Errors tab before importing."
            )
            self._show_tab(1)
        else:
            self.status_label.setStyleSheet(
                f"color: {palette()['success']}; background: {palette()['success_soft']};"
                " border-radius: 7px; padding: 7px 9px;"
            )
            self.status_label.setText(
                f"All {len(self.valid_rows)} row(s) passed validation and are ready to import."
            )
            self._show_tab(0)

    def _import(self) -> None:
        if not self.valid_rows:
            return
        if not confirm_action(
            self,
            "Import students",
            f"Import {len(self.valid_rows)} student(s) into "
            f"{self.session_combo.currentText()}? Existing students will not be changed.",
            confirm_text="Import",
        ):
            return
        session_id = int(self.session_combo.currentData())
        try:
            result = self.context.students.import_students(session_id, self.rows, skip_invalid=True)
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Import failed", str(exc))
            return
        notify(self, f"{result['imported']} student(s) imported successfully.")
        self.accept()

    def _download_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save student import template",
            str(config.default_export_dir() / "student_import_template.xlsx"),
            "Excel workbook (*.xlsx);;CSV file (*.csv)",
        )
        if not path:
            return
        try:
            saved = io_service.write_student_template(path)
            info_dialog(
                self,
                "Template saved",
                f"Template saved to:\n{saved}\n\nFill in the Students sheet and import it here.",
            )
        except OSError as exc:
            error_dialog(self, "Could not save template", str(exc))


class StudentsPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._page = 1
        self._page_size = 25
        self._sort_key = "roll_no"
        self._sort_dir = "asc"
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(260)
        self._search_timer.timeout.connect(self._filters_changed)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("Students")
        title.setObjectName("pageTitle")
        titles.addWidget(title)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("pageSubtitle")
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        self.session_badge = QLabel("")
        self.session_badge.setObjectName("sessionBadge")
        header.addWidget(self.session_badge)
        layout.addLayout(header)

        toolbar = QFrame()
        toolbar.setObjectName("card")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(12, 10, 12, 10)
        bar.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name, roll number or guardian…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(260)
        self.search_edit.textChanged.connect(lambda: self._search_timer.start())
        bar.addWidget(self.search_edit, 1)
        self.class_filter = class_combo(include_all=True)
        self.class_filter.currentIndexChanged.connect(self._filters_changed)
        bar.addWidget(self.class_filter)
        self.section_filter = QComboBox()
        self.section_filter.setMinimumWidth(110)
        self.section_filter.currentIndexChanged.connect(self._filters_changed)
        bar.addWidget(self.section_filter)
        self.status_filter = QComboBox()
        self.status_filter.addItem("Active", "active")
        self.status_filter.addItem("Inactive", "inactive")
        self.status_filter.addItem("Archived", "archived")
        self.status_filter.addItem("All", "all")
        self.status_filter.currentIndexChanged.connect(self._filters_changed)
        bar.addWidget(self.status_filter)
        export = QPushButton("Export")
        export.setIcon(make_icon("export", palette()["text"], 15))
        menu = QMenu(export)
        menu.addAction("Export list to Excel…", lambda: self._export("xlsx"))
        menu.addAction("Export list to CSV…", lambda: self._export("csv"))
        export.setMenu(menu)
        bar.addWidget(export)
        layout.addWidget(toolbar)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        add = QPushButton("Add student")
        add.setIcon(make_icon("plus", "#ffffff", 15))
        set_variant(add, "primary")
        add.clicked.connect(self.add_student)
        actions.addWidget(add)
        self.edit_button = QPushButton("Edit")
        self.edit_button.setIcon(make_icon("edit", palette()["text"], 15))
        self.edit_button.clicked.connect(self.edit_student)
        actions.addWidget(self.edit_button)
        self.archive_button = QPushButton("Archive")
        self.archive_button.setIcon(make_icon("trash", palette()["text"], 15))
        self.archive_button.clicked.connect(self.archive_student)
        actions.addWidget(self.archive_button)
        self.restore_button = QPushButton("Restore")
        self.restore_button.setIcon(make_icon("refresh", palette()["text"], 15))
        self.restore_button.clicked.connect(self.restore_student)
        actions.addWidget(self.restore_button)
        self.delete_button = QPushButton("Delete permanently")
        self.delete_button.setIcon(make_icon("trash", palette()["danger"], 15))
        self.delete_button.clicked.connect(self.delete_student)
        actions.addWidget(self.delete_button)
        import_button = QPushButton("Import CSV / Excel")
        import_button.setIcon(make_icon("import", palette()["text"], 15))
        import_button.clicked.connect(self.import_students)
        actions.addWidget(import_button)
        template_button = QPushButton("Sample template")
        template_button.setIcon(make_icon("reports", palette()["text"], 15))
        template_button.clicked.connect(self.download_template)
        actions.addWidget(template_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.empty_state = EmptyState(
            "No students yet",
            "Add students one at a time, or import a CSV/Excel file. Students are stored "
            "locally in this computer's SQLite database.",
            icon="students",
            action_text="Add your first student",
        )
        if self.empty_state.button:
            self.empty_state.button.clicked.connect(self.add_student)
        layout.addWidget(self.empty_state, 1)

        self.table_panel = QWidget()
        panel = QVBoxLayout(self.table_panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(6)
        self.no_results = QLabel("No students match your filters.")
        self.no_results.setObjectName("small")
        self.no_results.hide()
        panel.addWidget(self.no_results)
        self.table = DataTable(
            ["Roll", "Full name", "Class", "Section", "Guardian", "Contact", "Admission date", "Status"]
        )
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().sectionClicked.connect(self._header_clicked)
        self.table.doubleClicked.connect(lambda _: self.edit_student())
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.setMinimumHeight(320)
        panel.addWidget(self.table, 1)
        self.pager = Pager(self._page_size)
        self.pager.changed.connect(self._pager_changed)
        panel.addWidget(self.pager)
        layout.addWidget(self.table_panel, 1)
        self._selection_changed()

    # --------------------------------------------------------------- refresh
    def refresh(self) -> None:
        session_id = self.context.session_id
        self.session_badge.setText(
            f"Session {self.context.settings.active_session_name()}"
        )
        self.subtitle.setText(
            f"{self.context.settings.school_name} · {self.context.settings.subject} · "
            f"Session {self.context.settings.active_session_name()}"
        )
        if session_id is None:
            self.table_panel.hide()
            self.empty_state.show()
            return
        self._populate_sections(session_id)
        class_name = self.class_filter.currentData()
        section = self.section_filter.currentData()
        status = self.status_filter.currentData() or "active"
        try:
            rows, total = self.context.students.list_students(
                session_id,
                class_name=class_name,
                section=section,
                search=self.search_edit.text(),
                status=status,
                page=self._page,
                page_size=self._page_size,
                sort_by=self._sort_key,
                sort_dir=self._sort_dir,
            )
            active_counts = self.context.students.count_by_class(session_id)
        except DatabaseError as exc:
            error_dialog(self, "Database error", str(exc))
            return
        self.pager.set_total(total)
        data = [
            [
                row["roll_no"],
                row["full_name"],
                f"Class {row['class_name']}",
                row["section"] or "—",
                row["guardian_name"] or "—",
                row["contact_no"] or "—",
                date_utils.display(row["admission_date"]),
                row["status"].title(),
            ]
            for row in rows
        ]
        self.table.set_data(data, row_ids=[row["id"] for row in rows])
        self.table.apply_widths([70, 220, 70, 65, 170, 130, 110, 80])
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSortIndicator(
            {"roll_no": 0, "full_name": 1, "class_name": 2, "section": 3, "status": 7}.get(
                self._sort_key, 0
            ),
            Qt.SortOrder.DescendingOrder if self._sort_dir == "desc" else Qt.SortOrder.AscendingOrder,
        )
        has_any = (active_counts["9"] + active_counts["10"]) > 0
        no_filters = (
            not self.search_edit.text().strip()
            and class_name is None
            and section is None
            and (self.status_filter.currentData() or "active") == "active"
        )
        if total == 0 and not has_any and no_filters:
            self.table_panel.hide()
            self.empty_state.show()
            self.empty_state.title_label.setText("No students yet")
            self.empty_state.text_label.setText(
                "Add students one at a time, or import a CSV/Excel file. Every record is "
                "stored locally in the school database on this computer."
            )
        else:
            self.empty_state.hide()
            self.table_panel.show()
            self.no_results.setVisible(total == 0)
        self._selection_changed()

    def _populate_sections(self, session_id: int) -> None:
        current = self.section_filter.currentData()
        self.section_filter.blockSignals(True)
        self.section_filter.clear()
        self.section_filter.addItem("All sections", None)
        for section in self.context.students.sections(
            session_id, self.class_filter.currentData()
        ):
            self.section_filter.addItem(f"Section {section}", section)
        if current:
            index = self.section_filter.findData(current)
            if index >= 0:
                self.section_filter.setCurrentIndex(index)
        self.section_filter.blockSignals(False)

    def _filters_changed(self) -> None:
        self._page = 1
        self.refresh()

    def _pager_changed(self) -> None:
        self._page = self.pager.page
        self._page_size = self.pager.page_size
        self.refresh()

    def _header_clicked(self, column: int) -> None:
        mapping = {0: "roll_no", 1: "full_name", 2: "class_name", 3: "section", 7: "status"}
        if column not in mapping:
            return
        key = mapping[column]
        if key == self._sort_key:
            self._sort_dir = "desc" if self._sort_dir == "asc" else "asc"
        else:
            self._sort_key = key
            self._sort_dir = "asc"
        self.refresh()

    def _selection_changed(self) -> None:
        row = self.table.currentRow()
        selected = row >= 0 and bool(self.table.selected_row_id())
        self.edit_button.setEnabled(selected)
        self.archive_button.setEnabled(selected)
        self.restore_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)
        if not selected:
            return
        student_id = self.table.selected_row_id()
        student = self.context.students.get(student_id)
        if student:
            archived = student["status"] == "archived"
            self.archive_button.setEnabled(not archived)
            self.restore_button.setEnabled(archived)
            self.edit_button.setEnabled(not archived)

    # --------------------------------------------------------------- actions
    def add_student(self) -> None:
        if self.context.session_id is None:
            error_dialog(self, "No academic session", "Create an academic session in Settings first.")
            return
        dialog = StudentDialog(self.context, None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            notify(self, "Student added successfully.")
            self.refresh()

    def edit_student(self) -> None:
        student_id = self.table.selected_row_id()
        if not student_id:
            return
        student = self.context.students.get(student_id)
        if not student:
            error_dialog(self, "Not found", "This student no longer exists.")
            return
        dialog = StudentDialog(self.context, dict(student), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            notify(self, "Student details updated.")
            self.refresh()

    def archive_student(self) -> None:
        student_id = self.table.selected_row_id()
        if not student_id:
            return
        student = self.context.students.get(student_id)
        if not student:
            return
        if not confirm_action(
            self,
            "Archive student",
            f"Archive {student['full_name']} (Roll {student['roll_no']})?\n\n"
            "The student will be hidden from active lists, but all attendance and marks "
            "records are preserved. You can restore the student later.",
            confirm_text="Archive",
            danger=True,
        ):
            return
        try:
            self.context.students.archive(student_id)
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not archive", str(exc))
            return
        notify(self, "Student archived. Records preserved.")
        self.refresh()

    def restore_student(self) -> None:
        student_id = self.table.selected_row_id()
        if not student_id:
            return
        try:
            self.context.students.restore(student_id)
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not restore", str(exc))
            return
        notify(self, "Student restored to the active list.")
        self.refresh()

    def delete_student(self) -> None:
        student_id = self.table.selected_row_id()
        if not student_id:
            return
        student = self.context.students.get(student_id)
        if not student:
            return
        counts = self.context.students.record_counts(student_id)
        if counts["attendance"] or counts["marks"]:
            warn_text = (
                f"{student['full_name']} has {counts['attendance']} attendance record(s) and "
                f"{counts['marks']} marks record(s).\n\n"
                "Permanent deletion is blocked to preserve data integrity. "
                "Archive this student instead."
            )
            error_dialog(self, "Cannot delete permanently", warn_text)
            return
        if not confirm_action(
            self,
            "Delete student permanently",
            f"Permanently delete {student['full_name']} (Roll {student['roll_no']})?\n\n"
            "This cannot be undone. This student has no attendance or marks records.",
            confirm_text="Delete permanently",
            danger=True,
        ):
            return
        try:
            self.context.students.delete_permanently(student_id)
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Could not delete", str(exc))
            return
        notify(self, "Student deleted permanently.", "warning")
        self.refresh()

    def import_students(self) -> None:
        if self.context.session_id is None:
            error_dialog(self, "No academic session", "Create an academic session first.")
            return
        dialog = ImportStudentsDialog(self.context, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def download_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save sample student import template",
            str(config.default_export_dir() / "student_import_template.xlsx"),
            "Excel workbook (*.xlsx);;CSV file (*.csv)",
        )
        if not path:
            return
        try:
            saved = io_service.write_student_template(path)
        except OSError as exc:
            error_dialog(self, "Could not save template", str(exc))
            return
        notify(self, f"Template saved: {saved}")

    def _export(self, kind: str) -> None:
        session_id = self.context.session_id
        if session_id is None:
            return
        rows, total = self.context.students.list_students(
            session_id,
            class_name=self.class_filter.currentData(),
            section=self.section_filter.currentData(),
            search=self.search_edit.text(),
            status=self.status_filter.currentData() or "active",
            page=1,
            page_size=10000,
            sort_by=self._sort_key,
            sort_dir=self._sort_dir,
        )
        if not rows:
            info_dialog(self, "Nothing to export", "No students match the current filters.")
            return
        extension = "xlsx" if kind == "xlsx" else "csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export student list",
            str(config.default_export_dir() / f"students_{self.context.session_name}.{extension}"),
            "Excel workbook (*.xlsx)" if kind == "xlsx" else "CSV file (*.csv)",
        )
        if not path:
            return
        headers = ["Roll", "Full name", "Class", "Section", "Session", "Guardian", "Contact", "Admission date", "Status"]
        data = [
            [
                row["roll_no"], row["full_name"], row["class_name"], row["section"],
                row["session_name"], row["guardian_name"] or "", row["contact_no"] or "",
                row["admission_date"] or "", row["status"],
            ]
            for row in rows
        ]
        try:
            if kind == "xlsx":
                io_service.export_excel(
                    path, headers, data, "Students", "Student list",
                    [self.context.settings.school_name, self.context.settings.subject],
                )
            else:
                io_service.export_csv(path, headers, data)
        except OSError as exc:
            error_dialog(self, "Export failed", str(exc))
            return
        notify(self, f"Exported {len(rows)} students.")

    def _context_menu(self, position) -> None:
        if self.table.rowAt(position.y()) < 0:
            return
        self.table.selectRow(self.table.rowAt(position.y()))
        menu = QMenu(self)
        edit = QAction("Edit student", self)
        edit.triggered.connect(self.edit_student)
        menu.addAction(edit)
        archive = QAction("Archive", self)
        archive.triggered.connect(self.archive_student)
        menu.addAction(archive)
        restore = QAction("Restore", self)
        restore.triggered.connect(self.restore_student)
        menu.addAction(restore)
        menu.addSeparator()
        delete = QAction("Delete permanently…", self)
        delete.triggered.connect(self.delete_student)
        menu.addAction(delete)
        menu.exec(self.table.viewport().mapToGlobal(position))
