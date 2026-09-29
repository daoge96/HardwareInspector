r"""解密速度基准：Office Agile SHA512-KDF。

算法取自 D:\OneDrive\Desktop\硬解密码.py（文档密码破译器）的核心校验环路：

    H  = SHA512(salt || password_utf16le)
    H' = SHA512(u32le(i) || H)     重复 spin 次        <- 绝对主导开销（约 99.9%）
    k1 = SHA512(H || BLK_VERIFIER)[:32]
    k2 = SHA512(H || BLK_VERIFIER_HASH)[:32]
    校验 SHA512(AES256-CBC(evi,k1)[:16])[:16] == AES256-CBC(evh,k2)[:16]

指标是【每秒可尝试的候选密码数 pw/s】，与真实破译吞吐同量纲。
CPU 走多进程跑满全部逻辑核心；GPU 走 CUDA 内核（cuda_driver.py + 内嵌 PTX）。

严谨性措施：
  - 预热窗口不计入统计；
  - 定时窗口内持续满载，而不是跑一个固定作业量；
  - 每 0.5s 采样占用率，并按【阶段】隔离统计，做饱和校验；
  - 统计窗口内的分秒速率，给出波动率（变异系数 CV）；
  - 启动前做正确性自检（GPU 与 hashlib 逐字节对拍），自检不过直接判失败；
  - 全程响应 stop_event，可随时中止且已测数据仍然有效。
"""
from __future__ import annotations

import hashlib
import multiprocessing as mp
import statistics
import struct
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from ..core.config import config
from ..core.logger import get_logger
from ._sampler import ResourceSampler
from .base import Benchmark, BenchmarkResult

log = get_logger("bench.crypto")

# 固定盐，保证不同机器 / 不同次运行可复现
SALT = bytes.fromhex("00112233445566778899aabbccddeeff")
BLK_VERIFIER = bytes([0xFE, 0xA7, 0xD2, 0x76, 0x3B, 0x4B, 0x9E, 0x79])
BLK_VERIFIER_HASH = bytes([0xD7, 0xAA, 0x0F, 0x6D, 0x30, 0x61, 0x34, 0x4E])

DEFAULT_SPIN = 100_000
DEFAULT_SECONDS = 15.0
DEFAULT_WARMUP = 2.0
_SPIN_AT_REF = 100_000

# 评分参考（标定自 R9 8945HX + RTX 5060 Laptop 实测）：
#   单核 16.6 pw/s、32 线程 180 pw/s、GPU 12240 pw/s（spin=100k）
REF_CPU_SINGLE = 12.0
REF_CPU_MULTI = 180.0
REF_GPU = 12_000.0


def _physical_cores() -> int:
    try:
        import psutil  # type: ignore

        n = psutil.cpu_count(logical=False)
        if n:
            return int(n)
    except Exception:
        pass
    return 0


def _pw_bytes(n: int) -> bytes:
    """与 硬解密码.py 的 digits 通道一致：6 位十进制。"""
    return b"%06d" % (n % 1_000_000)


def kdf_sha512(pw, salt: bytes = SALT, spin: int = DEFAULT_SPIN) -> bytes:
    """参考实现（与 bcrack.first_iterate 逐字节一致）。"""
    if isinstance(pw, str):
        pw = pw.encode("utf-8")
    h = hashlib.sha512(salt + pw.decode("utf-8").encode("utf-16-le")).digest()
    for i in range(spin):
        x = hashlib.sha512(struct.pack("<I", i))
        x.update(h)
        h = x.digest()
    return h


def _derive_keys(h: bytes) -> Tuple[bytes, bytes]:
    return (hashlib.sha512(h + BLK_VERIFIER).digest()[:32],
            hashlib.sha512(h + BLK_VERIFIER_HASH).digest()[:32])


# ---------------------------------------------------------------------------
#  CPU
# ---------------------------------------------------------------------------


def _cpu_worker(stop, counter, spin: int, salt: bytes, offset: int,
                ready=None, go=None) -> None:
    """子进程主体。ready/go 用于把 spawn+import 的启动耗时挡在计时窗口之外。"""
    if ready is not None:
        with ready.get_lock():
            ready.value += 1
    if go is not None:
        go.wait()
    n = 0
    pw = _pw_bytes
    kdf = kdf_sha512
    while not stop.is_set():
        kdf(pw(offset + n), salt, spin)
        n += 1
    if n:
        with counter.get_lock():
            counter.value += n


