"""Offscreen tests for the Marks page: exam setup, entry, import and export."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog, QFileDialog

from app.ui import marks as marks_module
from app.ui.marks import ExaminationDialog, MarksPage


@pytest.fixture()
def page(qapp, ctx, dataset):
    widget = MarksPage(ctx)
    widget.refresh()
    yield widget
    widget.deleteLater()
    qapp.processEvents()


@pytest.fixture()
def quiet(monkeypatch):
    messages = []
    monkeypatch.setattr(marks_module, "notify", lambda *a, **k: messages.append(("notify", a)))
    monkeypatch.setattr(
        marks_module, "error_dialog", lambda *a, **k: messages.append(("error", a))
    )
    monkeypatch.setattr(marks_module, "confirm_action", lambda *a, **k: True)
    monkeypatch.setattr(
        marks_module.QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: messages.append(("warning", a))),
    )
    return messages


# ------------------------------------------------------------ ExaminationDialog


def test_exam_dialog_creates_examination(qapp, ctx, quiet):
    dialog = ExaminationDialog(ctx)
    dialog.name_edit.setText("Half-Yearly 2026")
    dialog.type_combo.setCurrentText("Half-Yearly Examination")
    dialog.max_edit.setText("100")
    dialog.pass_percent_edit.setText("40")
    dialog.theory_edit.setText("70")
    dialog.practical_edit.setText("30")
    dialog._save()
    qapp.processEvents()
    assert dialog.result() == QDialog.DialogCode.Accepted
    exams = ctx.marks.list_examinations(ctx.session_id, "9")
    assert any(exam["name"] == "Half-Yearly 2026" for exam in exams)
    dialog.close()


def test_exam_dialog_rejects_components_that_do_not_add_up(qapp, ctx, quiet):
    dialog = ExaminationDialog(ctx)
    dialog.name_edit.setText("Broken Components")
    dialog.max_edit.setText("100")
    dialog.theory_edit.setText("70")
    dialog.practical_edit.setText("20")
    dialog._save()
    qapp.processEvents()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert any(kind == "error" for kind, _ in quiet)
    assert not any(
        exam["name"] == "Broken Components" for exam in ctx.marks.list_examinations(ctx.session_id, "9")
    )
    dialog.close()


def test_exam_dialog_populates_and_updates(qapp, ctx, dataset, quiet):
    exam = ctx.marks.get_examination(dataset["exam_id"])
    dialog = ExaminationDialog(ctx, exam)
    assert dialog.name_edit.text() == "Unit Test 1"
    assert dialog.max_edit.text() == "100"
    assert dialog.theory_edit.text() == "70"
    dialog.name_edit.setText("Unit Test 1 (revised)")
    dialog._save()
    qapp.processEvents()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert ctx.marks.get_examination(dataset["exam_id"])["name"] == "Unit Test 1 (revised)"
    dialog.close()


# --------------------------------------------------------------- exam actions


def test_page_exam_actions_new_edit_delete(page, ctx, dataset, monkeypatch, quiet):
    monkeypatch.setattr(
        marks_module.ExaminationDialog, "exec", lambda self: QDialog.DialogCode.Accepted
    )
    page._new_exam()
    assert any(kind == "notify" for kind, _ in quiet)
    page._edit_exam()
    assert any(kind == "notify" for kind, _ in quiet)

    page._reload_exams()
    exam_id = dataset["exam_id"]
    assert page._exam is not None and int(page._exam["id"]) == exam_id
    page._delete_exam()
    assert ctx.marks.get_examination(exam_id) is None
    assert page._exam is None
    assert page.empty.isHidden() is False


def test_page_delete_exam_can_be_cancelled(page, ctx, dataset, monkeypatch, quiet):
    monkeypatch.setattr(marks_module, "confirm_action", lambda *a, **k: False)
    page._reload_exams()
    page._delete_exam()
    assert ctx.marks.get_examination(dataset["exam_id"]) is not None


# ------------------------------------------------------------------ entry flow


def test_page_status_change_and_remarks_mark_dirty(page, dataset):
    page._reload_exams()
    beta = dataset["students"]["beta"]
    assert beta in page._widgets
    page._widgets[beta]["status"].setCurrentIndex(
        page._widgets[beta]["status"].findData("exempted")
    )
    assert page.has_unsaved_changes() is True
    page._remarks_changed("medical exemption")
    assert page.has_unsaved_changes() is True
    page._set_dirty(False)
    assert page.has_unsaved_changes() is False


def test_page_save_without_changes_is_safe(page, dataset, quiet):
    page._reload_exams()
    page.save()
    assert page.has_unsaved_changes() is False


def test_page_results_tab_uses_real_saved_data(page, dataset):
    page._reload_exams()
    page.refresh_results()
    assert page.result_table.rowCount() == 2
    names = {
        page.result_table.item(row, 2).text() for row in range(page.result_table.rowCount())
    }
    assert names == {"Alpha Sharma", "Beta Das"}
    assert page.cards["students"].value_label.text() == "2"
    assert "%" in page.cards["pass"].value_label.text()


# ------------------------------------------------------------------- importing


def test_import_marks_updates_rows_and_warns_about_bad_ones(
    page, ctx, dataset, tmp_path, monkeypatch, quiet
):
    source = tmp_path / "marks.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["roll_no", "status", "theory", "practical"])
        writer.writerow(["01", "entered", "65", "30"])
        writer.writerow(["99", "entered", "10", "10"])
    page._reload_exams()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(source), ""))
    )
    page._import_marks()
    rows = {row["student_id"]: row for row in ctx.marks.result_rows(dataset["exam_id"])}
    assert rows[dataset["students"]["alpha"]]["theory"] == 65
    assert rows[dataset["students"]["beta"]]["theory"] == 20  # untouched, not zeroed
    assert any(kind == "warning" for kind, _ in quiet)
    assert page.has_unsaved_changes() is False


def test_import_marks_happy_path_notifies(page, ctx, dataset, tmp_path, monkeypatch, quiet):
    source = tmp_path / "marks.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["roll_no", "status", "theory", "practical"])
        writer.writerow(["01", "entered", "68", "29"])
        writer.writerow(["02", "absent", "", ""])
    page._reload_exams()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(source), ""))
    )
    page._import_marks()
    assert any(kind == "notify" for kind, _ in quiet)
    rows = {row["student_id"]: row for row in ctx.marks.result_rows(dataset["exam_id"])}
    assert rows[dataset["students"]["alpha"]]["total"] == 97
    assert rows[dataset["students"]["beta"]]["status"] == "absent"


def test_import_marks_reports_unreadable_file(page, tmp_path, monkeypatch, quiet):
    bad = tmp_path / "bad.txt"
    bad.write_text("not a spreadsheet", encoding="utf-8")
    page._reload_exams()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(bad), ""))
    )
    page._import_marks()
    assert any(kind == "error" for kind, _ in quiet)


# ------------------------------------------------------------------- exporting


def test_download_marks_template(page, dataset, tmp_path, monkeypatch, quiet):
    target = tmp_path / "marks_template.xlsx"
    page._reload_exams()
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    page._download_template()
    assert target.exists() and target.stat().st_size > 0
    assert any(kind == "notify" for kind, _ in quiet)


def test_export_marks_excel_and_csv(page, tmp_path, monkeypatch, quiet):
    page._reload_exams()
    xlsx = tmp_path / "marks.xlsx"
    csv_path = tmp_path / "marks.csv"
    targets = iter([(str(xlsx), ""), (str(csv_path), "")])
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: next(targets))
    )
    page._export_excel()
    assert xlsx.exists() and xlsx.stat().st_size > 0
    page._export_csv()
    assert csv_path.exists()
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "Alpha Sharma" in text and "Grade" in text
