"""Vector line icons drawn with QPainter (no external icon assets required)."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QLinearGradient, QFont


def _pixmap(size: int, scale: int = 1) -> QPixmap:
    """A transparent canvas at `size * scale` pixels.

    Icons are handed to Qt at several pixel sizes with a device pixel ratio of 1.
    Attaching a ratio > 1 to the source pixmap makes Qt 6.12 clip the glyph inside
    icon-bearing buttons, so crispness is achieved by adding larger rasters instead.
    """
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


def make_icon(name: str, color: str = "#122033", size: int = 20, width: float = 1.8) -> QIcon:
    icon = QIcon()
    for scale in (1, 2, 3):
        pm = _pixmap(size, scale)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale((size * scale) / 24.0, (size * scale) / 24.0)
        pen = QPen(QColor(color), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        _draw(painter, name, QColor(color))
        painter.end()
        icon.addPixmap(pm)
    return icon


def _draw(p: QPainter, name: str, color: QColor) -> None:
    if name == "dashboard":
        for x, y, w, h in ((3, 3, 8, 8), (13, 3, 8, 5), (13, 10, 8, 11), (3, 13, 8, 8)):
            p.drawRoundedRect(QRectF(x, y, w, h), 1.6, 1.6)
    elif name == "students":
        p.drawEllipse(QPointF(9, 8.2), 3.1, 3.1)
        path = QPainterPath()
        path.moveTo(3.2, 20.5)
        path.cubicTo(3.2, 15.4, 6, 13.4, 9, 13.4)
        path.cubicTo(12, 13.4, 14.8, 15.4, 14.8, 20.5)
        p.drawPath(path)
        p.drawArc(QRectF(14.6, 6.0, 4.8, 4.8), -70 * 16, 220 * 16)
        path2 = QPainterPath()
        path2.moveTo(16.4, 13.8)
        path2.cubicTo(19.0, 13.9, 20.8, 15.8, 20.8, 20.5)
        p.drawPath(path2)
    elif name == "attendance":
        p.drawRoundedRect(QRectF(3, 5, 18, 16), 2, 2)
        p.drawLine(QPointF(3, 9.5), QPointF(21, 9.5))
        p.drawLine(QPointF(8, 2.6), QPointF(8, 6.4))
        p.drawLine(QPointF(16, 2.6), QPointF(16, 6.4))
        path = QPainterPath()
        path.moveTo(7.6, 14.6)
        path.lineTo(10.6, 17.6)
        path.lineTo(16.4, 11.8)
        p.drawPath(path)
    elif name == "marks":
        p.drawRoundedRect(QRectF(5, 5, 14, 16), 2, 2)
        p.drawRoundedRect(QRectF(9, 2.6, 6, 4), 1.2, 1.2)
        for y in (11, 14.5, 18):
            p.drawLine(QPointF(8.2, y), QPointF(15.8 if y != 18 else 13.2, y))
    elif name == "analytics":
        p.drawLine(QPointF(4.5, 3), QPointF(4.5, 21))
        p.drawLine(QPointF(4.5, 21), QPointF(21, 21))
        p.drawRoundedRect(QRectF(7.2, 13, 3.2, 6), 0.8, 0.8)
        p.drawRoundedRect(QRectF(12.2, 8.5, 3.2, 10.5), 0.8, 0.8)
        p.drawRoundedRect(QRectF(17.2, 5, 3.2, 14), 0.8, 0.8)
    elif name == "reports":
        p.drawRoundedRect(QRectF(5.5, 3, 13, 18), 1.6, 1.6)
        p.drawLine(QPointF(8.5, 8.5), QPointF(15.5, 8.5))
        p.drawLine(QPointF(8.5, 12), QPointF(15.5, 12))
        p.drawLine(QPointF(8.5, 15.5), QPointF(13, 15.5))
    elif name == "settings":
        p.drawEllipse(QPointF(12, 12), 3.1, 3.1)
        for index in range(8):
            angle = index * math.pi / 4
            x1 = 12 + 6.0 * math.cos(angle)
            y1 = 12 + 6.0 * math.sin(angle)
            x2 = 12 + 8.6 * math.cos(angle)
            y2 = 12 + 8.6 * math.sin(angle)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    elif name == "backup":
        p.drawEllipse(QRectF(4.5, 3.5, 15, 5))
        p.drawLine(QPointF(4.5, 6), QPointF(4.5, 18))
        p.drawLine(QPointF(19.5, 6), QPointF(19.5, 18))
        p.drawArc(QRectF(4.5, 15.5, 15, 5), 180 * 16, 180 * 16)
        p.drawArc(QRectF(4.5, 9.5, 15, 5), 180 * 16, 180 * 16)
    elif name == "plus":
        p.drawLine(QPointF(12, 5), QPointF(12, 19))
        p.drawLine(QPointF(5, 12), QPointF(19, 12))
    elif name == "edit":
        path = QPainterPath()
        path.moveTo(4.5, 19.5)
        path.lineTo(5.4, 15.2)
        path.lineTo(15.8, 4.8)
        path.lineTo(19.2, 8.2)
        path.lineTo(8.8, 18.6)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(13.8, 6.8), QPointF(17.2, 10.2))
    elif name == "trash":
        p.drawLine(QPointF(4, 6.5), QPointF(20, 6.5))
        p.drawLine(QPointF(9, 3.5), QPointF(15, 3.5))
        p.drawLine(QPointF(6, 6.5), QPointF(7, 20.5))
        p.drawLine(QPointF(18, 6.5), QPointF(17, 20.5))
        p.drawLine(QPointF(7, 20.5), QPointF(17, 20.5))
        p.drawLine(QPointF(10, 10), QPointF(10.4, 17))
        p.drawLine(QPointF(14, 10), QPointF(13.6, 17))
    elif name == "search":
        p.drawEllipse(QPointF(10.5, 10.5), 6.2, 6.2)
        p.drawLine(QPointF(15.2, 15.2), QPointF(20.5, 20.5))
    elif name == "import":
        p.drawLine(QPointF(12, 3.5), QPointF(12, 15))
        path = QPainterPath()
        path.moveTo(7.5, 10.5)
        path.lineTo(12, 15)
        path.lineTo(16.5, 10.5)
        p.drawPath(path)
        p.drawLine(QPointF(4, 17), QPointF(4, 20.5))
        p.drawLine(QPointF(4, 20.5), QPointF(20, 20.5))
        p.drawLine(QPointF(20, 20.5), QPointF(20, 17))
    elif name == "export":
        p.drawLine(QPointF(12, 15.5), QPointF(12, 3.5))
        path = QPainterPath()
        path.moveTo(7.5, 8)
        path.lineTo(12, 3.5)
        path.lineTo(16.5, 8)
        p.drawPath(path)
        p.drawLine(QPointF(4, 17), QPointF(4, 20.5))
        p.drawLine(QPointF(4, 20.5), QPointF(20, 20.5))
        p.drawLine(QPointF(20, 20.5), QPointF(20, 17))
    elif name == "print":
        p.drawRoundedRect(QRectF(6, 3, 12, 6), 1, 1)
        p.drawRoundedRect(QRectF(3, 9, 18, 8), 1.6, 1.6)
        p.drawRect(QRectF(6, 14, 12, 6.5))
        p.drawLine(QPointF(17.5, 11.5), QPointF(18.5, 11.5))
    elif name == "refresh":
        p.drawArc(QRectF(4.5, 4.5, 15, 15), 40 * 16, 290 * 16)
        path = QPainterPath()
        path.moveTo(17.5, 3)
        path.lineTo(20, 6.5)
        path.lineTo(16, 7.5)
        p.drawPath(path)
    elif name == "sun":
        p.drawEllipse(QPointF(12, 12), 4.2, 4.2)
        for index in range(8):
            angle = index * math.pi / 4
            p.drawLine(
                QPointF(12 + 7 * math.cos(angle), 12 + 7 * math.sin(angle)),
                QPointF(12 + 9.3 * math.cos(angle), 12 + 9.3 * math.sin(angle)),
            )
    elif name == "moon":
        outer = QPainterPath()
        outer.addEllipse(QPointF(12, 12), 8, 8)
        inner = QPainterPath()
        inner.addEllipse(QPointF(16.5, 8.5), 7, 7)
        p.drawPath(outer.subtracted(inner))
    elif name == "warning":
        path = QPainterPath()
        path.moveTo(12, 3.5)
        path.lineTo(21, 20)
        path.lineTo(3, 20)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(12, 9), QPointF(12, 13.6))
        p.drawPoint(QPointF(12, 16.8))
    elif name == "check":
        path = QPainterPath()
        path.moveTo(5, 12.5)
        path.lineTo(10, 17.5)
        path.lineTo(19.5, 6.5)
        p.drawPath(path)
    elif name == "close":
        p.drawLine(QPointF(6, 6), QPointF(18, 18))
        p.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name == "chevron-left":
        path = QPainterPath()
        path.moveTo(14.5, 5)
        path.lineTo(8, 12)
        path.lineTo(14.5, 19)
        p.drawPath(path)
    elif name == "chevron-right":
        path = QPainterPath()
        path.moveTo(9.5, 5)
        path.lineTo(16, 12)
        path.lineTo(9.5, 19)
        p.drawPath(path)
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3, 6)
        path.lineTo(9, 6)
        path.lineTo(11, 8.5)
        path.lineTo(21, 8.5)
        path.lineTo(21, 19)
        path.lineTo(3, 19)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "info":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        p.drawLine(QPointF(12, 10.5), QPointF(12, 16.5))
        p.drawPoint(QPointF(12, 7.5))
    elif name == "print-preview":
        p.drawRoundedRect(QRectF(4, 3, 12, 16), 1.2, 1.2)
        p.drawEllipse(QPointF(17.5, 14.5), 3.5, 3.5)
        p.drawLine(QPointF(17.5, 13), QPointF(17.5, 16))
        p.drawPoint(QPointF(17.5, 17.4))
    elif name == "logout":
        p.drawLine(QPointF(4, 12), QPointF(14.5, 12))
        path = QPainterPath()
        path.moveTo(10.5, 8)
        path.lineTo(14.5, 12)
        path.lineTo(10.5, 16)
        p.drawPath(path)
        p.drawLine(QPointF(17, 4), QPointF(20, 4))
        p.drawLine(QPointF(20, 4), QPointF(20, 20))
        p.drawLine(QPointF(20, 20), QPointF(17, 20))
    else:
        p.drawEllipse(QPointF(12, 12), 8, 8)


def school_logo(size: int = 64) -> QPixmap:
    """Original crest-style school mark: teal rounded tile, open book, gold cap."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale((size * 2) / 64.0, (size * 2) / 64.0)
    gradient = QLinearGradient(0, 0, 64, 64)
    gradient.setColorAt(0, QColor("#0f766e"))
    gradient.setColorAt(1, QColor("#0b3b45"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(1.5, 1.5, 61, 61), 14, 14)
    painter.setBrush(QColor("#c2871b"))
    painter.drawEllipse(QPointF(32, 15), 2.5, 2.5)
    painter.setPen(QPen(QColor("#ffffff"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(12, 30)
    path.cubicTo(20, 26, 27, 27, 32, 31)
    path.cubicTo(37, 27, 44, 26, 52, 30)
    path.lineTo(52, 47)
    path.cubicTo(44, 43, 37, 44, 32, 48)
    path.cubicTo(27, 44, 20, 43, 12, 47)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(QPointF(32, 31), QPointF(32, 48))
    painter.setPen(QPen(QColor("#c2871b"), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawLine(QPointF(21, 34), QPointF(28, 33))
    painter.drawLine(QPointF(21, 39), QPointF(28, 38))
    painter.drawLine(QPointF(36, 33), QPointF(43, 34))
    painter.drawLine(QPointF(36, 38), QPointF(43, 39))
    painter.end()
    return pm


def avatar_pixmap(initials: str, size: int = 34, color: str = "#0f766e") -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale((size * 2) / 40.0, (size * 2) / 40.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(QRectF(1, 1, 38, 38))
    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", 12)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(1, 1, 38, 38), Qt.AlignmentFlag.AlignCenter, initials[:2].upper())
    painter.end()
    return pm
