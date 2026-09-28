"""基准测试基类与结果结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class BenchmarkResult:
    key: str
    name: str
    score: float = 0.0
    unit: str = "分"
    details: Dict[str, object] = field(default_factory=dict)
    duration: float = 0.0
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "score": self.score,
            "unit": self.unit,
            "details": dict(self.details),
            "duration": self.duration,
            "error": self.error,
        }

    def rows(self) -> List[Tuple[str, str]]:
        return [(str(k), str(v)) for k, v in self.details.items()]


class Benchmark:
    """所有基准的基类。run(progress_cb(percent, message), stop_event)。"""

    key = "base"
    name = "基准测试"
    unit = "分"

    def run(self, progress_cb=None, stop_event=None) -> BenchmarkResult:
        raise NotImplementedError
