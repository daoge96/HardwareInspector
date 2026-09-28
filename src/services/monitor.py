"""后台监控线程：周期性采样传感器并发出快照信号。"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QThread, Signal

from ..core.logger import get_logger
from ..core.sensors import SensorHub

log = get_logger("monitor")


class MonitorService(QThread):
    snapshot = Signal(dict)

    def __init__(self, hub: SensorHub, interval_ms: int, gpu_count_getter: Callable[[], int]) -> None:
        super().__init__()
        self._hub = hub
        self._interval = max(200, int(interval_ms))
        self._gpu_count_getter = gpu_count_getter
        self._stop = False

    def stop(self) -> None:
        self._stop = True
        self.wait(2000)

    def run(self) -> None:
        try:
            import pythoncom

            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            while not self._stop:
                try:
                    self.snapshot.emit(self._hub.snapshot(self._gpu_count_getter()))
                except Exception as exc:
                    log.debug("采样失败: %s", exc)
                slept = 0
                while slept < self._interval and not self._stop:
                    self.msleep(100)
                    slept += 100
        finally:
            try:
                import pythoncom

                pythoncom.CoUninitialize()
            except Exception:
                pass
