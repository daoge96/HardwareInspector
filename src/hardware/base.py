"""硬件检测基类与安全查询工具。"""
from __future__ import annotations

from typing import List

from ..core.logger import get_logger
from ..core.wmi_client import DEFAULT_NAMESPACE, WmiClient, WmiUnavailable

log = get_logger("hardware")


class HardwareDetector:
    """硬件检测器基类。"""

    name = "base"

    def __init__(self, wmi: WmiClient | None = None) -> None:
        self.wmi = wmi or WmiClient()

    def detect(self):
        raise NotImplementedError


def safe_query(wmi: WmiClient, wql: str, namespace: str = DEFAULT_NAMESPACE) -> List[dict]:
    """查询 WMI，失败记录日志并返回空列表（不抛异常）。"""
    try:
        return wmi.query(wql, namespace)
    except WmiUnavailable as exc:
        log.warning("WMI 查询失败 [%s]: %s", wql, exc)
    except Exception as exc:
        log.warning("WMI 异常 [%s]: %s", wql, exc)
    return []
