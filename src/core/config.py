"""应用配置（单例）：读写 %APPDATA%/HardwareInspector/config.json。"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Optional

from .constants import APP_NAME, DEFAULT_CHART_POINTS, DEFAULT_SAMPLE_INTERVAL_MS


def _base_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME
    return Path.home() / f".{APP_NAME}"


@dataclass
class AppConfig:
    """全部配置字段均带缺省值，load 时缺失键自动补齐。"""

    theme: str = "dark"
    sample_interval_ms: int = DEFAULT_SAMPLE_INTERVAL_MS
    chart_points: int = DEFAULT_CHART_POINTS
    report_dir: str = ""
    auto_detect_on_start: bool = True
    cpu_bench_scale: float = 1.0
    cpu_stress_seconds: int = 60
    mem_bench_block_mb: int = 256
    mem_stress_percent: int = 70
    disk_bench_file_mb: int = 512
    disk_bench_random_ops: int = 20000
    gpu_bench_frames: int = 600


class Config:
    _lock = threading.RLock()
    _inst: Optional["Config"] = None

    def __new__(cls) -> "Config":
        with cls._lock:
            if cls._inst is None:
                inst = super().__new__(cls)
                inst._init()
                cls._inst = inst
            return cls._inst

    def _init(self) -> None:
        self._dir = _base_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "config.json"
        self._data = AppConfig()
        self.load()

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        with self._lock:
            if self._path.exists():
                try:
                    raw = json.loads(self._path.read_text(encoding="utf-8"))
                    valid = {f.name for f in fields(AppConfig)}
                    for key, value in raw.items():
                        if key in valid:
                            setattr(self._data, key, value)
                except Exception:
                    pass
            if not self._data.report_dir:
                self._data.report_dir = str(self._dir / "reports")

    def save(self) -> None:
        with self._lock:
            self._path.write_text(
                json.dumps(asdict(self._data), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def get(self, name: str, default: Any = None) -> Any:
        return getattr(self._data, name, default)

    def set(self, name: str, value: Any) -> None:
        if hasattr(self._data, name):
            setattr(self._data, name, value)

    @property
    def report_dir(self) -> Path:
        d = Path(self.get("report_dir") or (self._dir / "reports"))
        d.mkdir(parents=True, exist_ok=True)
        return d


def config() -> Config:
    return Config()
