"""Professional A4 PDF rendering for report documents."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape as landscape_size
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.report_service import ReportDocument, ReportTable

TEAL = colors.HexColor("#0F766E")
DARK = colors.HexColor("#122033")
MUTED = colors.HexColor("#5B6B7F")
BORDER = colors.HexColor("#D8E0EA")
ZEBRA = colors.HexColor("#F7F9FC")
SOFT = colors.HexColor("#EEF4F7")


def _styles(base_font: str = "Helvetica") -> dict[str, ParagraphStyle]:
    return {
        "school": ParagraphStyle(
            "school", fontName=f"{base_font}-Bold", fontSize=15.5, leading=18,
            textColor=TEAL, alignment=TA_CENTER, spaceAfter=1,
        ),
        "board": ParagraphStyle(
            "board", fontName=base_font, fontSize=8, leading=10, textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "title": ParagraphStyle(
            "title", fontName=f"{base_font}-Bold", fontSize=12.5, leading=16,
            textColor=DARK, spaceBefore=8, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName=base_font, fontSize=8.8, leading=11, textColor=MUTED,
            spaceAfter=5,
        ),
        "meta": ParagraphStyle(
            "meta", fontName=base_font, fontSize=7.6, leading=9.4, textColor=DARK,
        ),
        "meta_label": ParagraphStyle(
            "meta_label", fontName=f"{base_font}-Bold", fontSize=7.6, leading=9.4,
            textColor=MUTED,
        ),
        "cell": ParagraphStyle(
            "cell", fontName=base_font, fontSize=7.4, leading=9.0, textColor=DARK,
        ),
        "table_title": ParagraphStyle(
            "table_title", fontName=f"{base_font}-Bold", fontSize=9.2, leading=12,
            textColor=TEAL, spaceBefore=8, spaceAfter=3,
        ),
        "note": ParagraphStyle(
            "note", fontName=base_font, fontSize=7.4, leading=10, textColor=MUTED,
            leftIndent=8, bulletIndent=0, spaceAfter=2,
        ),
        "section": ParagraphStyle(
            "section", fontName=f"{base_font}-Bold", fontSize=9, leading=12,
            textColor=DARK, spaceBefore=8, spaceAfter=3,
        ),
        "signature": ParagraphStyle(
            "signature", fontName=base_font, fontSize=8, leading=11, textColor=MUTED,
        ),
    }


def _footer(canvas_obj: pdfcanvas.Canvas, doc: SimpleDocTemplate, school: str, generated: str) -> None:
    canvas_obj.saveState()
    width, _ = doc.pagesize
    canvas_obj.setFont("Helvetica", 6.8)
    canvas_obj.setFillColor(MUTED)
    canvas_obj.drawString(doc.leftMargin, 10 * mm, school[:80])
    canvas_obj.drawCentredString(width / 2, 10 * mm, f"Generated {generated}")
    canvas_obj.setStrokeColor(BORDER)
    canvas_obj.setLineWidth(0.4)
    canvas_obj.line(doc.leftMargin, 12.5 * mm, width - doc.rightMargin, 12.5 * mm)
    canvas_obj.restoreState()


def _header(canvas_obj: pdfcanvas.Canvas, doc: SimpleDocTemplate) -> None:
    canvas_obj.saveState()
    width, height = doc.pagesize
    canvas_obj.setFillColor(TEAL)
    canvas_obj.rect(0, height - 5 * mm, width, 5 * mm, fill=1, stroke=0)
    canvas_obj.restoreState()


class _NumberedCanvas(pdfcanvas.Canvas):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.setFont("Helvetica", 6.8)
            self.setFillColor(MUTED)
            self.drawRightString(
                self._pagesize[0] - 16 * mm,
                10 * mm,
                f"Page {self._pageNumber} of {total}",
            )
            super().showPage()
        super().save()


def _meta_table(doc: ReportDocument, width: float, base_font: str) -> Table:
    styles = _styles(base_font)
    pairs = doc.meta
    rows = []
    for index in range(0, len(pairs), 2):
        row: list[Any] = []
        for label, value in pairs[index:index + 2]:
            row.append(Paragraph(label.upper(), styles["meta_label"]))
            row.append(Paragraph(str(value), styles["meta"]))
        while len(row) < 4:
            row.extend(["", ""])
        rows.append(row)
    table = Table(rows, colWidths=[width * 0.16, width * 0.34, width * 0.16, width * 0.34])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _summary_table(doc: ReportDocument, width: float, base_font: str) -> Table | None:
    if not doc.summary:
        return None
    styles = _styles(base_font)
    cells: list[Any] = []
    for label, value in doc.summary:
        cells.append(
            Paragraph(
                f'<font size="6.8" color="#5B6B7F">{label}</font><br/>'
                f'<font size="11" color="#122033"><b>{value}</b></font>',
                styles["cell"],
            )
        )
    per_row = 4 if len(cells) > 4 else max(1, len(cells))
    rows = []
    for index in range(0, len(cells), per_row):
        row = cells[index:index + per_row]
        while len(row) < per_row:
            row.append("")
        rows.append(row)
    table = Table(rows, colWidths=[width / per_row] * per_row)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _cell(value: Any, styles: dict[str, ParagraphStyle], font_size: float) -> Any:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if len(text) > 22:
        style = ParagraphStyle(
            "cellwrap", parent=styles["cell"], fontSize=font_size, leading=font_size + 1.6
        )
        return Paragraph(text.replace("&", "&amp;").replace("<", "&lt;"), style)
    return text


def _data_table(
    spec: ReportTable, width: float, base_font: str
) -> Table:
    headers = [str(h) for h in spec.headers]
    column_count = max(1, len(headers))
    if spec.widths and len(spec.widths) == column_count:
        total = sum(spec.widths)
        widths = [width * w / total for w in spec.widths]
    else:
        widths = [width / column_count] * column_count
    font_size = 7.2
    if column_count > 16:
        font_size = 4.9
    elif column_count > 12:
        font_size = 5.5
    elif column_count > 9:
        font_size = 6.2
    elif column_count > 7:
        font_size = 6.8
    styles = _styles(base_font)
    header_style = ParagraphStyle(
        "hdr", parent=styles["cell"], fontName=f"{base_font}-Bold",
        fontSize=font_size, leading=font_size + 1.4, textColor=colors.white,
    )
    data = [[Paragraph(str(h), header_style) for h in headers]]
    if spec.rows:
        for row in spec.rows:
            padded = list(row[:column_count]) + [""] * max(0, column_count - len(row))
            data.append([_cell(value, styles, font_size) for value in padded])
    else:
        data.append(
            [
                Paragraph(
                    f'<i>{spec.empty_message}</i>',
                    ParagraphStyle("empty", parent=styles["cell"], fontSize=font_size + 0.3),
                )
            ]
            + [""] * (column_count - 1)
        )
    table = Table(data, colWidths=widths, repeatRows=1 if spec.rows else 0)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), f"{base_font}-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, TEAL),
        ("GRID", (0, 1), (-1, -1), 0.35, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for row_index in range(1, len(data)):
        if row_index % 2 == 0:
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), ZEBRA))
    if spec.align:
        for index, alignment in enumerate(spec.align[:column_count]):
            mapped = {"left": "LEFT", "center": "CENTER", "right": "RIGHT"}.get(alignment, "LEFT")
            commands.append(("ALIGN", (index, 0), (index, -1), mapped))
    table.setStyle(TableStyle(commands))
    return table


def render_pdf(document: ReportDocument, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    base_font = "Helvetica"
    page_size = landscape_size(A4) if document.landscape else A4
    margins = 16 * mm
    doc = SimpleDocTemplate(
        str(path),
        pagesize=page_size,
        leftMargin=margins,
        rightMargin=margins,
        topMargin=20 * mm,
        bottomMargin=17 * mm,
        title=document.title,
        author="School Attendance & Marks Manager",
        subject=document.subtitle,
        creator=document.school,
    )
    width = page_size[0] - 2 * margins
    styles = _styles(base_font)
    story: list[Any] = []
    story.append(Paragraph(document.school, styles["school"]))
    story.append(
        Paragraph(
            escape(document.letterhead_line),
            styles["board"],
        )
    )
    story.append(Spacer(1, 2))
    rule = Table([[""]], colWidths=[width], rowHeights=[1.6])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL)]))
    story.append(rule)
    story.append(Paragraph(document.title, styles["title"]))
    story.append(Paragraph(document.subtitle, styles["subtitle"]))
    story.append(_meta_table(document, width, base_font))
    summary = _summary_table(document, width, base_font)
    if summary is not None:
        story.append(Spacer(1, 7))
        story.append(summary)
    for spec in document.tables:
        if spec.title:
            story.append(Paragraph(spec.title, styles["table_title"]))
        else:
            story.append(Spacer(1, 9))
        story.append(_data_table(spec, width, base_font))
    if document.notes:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Notes and rules", styles["section"]))
        for note in document.notes:
            story.append(Paragraph(note, styles["note"], bulletText="•"))
    story.append(Spacer(1, 14))
    teacher = next((value for label, value in document.meta if label == "Teacher"), "")
    signature_data = [
        [
            Paragraph("Prepared by", styles["signature"]),
            Paragraph("Checked by", styles["signature"]),
        ],
        [
            Paragraph(
                f"<b>{teacher}</b><br/>"
                f"Computer Science Teacher<br/>{document.school}",
                styles["signature"],
            ),
            Paragraph("<br/>Signature / date", styles["signature"]),
        ],
    ]
    signature = Table(signature_data, colWidths=[width * 0.5, width * 0.5])
    signature.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(signature)

    def on_page(canvas_obj: pdfcanvas.Canvas, template_doc: SimpleDocTemplate) -> None:
        _header(canvas_obj, template_doc)
        _footer(canvas_obj, template_doc, document.school, document.generated_at)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page, canvasmaker=_NumberedCanvas)
    return path
