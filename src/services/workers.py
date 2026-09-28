"""基准与压力的 QThread 工作器。"""
from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QThread, Signal

from ..benchmark.base import Benchmark
from ..core.logger import get_logger
from .runner import registry

log = get_logger("workers")


class BenchmarkWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, benchmark: Benchmark, parent=None) -> None:
        super().__init__(parent)
        self._benchmark = benchmark
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            result = self._benchmark.run(
                progress_cb=lambda p, m="": self.progress.emit(int(p), str(m)),
                stop_event=self._stop,
            )
            self.finished_ok.emit(result.as_dict())
        except Exception as exc:  # pragma: no cover
            log.exception("基准执行失败")
            self.failed.emit(str(exc))
        finally:
            registry.unregister(self)


class StressWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(dict)
    failed = Signal(str)
    sample = Signal(dict)

    def __init__(self, stresser, seconds: int, parent=None, **run_kwargs) -> None:
        super().__init__(parent)
        self._stresser = stresser
        self._seconds = max(0, int(seconds))
        self._run_kwargs = run_kwargs
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            def on_sample(elapsed: float = 0.0, **kw) -> None:
                if self._seconds:
                    pct = int(min(99, elapsed / max(1, self._seconds) * 100))
                else:
                    pct = int(min(99, elapsed))
                self.progress.emit(pct, f"已运行 {elapsed:.0f}s")
                payload = {"elapsed": elapsed}
                payload.update(kw)
                self.sample.emit(payload)

            result = self._stresser.run(
                seconds=self._seconds,
                on_sample=on_sample,
                stop_event=self._stop,
                **self._run_kwargs,
            )
            self.finished_ok.emit(result)
        except Exception as exc:  # pragma: no cover
            log.exception("压力测试失败")
            self.failed.emit(str(exc))
        finally:
            registry.unregister(self)
