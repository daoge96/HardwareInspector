"""硬盘页面。"""
from __future__ import annotations

import os
import string

from PySide6.QtWidgets import QComboBox, QLabel

from ..benchmark.disk_bench import DiskBenchmark
from ..core.config import config
from ..core.state import app_state
from ..hardware.disk import DiskDetector
from ..services.runner import registry
from ..services.workers import BenchmarkWorker
from .base_page import BasePage
from .widgets.card import InfoCard
from .widgets.chart import RealtimeChart


class DiskPage(BasePage):
    def __init__(self, parent=None) -> None:
        super().__init__("硬盘检测与测试", parent)
        self.info = InfoCard("检测信息")
        self.body.addWidget(self.info)
        self.chart = RealtimeChart(
            [
                ("read", "读取(MB/s)", "#06b6d4", "left"),
                ("write", "写入(MB/s)", "#f97316", "left"),
            ],
            max_points=int(config().get("chart_points", 120)),
            y_left=(0, 2000),
        )
        self.body.addWidget(self.chart)
        self.drive = QComboBox()
        for letter in string.ascii_uppercase:
            self.drive.addItem(f"{letter}:")
        system_drive = os.environ.get("SystemDrive", "C:")
        if not system_drive.endswith(":"):
            system_drive = system_drive + ":"
        index = self.drive.findText(system_drive)
        if index >= 0:
            self.drive.setCurrentIndex(index)
        self.actions.addWidget(QLabel("目标盘符"))
        self.actions.addWidget(self.drive)
        self.btn_bench = self.add_button("开始基准测试", self._on_bench)
        self.btn_stop = self.add_button("停止", self._on_stop)
        self.btn_stop.setEnabled(False)
        self.result = QLabel("尚未运行")
        self.result.setObjectName("statusLabel")
        self.body.addWidget(self.result)
        self._worker = None
        self._disks = []

    def apply_detection(self, disks) -> None:
        self._disks = disks or []
        if self._disks:
            self.info.set_rows(self._disks[0].rows())

    def update_snapshot(self, snap: dict) -> None:
        io = snap.get("disk_io") or {}
        self.chart.append({"read": io.get("read_mb_s"), "write": io.get("write_mb_s")})

    def _on_bench(self) -> None:
        if self._worker is not None:
            return
        target = self.drive.currentText() + "\\"
        worker = BenchmarkWorker(DiskBenchmark(target))
        self._worker = worker
        worker.progress.connect(self.set_progress)
        worker.failed.connect(self._on_failed)
        worker.finished_ok.connect(self._on_done)
        worker.finished.connect(self._on_finished)
        registry.register(worker)
        self.btn_bench.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.set_status("运行中…")
        worker.start()

    def _on_done(self, data: dict) -> None:
        app_state.add_result(data)
        details = "  ".join(f"{k}:{v}" for k, v in (data.get("details") or {}).items())
        self.result.setText(f"得分 {data.get('score')} | {details}")
        self.set_progress(100, "基准完成")

    def _on_failed(self, message: str) -> None:
        self.set_status(f"失败: {message}")

    def _on_finished(self) -> None:
        self._worker = None
        self.btn_bench.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
