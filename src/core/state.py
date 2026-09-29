"""全局会话状态：收集检测信息与基准结果，供报告使用。"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional


class AppState:
    _inst: Optional["AppState"] = None
    _lock = threading.RLock()

    def __new__(cls) -> "AppState":
        with cls._lock:
            if cls._inst is None:
                inst = super().__new__(cls)
                inst._reset()
                cls._inst = inst
            return cls._inst

    def _reset(self) -> None:
        self.detections: Dict[str, Any] = {}
        self.results: List[Dict[str, Any]] = []

    def set_detection(self, key: str, value: Any) -> None:
        with self._lock:
            self.detections[key] = value

    def add_result(self, result: Dict[str, Any]) -> None:
        """同 key 的结果覆盖旧的（重跑一次不应该在报告里出现两条）。"""
        with self._lock:
            key = result.get("key")
            if key:
                for i, old in enumerate(self.results):
                    if old.get("key") == key:
                        self.results[i] = result
                        return
            self.results.append(result)

    def clear(self) -> None:
        with self._lock:
            self._reset()


app_state = AppState()
