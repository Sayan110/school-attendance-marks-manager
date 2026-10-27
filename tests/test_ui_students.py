"""Offscreen tests for the Students page, its dialogs, import and export."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog, QFileDialog

from app.ui import students as students_module
from app.ui.students import ImportStudentsDialog, StudentDialog, StudentsPage


@pytest.fixture()
def page(qapp, ctx):
    widget = StudentsPage(ctx)
    widget.refresh()
    yield widget
    widget.deleteLater()
    qapp.processEvents()


@pytest.fixture()
def quiet(monkeypatch):
    """Silence message boxes/popups and auto-accept confirmations."""
    messages = []
    monkeypatch.setattr(students_module, "notify", lambda *a, **k: messages.append(("notify", a)))
    monkeypatch.setattr(
        students_module, "error_dialog", lambda *a, **k: messages.append(("error", a))
    )
    monkeypatch.setattr(
        students_module, "info_dialog", lambda *a, **k: messages.append(("info", a))
    )
    monkeypatch.setattr(students_module, "confirm_action", lambda *a, **k: True)
    return messages


def select_student(page, student_id):
    for row in range(page.table.rowCount()):
        page.table.selectRow(row)
        if page.table.selected_row_id() == student_id:
            return row
    raise AssertionError(f"student {student_id} is not on the current page")


# --------------------------------------------------------------- StudentDialog


def test_student_dialog_rejects_empty_form_and_keeps_dialog_open(qapp, ctx):
    dialog = StudentDialog(ctx)
    dialog.show()
    dialog._save()
    qapp.processEvents()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.isHidden() is False
    assert "required" in dialog.error_label.text().lower()
    assert ctx.students.list_students(ctx.session_id)[1] == 0
    dialog.close()


def test_student_dialog_creates_and_updates_a_student(qapp, ctx):
    dialog = StudentDialog(ctx)
    dialog.roll_edit.setText("21")
    dialog.name_edit.setText("Nayan Deka")
    dialog.section_edit.setText("A")
    dialog.guardian_edit.setText("Guardian")
    dialog.contact_edit.setText("9812345678")
    dialog._save()
    qapp.processEvents()
    assert dialog.result() == QDialog.DialogCode.Accepted
    rows, total = ctx.students.list_students(ctx.session_id, search="Nayan")
    assert total == 1
    student = rows[0]
    assert student["roll_no"] == "21"
    assert student["admission_date"]  # admission date was recorded by default
    dialog.close()

    edit = StudentDialog(ctx, dict(student))
    assert edit.name_edit.text() == "Nayan Deka"
    edit.name_edit.setText("Nayan K. Deka")
    edit._save()
    qapp.processEvents()
    assert edit.result() == QDialog.DialogCode.Accepted
    assert ctx.students.get(student["id"])["full_name"] == "Nayan K. Deka"
    edit.close()


def test_student_dialog_duplicate_roll_shows_error(qapp, ctx, dataset):
    dialog = StudentDialog(ctx)
    dialog.roll_edit.setText("01")
    dialog.name_edit.setText("Another Student")
    dialog.class_combo.setCurrentIndex(dialog.class_combo.findData("9"))
    dialog._save()
    qapp.processEvents()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "already" in dialog.error_label.text().lower()
    dialog.close()


def test_student_dialog_shows_database_style_validation_for_contact(qapp, ctx):
    dialog = StudentDialog(ctx)
    dialog.roll_edit.setText("22")
    dialog.name_edit.setText("Contact Check")
    dialog.contact_edit.setText("not-a-number")
    dialog._save()
    qapp.processEvents()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.contact_edit.property("invalid") is True
    dialog.close()


# -------------------------------------------------------- ImportStudentsDialog


def _write_csv(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["roll_no", "full_name", "class_name", "section", "guardian_name", "contact_no", "admission_date"]
        )
        writer.writerows(rows)
    return path


def test_import_dialog_validates_and_imports_rows(qapp, ctx, tmp_path, monkeypatch, quiet):
    csv_path = _write_csv(
        tmp_path / "students.csv",
        [
            ["31", "Imported One", "9", "A", "Guardian One", "9800000001", "2026-04-05"],
            ["32", "Imported Two", "10", "B", "", "", "2026-04-06"],
            ["33", "", "9", "A", "", "", ""],
        ],
    )
    dialog = ImportStudentsDialog(ctx)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(csv_path), ""))
    )
    dialog._choose_file()
    qapp.processEvents()
    assert dialog.file_label.text() == "students.csv"
    assert len(dialog.valid_rows) == 2
    assert len(dialog.errors) == 1
    assert dialog.import_button.isEnabled() is True
    assert dialog.tabs.currentIndex() == 1  # errors tab wins when problems exist

    dialog._import()
    qapp.processEvents()
    assert dialog.result() == QDialog.DialogCode.Accepted
    rows, total = ctx.students.list_students(ctx.session_id, search="Imported")
    assert total == 2
    assert {row["full_name"] for row in rows} == {"Imported One", "Imported Two"}
    dialog.close()


def test_import_dialog_reports_unreadable_file(qapp, ctx, tmp_path, monkeypatch, quiet):
    bad = tmp_path / "wrong.txt"
    bad.write_text("roll_no,full_name\n1,X\n", encoding="utf-8")
    dialog = ImportStudentsDialog(ctx)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(bad), ""))
    )
    dialog._choose_file()
    qapp.processEvents()
    assert dialog.valid_rows == []
    assert any(kind == "error" for kind, _ in quiet)
    dialog.close()


def test_import_dialog_cancelled_confirmation_imports_nothing(qapp, ctx, tmp_path, monkeypatch, quiet):
    csv_path = _write_csv(
        tmp_path / "students.csv",
        [["41", "Cancelled Student", "9", "A", "", "", ""]],
    )
    dialog = ImportStudentsDialog(ctx)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(csv_path), ""))
    )
    dialog._choose_file()
    assert dialog.import_button.isEnabled() is True
    monkeypatch.setattr(students_module, "confirm_action", lambda *a, **k: False)
    dialog._import()
    qapp.processEvents()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert ctx.students.list_students(ctx.session_id, search="Cancelled")[1] == 0
    dialog.close()


def test_import_dialog_downloads_template(qapp, ctx, tmp_path, monkeypatch, quiet):
    target = tmp_path / "template.xlsx"
    dialog = ImportStudentsDialog(ctx)
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    dialog._download_template()
    qapp.processEvents()
    assert target.exists() and target.stat().st_size > 0
    assert any(kind == "info" for kind, _ in quiet)
    dialog.close()


# ------------------------------------------------------------------ page actions


def test_page_archive_and_restore_preserve_records(page, ctx, dataset, quiet):
    alpha = dataset["students"]["alpha"]
    page.refresh()
    select_student(page, alpha)
    page.archive_student()
    assert ctx.students.get(alpha)["status"] == "archived"
    assert ctx.students.record_counts(alpha)["attendance"] == 2

    page.status_filter.setCurrentIndex(page.status_filter.findData("archived"))
    page._filters_changed()
    select_student(page, alpha)
    page.restore_student()
    assert ctx.students.get(alpha)["status"] == "active"


def test_page_delete_blocked_when_records_exist(page, ctx, dataset, quiet):
    beta = dataset["students"]["beta"]
    page.refresh()
    select_student(page, beta)
    page.delete_student()
    assert any(kind == "error" for kind, _ in quiet)
    assert ctx.students.get(beta) is not None


def test_page_delete_allowed_for_student_without_records(page, ctx, session_id, quiet):
    plain = ctx.students.create(
        {
            "roll_no": "77",
            "full_name": "No Records",
            "class_name": "9",
            "section": "A",
            "session_id": session_id,
            "status": "active",
        }
    )
    page.refresh()
    select_student(page, plain)
    page.delete_student()
    assert ctx.students.get(plain) is None
    assert any(kind == "notify" for kind, _ in quiet)


def test_page_export_writes_csv_and_excel(page, dataset, tmp_path, monkeypatch, quiet):
    csv_target = tmp_path / "students.csv"
    xlsx_target = tmp_path / "students.xlsx"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(csv_target), ""))
    )
    page._export("csv")
    assert csv_target.exists()
    assert "Alpha Sharma" in csv_target.read_text(encoding="utf-8-sig")

    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(xlsx_target), ""))
    )
    page._export("xlsx")
    assert xlsx_target.exists() and xlsx_target.stat().st_size > 0


def test_page_export_without_matches_shows_info(page, monkeypatch, quiet):
    page.search_edit.setText("no such student")
    page._filters_changed()
    assert page.table.rowCount() == 0
    page._export("csv")
    assert any(kind == "info" for kind, _ in quiet)


def test_page_add_edit_and_import_actions_refresh(page, ctx, dataset, monkeypatch, quiet):
    accepted = {"value": QDialog.DialogCode.Accepted}
    monkeypatch.setattr(students_module.StudentDialog, "exec", lambda self: accepted["value"])
    before, _ = ctx.students.list_students(ctx.session_id)
    page.add_student()
    # The stubbed dialog saves nothing, but the page must not crash and must refresh.
    after, _ = ctx.students.list_students(ctx.session_id)
    assert len(after) == len(before)

    monkeypatch.setattr(students_module.ImportStudentsDialog, "exec", lambda self: accepted["value"])
    page.import_students()

    page.refresh()
    select_student(page, dataset["students"]["alpha"])
    page.edit_student()
    assert page.table.rowCount() >= 1


def test_page_sorting_and_pagination(page, ctx, session_id, qapp):
    for index in range(12):
        ctx.students.create(
            {
                "roll_no": f"5{index:02d}",
                "full_name": f"Paged Student {index:02d}",
                "class_name": "9",
                "section": "A",
                "session_id": session_id,
                "status": "active",
            }
        )
    page.refresh()
    assert page._sort_key == "roll_no"
    page._header_clicked(1)
    assert page._sort_key == "full_name" and page._sort_dir == "asc"
    page._header_clicked(1)
    assert page._sort_dir == "desc"
    page._header_clicked(4)  # unsupported column: unchanged
    assert page._sort_key == "full_name"

    page.pager.size_combo.setCurrentText("10")
    qapp.processEvents()
    assert page._page_size == 10
    assert page.table.rowCount() <= 10
    if page.pager.next_button.isEnabled():
        page.pager.next_button.click()
        qapp.processEvents()
        assert page._page == 2
        page.pager.prev_button.click()
        assert page._page == 1


def test_page_section_filter_follows_class(page, ctx, session_id, dataset):
    ctx.students.create(
        {
            "roll_no": "88",
            "full_name": "Section C Student",
            "class_name": "9",
            "section": "C",
            "session_id": session_id,
            "status": "active",
        }
    )
    page.refresh()
    page.class_filter.setCurrentIndex(page.class_filter.findData("9"))
    page._filters_changed()
    sections = {
        page.section_filter.itemData(i) for i in range(page.section_filter.count())
    }
    assert {"A", "B", "C"} <= sections
    page.section_filter.setCurrentIndex(page.section_filter.findData("C"))
    page._filters_changed()
    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "Section C Student"
