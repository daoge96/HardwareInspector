"""主页：实时硬件状态卡片 + 系统概览。"""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout

from ..core.state import app_state
from ..core.utils import fmt, human_bytes
from .base_page import BasePage
from .widgets.card import InfoCard, StatCard


class HomePage(BasePage):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "系统总览",
            "各硬件关键状态实时刷新，含功率与温度。",
            parent,
        )
        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards = {}
        for index, (key, title) in enumerate(
            (("cpu", "CPU"), ("gpu", "GPU"), ("mem", "内存"), ("disk", "磁盘"))
        ):
            card = StatCard(title)
            self.cards[key] = card
            grid.addWidget(card, index // 2, index % 2)
        self.body.addLayout(grid)
        self.summary = InfoCard("系统概览")
        self.body.addWidget(self.summary)

    def apply_detections(self, data: dict) -> None:
        cpu = data.get("cpu")
        gpus = data.get("gpu") or []
        mem = data.get("mem")
        disks = data.get("disk") or []
        rows = [
            ("CPU", cpu.name if cpu else "N/A"),
            ("GPU", ", ".join(g.name for g in gpus) if gpus else "N/A"),
            ("内存", mem.total if mem else "N/A"),
            ("硬盘", f"{len(disks)} 个物理磁盘" if disks else "N/A"),
        ]
        self.summary.set_rows(rows)

    def update_snapshot(self, snap: dict) -> None:
        cpu = snap.get("cpu")
        if cpu is not None:
            usage = f"{cpu.usage:.0f}%" if cpu.usage is not None else "N/A"
            sub = f"占用率 · 温度 {fmt(cpu.temp, ' °C', 0)} · 功率 {fmt(cpu.power, ' W', 0)}"
            self.cards["cpu"].set_value(usage, sub)
        mem = snap.get("mem")
        if mem is not None and mem.percent is not None:
            used = human_bytes((mem.used_mb or 0) * 1048576)
            total = human_bytes((mem.total_mb or 0) * 1048576)
            self.cards["mem"].set_value(f"{mem.percent:.0f}%", f"{used} / {total}")
        gpus = snap.get("gpus") or []
        if gpus:
            gpu = gpus[0]
            usage = f"{gpu.usage:.0f}%" if gpu.usage is not None else "N/A"
            sub = f"占用率 · 温度 {fmt(gpu.temp, ' °C', 0)} · 功率 {fmt(gpu.power, ' W', 0)}"
            self.cards["gpu"].set_value(usage, sub)
        io = snap.get("disk_io") or {}
        rb = io.get("read_mb_s")
        wb = io.get("write_mb_s")
        self.cards["disk"].set_value(
            f"{(rb or 0):.0f} / {(wb or 0):.0f}",
            "读 / 写 MB/s",
        )
