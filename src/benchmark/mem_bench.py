"""内存带宽与访问延迟基准。

旧版问题：
  1. 所谓"读取带宽"根本不是在测读——a[idx] 这个 gather 放在计时之外，
     计时区间里只有 gathered.sum()，测的是"对一个已经生成好的 32MB 数组求和"，
     既不是内存读带宽，量级也完全不对；
  2. 每一项只测一遍，单次抖动直接进成绩；
  3. stop_event 收下不用。

现在：每次计时都包含完整的访存动作，重复 N 次取中位数，并区分
【顺序写 / 顺序复制 / 随机读 gather / 指针追逐延迟】四类。
"""
from __future__ import annotations

import statistics
import time
from array import array
from typing import Callable, List

import numpy as np

from ..core.config import config
from ..core.logger import get_logger
from .base import Benchmark, BenchmarkResult

log = get_logger("bench.mem")

_WRITE_REF_MBPS = 9000.0
_COPY_REF_MBPS = 9000.0
_GATHER_REF_MBPS = 3500.0
_LAT_REF_NS = 85.0


def _best_of(fn: Callable[[], None], repeats: int, stop_event=None) -> float:
    """重复跑取中位数，抵抗单次抖动。"""
    times: List[float] = []
    for _ in range(max(1, repeats)):
        if stop_event is not None and stop_event.is_set():
            break
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    if not times:
        return float("nan")
    return statistics.median(times)


class MemBenchmark(Benchmark):
    key = "memory"
    name = "内存基准测试"

    def run(self, progress_cb=None, stop_event=None) -> BenchmarkResult:
        cb = progress_cb or (lambda p, m="": None)
        started = time.perf_counter()
        result = BenchmarkResult(key=self.key, name=self.name)
        try:
            block_mb = max(64, int(config().get("mem_bench_block_mb", 512) or 512))
            repeats = max(1, min(int(config().get("bench_repeats", 3) or 3), 9))
            n = block_mb * 1024 * 1024

            cb(5, "分配缓冲…")
            a = np.ones(n, dtype=np.uint8)
            b = np.empty_like(a)

            cb(20, "顺序写入…")
            t_write = _best_of(lambda: a.fill(123), repeats, stop_event)

            cb(38, "顺序复制…")
            t_copy = _best_of(lambda: np.copyto(b, a), repeats, stop_event)

            # 真正计时的随机读：整个 gather 都算进去
            # （读索引 8B + 随机读 1B + 写回 1B）
            cb(56, "随机读（gather）…")
            count = min(max(2_000_000, n // 16), 8_000_000)
            idx = np.random.randint(0, n, size=count, dtype=np.int64)
            gathered = np.empty(count, dtype=np.uint8)
            t_gather = _best_of(lambda: np.take(a, idx, out=gathered), repeats, stop_event)
            gather_bytes = count * (8 + 1 + 1)

            cb(74, "指针追逐延迟…")
            steps = 4_000_000
            stride = 1_000_003
            buf = array("i", [(i * stride) % steps for i in range(steps)])
            pos = 0

            def chase() -> None:
                nonlocal pos
                p = pos
                for _ in range(steps):
                    p = buf[p]
                pos = p

            t_lat = _best_of(chase, repeats, stop_event)
            latency_ns = t_lat / steps * 1e9

            write_bw = n / max(t_write, 1e-9) / 1e6
            copy_bw = (n * 2) / max(t_copy, 1e-9) / 1e6      # 读 + 写两个方向
            gather_bw = gather_bytes / max(t_gather, 1e-9) / 1e6

            score = (
                min(write_bw / _WRITE_REF_MBPS, 3.0) * 1000
                + min(copy_bw / _COPY_REF_MBPS, 3.0) * 1000
                + min(gather_bw / _GATHER_REF_MBPS, 3.0) * 1000
                + min(_LAT_REF_NS / max(latency_ns, 1e-9), 3.0) * 1000
            ) / 4.0
            result.score = round(score, 1)
            result.details = {
                "顺序写入": f"{write_bw:.0f} MB/s",
                "顺序复制": f"{copy_bw:.0f} MB/s",
                "随机读 gather": f"{gather_bw:.0f} MB/s",
                "指针追逐延迟": f"{latency_ns:.1f} ns",
                "测试块大小": f"{block_mb} MB",
                "重复次数": repeats,
                "取值方式": "中位数",
            }
        except Exception as exc:  # pragma: no cover
            log.exception("内存基准失败")
            result.error = str(exc)
        result.duration = time.perf_counter() - started
        cb(100, "完成")
        return result
