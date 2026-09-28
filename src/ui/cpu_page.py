"""CPU 页面。"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from ..benchmark.cpu_bench import CpuBenchmark
from ..core.config import config
from ..core.state import app_state
from ..hardware.cpu import CpuDetector
from ..services.runner import registry
from ..services.workers import BenchmarkWorker, StressWorker
from ..stress.cpu_stress import CpuStresser
from .base_page import BasePage
from .widgets.card import InfoCard
from .widgets.chart import RealtimeChart


class CpuPage(BasePage):
    def __init__(self, parent=None) -> None:
        super().__init__("CPU 检测与测试", parent)
        self.info = InfoCard("检测信息")
        self.body.addWidget(self.info)
        self.chart = RealtimeChart(
            [
                ("temp", "温度(°C)", "#ef4444", "left"),
                ("usage", "占用率(%)", "#3b82f6", "left"),
                ("freq", "频率(MHz)", "#22c55e", "right"),
            ],
            max_points=int(config().get("chart_points", 120)),
            y_left=(0, 110),
            y_right=(0, 6000),
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
        cpu = snap.get("cpu")
        if cpu is None:
            return
        self.chart.append({"temp": cpu.temp, "usage": cpu.usage, "freq": cpu.freq_mhz})

    def _on_bench(self) -> None:
        self._start(BenchmarkWorker(CpuBenchmark()), is_bench=True)

    def _on_stress(self) -> None:
        seconds = int(config().get("cpu_stress_seconds", 60))
        self._start(StressWorker(CpuStresser(), seconds), is_bench=False)

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
