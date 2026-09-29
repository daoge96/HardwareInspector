"""主窗口：顶部标题栏、页签、全局监控、全部停止。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.config import config
from ..core.constants import APP_DISPLAY_NAME, APP_VERSION
from ..core.sensors import SensorHub
from ..core.state import app_state
from ..core.utils import fmt, is_admin
from ..services.detection import DetectionWorker
from ..services.monitor import MonitorService
from ..services.runner import registry
from .cpu_page import CpuPage
from .crypto_page import CryptoPage
from .disk_page import DiskPage
from .gpu_page import GpuPage
from .home_page import HomePage
from .mem_page import MemPage
from .report_page import ReportPage
from .widgets.section import Pill


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_DISPLAY_NAME} v{APP_VERSION}")
        self.resize(1220, 820)

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.home = HomePage()
        self.crypto = CryptoPage()
        self.cpu = CpuPage()
        self.gpu = GpuPage()
        self.mem = MemPage()
        self.disk = DiskPage()
        self.report = ReportPage()
        for title, page in (
            ("系统总览", self.home),
            ("解密基准", self.crypto),
            ("CPU", self.cpu),
            ("GPU", self.gpu),
            ("内存", self.mem),
            ("硬盘", self.disk),
            ("报告", self.report),
        ):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, title)

        toolbar = self.addToolBar("main")
        toolbar.setMovable(False)
        stop_action = toolbar.addAction("全部停止")
        stop_action.triggered.connect(self._stop_all)
        detect_action = toolbar.addAction("重新检测")
        detect_action.triggered.connect(self._detect_all)

        self._gpu_count = 0
        self._detector = None
        self.monitor = MonitorService(
            SensorHub(), int(config().get("sample_interval_ms", 1000)), lambda: self._gpu_count
        )
        self.monitor.snapshot.connect(self._on_snapshot)
        self.monitor.start()
        QTimer.singleShot(200, self._detect_all)

    # ------------------------------------------------------------------
    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("appHeader")
        header.setFixedHeight(56)
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 8, 18, 8)
        row.setSpacing(10)

        title = QLabel(APP_DISPLAY_NAME)
        title.setObjectName("appTitle")
        row.addWidget(title)
        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("appVersion")
        row.addWidget(version)
        row.addStretch(1)

        admin = is_admin()
        self.perm_pill = Pill("管理员" if admin else "普通用户（温度/SMART 可能受限）",
                              "ok" if admin else "warn")
        row.addWidget(self.perm_pill)
        self.gpu_pill = Pill("GPU 解密：探测中…", "info")
        row.addWidget(self.gpu_pill)
        return header

    # ------------------------------------------------------------------
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
        self._probe_cuda()

    def _probe_cuda(self) -> None:
        try:
            from ..benchmark.crypto_bench import available as gpu_available

            ok, info = gpu_available()
            self.gpu_pill.show_text(f"GPU 解密：{info}" if ok else f"GPU 解密不可用：{info}",
                                    "ok" if ok else "warn")
        except Exception as exc:
            self.gpu_pill.show_text(f"GPU 解密不可用：{exc}", "warn")

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
            rows.extend([
                ("CPU 功率", fmt(cpu.power, " W", 1)),
                ("CPU 温度", fmt(cpu.temp, " °C", 0)),
                ("CPU 主频", fmt(cpu.freq_mhz, " MHz", 0)),
                ("CPU 有效频率", fmt(cpu.effective_mhz, " MHz", 0)),
            ])
        gpus = snap.get("gpus") or []
        if gpus:
            gpu = gpus[0]
            rows.extend([
                ("GPU 功率", fmt(gpu.power, " W", 1)),
                ("GPU 温度", fmt(gpu.temp, " °C", 0)),
                ("GPU 主频", fmt(gpu.clock_mhz, " MHz", 0)),
                ("GPU 有效频率", fmt(gpu.effective_mhz, " MHz", 0)),
            ])
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
