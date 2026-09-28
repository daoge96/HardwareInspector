"""通用工具函数。"""
from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path
from typing import Optional


def resource_path(rel: str) -> Path:
    """兼容源码运行与 PyInstaller onefile 的资源定位。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    # src/core/utils.py -> 项目根目录
    return Path(__file__).resolve().parents[2] / rel


def is_admin() -> bool:
    """当前进程是否具备管理员权限。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def to_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return default


def clamp(value, low, high):
    return max(low, min(high, value))


def human_bytes(size) -> str:
    try:
        n = float(size)
    except Exception:
        return "N/A"
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"


def fmt(value, unit: str = "", digits: int = 1, na: str = "N/A") -> str:
    if value is None:
        return na
    try:
        if isinstance(value, float):
            return f"{value:.{digits}f}{unit}"
        return f"{value}{unit}"
    except Exception:
        return na


def now_str(fmt_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    return time.strftime(fmt_str)
