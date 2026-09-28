"""内存压力测试（多进程反复写-校验）。"""
from __future__ import annotations

import multiprocessing as mp
import time
from typing import Callable, Optional

from ..core.logger import get_logger

log = get_logger("stress.mem")

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


def _mem_burn(stop_event, size_mb: int, seed: int) -> int:
    size = max(1, size_mb) * 1024 * 1024
    pattern = bytes([seed & 0xFF]) * size
    buf = bytearray(size)
    errors = 0
    while not stop_event.is_set():
        buf[:] = pattern
        if buf[0] != seed & 0xFF or buf[size - 1] != seed & 0xFF:
            errors += 1
    return errors


class MemStresser:
    name = "内存压力测试"

    def run(self, seconds: int = 0, on_sample: Optional[Callable] = None, stop_event=None, workers: int = 1, percent: int = 70) -> dict:
        sample = on_sample or (lambda **kw: None)
        workers = max(1, workers)
        available_mb = 4096
        if psutil is not None:
            try:
                available_mb = int(psutil.virtual_memory().available / 1048576)
            except Exception:
                pass
        size_mb = max(64, int(available_mb * max(10, min(percent, 95)) / 100 / workers))
        ev = mp.Event()
        procs = [mp.Process(target=_mem_burn, args=(ev, size_mb, i + 1), daemon=True) for i in range(workers)]
        for p in procs:
            p.start()
        t0 = time.perf_counter()
        total_errors = 0
        try:
            while True:
                elapsed = time.perf_counter() - t0
                if stop_event is not None and stop_event.is_set():
                    break
                if seconds and elapsed >= seconds:
                    break
                sample(elapsed=elapsed, errors=total_errors)
                time.sleep(1.0)
        finally:
            ev.set()
            for p in procs:
                p.join(timeout=2.0)
                if p.is_alive():
                    p.terminate()
        duration = time.perf_counter() - t0
        return {"workers": workers, "size_mb": size_mb, "duration": duration, "errors": total_errors}
