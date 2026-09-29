"""信息卡片、指标卡与带操作区的板块卡片。

InfoCard / ActionCard 支持【原地更新】：行数不变时复用已有 QLabel，
不再每秒 deleteLater 重建全部控件（旧版每秒重建，滚动位置与选中文本都会丢）。
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)


class InfoCard(QFrame):
    """两列 key/value 卡片，原地更新。"""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)
        self._title = QLabel(title)
        self._title.setObjectName("cardTitle")
        outer.addWidget(self._title)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(20)
        self._grid.setVerticalSpacing(7)
        self._grid.setColumnStretch(1, 1)
        outer.addLayout(self._grid)
        self._rows: List[Tuple[QLabel, QLabel]] = []
        self._title.setVisible(bool(title))

    def _ensure(self, count: int) -> None:
        while len(self._rows) < count:
            k = QLabel()
            k.setObjectName("keyLabel")
            k.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            v = QLabel()
            v.setObjectName("valLabel")
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            index = len(self._rows)
            self._grid.addWidget(k, index, 0)
            self._grid.addWidget(v, index, 1)
            self._rows.append((k, v))
        while len(self._rows) > count:
            k, v = self._rows.pop()
            self._grid.removeWidget(k)
            self._grid.removeWidget(v)
            k.deleteLater()
            v.deleteLater()

    def set_rows(self, rows: Sequence[Tuple[str, str]]) -> None:
        rows = list(rows)
        self._ensure(len(rows))
        for (k, v), (key, value) in zip(self._rows, rows):
            if k.text() != str(key):
                k.setText(str(key))
            if v.text() != str(value):
                v.setText(str(value))

    def set_title(self, text: str) -> None:
        self._title.setText(text)
        self._title.setVisible(bool(text))


class StatCard(QFrame):
    """大数值卡片，左侧一条强调色。"""

    def __init__(self, title: str, accent: str = "#3b82f6", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setStyleSheet(f"QFrame#statCard {{ border-left: 3px solid {accent}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        self._title = QLabel(title)
        self._title.setObjectName("cardTitle")
        self._value = QLabel("--")
        self._value.setObjectName("statValue")
        self._sub = QLabel("")
        self._sub.setObjectName("statSub")
        self._sub.setWordWrap(True)
        layout.addWidget(self._title)
        layout.addWidget(self._value)
        layout.addWidget(self._sub)

    def set_value(self, text: str, sub: str = "") -> None:
        if self._value.text() != text:
            self._value.setText(text)
        if self._sub.text() != sub:
            self._sub.setText(sub)


class ActionCard(QFrame):
    """标题 + 说明 + 操作按钮 + 结果行。"""

    def __init__(self, title: str, subtitle: str = "", button_text: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._title = QLabel(title)
        self._title.setObjectName("cardTitle")
        text_col.addWidget(self._title)
        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("cardHint")
        self._subtitle.setWordWrap(True)
        self._subtitle.setVisible(bool(subtitle))
        text_col.addWidget(self._subtitle)
        head.addLayout(text_col, 1)

        self.button = QPushButton(button_text)
        self.button.setObjectName("primary")
        self.button.setVisible(bool(button_text))
        self.button.setMinimumWidth(150)
        head.addWidget(self.button, 0, Qt.AlignTop)
        outer.addLayout(head)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(20)
        self.grid.setVerticalSpacing(7)
        self.grid.setColumnStretch(1, 1)
        outer.addLayout(self.grid)
        self._rows: List[Tuple[QLabel, QLabel]] = []
        self.hint = QLabel("")
        self.hint.setObjectName("cardHint")
        self.hint.setWordWrap(True)
        self.hint.setVisible(False)
        outer.addWidget(self.hint)

    def _ensure(self, count: int) -> None:
        while len(self._rows) < count:
            k = QLabel()
            k.setObjectName("keyLabel")
            v = QLabel("--")
            v.setObjectName("valLabel")
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            v.setWordWrap(True)
            index = len(self._rows)
            self.grid.addWidget(k, index, 0)
            self.grid.addWidget(v, index, 1)
            self._rows.append((k, v))
        while len(self._rows) > count:
            k, v = self._rows.pop()
            self.grid.removeWidget(k)
            self.grid.removeWidget(v)
            k.deleteLater()
            v.deleteLater()

    def set_rows(self, rows: Sequence[Tuple[str, str]]) -> None:
        rows = list(rows)
        self._ensure(len(rows))
        for (k, v), (key, value) in zip(self._rows, rows):
            if k.text() != str(key):
                k.setText(str(key))
            if v.text() != str(value):
                v.setText(str(value))

    def set_hint(self, text: str, kind: str = "hint") -> None:
        self.hint.setText(text)
        self.hint.setObjectName({"hint": "cardHint", "warn": "warnText",
                                 "ok": "okText", "bad": "badText"}.get(kind, "cardHint"))
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)
        self.hint.setVisible(bool(text))
