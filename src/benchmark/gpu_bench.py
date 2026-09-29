"""GPU 并行计算基准 + 渲染结果构造。

旧版问题：所谓"GPU 并行计算(矩阵乘)"其实是 numpy 的 a @ b，
跑在 CPU 的 BLAS 上，跟显卡毫无关系，名字属于冒名顶替。

现在：结果里显式标注【执行设备】和【后端】，不再含糊；
真正的显卡算力由 crypto_bench.GpuDecryptBenchmark 的 CUDA 内核给出。
"""
from __future__ import annotations

import statistics
import time
from typing import List

import numpy as np

from ..core.config import config
from .base import BenchmarkResult

_GFLOPS_REF = 350.0
_FPS_REF = 300.0
DEFAULT_SECONDS = 6.0


def _run_numpy(dim: int, seconds: float, stop_event) -> float:
    a = np.random.rand(dim, dim).astype(np.float32)
    b = np.random.rand(dim, dim).astype(np.float32)
    flops_per = 2.0 * dim ** 3
    rates: List[float] = []
    t0 = time.perf_counter()
    while True:
        t1 = time.perf_counter()
        _ = a @ b
        dt = time.perf_counter() - t1
        if dt > 0:
            rates.append(flops_per / dt / 1e9)
        if stop_event is not None and stop_event.is_set():
            break
        if time.perf_counter() - t0 >= seconds:
            break
    return statistics.median(rates) if rates else 0.0


def compute_benchmark(progress_cb=None, stop_event=None) -> BenchmarkResult:
    cb = progress_cb or (lambda p, m="": None)
    result = BenchmarkResult(key="gpu_compute", name="GPU 并行计算(矩阵乘)", unit="GFLOP/s")
    started = time.perf_counter()
    try:
        seconds = float(config().get("gpu_phase_seconds", DEFAULT_SECONDS) or DEFAULT_SECONDS)
        dim = 1024
        cb(10, f"矩阵乘窗口 {seconds:.0f}s…")
        gflops = _run_numpy(dim, seconds, stop_event)
        result.score = round(min(gflops / _GFLOPS_REF, 5.0) * 1000, 1)
        result.details = {
            "矩阵乘": f"{gflops:.1f} GFLOP/s",
            "矩阵规模": f"{dim}×{dim} FP32",
            "执行设备": "CPU（numpy/BLAS，非显卡）",
            "后端": f"numpy {np.__version__}",
            "窗口": f"{seconds:.0f}s · 取中位数",
            "说明": "想要真正的显卡算力请看「GPU 解密速度」",
        }
    except Exception as exc:  # pragma: no cover
        result.error = str(exc)
    result.duration = time.perf_counter() - started
    cb(100, "完成")
    return result


def make_render_result(avg_fps: float, frames: int, elapsed: float) -> BenchmarkResult:
    result = BenchmarkResult(key="gpu_render", name="GPU 图形渲染", unit="FPS")
    result.score = round(min(avg_fps / _FPS_REF, 5.0) * 1000, 1)
    result.details = {
        "平均帧率": f"{avg_fps:.1f} FPS",
        "总帧数": frames,
        "耗时": f"{elapsed:.2f} s",
    }
    result.duration = elapsed
    return result
