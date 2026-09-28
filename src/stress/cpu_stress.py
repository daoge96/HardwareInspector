"""CPU 压力测试（多进程满载）。"""
from __future__ import annotations

import math
import multiprocessing as mp
import time
from typing import Callable, Optional

from ..core.logger import get_logger

log = get_logger("stress.cpu")


def _burn(stop_event) -> int:
    x = 12345
    y = 1.0
    while not stop_event.is_set():
        for _ in range(100_000):
            x = (x * 1103515245 + 12345) & 0xFFFFFFFF
        y = math.sqrt(abs(math.sin(y) + 2.0))
    return x


class CpuStresser:
    name = "CPU 压力测试"

    def run(self, seconds: int = 0, on_sample: Optional[Callable] = None, stop_event=None, workers: Optional[int] = None) -> dict:
        sample = on_sample or (lambda **kw: None)
        workers = max(1, workers or (mp.cpu_count() or 1))
        ev = mp.Event()
        procs = [mp.Process(target=_burn, args=(ev,), daemon=True) for _ in range(workers)]
        for p in procs:
            p.start()
        t0 = time.perf_counter()
        try:
            while True:
                elapsed = time.perf_counter() - t0
                if stop_event is not None and stop_event.is_set():
                    break
                if seconds and elapsed >= seconds:
                    break
                sample(elapsed=elapsed)
                time.sleep(1.0)
        finally:
            ev.set()
            for p in procs:
                p.join(timeout=2.0)
                if p.is_alive():
                    p.terminate()
        duration = time.perf_counter() - t0
        sample(elapsed=duration)
        return {"workers": workers, "duration": duration}
