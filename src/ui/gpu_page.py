"""GPU 页面。"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from ..benchmark.gpu_bench import compute_benchmark, make_render_result
from ..core.config import config
from ..core.state import app_state
from ..core.utils import fmt
from ..hardware.gpu import GpuDetector
from ..services.runner import registry
from ..services.workers import BenchmarkWorker
from .base_page import BasePage
from .widgets.card import InfoCard
from .widgets.chart import RealtimeChart
from .widgets.gpu_canvas import GpuCanvas


class GpuPage(BasePage):
    def __init__(self, parent=None) -> None:
        super().__init__("GPU 检测与测试", parent)
        self.info = InfoCard("检测信息")
        self.body.addWidget(self.info)
        self.metrics = InfoCard("实时指标（功率 / 温度 / 主频 / 有效频率）")
        self.body.addWidget(self.metrics)
        self.metrics.set_rows([("功率", "N/A"), ("温度", "N/A"), ("主频", "N/A"), ("有效频率", "N/A")])
        self.canvas = GpuCanvas()
        self.body.addWidget(self.canvas)
        self.chart = RealtimeChart(
            [
                ("temp", "温度(°C)", "#ef4444", "left"),
                ("usage", "占用率(%)", "#3b82f6", "left"),
                ("clock", "主频(MHz)", "#22c55e", "right"),
                ("power", "功率(W)", "#eab308", "right2"),
            ],
            max_points=int(config().get("chart_points", 120)),
            y_left=(0, 110),
            y_right=(0, 3000),
            y_right2=(0, 500),
        )
        self.body.addWidget(self.chart)
        self.btn_bench = self.add_button("开始基准测试", self._on_bench)
        self.btn_stop = self.add_button("停止", self._on_stop)
        self.btn_stop.setEnabled(False)
        self.result = QLabel("尚未运行")
        self.result.setObjectName("statusLabel")
        self.body.addWidget(self.result)
        self._worker = None
        self.canvas.benchProgress.connect(self.set_progress)
        self.canvas.benchFinished.connect(self._on_render_done)

    def apply_detection(self, gpus) -> None:
        if gpus:
            self.info.set_rows(gpus[0].rows())
        self.canvas.start_preview()

    def update_snapshot(self, snap: dict) -> None:
        gpus = snap.get("gpus") or []
        if not gpus:
            return
        gpu = gpus[0]
        self.chart.append({"temp": gpu.temp, "usage": gpu.usage, "clock": gpu.clock_mhz, "power": gpu.power})
        self.metrics.set_rows(
            [
                ("功率", fmt(gpu.power, " W", 1)),
                ("温度", fmt(gpu.temp, " °C", 0)),
                ("主频", fmt(gpu.clock_mhz, " MHz", 0)),
                ("有效频率", fmt(gpu.effective_mhz, " MHz", 0)),
            ]
        )

    def _on_bench(self) -> None:
        self.btn_bench.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.set_status("GPU 渲染基准运行中…")
        self.canvas.start_benchmark(int(config().get("gpu_bench_frames", 600)))

    def _on_render_done(self, avg_fps: float, frames: int, elapsed: float) -> None:
        result = make_render_result(avg_fps, frames, elapsed)
        app_state.add_result(result.as_dict())
        self.result.setText(f"渲染: {avg_fps:.1f} FPS (得分 {result.score})，开始并行计算…")
        worker = BenchmarkWorker(_ComputeWrapper())
        worker.progress.connect(self.set_progress)
        worker.failed.connect(self._on_failed)
        worker.finished_ok.connect(self._on_compute_done)
        worker.finished.connect(self._on_finished)
        self._worker = worker
        registry.register(worker)
        worker.start()

    def _on_compute_done(self, data: dict) -> None:
        app_state.add_result(data)
        self.result.setText(self.result.text() + f" | 计算得分 {data.get('score')}")
        self.set_progress(100, "基准完成")

    def _on_failed(self, message: str) -> None:
        self.set_status(f"失败: {message}")

    def _on_finished(self) -> None:
        self._worker = None
        self.btn_bench.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def _on_stop(self) -> None:
        self.canvas.request_stop()
        if self._worker is not None:
            self._worker.request_stop()
        self._on_finished()


class _ComputeWrapper:
    """把函数式 GPU 计算基准适配为 Benchmark 接口。"""

    key = "gpu_compute"
    name = "GPU 并行计算(矩阵乘)"

    def run(self, progress_cb=None, stop_event=None):
        return compute_benchmark(progress_cb, stop_event)