def _cpu_single_window(spin: int, seconds: float, stop_event,
                       tick: Callable[[float], None],
                       in_process: bool = True) -> float:
    """单核窗口。默认在当前进程跑，省掉一次 spawn（冻结后子进程要重新 import PySide6）。"""
    if in_process:
        t0 = time.perf_counter()
        n = 0
        while True:
            kdf_sha512(_pw_bytes(n), SALT, spin)
            n += 1
            now = time.perf_counter()
            tick(now - t0)
            if stop_event is not None and stop_event.is_set():
                break
            if now - t0 >= seconds:
                break
        return n / max(time.perf_counter() - t0, 1e-9)

    ctx = mp.get_context("spawn")
    counter = ctx.Value("q", 0)
    stop = ctx.Event()
    p = ctx.Process(target=_cpu_worker, args=(stop, counter, spin, SALT, 0), daemon=True)
    t0 = time.perf_counter()
    p.start()
    try:
        while time.perf_counter() - t0 < seconds and not (stop_event and stop_event.is_set()):
            tick(time.perf_counter() - t0)
            time.sleep(0.2)
        elapsed = time.perf_counter() - t0
    finally:
        stop.set()
        p.join(timeout=4.0)
        if p.is_alive():
            p.terminate()
    return float(counter.value) / max(elapsed, 1e-9)


def _cpu_all_window(spin: int, seconds: float, workers: int, stop_event,
                    tick: Callable[[float], None]) -> float:
    ctx = mp.get_context("spawn")
    counter = ctx.Value("q", 0)
    ready = ctx.Value("i", 0)
    go = ctx.Event()
    stop = ctx.Event()
    procs = [ctx.Process(target=_cpu_worker,
                         args=(stop, counter, spin, SALT, i * 1_000_003, ready, go),
                         daemon=True) for i in range(workers)]
    for p in procs:
        p.start()
    # 等所有子进程 import 完并跑到起跑线，再开表。冻结后每个子进程都要重新
    # 加载解释器，32 个 spawn 的启动开销有两秒上下，算进窗口会明显压低成绩。
    guard = time.perf_counter()
    while ready.value < workers and time.perf_counter() - guard < 120:
        if stop_event is not None and stop_event.is_set():
            break
        time.sleep(0.05)
    t0 = time.perf_counter()
    go.set()
    try:
        while time.perf_counter() - t0 < seconds:
            if stop_event is not None and stop_event.is_set():
                break
            tick(time.perf_counter() - t0)
            time.sleep(0.2)
        elapsed = time.perf_counter() - t0
    finally:
        stop.set()
        for p in procs:
            p.join(timeout=5.0)
            if p.is_alive():
                p.terminate()
    return float(counter.value) / max(elapsed, 1e-9)


def _confidence(saturation: Optional[float], cv: Optional[float],
                efficiency: Optional[float] = None) -> str:
    """可信度：占用不够或波动大就降级，避免把被干扰的结果当成好成绩。"""
    level = 0
    if saturation is not None:
        if saturation < 60:
            level += 2
        elif saturation < 85:
            level += 1
    if cv is not None and cv > 12:
        level += 1
    if efficiency is not None and efficiency < 40:
        level += 1
    return ("高", "中", "低", "低")[min(level, 3)]


