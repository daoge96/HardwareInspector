"""CPU 检测。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from ..core.constants import ARCH_MAP
from ..core.logger import get_logger
from ..core.utils import to_float, to_int
from .base import HardwareDetector, safe_query

log = get_logger("hardware.cpu")

try:
    import cpuinfo
except Exception:  # pragma: no cover
    cpuinfo = None

_PROCESS_HINTS = [
    (("ultra 9", "ultra 7", "ultra 5"), "Intel 4 / TSMC N5"),
    (("14900", "14700", "13900", "13700", "12900", "12700", "13600", "12600"), "Intel 7 (10nm)"),
    (("11900", "11700", "11600", "10900", "10700", "10500"), "Intel 14nm"),
    (("ryzen 9 7", "ryzen 7 7", "ryzen 5 7"), "TSMC 5nm"),
    (("ryzen 9 5", "ryzen 7 5", "ryzen 5 5", "ryzen 5 3", "ryzen 3 3"), "TSMC 7nm"),
]


def match_process(name: str) -> str:
    low = (name or "").lower()
    for keys, value in _PROCESS_HINTS:
        if any(key in low for key in keys):
            return value
    return "未知(型号库未收录)"


@dataclass
class CpuInfo:
    name: str = ""
    manufacturer: str = ""
    architecture: str = ""
    socket: str = ""
    cores: int = 0
    threads: int = 0
    base_mhz: float = 0.0
    boost_mhz: float = 0.0
    l1_cache: str = ""
    l2_cache: str = ""
    l3_cache: str = ""
    process: str = ""

    def rows(self) -> List[Tuple[str, str]]:
        return [
            ("型号", self.name or "N/A"),
            ("厂商", self.manufacturer or "N/A"),
            ("架构", self.architecture or "N/A"),
            ("插槽", self.socket or "N/A"),
            ("核心/线程", f"{self.cores} / {self.threads}"),
            ("基础频率", f"{self.base_mhz:.0f} MHz" if self.base_mhz else "N/A"),
            ("睿频频率", f"{self.boost_mhz:.0f} MHz" if self.boost_mhz else "N/A"),
            ("L1 缓存", self.l1_cache or "N/A"),
            ("L2 缓存", self.l2_cache or "N/A"),
            ("L3 缓存", self.l3_cache or "N/A"),
            ("制程", self.process or "N/A"),
        ]

    def key_metrics(self) -> Dict[str, str]:
        return {
            "型号": self.name or "N/A",
            "核心/线程": f"{self.cores}/{self.threads}",
            "睿频": f"{self.boost_mhz:.0f} MHz" if self.boost_mhz else "N/A",
        }


class CpuDetector(HardwareDetector):
    name = "cpu"

    def detect(self) -> CpuInfo:
        info = CpuInfo()
        rows = safe_query(self.wmi, "SELECT * FROM Win32_Processor")
        if rows:
            row = rows[0]
            info.name = str(row.get("Name") or "").strip()
            info.manufacturer = str(row.get("Manufacturer") or "").strip()
            info.cores = to_int(row.get("NumberOfCores"), 0)
            info.threads = to_int(row.get("NumberOfLogicalProcessors"), 0)
            info.boost_mhz = to_float(row.get("MaxClockSpeed"), 0.0) or 0.0
            info.base_mhz = to_float(row.get("CurrentClockSpeed"), 0.0) or 0.0
            arch = row.get("Architecture")
            info.architecture = ARCH_MAP.get(arch, f"未知({arch})")
            info.socket = str(row.get("SocketDesignation") or "").strip()
            l2 = row.get("L2CacheSize")
            l3 = row.get("L3CacheSize")
            if l2:
                info.l2_cache = f"{to_int(l2)} KB"
            if l3:
                info.l3_cache = f"{to_int(l3)} KB"
        if cpuinfo is not None:
            try:
                ci = cpuinfo.get_cpu_info()
                if not info.name:
                    info.name = str(ci.get("brand_raw") or "")
                hz = ci.get("hz_actual")
                if hz and not info.base_mhz:
                    info.base_mhz = to_float(hz[0], 0.0) or 0.0
                if not info.l1_cache:
                    cache = ci.get("cache_size") or ""
                    if cache:
                        info.l1_cache = f"{cache} (py-cpuinfo)"
            except Exception as exc:
                log.debug("py-cpuinfo 读取失败: %s", exc)
        if not info.cores and info.threads:
            info.cores = info.threads
        info.process = match_process(info.name)
        return info
