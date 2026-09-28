"""硬盘顺序/随机读写基准测试。"""
from __future__ import annotations

import os
import random
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

from ..core.config import config
from ..core.logger import get_logger
from .base import Benchmark, BenchmarkResult

log = get_logger("bench.disk")

_SEQ_READ_REF = 2500.0
_SEQ_WRITE_REF = 1500.0
_RAND_READ_REF = 40000.0
_RAND_WRITE_REF = 20000.0
_RAND_LAT_REF = 0.15


class DiskBenchmark(Benchmark):
    key = "disk"
    name = "硬盘基准测试"

    def __init__(self, target: Optional[str] = None) -> None:
        self.target = target

    def run(self, progress_cb=None, stop_event=None) -> BenchmarkResult:
        cb = progress_cb or (lambda p, m="": None)
        started = time.perf_counter()
        result = BenchmarkResult(key=self.key, name=self.name)
        tmp_path = None
        try:
            target = Path(self.target) if self.target else Path(os.environ.get("SystemDrive", "C:") + "\\")
            file_mb = max(64, int(config().get("disk_bench_file_mb", 512) or 512))
            ops = max(1000, int(config().get("disk_bench_random_ops", 20000) or 20000))
            try:
                free = shutil.disk_usage(str(target)).free
                file_mb = min(file_mb, max(64, int(free // (2 * 1048576))))
            except Exception:
                pass
            ops = min(ops, 200000)
            fd, tmp_name = tempfile.mkstemp(prefix="hwbench_", suffix=".tmp", dir=str(target))
            os.close(fd)
            tmp_path = Path(tmp_name)
            chunk = b"x" * (1024 * 1024)
            cb(5, "顺序写入…")
            with open(tmp_path, "wb", buffering=0) as f:
                t0 = time.perf_counter()
                for _ in range(file_mb):
                    f.write(chunk)
                os.fsync(f.fileno())
                t_seqwrite = time.perf_counter() - t0
            cb(35, "顺序读取…")
            with open(tmp_path, "rb", buffering=0) as f:
                t0 = time.perf_counter()
                while f.read(1024 * 1024):
                    pass
                t_seqread = time.perf_counter() - t0
            rnd = random.Random(1234)
            max_off = max(1, file_mb * 1024 - 4)
            offsets = [rnd.randrange(0, max_off) * 1024 for _ in range(ops)]
            cb(60, "随机 4K 读取…")
            with open(tmp_path, "rb", buffering=0) as f:
                t0 = time.perf_counter()
                for off in offsets:
                    f.seek(off)
                    f.read(4096)
                t_randread = time.perf_counter() - t0
            cb(80, "随机 4K 写入…")
            with open(tmp_path, "r+b", buffering=0) as f:
                t0 = time.perf_counter()
                for off in offsets:
                    f.seek(off)
                    f.write(b"y" * 4096)
                os.fsync(f.fileno())
                t_randwrite = time.perf_counter() - t0
            seq_write_bw = file_mb / max(t_seqwrite, 1e-6)
            seq_read_bw = file_mb / max(t_seqread, 1e-6)
            rand_read_iops = ops / max(t_randread, 1e-6)
            rand_write_iops = ops / max(t_randwrite, 1e-6)
            rand_lat_ms = 1000.0 / max(rand_read_iops, 1e-6)
            score = (
                min(seq_read_bw / _SEQ_READ_REF, 3.0) * 1000
                + min(seq_write_bw / _SEQ_WRITE_REF, 3.0) * 1000
                + min(rand_read_iops / _RAND_READ_REF, 3.0) * 1000
                + min(rand_write_iops / _RAND_WRITE_REF, 3.0) * 1000
                + min(_RAND_LAT_REF / max(rand_lat_ms, 1e-6), 3.0) * 1000
            ) / 5.0
            result.score = round(score, 1)
            result.details = {
                "顺序读取": f"{seq_read_bw:.0f} MB/s",
                "顺序写入": f"{seq_write_bw:.0f} MB/s",
                "4K 随机读": f"{rand_read_iops:.0f} IOPS",
                "4K 随机写": f"{rand_write_iops:.0f} IOPS",
                "4K 读延迟": f"{rand_lat_ms:.3f} ms",
                "测试文件": f"{file_mb} MB",
            }
        except Exception as exc:  # pragma: no cover
            log.exception("硬盘基准失败")
            result.error = str(exc)
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
        result.duration = time.perf_counter() - started
        cb(100, "完成")
        return result
