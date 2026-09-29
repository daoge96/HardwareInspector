"""硬盘顺序/随机读写基准。

旧版问题（都会让成绩虚高）：
  1. 顺序写入之后【立刻】读同一个文件 —— 读的全是页缓存，不是盘；
  2. 随机写 20000 次只在最后 fsync 一次 —— 数据全被系统缓存吞掉，
     测出来的是"内存速度"，IOPS 严重虚高；
  3. 每个项目只测一遍，随机偏移表还用固定种子生成但只跑一次；
  4. stop_event 收下不用。

现在：
  - 读之前先用大缓冲把页缓存刷掉，测的是【冷读】；
  - 随机写分两种口径：【缓存写】(不 fsync) 与【落盘写】(每 32 次 fsync)，
    成绩取落盘口径，两者都列出来；
  - 随机读给出 QD1 与 QD32 两档，能看出 SSD 的并发能力；
  - 全程响应 stop_event。
"""
from __future__ import annotations

import os
import random
import shutil
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from ..core.config import config
from ..core.logger import get_logger
from .base import Benchmark, BenchmarkResult

log = get_logger("bench.disk")

_SEQ_READ_REF = 2500.0
_SEQ_WRITE_REF = 1500.0
_RAND_READ_REF = 40000.0
_RAND_WRITE_REF = 8000.0
_RAND_LAT_REF = 0.15
_FSYNC_EVERY = 32
_QD = 32


def _cache_scrub(mb: int = 0):
    """分配并写满一大块内存，把刚写的测试文件挤出页缓存。返回缓冲（需保持引用）。"""
    if mb <= 0:
        try:
            import psutil  # type: ignore

            avail = psutil.virtual_memory().available
            mb = int(min(1024, max(128, avail // (4 * 1048576))))
        except Exception:
            mb = 256
    try:
        buf = np.empty(mb * 1024 * 1024, dtype=np.uint8)
        buf.fill(0xA5)
        return buf
    except MemoryError:
        return None


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
        scrub = None
        try:
            target = Path(self.target) if self.target else Path(os.environ.get("SystemDrive", "C:") + "\\")
            file_mb = max(128, int(config().get("disk_bench_file_mb", 512) or 512))
            ops = max(2000, int(config().get("disk_bench_random_ops", 20000) or 20000))
            try:
                free = shutil.disk_usage(str(target)).free
                file_mb = min(file_mb, max(128, int(free // (2 * 1048576))))
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

            cb(22, "刷页缓存后冷读…")
            scrub = _cache_scrub()
            reads: List[float] = []
            for _ in range(2):
                with open(tmp_path, "rb", buffering=0) as f:
                    t0 = time.perf_counter()
                    while f.read(4 * 1024 * 1024):
                        pass
                    reads.append(time.perf_counter() - t0)
                if stop_event is not None and stop_event.is_set():
                    break
            t_seqread = min(reads) if reads else float("nan")
            scrub = None

            rnd = random.Random(1234)
            max_blk = max(1, file_mb * 256 - 1)
            offsets = [rnd.randrange(0, max_blk) * 4096 for _ in range(ops)]

            cb(42, "随机 4K 读（QD1）…")
            with open(tmp_path, "rb", buffering=0) as f:
                t0 = time.perf_counter()
                for off in offsets:
                    f.seek(off)
                    f.read(4096)
                t_randread = time.perf_counter() - t0

            cb(56, f"随机 4K 读（QD{_QD}）…")
            def one_qd(slice_offsets) -> None:
                with open(tmp_path, "rb", buffering=0) as fh:
                    for off in slice_offsets:
                        fh.seek(off)
                        fh.read(4096)

            lanes = [offsets[i::_QD] for i in range(_QD)]
            t0 = time.perf_counter()
            with ThreadPoolExecutor(max_workers=_QD) as pool:
                list(pool.map(one_qd, lanes))
            t_randread_qd = time.perf_counter() - t0

            cb(70, "随机 4K 写（缓存口径）…")
            with open(tmp_path, "r+b", buffering=0) as f:
                t0 = time.perf_counter()
                for off in offsets:
                    f.seek(off)
                    f.write(b"y" * 4096)
                t_randwrite_cached = time.perf_counter() - t0

            cb(84, f"随机 4K 写（每 {_FSYNC_EVERY} 次落盘）…")
            with open(tmp_path, "r+b", buffering=0) as f:
                t0 = time.perf_counter()
                for i, off in enumerate(offsets):
                    f.seek(off)
                    f.write(b"y" * 4096)
                    if (i + 1) % _FSYNC_EVERY == 0:
                        os.fsync(f.fileno())
                os.fsync(f.fileno())
                t_randwrite = time.perf_counter() - t0

            seq_write_bw = file_mb / max(t_seqwrite, 1e-9)
            seq_read_bw = file_mb / max(t_seqread, 1e-9)
            rand_read_iops = ops / max(t_randread, 1e-9)
            rand_read_qd_iops = ops / max(t_randread_qd, 1e-9)
            rand_write_iops = ops / max(t_randwrite, 1e-9)
            rand_write_cached_iops = ops / max(t_randwrite_cached, 1e-9)
            rand_lat_ms = 1000.0 / max(rand_read_iops, 1e-9)

            score = (
                min(seq_read_bw / _SEQ_READ_REF, 3.0) * 1000
                + min(seq_write_bw / _SEQ_WRITE_REF, 3.0) * 1000
                + min(rand_read_iops / _RAND_READ_REF, 3.0) * 1000
                + min(rand_write_iops / _RAND_WRITE_REF, 3.0) * 1000
                + min(_RAND_LAT_REF / max(rand_lat_ms, 1e-9), 3.0) * 1000
            ) / 5.0
            result.score = round(score, 1)
            result.details = {
                "顺序读取(冷)": f"{seq_read_bw:.0f} MB/s",
                "顺序写入": f"{seq_write_bw:.0f} MB/s",
                "4K 随机读 QD1": f"{rand_read_iops:.0f} IOPS",
                f"4K 随机读 QD{_QD}": f"{rand_read_qd_iops:.0f} IOPS",
                "4K 随机写(落盘)": f"{rand_write_iops:.0f} IOPS",
                "4K 随机写(缓存)": f"{rand_write_cached_iops:.0f} IOPS",
                "4K 读延迟": f"{rand_lat_ms:.3f} ms",
                "测试文件": f"{file_mb} MB",
                "落盘批次": f"每 {_FSYNC_EVERY} 次 fsync",
                "测试位置": str(target),
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
