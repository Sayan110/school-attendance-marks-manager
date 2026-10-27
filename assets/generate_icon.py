"""Generate the Windows application icon (app.ico) from the school crest.

Run from the project root:

    python assets/generate_icon.py

The crest is drawn with QPainter at every icon size and written as a
multi-resolution ICO (PNG-compressed entries), so Windows Explorer, the
taskbar and the shortcut all get a crisp image instead of one bitmap
downscaled to 16 pixels.
"""
from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

# Make `app` importable when this script is run from anywhere.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_crest(size: int) -> QImage:
    """Draw the school crest at exactly `size` x `size` pixels."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / 64.0, size / 64.0)

    # Rounded teal tile with a diagonal gradient.
    gradient = QLinearGradient(0, 0, 64, 64)
    gradient.setColorAt(0.0, QColor("#0f766e"))
    gradient.setColorAt(1.0, QColor("#0b3b45"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(1.5, 1.5, 61, 61), 14, 14)

    # Gold lamp of learning above the open book.
    painter.setBrush(QColor("#e0a63a"))
    painter.drawEllipse(QPointF(32, 15), 3.0, 3.0)

    # Keep the book readable when the whole icon is only 16 pixels wide.
    stroke = 2.4 if size >= 48 else 3.6
    painter.setPen(
        QPen(
            QColor("#ffffff"),
            stroke,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    book = QPainterPath()
    book.moveTo(12, 30)
    book.cubicTo(20, 26, 27, 27, 32, 31)
    book.cubicTo(37, 27, 44, 26, 52, 30)
    book.lineTo(52, 47)
    book.cubicTo(44, 43, 37, 44, 32, 48)
    book.cubicTo(27, 44, 20, 43, 12, 47)
    book.closeSubpath()
    painter.drawPath(book)
    painter.drawLine(QPointF(32, 31), QPointF(32, 48))

    # Gold page lines; skipped at 16 px where they would smear.
    if size >= 32:
        painter.setPen(
            QPen(
                QColor("#e0a63a"),
                2.6 if size >= 48 else 3.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawLine(QPointF(20, 34.5), QPointF(28, 33.5))
        painter.drawLine(QPointF(20, 39.5), QPointF(28, 38.5))
        painter.drawLine(QPointF(36, 33.5), QPointF(44, 34.5))
        painter.drawLine(QPointF(36, 38.5), QPointF(44, 39.5))

    painter.end()
    return image


def write_ico(path: Path) -> None:
    """Write a multi-resolution ICO with one PNG payload per size."""
    payloads: list[tuple[int, bytes]] = []
    with tempfile.TemporaryDirectory(prefix="svsm-icon-") as temp:
        for size in ICON_SIZES:
            png_path = Path(temp) / f"crest-{size}.png"
            if not render_crest(size).save(str(png_path), "PNG"):
                raise RuntimeError(f"could not render icon at {size}px")
            payloads.append((size, png_path.read_bytes()))

    header = struct.pack("<HHH", 0, 1, len(payloads))
    directory = bytearray()
    offset = 6 + 16 * len(payloads)
    for size, data in payloads:
        # 256 px is encoded as 0 in the single-byte width/height fields.
        dimension = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII",
            dimension,
            dimension,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        )
        offset += len(data)

    path.write_bytes(header + bytes(directory) + b"".join(data for _, data in payloads))


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    target = ROOT / "app.ico"
    write_ico(target)
    print(f"wrote {target} ({target.stat().st_size:,} bytes, {len(ICON_SIZES)} sizes)")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
