"""小控件：区块标题、状态药丸、评分徽章。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class SectionTitle(QLabel):
    def __init__(self, text: str, hint: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sectionTitle")
        self.setTextFormat(Qt.RichText)
        self.set_text(text, hint)

    def set_text(self, text: str, hint: str = "") -> None:
        tail = f"<span style='color:#7d8590;font-size:12px;font-weight:400'>{hint}</span>" if hint else ""
        self.setText(f"<span>{text}</span>{tail}")


class Pill(QLabel):
    """状态药丸：ok / warn / bad / info。"""

    def __init__(self, text: str = "", kind: str = "info", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("pill")
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        self.setProperty("kind", kind)
        self.style().unpolish(self)
        self.style().polish(self)

    def show_text(self, text: str, kind: str = "info") -> None:
        self.setText(text)
        self.set_kind(kind)
        self.setVisible(bool(text))


class ScoreBadge(QFrame):
    """评分徽章：分数 + 等级。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("scoreBadge")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(10)
        self._score = QLabel("--")
        self._score.setObjectName("badgeScore")
        self._grade = QLabel("")
        self._grade.setObjectName("badgeGrade")
        row.addWidget(self._score)
        row.addWidget(self._grade)
        self.setVisible(False)

    def show_score(self, score: float, grade: str = "", label: str = "") -> None:
        self._score.setText(f"{score:,.0f}")
        self._grade.setText(f"{grade} {label}".strip())
        self.setVisible(True)
