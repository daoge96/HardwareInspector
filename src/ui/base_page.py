"""页面基类：统一标题区、进度区与按钮区。"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BasePage(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 18, 20, 18)
        self.root.setSpacing(14)

        header = QVBoxLayout()
        header.setSpacing(3)
        self.header = QLabel(title)
        self.header.setObjectName("pageTitle")
        header.addWidget(self.header)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        self.subtitle.setVisible(bool(subtitle))
        header.addWidget(self.subtitle)
        self.root.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        self.root.addLayout(self.body)
        self.root.addStretch(1)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        self.buttons: List[QPushButton] = []
        self.root.addLayout(self.actions)

        bar = QFrame()
        bar.setObjectName("statusBarCard")
        bottom = QHBoxLayout(bar)
        bottom.setContentsMargins(12, 8, 12, 8)
        bottom.setSpacing(12)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedWidth(240)
        self.progress.setTextVisible(False)
        bottom.addWidget(self.progress)
        self.status = QLabel("就绪")
        self.status.setObjectName("statusLabel")
        bottom.addWidget(self.status, 1)
        self.root.addWidget(bar)

    def add_button(self, text: str, slot, kind: str = "") -> QPushButton:
        button = QPushButton(text)
        if kind:
            button.setObjectName(kind)
        button.clicked.connect(slot)
        self.actions.addWidget(button)
        self.buttons.append(button)
        return button

    def set_progress(self, percent: int, message: str = "") -> None:
        self.progress.setValue(int(percent))
        if message:
            self.status.setText(message)

    def set_status(self, message: str) -> None:
        self.status.setText(message)

    def set_busy(self, busy: bool) -> None:
        for b in self.buttons:
            if b.property("alwaysEnabled"):
                continue
            b.setEnabled(not busy)
