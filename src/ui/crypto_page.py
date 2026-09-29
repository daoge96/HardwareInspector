r"""解密基准页：用 Office Agile SHA512-KDF 的破译吞吐给 CPU / GPU 打分。

为什么用这个算法：它就是 D:\OneDrive\Desktop\硬解密码.py 里真正决定
破译速度的那条迭代链（SHA512 迭代 spin 次），
CPU 满载多进程 / GPU 满载 CUDA 内核，指标是每秒尝试的候选密码数，
和真实破译场景同量纲，比跑几个玩具循环有意义得多。
"""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel

from ..benchmark.crypto_bench import (
    CpuDecryptBenchmark,
    GpuDecryptBenchmark,
    available as gpu_available,
)
from ..core.config import BENCH_PRESETS, apply_preset, config
from ..core.state import app_state
from ..services.runner import registry
from ..services.workers import BenchmarkWorker
from .base_page import BasePage
from .widgets.card import ActionCard
from .widgets.section import Pill, SectionTitle

_METHOD = (
    "算法：Office Agile SHA512-KDF（salt → SHA512 → 迭代 spin 次 → 派生 k1/k2 → AES 校验）。"
    "指标为每秒可尝试的候选密码数，与真实文档破译吞吐同量纲。"
)

_BASELINE = "评分基线：1000 分 = 参考机（R9 8945HX 32 线程 + RTX 5060 Laptop）实测水平。"

# 解密专用的等级带（整机 GRADE_BANDS 是按 0~10000 的总分设计的，
# 直接套到单模块上会让一台好机器显示成 D）
_BANDS = (
    (1800, "S", "旗舰级"),
    (1400, "A", "高性能"),
    (900, "B", "主流"),
    (600, "C", "入门"),
    (0, "D", "基础"),
)


def _grade(score: float):
    for threshold, letter, label in _BANDS:
        if score >= threshold:
            return letter, label
    return "D", "基础"


