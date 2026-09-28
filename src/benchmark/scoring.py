"""评分工具：归一化与等级。"""
from __future__ import annotations

from typing import Optional

from ..core.constants import GRADE_BANDS


def ratio(value, ref) -> float:
    try:
        return max(0.0, float(value)) / max(float(ref), 1e-9)
    except Exception:
        return 0.0


def mean(values) -> float:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else 0.0


def combine(*scores) -> float:
    return round(mean(scores), 1)


def grade(total: float):
    for threshold, letter, label in GRADE_BANDS:
        if total >= threshold:
            return letter, label
    return "D", "基础"
