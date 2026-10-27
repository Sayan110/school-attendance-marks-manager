"""Reports page: A4 PDF reports, Excel/CSV export and print preview."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.context import AppContext
from app.database import DatabaseError
from app.reports.exporters import document_to_csv, document_to_excel
from app.reports.html_reports import render_html
from app.reports.pdf_reports import render_pdf
from app.services.report_service import REPORT_TYPES, ReportDocument
from app.ui.common import class_combo, date_to_iso, make_date_edit, set_date_edit
from app.ui.icons import make_icon
from app.ui.widgets import PageHeader, busy, error_dialog, notify, palette, set_variant
from app.utils import dates as date_utils
from app.utils.validators import ValidationError


class ReportsPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._document: ReportDocument | None = None
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(12)
        outer.addWidget(
            PageHeader(
                "Reports",
                "Ten A4 reports with the school name, previewed before export. PDF, Excel and CSV "
                "exports are available.",
            )
        )
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("small")
        outer.addWidget(self.subtitle)

        card = QFrame()
        card.setObjectName("inset")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Report type"))
        self.report_combo = QComboBox()
        for key, label in REPORT_TYPES:
            self.report_combo.addItem(label, key)
        self.report_combo.setMinimumWidth(320)
        self.report_combo.setMaximumWidth(380)
        self.report_combo.currentIndexChanged.connect(self._type_changed)
        top.addWidget(self.report_combo)
        top.addStretch(1)
        top.addWidget(QLabel("Academic session"))
        self.session_label = QLabel("")
        self.session_label.setObjectName("badge")
        top.addWidget(self.session_label)
        card_layout.addLayout(top)

        self.params = QGridLayout()
        self.params.setHorizontalSpacing(10)
        self.params.setVerticalSpacing(6)

        self.class_combo = class_combo(include_all=True)
        self.class_combo.currentIndexChanged.connect(self._students_changed)
        self.class_combo.currentIndexChanged.connect(self._preview)
        self.class_container = self._field("Class", self.class_combo)

        self.student_combo = QComboBox()
        self.student_combo.setMinimumWidth(260)
        self.student_combo.currentIndexChanged.connect(self._preview)
        self.student_container = self._field("Student", self.student_combo)

        self.exam_combo = QComboBox()
        self.exam_combo.setMinimumWidth(240)
        self.exam_combo.currentIndexChanged.connect(self._preview)
        self.exam_container = self._field("Examination", self.exam_combo)

        self.date_edit = make_date_edit(date.today())
        self.date_edit.dateChanged.connect(self._preview)
        self.date_container = self._field("Date", self.date_edit)

        self.month_edit = make_date_edit(date.today().replace(day=1))
        self.month_edit.setDisplayFormat("MMMM yyyy")
        self.month_edit.dateChanged.connect(self._preview)
        self.month_container = self._field("Month", self.month_edit)

        self.start_edit = make_date_edit(date(date.today().year, 4, 1))
        self.end_edit = make_date_edit(date.today())
        self.start_edit.dateChanged.connect(self._preview)
        self.end_edit.dateChanged.connect(self._preview)
        self.range_container = QWidget()
        range_layout = QHBoxLayout(self.range_container)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setSpacing(5)
        range_layout.addWidget(self.start_edit)
        range_layout.addWidget(QLabel("to"))
        range_layout.addWidget(self.end_edit)
        self.range_field = self._field("Date range", self.range_container)

        self.params.addWidget(self.class_container, 0, 0)
        self.params.addWidget(self.student_container, 0, 1)
        self.params.addWidget(self.exam_container, 0, 2)
        self.params.addWidget(self.date_container, 1, 0)
        self.params.addWidget(self.month_container, 1, 1)
        self.params.addWidget(self.range_field, 1, 2)
        self.params.setColumnStretch(3, 1)
        card_layout.addLayout(self.params)
        self._reflow_params()

        actions = QHBoxLayout()
        actions.setSpacing(7)
        preview_button = QPushButton("Refresh preview")
        preview_button.setIcon(make_icon("refresh", palette()["text"], 15))
        preview_button.clicked.connect(self._preview)
        actions.addWidget(preview_button)
        actions.addStretch(1)
        print_button = QPushButton("Print preview")
        print_button.setIcon(make_icon("print-preview", palette()["text"], 15))
        print_button.clicked.connect(self.print_preview)
        actions.addWidget(print_button)
        pdf_button = QPushButton("Save PDF")
        pdf_button.setIcon(make_icon("print", "#ffffff", 15))
        set_variant(pdf_button, "primary")
        pdf_button.clicked.connect(self.save_pdf)
        actions.addWidget(pdf_button)
        excel_button = QPushButton("Export Excel")
        excel_button.setIcon(make_icon("export", palette()["text"], 15))
        excel_button.clicked.connect(self.export_excel)
        actions.addWidget(excel_button)
        csv_button = QPushButton("Export CSV")
        csv_button.clicked.connect(self.export_csv)
        actions.addWidget(csv_button)
        card_layout.addLayout(actions)
        outer.addWidget(card)

        note = QLabel(
            "Session summary, student progress, support and threshold reports use only saved "
            "records. Blank marks remain blank; attendance percentages follow the Leave setting."
        )
        note.setObjectName("small")
        note.setWordWrap(True)
        outer.addWidget(note)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.preview.setStyleSheet(
            f"QTextBrowser {{ background: #ffffff; border: 1px solid {palette()['border']};"
            f" border-radius: 10px; padding: 10px; }}"
        )
        outer.addWidget(self.preview, 1)
        self.status = QLabel("")
        self.status.setObjectName("small")
        outer.addWidget(self.status)

    @staticmethod
    def _field(label: str, widget: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        caption = QLabel(label)
        caption.setObjectName("small")
        caption.setStyleSheet("font-weight: 600;")
        layout.addWidget(caption)
        layout.addWidget(widget)
        return container

    # ---------------------------------------------------------------- state
    def refresh(self) -> None:
        self.subtitle.setText(
            f"{self.context.settings.school_name} · {self.context.settings.subject} · "
            f"{self.context.settings.board}"
        )
        self.session_label.setText(f"Session {self.context.settings.active_session_name()}")
        self._students_changed()
        self._exams_changed()
        self._type_changed()

    def _required(self) -> dict[str, bool]:
        key = self.report_combo.currentData()
        return {
            "class": key in (
                "daily_attendance",
                "monthly_attendance",
                "class_attendance",
                "marksheet",
                "class_performance",
            ),
            "class_optional": key in ("support_report", "below_threshold"),
            "student": key in ("student_attendance", "student_progress"),
            "exam": key == "marksheet",
            "date": key == "daily_attendance",
            "month": key == "monthly_attendance",
            "range": key in (
                "student_attendance",
                "student_progress",
                "class_attendance",
                "class_performance",
                "support_report",
                "below_threshold",
                "session_summary",
            ),
        }

    def _type_changed(self) -> None:
        required = self._required()
        self.class_container.setVisible(required["class"] or required["class_optional"])
        self.student_container.setVisible(required["student"])
        self.exam_container.setVisible(required["exam"])
        self.date_container.setVisible(required["date"])
        self.month_container.setVisible(required["month"])
        self.range_field.setVisible(required["range"])
        self._reflow_params()
        if required["class_optional"]:
            index = self.class_combo.findData(None)
            if self.class_combo.currentData() is not None:
                self.class_combo.setCurrentIndex(index if index >= 0 else 0)
        elif required["class"]:
            if self.class_combo.currentData() is None:
                self.class_combo.setCurrentIndex(1)
        if required["student"]:
            self._students_changed()
        self._preview()

    def _reflow_params(self) -> None:
        """Lay the visible parameter fields out left to right, three per row."""
        order = (
            self.class_container,
            self.student_container,
            self.exam_container,
            self.date_container,
            self.month_container,
            self.range_field,
        )
        while self.params.count():
            self.params.takeAt(0)
        row = column = 0
        for field in order:
            if field.isHidden():
                continue
            self.params.addWidget(field, row, column)
            column += 1
            if column == 3:
                row, column = row + 1, 0

    def _students_changed(self) -> None:
        if not hasattr(self, "student_combo"):
            return
        session_id = self.context.session_id
        class_name = self.class_combo.currentData()
        current = self.student_combo.currentData()
        self.student_combo.blockSignals(True)
        self.student_combo.clear()
        if session_id is not None:
            for student in self.context.students.all_students(session_id, class_name):
                self.student_combo.addItem(
                    f"{student['roll_no']} · {student['full_name']} (Class {student['class_name']})",
                    int(student["id"]),
                )
        index = self.student_combo.findData(current) if current else -1
        if index >= 0:
            self.student_combo.setCurrentIndex(index)
        self.student_combo.blockSignals(False)

    def _exams_changed(self) -> None:
        session_id = self.context.session_id
        current = self.exam_combo.currentData()
        self.exam_combo.blockSignals(True)
        self.exam_combo.clear()
        if session_id is not None:
            for exam in self.context.marks.list_examinations(session_id, None):
                self.exam_combo.addItem(
                    f"{exam['name']} · Class {exam['class_name']}", int(exam["id"])
                )
        index = self.exam_combo.findData(current) if current else -1
        if index >= 0:
            self.exam_combo.setCurrentIndex(index)
        self.exam_combo.blockSignals(False)

    # --------------------------------------------------------------- building
    def _build_document(self) -> ReportDocument:
        key = self.report_combo.currentData()
        session_id = self.context.session_id
        if session_id is None:
            raise ValidationError("Create an academic session before generating reports.")
        class_name = self.class_combo.currentData()
        start = date_to_iso(self.start_edit)
        end = date_to_iso(self.end_edit)
        if start > end:
            start, end = end, start
        if key == "daily_attendance":
            if class_name not in ("9", "10"):
                raise ValidationError("Select Class 9 or Class 10 for a daily register.")
            return self.context.reports.daily_attendance(
                session_id, class_name, date_to_iso(self.date_edit)
            )
        if key == "monthly_attendance":
            if class_name not in ("9", "10"):
                raise ValidationError("Select Class 9 or Class 10 for a monthly register.")
            selected = self.month_edit.date()
            return self.context.reports.monthly_attendance(
                session_id, class_name, selected.year(), selected.month()
            )
        if key in ("student_attendance", "student_progress"):
            student_id = self.student_combo.currentData()
            if not student_id:
                raise ValidationError("Select a student for this report.")
            builder = (
                self.context.reports.student_attendance
                if key == "student_attendance"
                else self.context.reports.student_progress
            )
            return builder(int(student_id), start, end)
        if key in ("class_attendance", "class_performance"):
            if class_name not in ("9", "10"):
                raise ValidationError("Select Class 9 or Class 10 for this report.")
            builder = (
                self.context.reports.class_attendance
                if key == "class_attendance"
                else self.context.reports.class_performance
            )
            return builder(session_id, class_name, start, end)
        if key == "marksheet":
            exam_id = self.exam_combo.currentData()
            if not exam_id:
                raise ValidationError("Create an examination before generating a marksheet.")
            return self.context.reports.marksheet(int(exam_id))
        if key == "support_report":
            return self.context.reports.support_report(session_id, class_name, start, end)
        if key == "below_threshold":
            return self.context.reports.below_threshold(session_id, class_name, start, end)
        if key == "session_summary":
            return self.context.reports.session_summary(session_id, start, end)
        raise ValidationError("Select a report type.")

    def _preview(self) -> None:
        if not hasattr(self, "preview"):
            return
        try:
            document = self._build_document()
        except (ValidationError, DatabaseError) as exc:
            self._document = None
            self.preview.setHtml(
                f"<p style='color:{palette()['danger']}; font-family: Segoe UI;'>"
                f"{self._escape(str(exc))}</p>"
            )
            self.status.setText("Preview unavailable — check the selected parameters.")
            return
        self._document = document
        self.preview.setHtml(render_html(document))
        table_rows = sum(len(table.rows) for table in document.tables)
        self.status.setText(
            f"{document.title} · {document.filename_stem} · {table_rows} table rows · "
            f"Generated {document.generated_at} · A4 {'landscape' if document.landscape else 'portrait'}"
        )

    @staticmethod
    def _escape(text: str) -> str:
        import html

        return html.escape(text).replace("\n", "<br/>")

    def _current(self) -> ReportDocument | None:
        try:
            document = self._build_document()
        except (ValidationError, DatabaseError) as exc:
            error_dialog(self, "Report not available", str(exc))
            return None
        self._document = document
        self.preview.setHtml(render_html(document))
        return document

    # ---------------------------------------------------------------- actions
    def save_pdf(self) -> None:
        document = self._current()
        if document is None:
            return
        default = f"{document.filename_stem}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save report as PDF", default, "PDF document (*.pdf)"
        )
        if not path:
            return
        try:
            with busy(self):
                render_pdf(document, path)
        except (ValidationError, OSError, DatabaseError) as exc:
            error_dialog(self, "Could not save PDF", str(exc))
            return
        notify(self, f"PDF saved to {path}")

    def export_excel(self) -> None:
        document = self._current()
        if document is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export report to Excel",
            f"{document.filename_stem}.xlsx",
            "Excel workbook (*.xlsx)",
        )
        if not path:
            return
        try:
            with busy(self):
                document_to_excel(document, path)
        except (ValidationError, OSError, DatabaseError) as exc:
            error_dialog(self, "Could not export Excel", str(exc))
            return
        notify(self, f"Excel report saved to {path}")

    def export_csv(self) -> None:
        document = self._current()
        if document is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export report to CSV",
            f"{document.filename_stem}.csv",
            "CSV file (*.csv)",
        )
        if not path:
            return
        try:
            with busy(self):
                document_to_csv(document, path)
        except (ValidationError, OSError, DatabaseError) as exc:
            error_dialog(self, "Could not export CSV", str(exc))
            return
        notify(self, f"CSV report saved to {path}")

    def print_preview(self) -> None:
        document = self._current()
        if document is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPrinter.PageSize.A4)
        printer.setPageOrientation(
            QPrinter.Orientation.Landscape
            if document.landscape
            else QPrinter.Orientation.Portrait
        )
        printer.setDocName(document.title)
        dialog = QPrintPreviewDialog(printer, self)
        dialog.setWindowTitle(f"Print preview — {document.title}")
        dialog.paintRequested.connect(lambda target: self._render_print(target, document))
        dialog.exec()

    def _render_print(self, printer: QPrinter, document: ReportDocument) -> None:
        text = QTextDocument()
        text.setHtml(render_html(document))
        text.setPageSize(printer.pageRect(QPrinter.Unit.DevicePixel).size())
        text.print_(printer)
