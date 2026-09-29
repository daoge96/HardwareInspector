r"""HardwareInspector 程序入口。

freeze_support() 必须放在 PySide6 之前：PyInstaller 冻结后 multiprocessing 的
spawn 子进程是靠重新执行本 exe 实现的，freeze_support() 会认出
--multiprocessing-fork 并直接跑子进程引导后 sys.exit()。放在 Qt 导入之前，
子进程就不必再把整个 PySide6 拖起来 —— 解密基准要 spawn 几十个进程，
这一个改动能省下可观的启动时间。

命令行：
    HardwareInspector.exe                 正常启动界面
    HardwareInspector.exe --selftest      跑一遍短自检（CPU/GPU 解密基准），
                                          结果写到 %APPDATA%\HardwareInspector\logs\selftest.txt
    HardwareInspector.exe --selftest --cpu-only
"""
from __future__ import annotations

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()

from PySide6.QtGui import QIcon, QSurfaceFormat  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core.config import config  # noqa: E402
from src.core.constants import APP_DISPLAY_NAME, APP_NAME, APP_VERSION  # noqa: E402
from src.core.utils import resource_path  # noqa: E402


def _configure_gl() -> None:
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(fmt)


def _selftest(argv) -> int:
    """短自检：验证 spawn 子进程链路、CUDA 自检、评分与结果结构。"""
    import platform
    import time

    cpu_only = "--cpu-only" in argv
    seconds = 2.0
    lines = []

    def say(text: str) -> None:
        lines.append(text)
        print(text, flush=True)

    say("#" * 60)
    say("HardwareInspector 自检  " + time.strftime("%Y-%m-%d %H:%M:%S"))
    say(f"Python {platform.python_version()}  frozen={getattr(sys, 'frozen', False)}")
    say(f"exe: {sys.executable}")
    say(f"cpu_count={multiprocessing.cpu_count()}")

    cfg = config()
    cfg.set("crypto_bench_seconds", seconds)
    cfg.set("crypto_bench_warmup", 0.3)
    cfg.set("crypto_bench_spin", 5000)

    from src.benchmark.crypto_bench import CpuDecryptBenchmark, GpuDecryptBenchmark, available

    ok_all = True

    say("")
    say("=== 参考实现对拍 ===")
    try:
        import hashlib
        import struct

        from src.benchmark.crypto_bench import SALT, kdf_sha512

        spin = 50
        mine = kdf_sha512(b"000000", SALT, spin)
        ref = hashlib.sha512(SALT + "000000".encode("utf-16-le")).digest()
        for i in range(spin):
            ref = hashlib.sha512(struct.pack("<I", i) + ref).digest()
        ok = mine == ref
        ok_all &= ok
        say(f"CPU KDF 与 hashlib 一致: {ok}")
    except Exception as exc:
        ok_all = False
        say(f"CPU KDF 对拍失败: {exc!r}")

    say("")
    say("=== CPU 解密基准（含 spawn 子进程）===")
    try:
        t0 = time.perf_counter()
        r = CpuDecryptBenchmark().run()
        say(f"耗时 {time.perf_counter() - t0:.1f}s  得分 {r.score}  error={r.error!r}")
        for k, v in (r.details or {}).items():
            say(f"    {k} = {v}")
        ok_all &= not r.error
    except Exception as exc:
        ok_all = False
        say(f"CPU 基准异常: {exc!r}")

    if not cpu_only:
        say("")
        say("=== 可用性检查 ===")
        avail, info = available()
        say(f"GPU available={avail} info={info}")
        if avail:
            say("")
            say("=== GPU 解密基准（含 hashlib 对拍）===")
            try:
                t0 = time.perf_counter()
                g = GpuDecryptBenchmark().run()
                say(f"耗时 {time.perf_counter() - t0:.1f}s  得分 {g.score}  error={g.error!r}")
                for k, v in (g.details or {}).items():
                    say(f"    {k} = {v}")
                ok_all &= not g.error
            except Exception as exc:
                ok_all = False
                say(f"GPU 基准异常: {exc!r}")
        else:
            say("GPU 不可用（CPU 结果仍然有效）")

    say("")
    say(f"RESULT: {'PASS' if ok_all else 'FAIL'}")
    try:
        out_dir = config().dir / "logs"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "selftest.txt").write_text("\n".join(lines), encoding="utf-8")
        print("written:", out_dir / "selftest.txt", flush=True)
    except Exception:
        pass
    return 0 if ok_all else 1


def main() -> int:
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return _selftest(argv)

    _configure_gl()
    config().save()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)

    qss = resource_path("assets/style.qss")
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))
    icon = resource_path("assets/icon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    from src.ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
