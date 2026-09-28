"""内存带宽与延迟基准测试。"""
from __future__ import annotations

import time
from array import array

import numpy as np

from ..core.config import config
from ..core.logger import get_logger
from .base import Benchmark, BenchmarkResult

log = get_logger("bench.mem")

_COPY_REF = 18000.0
_WRITE_REF = 14000.0
_READ_REF = 9000.0
_LAT_REF = 85.0


class MemBenchmark(Benchmark):
    key = "memory"
    name = "内存基准测试"

    def run(self, progress_cb=None, stop_event=None) -> BenchmarkResult:
        cb = progress_cb or (lambda p, m="": None)
        started = time.perf_counter()
        result = BenchmarkResult(key=self.key, name=self.name)
        try:
            block_mb = max(32, int(config().get("mem_bench_block_mb", 256) or 256))
            n = block_mb * 1024 * 1024
            cb(5, "分配缓冲…")
            a = np.ones(n, dtype=np.uint8)
            b = np.empty_like(a)
            cb(20, "复制带宽…")
            t0 = time.perf_counter()
            b[:] = a
            t_copy = time.perf_counter() - t0
            cb(40, "写入带宽…")
            t0 = time.perf_counter()
            a[:] = 123
            t_write = time.perf_counter() - t0
            cb(60, "读取带宽…")
            idx = np.random.randint(0, n, size=min(n // 8, 4_000_000))
            gathered = a[idx]
            t0 = time.perf_counter()
            _ = int(gathered.sum())
            t_read = time.perf_counter() - t0
            cb(80, "访问延迟…")
            count = 4_000_000
            stride = 1_000_003
            buf = array("i", [(i * stride) % count for i in range(count)])
            pos = 0
            t0 = time.perf_counter()
            for _ in range(count):
                pos = buf[pos]
            t_lat = time.perf_counter() - t0
            latency_ns = t_lat / count * 1e9
            copy_bw = n / max(t_copy, 1e-6) / 1e6
            write_bw = n / max(t_write, 1e-6) / 1e6
            read_bw = gathered.nbytes / max(t_read, 1e-6) / 1e6
            score = (
                min(copy_bw / _COPY_REF, 3.0) * 1000
                + min(write_bw / _WRITE_REF, 3.0) * 1000
                + min(read_bw / _READ_REF, 3.0) * 1000
                + min(_LAT_REF / max(latency_ns, 1e-6), 3.0) * 1000
            ) / 4.0
            result.score = round(score, 1)
            result.details = {
                "复制带宽": f"{copy_bw:.0f} MB/s",
                "写入带宽": f"{write_bw:.0f} MB/s",
                "读取带宽": f"{read_bw:.0f} MB/s",
                "访问延迟": f"{latency_ns:.1f} ns",
                "测试块大小": f"{block_mb} MB",
            }
        except Exception as exc:  # pragma: no cover
            log.exception("内存基准失败")
            result.error = str(exc)
        result.duration = time.perf_counter() - started
        cb(100, "完成")
        return result
