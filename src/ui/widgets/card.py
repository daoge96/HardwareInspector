"""信息卡片与大数值卡片。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout


class InfoCard(QFrame):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        layout.addWidget(title_label)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(18)
        self._grid.setVerticalSpacing(6)
        layout.addLayout(self._grid)

    def set_rows(self, rows) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, (key, value) in enumerate(rows):
            key_label = QLabel(str(key))
            key_label.setObjectName("keyLabel")
            val_label = QLabel(str(value))
            val_label.setObjectName("valLabel")
            val_label.setWordWrap(True)
            val_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._grid.addWidget(key_label, index, 0)
            self._grid.addWidget(val_label, index, 1)


class StatCard(QFrame):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        self._value = QLabel("--")
        self._value.setObjectName("statValue")
        self._sub = QLabel("")
        self._sub.setObjectName("statSub")
        self._sub.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(self._value)
        layout.addWidget(self._sub)

    def set_value(self, text: str, sub: str = "") -> None:
        self._value.setText(text)
        self._sub.setText(sub)
