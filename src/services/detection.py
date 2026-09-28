"""一次性硬件检测工作线程。"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..core.logger import get_logger
from ..hardware.cpu import CpuDetector
from ..hardware.disk import DiskDetector
from ..hardware.gpu import GpuDetector
from ..hardware.memory import MemDetector

log = get_logger("detection")


class DetectionWorker(QThread):
    done = Signal(dict)

    def run(self) -> None:
        try:
            import pythoncom

            pythoncom.CoInitialize()
        except Exception:
            pass
        data: dict = {"cpu": None, "gpu": [], "mem": None, "disk": []}
        try:
            data["cpu"] = CpuDetector().detect()
            data["gpu"] = GpuDetector().detect()
            data["mem"] = MemDetector().detect()
            data["disk"] = DiskDetector().detect()
        except Exception as exc:  # pragma: no cover
            log.exception("硬件检测失败: %s", exc)
        self.done.emit(data)
