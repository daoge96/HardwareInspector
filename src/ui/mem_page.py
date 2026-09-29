"""内存页面。"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from ..benchmark.mem_bench import MemBenchmark
from ..core.config import config
from ..core.state import app_state
from ..hardware.memory import MemDetector
from ..services.runner import registry
from ..services.workers import BenchmarkWorker, StressWorker
from ..stress.mem_stress import MemStresser
from .base_page import BasePage
from .widgets.card import InfoCard
from .widgets.chart import RealtimeChart


class MemPage(BasePage):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "内存检测与测试",
            "容量 / 通道 / 频率 / 时序 / 颗粒厂商，带宽与延迟基准，满载分配写入校验。",
            parent,
        )
        self.info = InfoCard("检测信息")
        self.body.addWidget(self.info)
        self.chart = RealtimeChart(
            [("percent", "占用率(%)", "#a855f7", "left")],
            max_points=int(config().get("chart_points", 120)),
            y_left=(0, 100),
        )
        self.body.addWidget(self.chart)
        self.btn_bench = self.add_button("开始基准测试", self._on_bench)
        self.btn_stress = self.add_button("开始压力测试", self._on_stress)
        self.btn_stop = self.add_button("停止", self._on_stop)
        self.btn_stop.setEnabled(False)
        self.result = QLabel("尚未运行")
        self.result.setObjectName("statusLabel")
        self.body.addWidget(self.result)
        self._worker = None

    def apply_detection(self, info) -> None:
        if info is not None:
            self.info.set_rows(info.rows())

    def update_snapshot(self, snap: dict) -> None:
        mem = snap.get("mem")
        if mem is None:
            return
        self.chart.append({"percent": mem.percent})

    def _on_bench(self) -> None:
        self._start(BenchmarkWorker(MemBenchmark()), is_bench=True)

    def _on_stress(self) -> None:
        seconds = int(config().get("cpu_stress_seconds", 60))
        percent = int(config().get("mem_stress_percent", 70))
        self._start(StressWorker(MemStresser(), seconds, percent=percent), is_bench=False)

    def _start(self, worker, is_bench: bool) -> None:
        if self._worker is not None:
            return
        self._worker = worker
        worker.progress.connect(self.set_progress)
        worker.failed.connect(self._on_failed)
        worker.finished_ok.connect(self._on_bench_done if is_bench else self._on_stress_done)
        worker.finished.connect(self._on_finished)
        registry.register(worker)
        self.btn_bench.setEnabled(False)
        self.btn_stress.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.set_status("运行中…")
        worker.start()

    def _on_bench_done(self, data: dict) -> None:
        app_state.add_result(data)
        details = "  ".join(f"{k}:{v}" for k, v in (data.get("details") or {}).items())
        self.result.setText(f"得分 {data.get('score')} | {details}")
        self.set_progress(100, "基准完成")

    def _on_stress_done(self, data: dict) -> None:
        self.result.setText(f"压力测试完成: {data}")
        self.set_progress(100, "压力完成")

    def _on_failed(self, message: str) -> None:
        self.set_status(f"失败: {message}")

    def _on_finished(self) -> None:
        self._worker = None
        self.btn_bench.setEnabled(True)
        self.btn_stress.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
