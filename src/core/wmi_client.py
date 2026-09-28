"""WMI 访问封装：所有硬件检测统一经此取数。"""
from __future__ import annotations

from typing import Dict, List, Optional

from .logger import get_logger

log = get_logger("wmi")

try:  # pywin32
    import win32com.client as _win32

    _HAS_WIN32 = True
except Exception:  # pragma: no cover
    _win32 = None
    _HAS_WIN32 = False

DEFAULT_NAMESPACE = "root\\cimv2"


class WmiUnavailable(RuntimeError):
    """WMI 不可用或查询失败。"""


class WmiClient:
    """按命名空间缓存连接；失败命名空间记入失败集避免反复重试。"""

    def __init__(self) -> None:
        self._services: Dict[str, object] = {}
        self._failed: set = set()
        self._locator = None

    def _service(self, namespace: str):
        if namespace in self._failed:
            raise WmiUnavailable(f"namespace unavailable: {namespace}")
        if namespace in self._services:
            return self._services[namespace]
        if not _HAS_WIN32:
            self._failed.add(namespace)
            raise WmiUnavailable("pywin32 未安装")
        try:
            if self._locator is None:
                self._locator = _win32.Dispatch("WbemScripting.SWbemLocator")
            service = self._locator.ConnectServer(".", namespace)
            self._services[namespace] = service
            return service
        except Exception as exc:
            self._failed.add(namespace)
            log.warning("连接 WMI 命名空间 %s 失败: %s", namespace, exc)
            raise WmiUnavailable(str(exc))

    def query(self, wql: str, namespace: str = DEFAULT_NAMESPACE) -> List[Dict[str, object]]:
        service = self._service(namespace)
        try:
            items = service.ExecQuery(wql)
        except Exception as exc:
            raise WmiUnavailable(str(exc))
        rows: List[Dict[str, object]] = []
        for item in items:
            row: Dict[str, object] = {}
            try:
                props = item.Properties_
            except Exception:
                continue
            for prop in props:
                try:
                    row[prop.Name] = prop.Value
                except Exception:
                    row[prop.Name] = None
            rows.append(row)
        return rows

    def single(self, wql: str, namespace: str = DEFAULT_NAMESPACE) -> Optional[Dict[str, object]]:
        rows = self.query(wql, namespace)
        return rows[0] if rows else None
