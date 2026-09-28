"""运行注册表：登记所有活跃 Worker，供全局停止与关闭清理。"""
from __future__ import annotations

import threading
from typing import List


class RunRegistry:
    _inst = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._inst is None:
                inst = super().__new__(cls)
                inst._items: List[object] = []
                cls._inst = inst
            return cls._inst

    def register(self, worker) -> None:
        with self._lock:
            if worker not in self._items:
                self._items.append(worker)

    def unregister(self, worker) -> None:
        with self._lock:
            try:
                self._items.remove(worker)
            except ValueError:
                pass

    def stop_all(self) -> None:
        with self._lock:
            items = list(self._items)
        for worker in items:
            try:
                worker.request_stop()
            except Exception:
                pass


registry = RunRegistry()