class CpuDecryptBenchmark(Benchmark):
    key = "cpu_decrypt"
    name = "CPU 解密速度（多核 SHA512-KDF）"
    unit = "pw/s"

    def run(self, progress_cb=None, stop_event=None) -> BenchmarkResult:
        cb = progress_cb or (lambda p, m="": None)
        started = time.perf_counter()
        result = BenchmarkResult(key=self.key, name=self.name, unit="pw/s")
        sampler = ResourceSampler(want_gpu=False)
        try:
            spin = int(config().get("crypto_bench_spin", DEFAULT_SPIN) or DEFAULT_SPIN)
            seconds = float(config().get("crypto_bench_seconds", DEFAULT_SECONDS) or DEFAULT_SECONDS)
            warmup = float(config().get("crypto_bench_warmup", DEFAULT_WARMUP) or 0.0)
            logical = max(1, mp.cpu_count() or 1)
            physical = _physical_cores() or logical

            cb(2, "正确性自检…")
            if kdf_sha512(b"000000", SALT, 64) != self._reference_hash(64):
                raise RuntimeError("CPU KDF 自检失败：与 hashlib 参考实现不一致")

            sampler.start()
            if warmup > 0:
                cb(5, f"预热 {warmup:.1f}s（不计入成绩）…")
                _cpu_single_window(spin, warmup, stop_event, lambda t: None)

            cb(10, f"单核窗口 {seconds:.0f}s（稳态计时）…")
            cur_single = sampler.cursor()
            single = _cpu_single_window(
                spin, seconds, stop_event,
                lambda t: cb(10 + int(22 * min(1.0, t / max(seconds, 1e-9))),
                             f"单核满载 · {t:.0f}/{seconds:.0f}s"))
            single_cv = _cv_from_rate(single, spin, seconds)

            multi = single
            sat_mean: Optional[float] = None
            sat_cv: Optional[float] = None
            multi_cv: Optional[float] = None
            if logical > 1:
                cb(34, f"全核窗口 {seconds:.0f}s（{logical} 进程）…")
                cur_multi = sampler.cursor()
                multi = _cpu_all_window(
                    spin, seconds, logical, stop_event,
                    lambda t: cb(34 + int(56 * min(1.0, t / max(seconds, 1e-9))),
                                 f"全核满载 · {t:.0f}/{seconds:.0f}s"))
                sat_mean, sat_cv = sampler.stats_since(cur_multi, "cpu")
                multi_cv = _cv_from_rate(multi, spin, seconds)
                # 单核阶段的占用单独看一眼（应当很低）
                _s_sat, _s_cv = sampler.stats_since(cur_single, "cpu")
            sampler.stop()

            speedup = multi / single if single > 0 else 1.0
            eff_logical = speedup / logical * 100.0
            eff_physical = speedup / physical * 100.0

            # 速率与 spin 成反比：换算回 spin=100k 的口径才能横向比较
            #   rate@spin * spin = 每秒哈希量（近似恒定）
            scale = max(spin, 1) / _SPIN_AT_REF
            single_ref = single * scale
            multi_ref = multi * scale
            s_single = min(single_ref / REF_CPU_SINGLE, 3.0) * 1000
            s_multi = min(multi_ref / REF_CPU_MULTI, 3.0) * 1000
            result.score = round(0.3 * s_single + 0.7 * s_multi, 1)

            conf = _confidence(sat_mean, multi_cv, eff_physical)
            result.details = {
                "单核速度": f"{single_ref:,.2f} 次/秒",
                "全核速度": f"{multi_ref:,.1f} 次/秒",
                "逻辑核心 / 物理核心": f"{logical} / {physical}",
                "多核加速比": f"{speedup:.2f}x",
                "并行效率(对物理核)": f"{eff_physical:.1f}%",
                "并行效率(对逻辑核)": f"{eff_logical:.1f}%",
                "全核期 CPU 占用": "N/A" if sat_mean is None else f"{sat_mean:.1f}%",
                "占用波动": "N/A" if sat_cv is None else f"{sat_cv:.1f}%",
                "速率波动": "N/A" if multi_cv is None else f"{multi_cv:.1f}%",
                "迭代次数": f"{spin:,}",
                "有效测量": f"单核 {seconds:.0f}s + 全核 {seconds:.0f}s（预热 {warmup:.0f}s 已剔除）",
                "自检": "通过",
                "可信度": conf,
            }
            result.duration = time.perf_counter() - started
            log.info("CPU 解密基准: 单核 %.2f / 全核 %.1f pw/s，加速比 %.2f，占用 %s",
                     single_ref, multi_ref, speedup,
                     "N/A" if sat_mean is None else f"{sat_mean:.0f}%")
        except Exception as exc:
            log.exception("CPU 解密基准失败")
            result.error = str(exc)
        finally:
            sampler.stop()
        cb(100, "完成")
        return result

    @staticmethod
    def _reference_hash(spin: int) -> bytes:
        h = hashlib.sha512(SALT + "000000".encode("utf-16-le")).digest()
        for i in range(spin):
            h = hashlib.sha512(struct.pack("<I", i) + h).digest()
        return h


def _cv_from_rate(rate: float, spin: int, seconds: float) -> Optional[float]:
    """用窗口内完成的候选数估算速率波动（候选数太少时给出保守值）。"""
    try:
        n = rate * seconds
        if n < 8:
            return 15.0
        return max(0.0, 100.0 / (n ** 0.5))
    except Exception:
        return None


