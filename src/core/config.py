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

    # 解密基准（Office Agile SHA512-KDF）—— 必须在此登记，
    # 否则 Config.set() 会因 hasattr 为假而静默丢弃
    crypto_bench_spin: int = 100_000
    crypto_bench_seconds: float = 15.0
    crypto_bench_warmup: float = 2.0
    bench_repeats: int = 3
    bench_preset: str = "standard"
    cpu_phase_seconds: float = 6.0
    gpu_phase_seconds: float = 6.0
    bench_saturation_check: bool = True


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


# 测试强度预设：控制各基准的稳态窗口长度与作业规模
BENCH_PRESETS = {
    "quick": {
        "label": "快速（约 15 秒/项）",
        "crypto_bench_seconds": 5.0, "crypto_bench_warmup": 1.0, "crypto_bench_spin": 50_000,
        "cpu_phase_seconds": 3.0, "gpu_phase_seconds": 3.0,
        "mem_bench_block_mb": 256, "disk_bench_file_mb": 256, "bench_repeats": 2,
    },
    "standard": {
        "label": "标准（约 40 秒/项）",
        "crypto_bench_seconds": 15.0, "crypto_bench_warmup": 2.0, "crypto_bench_spin": 100_000,
        "cpu_phase_seconds": 6.0, "gpu_phase_seconds": 6.0,
        "mem_bench_block_mb": 512, "disk_bench_file_mb": 512, "bench_repeats": 3,
    },
    "strict": {
        "label": "严格（约 90 秒/项）",
        "crypto_bench_seconds": 30.0, "crypto_bench_warmup": 3.0, "crypto_bench_spin": 100_000,
        "cpu_phase_seconds": 10.0, "gpu_phase_seconds": 10.0,
        "mem_bench_block_mb": 1024, "disk_bench_file_mb": 1024, "bench_repeats": 5,
    },
}


def apply_preset(name: str) -> None:
    """套用测试强度预设。"""
    preset = BENCH_PRESETS.get(name) or BENCH_PRESETS["standard"]
    cfg = config()
    for key, value in preset.items():
        if key != "label":
            cfg.set(key, value)
    cfg.set("bench_preset", name)
    cfg.save()


def config() -> Config:
    return Config()
