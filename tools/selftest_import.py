# -*- coding: utf-8 -*-
"""静态自检：导入全部模块 + 构造主窗口 + 走一遍结果渲染与报告生成。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

fails = []
mods = [
    "src.benchmark.base", "src.benchmark.crypto_bench", "src.benchmark.cpu_bench",
    "src.benchmark.mem_bench", "src.benchmark.disk_bench", "src.benchmark.gpu_bench",
    "src.benchmark.cuda_driver", "src.benchmark.kdf_ptx", "src.benchmark.py_aes",
    "src.benchmark._sampler", "src.benchmark.scoring",
    "src.core.config", "src.core.constants", "src.core.state", "src.core.utils",
    "src.ui.base_page", "src.ui.widgets.card", "src.ui.widgets.section",
    "src.ui.widgets.chart", "src.ui.home_page", "src.ui.cpu_page", "src.ui.gpu_page",
    "src.ui.mem_page", "src.ui.disk_page", "src.ui.report_page", "src.ui.crypto_page",
    "src.ui.main_window",
]
for m in mods:
    try:
        __import__(m)
    except Exception as e:
        fails.append((m, repr(e)))
        print("IMPORT FAIL", m, e)
print("imports ok:", len(mods) - len(fails), "/", len(mods))

if not fails:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from src.ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    print("tabs:", [w.tabs.tabText(i) for i in range(w.tabs.count())])

    fake = {"key": "cpu_decrypt", "name": "CPU 解密速度", "score": 1234.5,
            "details": {"单核速度": "16.6 次/秒", "可信度": "高"}}
    w.crypto._done(dict(fake), w.crypto.cpu_card)
    fake2 = dict(fake, key="gpu_decrypt", score=1000.0, name="GPU 解密速度")
    w.crypto._done(fake2, w.crypto.gpu_card)
    print("badge:", w.crypto.badge.text())
    print("summary rows:", len(w.crypto.summary._rows))

    from src.report.generator import generate
    from src.core.state import app_state
    app_state.add_result(dict(fake)); app_state.add_result(dict(fake2))
    p = generate([("CPU", "x")], [], [("内存", "y")], [], list(app_state.results))
    print("report:", p.exists(), p.stat().st_size, "bytes")

    # 预设切换
    w.crypto.preset.setCurrentIndex(0)
    from src.core.config import config
    print("preset applied:", config().get("bench_preset"),
          config().get("crypto_bench_seconds"), config().get("crypto_bench_spin"))
    w.crypto.preset.setCurrentIndex(1)
    print("preset back:", config().get("bench_preset"), config().get("crypto_bench_seconds"))

    QTimer.singleShot(1200, app.quit)
    app.exec()
    print("SETUP OK")
print("FAILS:", fails)