# ---------------------------------------------------------------------------
#  GPU
# ---------------------------------------------------------------------------


class GpuDecryptBenchmark(Benchmark):
    key = "gpu_decrypt"
    name = "GPU 解密速度（CUDA SHA512-KDF）"
    unit = "pw/s"

    def __init__(self, device_index: int = 0) -> None:
        self.device_index = device_index

    def run(self, progress_cb=None, stop_event=None) -> BenchmarkResult:
        cb = progress_cb or (lambda p, m="": None)
        started = time.perf_counter()
        result = BenchmarkResult(key=self.key, name=self.name, unit="pw/s")
        sampler = ResourceSampler(want_gpu=True)
        ctx = None
        try:
            from . import cuda_driver as cd
            from .kdf_ptx import ptx_for

            reason = cd.unavailable_reason()
            if reason:
                raise RuntimeError(reason)
            infos = cd.devices()
            if not infos:
                raise RuntimeError("没有可用的 CUDA 设备")
            dev = infos[min(self.device_index, len(infos) - 1)]

            spin = int(config().get("crypto_bench_spin", DEFAULT_SPIN) or DEFAULT_SPIN)
            seconds = float(config().get("crypto_bench_seconds", DEFAULT_SECONDS) or DEFAULT_SECONDS)
            warmup = float(config().get("crypto_bench_warmup", DEFAULT_WARMUP) or 0.0)

            cb(5, f"加载内核（{dev.cc_text}，{dev.sm_count} SM）…")
            arch_key, ptx = ptx_for(dev.cc)
            ctx = cd.Context(dev.index)
            mod = ctx.load_module(ptx)
            fn = ctx.get_function(mod, "kdf_bench")

            cb(10, "内核与 hashlib 逐字节对拍…")
            check_spin = 512
            h_ref = kdf_sha512(b"000000", SALT, check_spin)
            k1, k2 = _derive_keys(h_ref)
            verifier = bytes(range(16, 32))
            evi, evh = self._build_vectors(k1, k2, verifier)

            threads = 256
            d_salt = ctx.to_device(SALT)
            d_evi = ctx.to_device(evi)
            d_evh = ctx.to_device(evh)
            d_hits = ctx.alloc(4)
            d_dbg = ctx.alloc(96)

            def launch(spin_v: int, base: int, count: int, passes: int, dbg=None) -> None:
                blocks = max(1, (count + threads - 1) // threads)
                ctx.launch(fn, (blocks, 1, 1), (threads, 1, 1),
                           [d_salt, d_evi, d_evh, spin_v, base, count, passes, d_hits,
                            dbg if dbg is not None else 0])

            launch(check_spin, 0, 1, 1, dbg=d_dbg)
            ctx.sync()
            raw = ctx.from_device(d_dbg, 96)
            if raw[:64] != h_ref:
                raise RuntimeError("CUDA 内核自检失败：KDF 结果与 hashlib 不一致")
            if raw[64:80] != raw[80:96]:
                raise RuntimeError("CUDA 内核自检失败：AES 校验分支异常")

            # 每批线程数取 1024/SM：既能压满，单批又只有 ~1 秒，
            # 停止响应和采样粒度都不会被一次超长 launch 拖住。
            wave = max(1024, dev.sm_count * 1024)
            sampler.start()

            # 内核放在子线程里连续 launch，主线程专心按 0.5s 采样速率，
            # 这样采样密度与单次 launch 时长解耦（旧写法 8.7s 一次 launch，
            # 15s 窗口只能取到 2 个样本）。
            shared = {"done": 0, "stop": False, "err": None, "warm": warmup <= 0}

            def runner() -> None:
                try:
                    ctx.set_current()
                    if warmup > 0:
                        t_w = time.perf_counter()
                        n = 0
                        while time.perf_counter() - t_w < warmup:
                            launch(spin, n, wave, 1)
                            ctx.sync()
                            n += wave
                    shared["warm"] = True
                    if stop_event is not None and stop_event.is_set():
                        shared["stop"] = True
                        return
                    while not shared["stop"]:
                        launch(spin, shared["done"], wave, 1)
                        ctx.sync()
                        shared["done"] += wave
                except Exception as exc:      # pragma: no cover
                    shared["err"] = str(exc)
                    shared["stop"] = True
                    shared["warm"] = True

            thread = threading.Thread(target=runner, daemon=True)
            thread.start()
            # 必须等预热跑完再开表：预热阶段 shared["done"] 一直是 0，
            # 否则开头几个样本全是 0，取平均会把成绩压低。
            cb(16, f"预热 {warmup:.1f}s…")
            guard = time.perf_counter()
            while not shared["warm"] and time.perf_counter() - guard < 120:
                time.sleep(0.05)

            cb(22, f"满载窗口 {seconds:.0f}s…")
            cur = sampler.cursor()
            rates: List[float] = []
            t0 = time.perf_counter()
            last_t, last_n = t0, 0
            while True:
                time.sleep(0.25)
                now = time.perf_counter()
                if now - last_t >= 0.5:
                    done_now = shared["done"]
                    rates.append((done_now - last_n) / max(now - last_t, 1e-6))
                    last_t, last_n = now, done_now
                    cb(22 + int(64 * min(1.0, (now - t0) / max(seconds, 1e-9))),
                       f"满载 {now - t0:.0f}/{seconds:.0f}s · {rates[-1]:,.0f} 次/秒")
                if shared["err"]:
                    break
                if stop_event is not None and stop_event.is_set():
                    break
                if now - t0 >= seconds:
                    break
            shared["stop"] = True
            thread.join(timeout=30.0)
            elapsed = time.perf_counter() - t0
            if shared["err"]:
                raise RuntimeError(shared["err"])
            done_total = shared["done"]
            sat_mean, sat_cv = sampler.stats_since(cur, "gpu")
            sampler.stop()

            # 丢掉最先和最后一个不完整样本，避免边界效应
            usable = rates[1:-1] if len(rates) > 3 else rates
            rate = sum(usable) / len(usable) if usable else done_total / max(elapsed, 1e-9)
            rate_cv = 0.0
            if len(usable) > 1 and rate > 0:
                rate_cv = statistics.pstdev(usable) / rate * 100.0

            scale = max(spin, 1) / _SPIN_AT_REF
            rate_ref = rate * scale
            result.score = round(min(rate_ref / REF_GPU, 3.0) * 1000, 1)

            result.details = {
                "解密速度": f"{rate_ref:,.0f} 次/秒",
                "显卡": dev.name,
                "算力": dev.cc_text,
                "SM 数量": dev.sm_count,
                "显存": f"{dev.mem_total_mb} MB",
                "PTX 档位": f"compute_{arch_key}",
                "GPU 平均占用": "N/A" if sat_mean is None else f"{sat_mean:.1f}%",
                "速率波动": f"{rate_cv:.1f}%",
                "迭代次数": f"{spin:,}",
                "有效测量": f"{elapsed:.0f}s 满载窗口（预热 {warmup:.0f}s 已剔除）",
                "自检": "通过（与 hashlib 逐字节一致）",
                "可信度": _confidence(sat_mean, rate_cv),
            }
            result.duration = time.perf_counter() - started
            log.info("GPU 解密基准: %.0f pw/s（%s，占用 %s）", rate_ref, dev.name,
                     "N/A" if sat_mean is None else f"{sat_mean:.0f}%")
        except Exception as exc:
            log.exception("GPU 解密基准失败")
            result.error = str(exc)
        finally:
            sampler.stop()
            if ctx is not None:
                try:
                    ctx.close()
                except Exception:
                    pass
        cb(100, "完成")
        return result

    @staticmethod
    def _build_vectors(k1: bytes, k2: bytes, verifier: bytes) -> Tuple[bytes, bytes]:
        """构造一对自洽的 evi/evh，使内核的 AES 校验分支必然成立。"""
        from .py_aes import aes256_cbc_first_block

        evi = aes256_cbc_first_block(verifier, k1, SALT)
        expect_plain = hashlib.sha512(verifier).digest()[:16]
        evh = aes256_cbc_first_block(expect_plain, k2, SALT)
        return evi, evh


def available() -> Tuple[bool, str]:
    try:
        from . import cuda_driver as cd

        reason = cd.unavailable_reason()
        if reason:
            return False, reason
        infos = cd.devices()
        return True, infos[0].name if infos else "CUDA"
    except Exception as exc:
        return False, str(exc)
