"""CPU 基准测试（CPU 密集型在子进程执行）。"""
from __future__ import annotations

import hashlib
import math
import multiprocessing as mp
import time
import zlib

from ..core.config import config
from ..core.logger import get_logger
from .base import Benchmark, BenchmarkResult

log = get_logger("bench.cpu")

_INT_REF = 0.06
_FLOAT_REF = 0.20
_ZIP_REF = 0.30
_CRYPT_REF = 0.40


def _int_work(iters: int) -> float:
    x = 12345
    t0 = time.perf_counter()
    for _ in range(iters):
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF
    return time.perf_counter() - t0


def _float_work(iters: int) -> float:
    x = 1.0
    acc = 0.0
    t0 = time.perf_counter()
    for _ in range(iters):
        x = math.sqrt(abs(math.sin(x) + 2.0))
        acc += x
    return time.perf_counter() - t0


def _zip_work(mb: int) -> float:
    size = mb * 1024 * 1024
    pattern = b"HardwareInspectorBenchmarkPattern-0123456789"
    data = (pattern * (size // len(pattern) + 1))[:size]
    t0 = time.perf_counter()
    zlib.compress(data, 6)
    return time.perf_counter() - t0


def _crypt_work(mb: int) -> float:
    block = b"x" * (1024 * 1024)
    h = hashlib.sha256()
    t0 = time.perf_counter()
    for _ in range(mb):
        h.update(block)
    h.hexdigest()
    return time.perf_counter() - t0


class CpuBenchmark(Benchmark):
    key = "cpu"
    name = "CPU 基准测试"

    def run(self, progress_cb=None, stop_event=None) -> BenchmarkResult:
        cb = progress_cb or (lambda p, m="": None)
        started = time.perf_counter()
        result = BenchmarkResult(key=self.key, name=self.name)
        try:
            scale = float(config().get("cpu_bench_scale", 1.0) or 1.0)
        except Exception:
            scale = 1.0
        threads = max(1, mp.cpu_count() or 1)
        iters = int(30_000_000 * scale)
        fiter = int(6_000_000 * scale)
        try:
            cb(5, "单核整数运算…")
            t_int = _int_work(iters)
            cb(25, "单核浮点运算…")
            t_float = _float_work(fiter)
            cb(45, "内存压缩…")
            t_zip = _zip_work(64)
            cb(65, "SHA256 加密…")
            t_crypt = _crypt_work(64)
            cb(80, f"多核整数({threads} 进程)…")
            per = max(1, iters // threads)
            pool = mp.Pool(processes=threads)
            try:
                t0 = time.perf_counter()
                pool.map(_int_work, [per] * threads)
                t_multi = time.perf_counter() - t0
            finally:
                pool.close()
                pool.join()
            cb(97, "汇总评分…")
            s_int = _INT_REF / max(t_int, 1e-6) * 1000
            s_float = _FLOAT_REF / max(t_float, 1e-6) * 1000
            s_zip = _ZIP_REF / max(t_zip, 1e-6) * 1000
            s_crypt = _CRYPT_REF / max(t_crypt, 1e-6) * 1000
            single_rate = iters / max(t_int, 1e-6)
            multi_rate = (per * threads) / max(t_multi, 1e-6)
            speedup = multi_rate / single_rate if single_rate else 1.0
            base_score = (s_int + s_float + s_zip + s_crypt) / 4.0
            factor = max(0.5, min(speedup, float(threads))) ** 0.5
            result.score = round(base_score * factor, 1)
            result.details = {
                "单核整数": f"{iters / max(t_int, 1e-6) / 1e6:.1f} Mops/s",
                "单核浮点": f"{fiter / max(t_float, 1e-6) / 1e6:.1f} Mops/s",
                "压缩吞吐": f"{64 / max(t_zip, 1e-6):.0f} MB/s",
                "SHA256 吞吐": f"{64 / max(t_crypt, 1e-6):.0f} MB/s",
                "多核加速比": f"{speedup:.2f}x",
                "逻辑核心": threads,
            }
        except Exception as exc:  # pragma: no cover
            log.exception("CPU 基准失败")
            result.error = str(exc)
        result.duration = time.perf_counter() - started
        cb(100, "完成")
        return result
