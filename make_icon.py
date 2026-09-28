"""生成 assets/icon.ico（避免二进制文件直接入库）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication, QImage, QPainter


def main() -> int:
    app = QGuiApplication([])  # noqa: F841
    size = 256
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#1f6feb")))
    painter.drawRoundedRect(QRect(12, 12, size - 24, size - 24), 48, 48)
    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", 110)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignCenter, "H")
    painter.end()
    out = Path(__file__).resolve().parent / "assets" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    ok = image.save(str(out), "ICO")
    print("图标已生成:", out, ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
