"""HTML preview / print rendering for report documents."""
from __future__ import annotations

import html
from typing import Any

from app.services.report_service import ReportDocument

BASE_CSS = """
body { font-family: 'Segoe UI', Arial, sans-serif; color: #122033; font-size: 10pt; }
h1.school { color: #0f766e; text-align: center; font-size: 17pt; margin: 0 0 2px 0; }
p.board { text-align: center; color: #5b6b7f; font-size: 8pt; margin: 0 0 8px 0; }
hr.rule { border: none; border-top: 2px solid #0f766e; margin: 4px 0 10px 0; }
h2.title { font-size: 14pt; margin: 10px 0 2px 0; }
p.subtitle { color: #5b6b7f; font-size: 9pt; margin: 0 0 10px 0; }
table.meta { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
table.meta td { padding: 2px 6px 2px 0; font-size: 8pt; vertical-align: top; }
table.meta td.label { color: #5b6b7f; font-weight: 600; width: 14%; }
table.meta td.value { width: 36%; }
table.summary { width: 100%; border-collapse: collapse; margin: 8px 0 12px 0; }
table.summary td { background: #eef4f7; border: 1px solid #ffffff; padding: 6px 8px; width: 25%; }
table.summary .s-label { display: block; color: #5b6b7f; font-size: 7.5pt; }
table.summary .s-value { display: block; font-size: 12pt; font-weight: 700; }
h3.tbl { color: #0f766e; font-size: 10pt; margin: 14px 0 4px 0; }
table.data { width: 100%; border-collapse: collapse; margin-bottom: 6px; }
table.data th { background: #0f766e; color: #ffffff; font-size: 8pt; padding: 4px; border: 1px solid #d8e0ea; text-align: left; }
table.data td { font-size: 8pt; padding: 4px; border: 1px solid #d8e0ea; }
table.data tr:nth-child(even) td { background: #f7f9fc; }
table.data td.empty { color: #5b6b7f; font-style: italic; }
h3.notes { font-size: 10pt; margin: 14px 0 4px 0; }
ul.notes { color: #5b6b7f; font-size: 8pt; margin: 4px 0 0 16px; padding: 0; }
ul.notes li { margin-bottom: 3px; }
p.generated { color: #5b6b7f; font-size: 7.5pt; margin-top: 12px; }
"""


def escape(value: Any) -> str:
    if value is None:
        return "—"
    return html.escape(str(value))


def render_html(document: ReportDocument) -> str:
    parts: list[str] = [
        f"<html><head><meta charset='utf-8'><style>{BASE_CSS}</style></head><body>",
        f"<h1 class='school'>{escape(document.school)}</h1>",
        f"<p class='board'>{escape(document.letterhead_line)}</p>",
        "<hr class='rule'/>",
        f"<h2 class='title'>{escape(document.title)}</h2>",
        f"<p class='subtitle'>{escape(document.subtitle)}</p>",
    ]
    if document.meta:
        parts.append("<table class='meta'>")
        pairs = document.meta
        for index in range(0, len(pairs), 2):
            row = pairs[index:index + 2]
            cells = []
            for label, value in row:
                cells.append(f"<td class='label'>{escape(label)}</td><td class='value'>{escape(value)}</td>")
            if len(cells) == 2:
                cells.extend(["<td class='label'></td>", "<td class='value'></td>"])
            parts.append("<tr>" + "".join(cells) + "</tr>")
        parts.append("</table>")
    if document.summary:
        parts.append("<table class='summary'>")
        cells = [
            f"<td><span class='s-label'>{escape(label)}</span>"
            f"<br/><span class='s-value'>{escape(value)}</span></td>"
            for label, value in document.summary
        ]
        for index in range(0, len(cells), 4):
            chunk = cells[index:index + 4]
            while len(chunk) < 4:
                chunk.append("<td></td>")
            parts.append("<tr>" + "".join(chunk) + "</tr>")
        parts.append("</table>")
    for table in document.tables:
        if table.title:
            parts.append(f"<h3 class='tbl'>{escape(table.title)}</h3>")
        parts.append("<table class='data'><thead><tr>")
        for header in table.headers:
            parts.append(f"<th>{escape(header)}</th>")
        parts.append("</tr></thead><tbody>")
        if table.rows:
            for row in table.rows:
                parts.append("<tr>")
                for value in row:
                    parts.append(f"<td>{escape(value)}</td>")
                parts.append("</tr>")
        else:
            parts.append(
                f"<tr><td class='empty' colspan='{max(1, len(table.headers))}'>"
                f"{escape(table.empty_message)}</td></tr>"
            )
        parts.append("</tbody></table>")
    if document.notes:
        parts.append("<h3 class='notes'>Notes and rules</h3><ul class='notes'>")
        for note in document.notes:
            parts.append(f"<li>{escape(note)}</li>")
        parts.append("</ul>")
    parts.append(
        f"<p class='generated'>Generated on {escape(document.generated_at)} • "
        "School Attendance &amp; Marks Manager</p>"
    )
    parts.append("</body></html>")
    return "".join(parts)
