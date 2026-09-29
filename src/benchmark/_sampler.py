"""测量期间的资源占用采样器（用于饱和校验）。

分段记录：调用 section() 拿到一个游标，stats_since() 只统计该段之后的样本。
这样"单核阶段"的低占用不会稀释"全核阶段"的饱和度。
"""
from __future__ import annotations

import threading
from typing import List, Optional, Tuple

SAMPLE_INTERVAL = 0.5


class ResourceSampler:
    def __init__(self, want_gpu: bool = False) -> None:
        self.cpu: List[float] = []
        self.gpu: List[float] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._want_gpu = want_gpu
        self._nvml = None
        self._handle = None

    def _init_gpu(self) -> None:
        if not self._want_gpu:
            return
        try:
            import pynvml  # type: ignore

            pynvml.nvmlInit()
            if pynvml.nvmlDeviceGetCount() > 0:
                self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._nvml = pynvml
        except Exception:
            self._nvml = None

    def _loop(self) -> None:
        try:
            import psutil  # type: ignore

            psutil.cpu_percent(interval=None, percpu=True)   # 首次调用恒为 0，先预热
        except Exception:
            psutil = None  # type: ignore
        while not self._stop.is_set():
            if psutil is not None:
                try:
                    vals = psutil.cpu_percent(interval=None, percpu=True)
                    if vals:
                        self.cpu.append(sum(vals) / len(vals))
                except Exception:
                    pass
            if self._nvml is not None and self._handle is not None:
                try:
                    self.gpu.append(
                        float(self._nvml.nvmlDeviceGetUtilizationRates(self._handle).gpu))
                except Exception:
                    pass
            self._stop.wait(SAMPLE_INTERVAL)

    def start(self) -> None:
        self._init_gpu()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        # 不调用 nvmlShutdown：sensors.py 也在用 NVML 且只 init 不 shutdown

    def cursor(self) -> int:
        return len(self.cpu)

    def stats_since(self, cursor: int, which: str = "cpu") -> Tuple[Optional[float], Optional[float]]:
        values = (self.cpu if which == "cpu" else self.gpu)[cursor:]
        return describe(values)


def describe(values: List[float]) -> Tuple[Optional[float], Optional[float]]:
    """返回 (均值, 变异系数%)。"""
    if not values:
        return None, None
    mean = sum(values) / len(values)
    if len(values) < 2 or mean <= 0:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, (var ** 0.5) / mean * 100.0
