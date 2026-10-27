"""Reusable UI widgets: stat cards, tables, pagination, toasts, dialogs."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Sequence

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.ui.icons import make_icon, school_logo

_current_palette: dict = config.THEME_LIGHT


def set_palette(palette: dict) -> None:
    global _current_palette
    _current_palette = palette


def polish_inputs(root: QWidget) -> None:
    """Hide native spin-box steppers.

    The Qt stylesheet engine cannot draw the up/down arrows inside a rounded field
    without leaving artefacts, so the steppers are removed. Values remain editable
    by typing, arrow keys, the mouse wheel and by clicking the field's text.
    """
    for spin in root.findChildren(QAbstractSpinBox):
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)


def palette() -> dict:
    return _current_palette


def format_pct(value: Any, digits: int = 1) -> str:
    if value is None or value == "":
        return "—"
    return f"{float(value):.{digits}f}%"


def set_variant(button: QPushButton, variant: str) -> None:
    button.setProperty("variant", variant)
    button.style().unpolish(button)
    button.style().polish(button)


def icon_button(name: str, tooltip: str, variant: str = "icon", size: int = 30) -> QPushButton:
    button = QPushButton()
    button.setIcon(make_icon(name, _current_palette["text"], 18))
    button.setIconSize(QSize(17, 17))
    button.setToolTip(tooltip)
    button.setFixedSize(size, size)
    set_variant(button, variant)
    return button


class StatCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str = "—",
        hint: str = "",
        icon: str = "analytics",
        accent: str = "primary",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(112)
        self._accent = accent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 13)
        layout.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("statLabel")
        top.addWidget(self.title_label)
        top.addStretch(1)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(28, 28)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet(
            f"background: {_current_palette[accent + '_soft']}; border-radius: 8px;"
        )
        self.icon_label.setPixmap(
            make_icon(icon, _current_palette[accent], 16).pixmap(16, 16)
        )
        top.addWidget(self.icon_label)
        layout.addLayout(top)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")
        layout.addWidget(self.value_label)
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("statHint")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def set_value(self, value: Any, hint: str | None = None) -> None:
        self.value_label.setText("—" if value is None else str(value))
        if hint is not None:
            self.hint_label.setText(hint)

    def set_tone(self, tone: str) -> None:
        self.value_label.setStyleSheet(f"color: {_current_palette[tone]};")


class InfoCard(QFrame):
    """Rounded surface panel with a title row and a content layout."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(16, 14, 16, 14)
        self.outer.setSpacing(10)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.title_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.header.addWidget(self.title_label)
        self.header.addStretch(1)
        if title:
            self.outer.addLayout(self.header)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        self.outer.addLayout(self.body)

    def add_header_widget(self, widget: QWidget) -> None:
        self.header.addWidget(widget)

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)


