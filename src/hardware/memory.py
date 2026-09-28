"""内存检测。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..core.logger import get_logger
from ..core.utils import human_bytes, to_int
from .base import HardwareDetector, safe_query

log = get_logger("hardware.memory")

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

# 常见内存频率对应的参考时序（CL-tRCD-tRP-tRAS），仅供参考
_TIMING_TABLE = {
    2133: (15, 15, 15, 36),
    2400: (16, 16, 16, 39),
    2666: (19, 19, 19, 43),
    2933: (20, 20, 20, 47),
    3200: (22, 22, 22, 52),
    3600: (18, 18, 18, 42),
    4000: (19, 19, 19, 44),
    4800: (40, 40, 40, 77),
    5600: (46, 46, 46, 90),
    6000: (30, 36, 36, 96),
    6400: (32, 39, 39, 102),
}


def _timing_for(speed: int) -> str:
    if speed <= 0:
        return ""
    nearest = min(_TIMING_TABLE.keys(), key=lambda k: abs(k - speed))
    cl, trcd, trp, tras = _TIMING_TABLE[nearest]
    return f"CL{cl}-{trcd}-{trp}-{tras} (参考值@{nearest}MHz)"


@dataclass
class MemInfo:
    total: str = ""
    total_bytes: int = 0
    channels: str = ""
    speed_mhz: int = 0
    modules: int = 0
    manufacturers: str = ""
    part_numbers: str = ""
    timings: str = ""

    def rows(self) -> List[Tuple[str, str]]:
        return [
            ("总容量", self.total or "N/A"),
            ("插槽/通道", f"{self.modules} 条 / 约 {self.channels} 通道" if self.modules else "N/A"),
            ("频率", f"{self.speed_mhz} MHz" if self.speed_mhz else "N/A"),
            ("时序", self.timings or "N/A"),
            ("颗粒厂商", self.manufacturers or "N/A"),
            ("型号", self.part_numbers or "N/A"),
        ]

    def key_metrics(self) -> Dict[str, str]:
        return {
            "总容量": self.total or "N/A",
            "频率": f"{self.speed_mhz} MHz" if self.speed_mhz else "N/A",
            "通道": self.channels or "N/A",
        }


class MemDetector(HardwareDetector):
    name = "memory"

    def detect(self) -> MemInfo:
        info = MemInfo()
        rows = safe_query(self.wmi, "SELECT * FROM Win32_PhysicalMemory")
        total = 0
        speeds: List[int] = []
        makers: List[str] = []
        parts: List[str] = []
        banks: set = set()
        for row in rows:
            total += to_int(row.get("Capacity"), 0)
            speed = to_int(row.get("ConfiguredClockSpeed") or row.get("Speed"), 0)
            if speed:
                speeds.append(speed)
            maker = str(row.get("Manufacturer") or "").strip()
            if maker:
                makers.append(maker)
            part = str(row.get("PartNumber") or "").strip()
            if part:
                parts.append(part)
            bank = str(row.get("BankLabel") or row.get("DeviceLocator") or "").strip()
            if bank:
                banks.add(bank)
        if total == 0 and psutil is not None:
            try:
                total = int(psutil.virtual_memory().total)
            except Exception:
                total = 0
        info.total_bytes = total
        info.total = human_bytes(total) if total else "N/A"
        info.modules = len(rows)
        info.speed_mhz = max(speeds) if speeds else 0
        info.channels = str(len(banks)) if banks else ("单/未知" if rows else "")
        info.manufacturers = "、".join(dict.fromkeys(makers)) if makers else ""
        info.part_numbers = "、".join(dict.fromkeys(parts)) if parts else ""
        info.timings = _timing_for(info.speed_mhz)
        return info
