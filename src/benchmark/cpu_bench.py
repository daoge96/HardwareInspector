"""CPU 综合基准：单核速度 + 真·全核并行扩展。

旧版问题（本次重写的原因）：
  1. 所谓"多核测试"用 pool.map 跑固定作业量，每个进程只有 ~15ms 的活，
     进程启动/回收开销占大头，测出来的"加速比"基本是噪声；
  2. 各阶段作业量写死（30M 次整数、6M 次浮点…），总耗时只有几秒，
     CPU 远未进入稳态，睿频/降频都还没走完；
  3. stop_event 收下了却从不检查，"停止"按钮对基准测试无效；
  4. 加速比只以 speedup**0.5 混进总分，不透明。

现在的做法：
  - 每个负载都跑满一个【定时窗口】（默认 6s），稳态取值；
  - 单核阶段直接在调用进程里跑，不付进程启动开销；
  - 全核阶段 spawn 出全部逻辑核心，聚合吞吐 / 单核吞吐 = 真实加速比，
    并以"并行效率"单独出分，不再塞进一个指数里；
  - 全程检查 stop_event，可随时中止且返回已经测到的有效数据。
"""
from __future__ import annotations

import hashlib
import math
import multiprocessing as mp
import threading
import time
import zlib
from typing import Callable, Dict, List, Optional, Tuple

from ..core.config import config
from ..core.logger import get_logger
from .base import Benchmark, BenchmarkResult

log = get_logger("bench.cpu")

# 参考值，单位必须与 _run_window 的返回值一致：
#   整数/浮点 -> 次/秒，压缩/SHA -> MB/s
# 若不统一，ratio 会差 1e6 倍，被 3.0 的上限一刀切平，四项全变满分。
_INT_REF = 25_000_000.0      # 次/秒
_FLOAT_REF = 8_000_000.0     # 次/秒
_ZIP_REF = 60.0             # MB/s
_SHA_REF = 900.0            # MB/s

DEFAULT_PHASE_SECONDS = 6.0
_CHUNK_INT = 4_000_000
_CHUNK_FLOAT = 800_000
_CHUNK_ZIP_MB = 16
_CHUNK_SHA_MB = 64

_PATTERN = b"HardwareInspectorBenchmarkPattern-0123456789"


# --- 负载（模块级，spawn 子进程要用） --------------------------------------


def _int_chunk(iters: int) -> int:
    x = 12345
    for _ in range(iters):
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF
    return x


def _float_chunk(iters: int) -> float:
    x = 1.0
    acc = 0.0
    for _ in range(iters):
        x = math.sqrt(abs(math.sin(x) + 2.0))
        acc += x
    return acc


