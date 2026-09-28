"""主窗口：页签、全局监控、全部停止。"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow, QScrollArea, QTabWidget

from ..core.config import config
from ..core.constants import APP_DISPLAY_NAME, APP_VERSION
from ..core.sensors import SensorHub
from ..core.state import app_state
from ..core.utils import fmt, is_admin
from ..services.detection import DetectionWorker
from ..services.monitor import MonitorService
from ..services.runner import registry
from .cpu_page import CpuPage
from .disk_page import DiskPage
from .gpu_page import GpuPage
from .home_page import HomePage
from .mem_page import MemPage
from .report_page import ReportPage


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_DISPLAY_NAME} v{APP_VERSION}")
        self.resize(1180, 780)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.home = HomePage()
        self.cpu = CpuPage()
        self.gpu = GpuPage()
        self.mem = MemPage()
        self.disk = DiskPage()
        self.report = ReportPage()
        for title, page in (
            ("主页", self.home),
            ("CPU", self.cpu),
            ("GPU", self.gpu),
            ("内存", self.mem),
            ("硬盘", self.disk),
            ("报告", self.report),
        ):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, title)

        toolbar = self.addToolBar("main")
        toolbar.setMovable(False)
        stop_action = toolbar.addAction("全部停止")
        stop_action.triggered.connect(self._stop_all)
        detect_action = toolbar.addAction("重新检测")
        detect_action.triggered.connect(self._detect_all)

        admin = "管理员" if is_admin() else "普通用户(温度/SMART 可能受限)"
        self.statusBar().showMessage(f"就绪 · 权限: {admin}")

        self._gpu_count = 0
        self._detector = None
        self.monitor = MonitorService(
            SensorHub(), int(config().get("sample_interval_ms", 1000)), lambda: self._gpu_count
        )
        self.monitor.snapshot.connect(self._on_snapshot)
        self.monitor.start()
        QTimer.singleShot(200, self._detect_all)

    def _detect_all(self) -> None:
        if self._detector is not None and self._detector.isRunning():
            return
        self.statusBar().showMessage("正在检测硬件…")
        self._detector = DetectionWorker()
        self._detector.done.connect(self._on_detected)
        self._detector.start()

    def _on_detected(self, data: dict) -> None:
        app_state.detections.update(data)
        self._gpu_count = len(data.get("gpu") or [])
        self.home.apply_detections(data)
        self.cpu.apply_detection(data.get("cpu"))
        self.gpu.apply_detection(data.get("gpu") or [])
        self.mem.apply_detection(data.get("mem"))
        self.disk.apply_detection(data.get("disk") or [])
        self.statusBar().showMessage("硬件检测完成")

    def _on_snapshot(self, snap: dict) -> None:
        self.home.update_snapshot(snap)
        self.cpu.update_snapshot(snap)
        self.gpu.update_snapshot(snap)
        self.mem.update_snapshot(snap)
        self.disk.update_snapshot(snap)
        app_state.set_detection("live", self._build_live_rows(snap))

    @staticmethod
    def _build_live_rows(snap: dict) -> list:
        rows = []
        cpu = snap.get("cpu")
        if cpu is not None:
            rows.extend(
                [
                    ("CPU 功率", fmt(cpu.power, " W", 1)),
                    ("CPU 温度", fmt(cpu.temp, " °C", 0)),
                    ("CPU 主频", fmt(cpu.freq_mhz, " MHz", 0)),
                    ("CPU 有效频率", fmt(cpu.effective_mhz, " MHz", 0)),
                ]
            )
        gpus = snap.get("gpus") or []
        if gpus:
            gpu = gpus[0]
            rows.extend(
                [
                    ("GPU 功率", fmt(gpu.power, " W", 1)),
                    ("GPU 温度", fmt(gpu.temp, " °C", 0)),
                    ("GPU 主频", fmt(gpu.clock_mhz, " MHz", 0)),
                    ("GPU 有效频率", fmt(gpu.effective_mhz, " MHz", 0)),
                ]
            )
        return rows

    def _stop_all(self) -> None:
        registry.stop_all()
        self.statusBar().showMessage("已请求停止全部任务")

    def closeEvent(self, event) -> None:  # noqa: N802
        registry.stop_all()
        try:
            self.monitor.stop()
        except Exception:
            pass
        event.accept()
