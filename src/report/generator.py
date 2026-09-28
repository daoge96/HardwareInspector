"""HTML 报告生成。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Sequence, Tuple

from ..benchmark.scoring import grade
from ..core.config import config
from ..core.logger import get_logger
from ..core.utils import resource_path

log = get_logger("report")

_FALLBACK = "<html><body><h1>HardwareInspector 报告</h1>{{CONTENT}}</body></html>"


def _esc(value) -> str:
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _table(rows: Sequence[Tuple[str, str]]) -> str:
    if not rows:
        return "<table class='kv'><tr><td colspan='2'>N/A</td></tr></table>"
    body = "\n".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows)
    return f"<table class='kv'>{body}</table>"


def _sections(sections: List[Tuple[str, Sequence[Tuple[str, str]]]]) -> str:
    if not sections:
        return "<p>N/A</p>"
    return "\n".join(f"<h3>{_esc(title)}</h3>{_table(rows)}" for title, rows in sections)


def _results_table(results: List[dict]) -> str:
    if not results:
        return "<p>尚未运行任何基准测试。</p>"
    rows = []
    for item in results:
        details = "、".join(f"{k}={v}" for k, v in (item.get("details") or {}).items())
        rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                _esc(item.get("name", "")),
                _esc(item.get("score", 0)),
                _esc(details),
                _esc(item.get("error") or "-"),
            )
        )
    header = "<tr><th>项目</th><th>得分</th><th>详情</th><th>错误</th></tr>"
    return f"<table class='grid'>{header}{''.join(rows)}</table>"


def generate(
    cpu_rows: Sequence[Tuple[str, str]],
    gpu_sections: List[Tuple[str, Sequence[Tuple[str, str]]]],
    mem_rows: Sequence[Tuple[str, str]],
    disk_sections: List[Tuple[str, Sequence[Tuple[str, str]]]],
    results: List[dict],
) -> Path:
    scores = [float(r.get("score", 0) or 0) for r in results if not r.get("error")]
    total = round(sum(scores) / len(scores), 1) if scores else 0.0
    letter, label = grade(total)
    summary = (
        f"本次共采集 {len(results)} 项基准结果，综合评分 {total} 分，等级 {letter}（{label}）。"
        if results
        else "本次仅采集硬件信息，未运行基准测试。"
    )

    template_path = resource_path("src/report/template.html")
    html = template_path.read_text(encoding="utf-8") if template_path.exists() else _FALLBACK

    replacements = {
        "{{TIMESTAMP}}": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "{{SUMMARY}}": _esc(summary),
        "{{TOTAL_SCORE}}": str(total),
        "{{GRADE}}": f"{letter} ({label})",
        "{{CPU_TABLE}}": _table(cpu_rows),
        "{{GPU_TABLES}}": _sections(gpu_sections),
        "{{MEM_TABLE}}": _table(mem_rows),
        "{{DISK_TABLES}}": _sections(disk_sections),
        "{{RESULT_TABLE}}": _results_table(results),
    }
    for key, value in replacements.items():
        html = html.replace(key, value)

    out_dir = config().report_dir
    out_path = out_dir / f"HardwareInspector_Report_{datetime.now():%Y%m%d_%H%M%S}.html"
    out_path.write_text(html, encoding="utf-8")
    log.info("报告已生成: %s", out_path)
    return out_path