class EmptyState(QWidget):
    def __init__(
        self,
        title: str,
        message: str,
        icon: str = "students",
        action_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        layout.setContentsMargins(24, 32, 24, 32)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setPixmap(make_icon(icon, _current_palette["border_strong"], 46).pixmap(46, 46))
        layout.addWidget(icon_label)
        title_label = QLabel(title)
        title_label.setObjectName("emptyTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        text = QLabel(message)
        text.setObjectName("emptyText")
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setFixedWidth(460)
        text.setMinimumHeight(text.heightForWidth(460))
        layout.addWidget(text, alignment=Qt.AlignmentFlag.AlignCenter)
        self.title_label = title_label
        self.text_label = text
        self.icon_label = icon_label
        self.button: QPushButton | None = None
        if action_text:
            self.button = QPushButton(action_text)
            set_variant(self.button, "primary")
            self.button.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignCenter)


class NumericItem(QTableWidgetItem):
    def __init__(self, text: str, value: float | None = None) -> None:
        super().__init__(text)
        self._value = value
        self.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        if isinstance(other, NumericItem):
            if self._value is None:
                return False
            if other._value is None:
                return True
            return self._value < other._value
        return str(self.text()) < str(other.text())


class DataTable(QTableWidget):
    def __init__(self, headers: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(list(headers))
        self.setAlternatingRowColors(True)
        self.setShowGrid(True)
        self.setWordWrap(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setSortingEnabled(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._row_ids: list[Any] = []
        self.setMinimumHeight(180)

    def set_data(
        self,
        rows: Iterable[Sequence[Any]],
        row_ids: Sequence[Any] | None = None,
        numeric_columns: Sequence[int] = (),
    ) -> None:
        rows = list(rows)
        self.setSortingEnabled(False)
        self.clearContents()
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                if c in numeric_columns and isinstance(value, (int, float)):
                    item = NumericItem(
                        f"{value:g}" if isinstance(value, float) else str(value), float(value)
                    )
                else:
                    text = "—" if value is None else str(value)
                    item = QTableWidgetItem(text)
                    if c in numeric_columns:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(r, c, item)
        self._row_ids = list(row_ids or [])
        self.setSortingEnabled(True)

    def selected_row_id(self) -> Any:
        row = self.currentRow()
        if 0 <= row < len(self._row_ids):
            return self._row_ids[row]
        return None

    def selected_row_ids(self) -> list[Any]:
        rows = sorted({index.row() for index in self.selectedIndexes()})
        return [self._row_ids[r] for r in rows if 0 <= r < len(self._row_ids)]

    def apply_widths(self, widths: Sequence[int]) -> None:
        for index, width in enumerate(widths):
            if index < self.columnCount():
                self.setColumnWidth(index, width)

    def fit_columns(self) -> None:
        self.resizeColumnsToContents()
        for index in range(self.columnCount()):
            self.setColumnWidth(index, min(320, max(70, self.columnWidth(index) + 16)))


class Pager(QWidget):
    changed = Signal()

    def __init__(self, page_size: int = 25, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page = 1
        self._page_size = page_size
        self._total = 0
        self._pages = 1
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)
        self.info = QLabel("No records")
        self.info.setObjectName("small")
        layout.addWidget(self.info)
        layout.addStretch(1)
        size_label = QLabel("Rows")
        size_label.setObjectName("small")
        layout.addWidget(size_label)
        self.size_combo = QComboBox()
        self.size_combo.addItems(["10", "25", "50", "100"])
        self.size_combo.setCurrentText(str(page_size))
        self.size_combo.setFixedWidth(72)
        self.size_combo.currentTextChanged.connect(self._size_changed)
        layout.addWidget(self.size_combo)
        self.prev_button = icon_button("chevron-left", "Previous page")
        self.prev_button.clicked.connect(lambda: self.go(self._page - 1))
        layout.addWidget(self.prev_button)
        self.page_label = QLabel("Page 1 of 1")
        self.page_label.setObjectName("small")
        self.page_label.setMinimumWidth(88)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.page_label)
        self.next_button = icon_button("chevron-right", "Next page")
        self.next_button.clicked.connect(lambda: self.go(self._page + 1))
        layout.addWidget(self.next_button)

    @property
    def page(self) -> int:
        return self._page

    @property
    def page_size(self) -> int:
        return self._page_size

    def set_total(self, total: int) -> None:
        self._total = max(0, int(total))
        self._pages = max(1, (self._total + self._page_size - 1) // self._page_size)
        if self._page > self._pages:
            self._page = self._pages
        self._update_labels()

    def _update_labels(self) -> None:
        if self._total == 0:
            self.info.setText("No records")
            self.page_label.setText("Page 1 of 1")
        else:
            first = (self._page - 1) * self._page_size + 1
            last = min(self._total, self._page * self._page_size)
            self.info.setText(f"Showing {first}–{last} of {self._total}")
            self.page_label.setText(f"Page {self._page} of {self._pages}")
        self.prev_button.setEnabled(self._page > 1)
        self.next_button.setEnabled(self._page < self._pages)

    def reset(self) -> None:
        self._page = 1
        self._update_labels()

    def go(self, page: int) -> None:
        page = max(1, min(self._pages, int(page)))
        if page != self._page:
            self._page = page
            self._update_labels()
            self.changed.emit()

    def _size_changed(self, text: str) -> None:
        try:
            self._page_size = int(text)
        except ValueError:
            self._page_size = 25
        self._page = 1
        self.set_total(self._total)
        self.changed.emit()


class Toast(QFrame):
    def __init__(self, parent: QWidget, message: str, tone: str = "success", ms: int = 3400) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(
            f"QFrame#toast {{ background: {_current_palette['text']}; border-radius: 10px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(13, 9, 15, 9)
        layout.setSpacing(9)
        icon = QLabel()
        icon.setPixmap(make_icon("check", _current_palette["success"], 16).pixmap(16, 16))
        if tone == "error":
            icon.setPixmap(make_icon("warning", _current_palette["danger"], 16).pixmap(16, 16))
        elif tone == "warning":
            icon.setPixmap(make_icon("warning", _current_palette["warning"], 16).pixmap(16, 16))
        elif tone == "info":
            icon.setPixmap(make_icon("info", _current_palette["info"], 16).pixmap(16, 16))
        layout.addWidget(icon)
        label = QLabel(message)
        label.setStyleSheet(f"color: {_current_palette['surface']}; font-weight: 500;")
        label.setWordWrap(True)
        label.setMaximumWidth(420)
        layout.addWidget(label)
        self.adjustSize()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.close)
        self._timer.start(ms)

    def show_at(self, x: int, y: int) -> None:
        self.move(x, y)
        self.show()
        self.raise_()
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(180)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start()
        self._animation = animation


def notify(widget: QWidget, message: str, tone: str = "success", ms: int = 3400) -> None:
    window = widget.window() if widget else None
    if window is None:
        return
    toast = Toast(window, message, tone, ms)
    margin = 26
    x = window.width() - toast.width() - margin
    y = window.height() - toast.height() - 42
    toast.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    toast.show_at(x, y)


def confirm_action(
    parent: QWidget | None,
    title: str,
    text: str,
    confirm_text: str = "Confirm",
    danger: bool = False,
    cancel_text: str = "Cancel",
) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    box.setText(text)
    confirm = box.addButton(confirm_text, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(cancel_text, QMessageBox.ButtonRole.RejectRole)
    if danger:
        confirm.setProperty("variant", "danger")
    box.exec()
    return box.clickedButton() is confirm


def info_dialog(parent: QWidget | None, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Information)
    box.setText(text)
    box.exec()


def error_dialog(parent: QWidget | None, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setText(text)
    box.exec()


def warn_dialog(parent: QWidget | None, title: str, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(text)
    box.exec()


@contextmanager
def busy(widget: QWidget | None = None):
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        if widget is not None:
            widget.setEnabled(False)
        yield
    finally:
        if widget is not None:
            widget.setEnabled(True)
        QApplication.restoreOverrideCursor()


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFrameShape(QFrame.Shape.HLine)
    return line


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            # Detach first so the old widget stops painting while deleteLater waits
            # for the event loop; otherwise stale text overlaps the new content.
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class ScrollPage(QWidget):
    """Page with a transparent, vertically scrolling content column."""

    def __init__(self, parent: QWidget | None = None) -> None:
        from PySide6.QtWidgets import QScrollArea

        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content = QWidget()
        self.content.setObjectName("pageContent")
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(24, 18, 24, 24)
        self.layout.setSpacing(14)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.layout.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self.layout.addLayout(layout)



def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("small")
    label.setStyleSheet("font-weight: 600;")
    return label


def labelled(label_text: str, widget: QWidget) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    layout.addWidget(field_label(label_text))
    layout.addWidget(widget)
    return container


class DirtyBanner(QFrame):
    save_requested = Signal()
    discard_requested = Signal()

    def __init__(self, text: str = "You have unsaved changes.", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(
            f"QFrame#card {{ background: {_current_palette['warning_soft']};"
            f" border: 1px solid {_current_palette['warning']}; border-radius: 9px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(9)
        icon = QLabel()
        icon.setPixmap(make_icon("warning", _current_palette["warning"], 16).pixmap(16, 16))
        layout.addWidget(icon)
        label = QLabel(text)
        label.setStyleSheet(f"color: {_current_palette['warning']}; font-weight: 600;")
        layout.addWidget(label)
        layout.addStretch(1)
        self.save_button = QPushButton("Save now")
        set_variant(self.save_button, "primary")
        self.save_button.clicked.connect(self.save_requested.emit)
        layout.addWidget(self.save_button)
        self.discard_button = QPushButton("Discard changes")
        set_variant(self.discard_button, "ghost")
        self.discard_button.clicked.connect(self.discard_requested.emit)
        layout.addWidget(self.discard_button)
        self.hide()


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("pageSubtitle")
            # Wrap so a long one-line description never forces the whole page
            # wider than the window on smaller school laptops.
            sub.setWordWrap(True)
            layout.addWidget(sub)


class ProgressPill(QWidget):
    """Compact percentage bar used in lists."""

    def __init__(self, value: float | None, width: int = 110, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QProgressBar

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(value or 0))
        bar.setTextVisible(False)
        bar.setFixedWidth(width)
        layout.addWidget(bar)
        label = QLabel(format_pct(value))
        label.setObjectName("small")
        layout.addWidget(label)
