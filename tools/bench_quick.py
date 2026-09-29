# -*- coding: utf-8 -*-
"""短测：验证 KDF 对拍 + GPU/CPU 基准，全部计时。"""
import os, sys, time

def main():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.core.config import config
    from src.benchmark.crypto_bench import CpuDecryptBenchmark, GpuDecryptBenchmark, available

    config().set("crypto_bench_seconds", 2.0)
    config().set("crypto_bench_warmup", 0.3)
    config().set("crypto_bench_spin", 3000)

    print("GPU available:", available(), flush=True)
    t = time.time(); r = GpuDecryptBenchmark().run()
    print("GPU score:", r.score, "err:", r.error, "dur:", round(time.time() - t, 1), flush=True)
    for k, v in r.details.items(): print("   ", k, "=", v, flush=True)
    t = time.time(); r2 = CpuDecryptBenchmark().run()
    print("CPU score:", r2.score, "err:", r2.error, "dur:", round(time.time() - t, 1), flush=True)
    for k, v in r2.details.items(): print("   ", k, "=", v, flush=True)

if __name__ == "__main__":
    main()
