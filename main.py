"""HardwareInspector 程序入口。"""
from __future__ import annotations

import multiprocessing
import sys

from PySide6.QtGui import QIcon, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from src.core.config import config
from src.core.constants import APP_DISPLAY_NAME, APP_NAME, APP_VERSION
from src.core.utils import resource_path
from src.ui.main_window import MainWindow


def _configure_gl() -> None:
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(fmt)


def main() -> int:
    multiprocessing.freeze_support()
    _configure_gl()
    config().save()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)

    qss = resource_path("assets/style.qss")
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))
    icon = resource_path("assets/icon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