def _zip_chunk(mb: int) -> int:
    size = mb * 1024 * 1024
    data = (_PATTERN * (size // len(_PATTERN) + 1))[:size]
    return len(zlib.compress(data, 6))


def _sha_chunk(mb: int) -> str:
    block = b"x" * (1024 * 1024)
    h = hashlib.sha256()
    for _ in range(mb):
        h.update(block)
    return h.hexdigest()


_KINDS = {
    "int": (_int_chunk, _CHUNK_INT, "Mops/s"),
    "float": (_float_chunk, _CHUNK_FLOAT, "Mops/s"),
    "zip": (_zip_chunk, _CHUNK_ZIP_MB, "MB/s"),
    "sha": (_sha_chunk, _CHUNK_SHA_MB, "MB/s"),
}


def _chunk_units(kind: str) -> float:
    fn, chunk, _unit = _KINDS[kind]
    if kind == "zip":
        return float(chunk)                       # MB
    if kind == "sha":
        return float(chunk)                       # MB
    return float(chunk)                           # 迭代次数


def _run_window(kind: str, seconds: float, stop_event=None,
                progress: Optional[Callable[[float], None]] = None) -> float:
    """在当前进程里把一个负载跑满 seconds 秒，返回 单位/秒。"""
    fn = _KINDS[kind][0]
    chunk = _KINDS[kind][1]
    t0 = time.perf_counter()
    units = 0.0
    while True:
        fn(chunk)
        units += _chunk_units(kind)
        now = time.perf_counter()
        if progress is not None:
            progress(now - t0)
        if stop_event is not None and stop_event.is_set():
            break
        if now - t0 >= seconds:
            break
    return units / max(time.perf_counter() - t0, 1e-9)


def _core_worker(stop, counter, kind: str, ready=None, go=None) -> None:
    """ready/go 把 spawn + import 的启动耗时挡在计时窗口之外。"""
    if ready is not None:
        with ready.get_lock():
            ready.value += 1
    if go is not None:
        go.wait()
    fn = _KINDS[kind][0]
    chunk = _KINDS[kind][1]
    units = 0.0
    per = _chunk_units(kind)
    while not stop.is_set():
        fn(chunk)
        units += per
    if units:
        with counter.get_lock():
            counter.value += int(units)


def _run_all_cores(kind: str, seconds: float, cores: int, stop_event=None,
                   progress: Optional[Callable[[float], None]] = None) -> float:
    ctx = mp.get_context("spawn")
    counter = ctx.Value("q", 0)
    ready = ctx.Value("i", 0)
    go = ctx.Event()
    stop = ctx.Event()
    procs = [ctx.Process(target=_core_worker, args=(stop, counter, kind, ready, go),
                         daemon=True) for _ in range(cores)]
    for p in procs:
        p.start()
    guard = time.perf_counter()
    while ready.value < cores and time.perf_counter() - guard < 120:
        if stop_event is not None and stop_event.is_set():
            break
        time.sleep(0.05)
    t0 = time.perf_counter()
    go.set()
    try:
        while time.perf_counter() - t0 < seconds:
            if stop_event is not None and stop_event.is_set():
                break
            if progress is not None:
                progress(time.perf_counter() - t0)
            time.sleep(0.2)
        elapsed = time.perf_counter() - t0
    finally:
        stop.set()
        for p in procs:
            p.join(timeout=4.0)
            if p.is_alive():
                p.terminate()
    return float(counter.value) / max(elapsed, 1e-9)


class CpuBenchmark(Benchmark):
    key = "cpu"
    name = "CPU 综合基准"

    def run(self, progress_cb=None, stop_event=None) -> BenchmarkResult:
        cb = progress_cb or (lambda p, m="": None)
        started = time.perf_counter()
        result = BenchmarkResult(key=self.key, name=self.name)
        try:
            seconds = float(config().get("cpu_phase_seconds", DEFAULT_PHASE_SECONDS)
                            or DEFAULT_PHASE_SECONDS)
            cores = max(1, mp.cpu_count() or 1)
            single: Dict[str, float] = {}
            refs = {"int": _INT_REF, "float": _FLOAT_REF,
                    "zip": _ZIP_REF, "sha": _SHA_REF}
            labels = {"int": "单核整数", "float": "单核浮点",
                      "zip": "单核压缩", "sha": "单核 SHA256"}

            for i, kind in enumerate(("int", "float", "zip", "sha")):
                base = 4 + i * 11
                cb(base, f"{labels[kind]}：窗口 {seconds:.0f}s…")
                done = {"t": 0.0}

                def prog(t, _b=base):
                    cb(_b + int(9 * min(1.0, t / max(seconds, 1e-9))), "")

                single[kind] = _run_window(kind, seconds, stop_event, prog)

            per_sec = [min(single[k] / refs[k], 3.0) * 1000 for k in refs]
            single_score = sum(per_sec) / len(per_sec)

            cb(50, f"全核并行窗口 {seconds:.0f}s（{cores} 进程）…")
            agg_single = single["int"]
            agg_multi = _run_all_cores(
                "int", seconds, cores, stop_event,
                lambda t: cb(50 + int(38 * min(1.0, t / max(seconds, 1e-9))),
                             f"全核满载 · {t:.0f}/{seconds:.0f}s"),
            )
            speedup = agg_multi / agg_single if agg_single > 0 else 1.0
            efficiency = speedup / cores * 100.0
            parallel_score = min(speedup / cores, 1.5) * 1000

            result.score = round(0.6 * single_score + 0.4 * parallel_score, 1)
            result.details = {
                "单核整数": f"{single['int'] / 1e6:.1f} Mops/s",
                "单核浮点": f"{single['float'] / 1e6:.1f} Mops/s",
                "单核压缩": f"{single['zip']:.0f} MB/s",
                "单核 SHA256": f"{single['sha']:.0f} MB/s",
                "全核整数": f"{agg_multi / 1e6:.1f} Mops/s",
                "逻辑核心": cores,
                "多核加速比": f"{speedup:.2f}x",
                "并行效率": f"{efficiency:.1f}%",
                "每阶段窗口": f"{seconds:.0f}s（稳态计时）",
                "单核评分": f"{single_score:.0f}",
                "并行评分": f"{parallel_score:.0f}",
            }
        except Exception as exc:  # pragma: no cover
            log.exception("CPU 基准失败")
            result.error = str(exc)
        result.duration = time.perf_counter() - started
        cb(100, "完成")
        return result