class CryptoPage(BasePage):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "解密基准",
            "用 SHA512-KDF 破译吞吐衡量 CPU / GPU 的真实算力。" + _METHOD + _BASELINE,
            parent,
        )
        self._worker: Optional[BenchmarkWorker] = None
        self._queue: List[Callable[[], object]] = []

        # ---- 强度选择 ----
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(SectionTitle("测试强度", "决定每个窗口的稳态时长"))
        self.preset = QComboBox()
        for key, preset in BENCH_PRESETS.items():
            self.preset.addItem(preset["label"], key)
        current = str(config().get("bench_preset", "standard"))
        index = self.preset.findData(current)
        self.preset.setCurrentIndex(max(0, index))
        self.preset.currentIndexChanged.connect(self._on_preset)
        self.preset.setFixedWidth(220)
        row.addWidget(self.preset)
        self.preset_hint = QLabel("")
        self.preset_hint.setObjectName("cardHint")
        row.addWidget(self.preset_hint, 1)
        self.body.addLayout(row)
        self._refresh_preset_hint()

        # ---- CPU ----
        self.cpu_card = ActionCard(
            "CPU 解密速度",
            f"spawn 全部逻辑核心并行跑 KDF，先测单核稳态、再测全核稳态，"
            f"给出真实加速比与并行效率。当前窗口 {self._seconds():.0f}s x2。",
            "开始 CPU 解密基准",
        )
        self.cpu_card.button.clicked.connect(lambda: self._start("cpu"))
        self.body.addWidget(self.cpu_card)

        # ---- GPU ----
        ok, info = gpu_available()
        self.gpu_card = ActionCard(
            "GPU 解密速度",
            "CUDA 内核直接跑同一条 KDF（驱动 API + 内嵌 PTX，不依赖 cupy），"
            "启动时先与 hashlib 逐字节对拍。",
            "开始 GPU 解密基准",
        )
        self.gpu_card.button.clicked.connect(lambda: self._start("gpu"))
        self.gpu_card.button.setEnabled(ok)
        if ok:
            self.gpu_card.set_hint(f"已就绪：{info}", "ok")
        else:
            self.gpu_card.set_hint(f"不可用：{info}", "warn")
        self.body.addWidget(self.gpu_card)

        # ---- 汇总 ----
        self.summary = ActionCard("综合解密评分", "CPU 与 GPU 分项得分的平均值。" + _BASELINE)
        self.body.addWidget(self.summary)
        self.badge = Pill("尚未测试", "info")
        head = QHBoxLayout()
        head.addWidget(self.badge)
        head.addStretch(1)
        self.summary_layout = self.summary.grid
        self.body.addLayout(head)

        self.btn_all = self.add_button("全部测试（先 CPU 后 GPU）", self._start_all, "primary")
        self.btn_stop = self.add_button("停止", self._on_stop)
        self.btn_stop.setEnabled(False)

    # ------------------------------------------------------------------
    def _seconds(self) -> float:
        return float(config().get("crypto_bench_seconds", 15.0) or 15.0)

    def _refresh_preset_hint(self) -> None:
        cfg = config()
        self.preset_hint.setText(
            f"解密窗口 {cfg.get('crypto_bench_spin', 100000):,} 次迭代 · "
            f"{cfg.get('crypto_bench_seconds', 15.0):.0f}s（预热 "
            f"{cfg.get('crypto_bench_warmup', 2.0):.0f}s 剔除）· "
            f"综合基准每阶段 {cfg.get('cpu_phase_seconds', 6.0):.0f}s"
        )

    def _on_preset(self, _index: int) -> None:
        apply_preset(self.preset.currentData())
        self._refresh_preset_hint()

    # ------------------------------------------------------------------
    def _start_all(self) -> None:
        self._queue = ["cpu", "gpu"] if self.gpu_card.button.isEnabled() else ["cpu"]
        self._next()

    def _start(self, which: str) -> None:
        self._queue = [which]
        self._next()

    def _next(self) -> None:
        if self._worker is not None or not self._queue:
            return
        which = self._queue.pop(0)
        card = self.cpu_card if which == "cpu" else self.gpu_card
        bench = CpuDecryptBenchmark() if which == "cpu" else GpuDecryptBenchmark()
        self._which = which
        card.set_hint("运行中…", "warn")
        self._start_worker(bench, card)

    def _start_worker(self, bench, card: ActionCard) -> None:
        worker = BenchmarkWorker(bench)
        self._worker = worker
        worker.progress.connect(self.set_progress)
        worker.failed.connect(lambda m: self._failed(m, card))
        worker.finished_ok.connect(lambda d: self._done(d, card))
        # 关键：把 worker 自己带进回调。否则上一个 worker 的 finished 会在
        # 下一个任务已经启动之后触发，把 self._worker 清成 None 并误放开按钮。
        worker.finished.connect(lambda w=worker: self._finished(w))
        registry.register(worker)
        self.set_busy(True)
        self.btn_all.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._set_cards_enabled(False)
        worker.start()

    def _set_cards_enabled(self, enabled: bool) -> None:
        self.cpu_card.button.setEnabled(enabled)
        self.gpu_card.button.setEnabled(enabled and gpu_available()[0])

    def _done(self, data: dict, card: ActionCard) -> None:
        if data.get("error"):
            self._failed(str(data["error"]), card)
            return
        app_state.add_result(data)
        score = float(data.get("score") or 0)
        details = data.get("details") or {}
        card.set_rows(list(details.items()))
        conf = details.get("可信度", "")
        kind = "ok" if conf == "高" else ("warn" if conf == "中" else "bad")
        card.set_hint(f"得分 {score:,.0f} · 可信度 {conf}", kind)
        self._tally()
        self.set_progress(100, "完成")

    def _failed(self, message: str, card: ActionCard) -> None:
        card.set_hint(f"失败：{message}", "bad")
        self.set_status(f"失败：{message}")

    def _finished(self, worker) -> None:
        if self._worker is not worker:
            return                       # 已经切换到下一个任务了，别动它的状态
        self._worker = None
        if self._queue:
            self._next()
            return
        self.set_busy(False)
        self.btn_all.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_cards_enabled(True)

    def _on_stop(self) -> None:
        self._queue = []
        if self._worker is not None:
            self._worker.request_stop()

    # ------------------------------------------------------------------
    def _tally(self) -> None:
        scores = [r for r in app_state.results if r.get("key") in ("cpu_decrypt", "gpu_decrypt")]
        if not scores:
            return
        total = sum(float(r.get("score") or 0) for r in scores) / len(scores)
        letter, label = _grade(total)
        rows = [(r.get("name", r.get("key", "")), f"{float(r.get('score') or 0):,.0f}") for r in scores]
        rows.append(("解密综合", f"{total:,.0f} 分 · {letter}（{label}）"))
        self.summary.set_rows(rows)
        self.badge.show_text(f"综合评分 {total:,.0f} 分 · 等级 {letter}（{label}）",
                             "ok" if total >= 1400 else ("warn" if total >= 600 else "bad"))
