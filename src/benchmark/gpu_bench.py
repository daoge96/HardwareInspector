"""GPU 并行计算基准（矩阵乘）+ 渲染基准结果构造。"""
from __future__ import annotations

import time

import numpy as np

from .base import BenchmarkResult

_GFLOPS_REF = 350.0
_FPS_REF = 300.0


def compute_benchmark(progress_cb=None, stop_event=None) -> BenchmarkResult:
    cb = progress_cb or (lambda p, m="": None)
    result = BenchmarkResult(key="gpu_compute", name="GPU 并行计算(矩阵乘)", unit="GFLOP/s")
    try:
        cb(0, "准备矩阵…")
        a = np.random.rand(1024, 1024).astype(np.float32)
        b = np.random.rand(1024, 1024).astype(np.float32)
        reps = 40
        cb(20, "矩阵乘…")
        t0 = time.perf_counter()
        for _ in range(reps):
            _c = a @ b
        dt = time.perf_counter() - t0
        gflops = (2 * 1024 ** 3 * reps) / max(dt, 1e-6) / 1e9
        result.score = round(min(gflops / _GFLOPS_REF, 5.0) * 1000, 1)
        result.details = {"矩阵乘": f"{gflops:.1f} GFLOP/s", "重复次数": reps}
        result.duration = dt
    except Exception as exc:  # pragma: no cover
        result.error = str(exc)
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
