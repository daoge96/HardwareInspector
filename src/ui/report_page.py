"""报告页面：结果列表 + 生成 HTML。"""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from ..core.config import config
from ..core.state import app_state
from ..report.generator import generate
from .base_page import BasePage


class ReportPage(BasePage):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "评分报告",
            "汇总各模块成绩，导出带实时指标的 HTML 报告。",
            parent,
        )
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["项目", "得分", "详情 / 错误"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.body.addWidget(self.table)
        self.btn_refresh = self.add_button("刷新结果", self._refresh)
        self.btn_gen = self.add_button("生成 HTML 报告", self._on_generate)
        self.btn_open = self.add_button("打开报告目录", self._on_open)

    def _refresh(self) -> None:
        results = app_state.results
        self.table.setRowCount(len(results))
        for row, item in enumerate(results):
            details = "  ".join(f"{k}:{v}" for k, v in (item.get("details") or {}).items())
            extra = item.get("error") or details
            self.table.setItem(row, 0, QTableWidgetItem(str(item.get("name", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(str(item.get("score", 0))))
            self.table.setItem(row, 2, QTableWidgetItem(str(extra)))
        self.set_status(f"共 {len(results)} 条结果")

    def _on_generate(self) -> None:
        detections = app_state.detections
        cpu = detections.get("cpu")
        mem = detections.get("mem")
        gpus = detections.get("gpu") or []
        disks = detections.get("disk") or []
        live = detections.get("live") or []
        gpu_sections = [(g.name or f"GPU {i + 1}", g.rows()) for i, g in enumerate(gpus)]
        disk_sections = [(d.model or f"磁盘 {i + 1}", d.rows()) for i, d in enumerate(disks)]
        path = generate(
            cpu.rows() if cpu else [],
            gpu_sections,
            mem.rows() if mem else [],
            disk_sections,
            list(app_state.results),
            live_rows=live,
        )
        self.set_status(f"已生成: {path.name}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_open(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(config().report_dir)))
