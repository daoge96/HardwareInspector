"""页面基类。"""
from __future__ import annotations

from typing import List

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BasePage(QWidget):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(16, 16, 16, 16)
        self.root.setSpacing(10)
        self.header = QLabel(title)
        self.header.setObjectName("pageTitle")
        self.root.addWidget(self.header)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        self.root.addLayout(self.body)
        self.root.addStretch(1)
        self.actions = QHBoxLayout()
        self.buttons: List[QPushButton] = []
        self.root.addLayout(self.actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(360)
        self.status = QLabel("就绪")
        self.status.setObjectName("statusLabel")
        bottom = QHBoxLayout()
        bottom.addWidget(self.progress)
        bottom.addWidget(self.status)
        bottom.addStretch(1)
        self.root.addLayout(bottom)

    def add_button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
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
