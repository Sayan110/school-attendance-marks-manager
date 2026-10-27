"""Deterministic Qt teardown.

Qt objects must be destroyed while the ``QApplication`` still exists. If they are
left to CPython's interpreter finalisation, PySide6 can abort the process on
Windows (observed as ``0xC0000409`` / ``0xC0000005`` on exit even though every
test passed). Calling :func:`shutdown_qt` before returning from ``main`` and at
the end of the test session keeps exits clean.
"""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


def shutdown_qt(app: QApplication | None = None, rounds: int = 3) -> None:
    """Delete every top-level widget, then flush deferred deletes."""
    instance = app if app is not None else QApplication.instance()
    if instance is None:
        return
    for _ in range(max(1, rounds)):
        instance.processEvents()
        instance.closeAllWindows()
        for widget in QApplication.topLevelWidgets():
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        instance.processEvents()
