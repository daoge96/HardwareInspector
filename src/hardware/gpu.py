"""GPU 检测。"""
from __future__ import annotations

import winreg
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..core.logger import get_logger
from ..core.utils import human_bytes, to_int
from .base import HardwareDetector, safe_query

log = get_logger("hardware.gpu")

try:
    import pynvml
except Exception:  # pragma: no cover
    pynvml = None

_CLASS_KEY = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"

_GPU_SPECS: List[Tuple[Tuple[str, ...], Tuple[str, int, int]]] = [
    (("rtx 4090",), ("GDDR6X", 384, 16384)),
    (("rtx 4080",), ("GDDR6X", 256, 9728)),
    (("rtx 4070 ti",), ("GDDR6X", 192, 7680)),
    (("rtx 4070",), ("GDDR6X", 192, 5888)),
    (("rtx 4060 ti",), ("GDDR6", 128, 4352)),
    (("rtx 4060",), ("GDDR6", 128, 3072)),
    (("rtx 3090",), ("GDDR6X", 384, 10496)),
    (("rtx 3080",), ("GDDR6X", 320, 8704)),
    (("rtx 3070",), ("GDDR6", 256, 5888)),
    (("rtx 3060",), ("GDDR6", 192, 3584)),
    (("rtx 2080",), ("GDDR6", 256, 2944)),
    (("rtx 2070",), ("GDDR6", 256, 2304)),
    (("rtx 2060",), ("GDDR6", 192, 1920)),
    (("gtx 1660",), ("GDDR6", 192, 1408)),
    (("gtx 1650",), ("GDDR6", 128, 896)),
    (("rx 7900",), ("GDDR6", 256, 6144)),
    (("rx 7800",), ("GDDR6", 256, 3840)),
    (("rx 7600",), ("GDDR6", 128, 2048)),
    (("rx 6900",), ("GDDR6", 256, 5120)),
    (("rx 6800",), ("GDDR6", 256, 3840)),
    (("rx 6700",), ("GDDR6", 192, 2560)),
    (("rx 6600",), ("GDDR6", 128, 1792)),
    (("arc a770",), ("GDDR6", 256, 4096)),
    (("arc a750",), ("GDDR6", 256, 3584)),
]

_UNKNOWN_SPEC = ("未知(型号库未收录)", 0, 0)


def match_spec(name: str) -> Tuple[str, int, int]:
    low = (name or "").lower()
    for keys, spec in _GPU_SPECS:
        if any(key in low for key in keys):
            return spec
    return _UNKNOWN_SPEC


def _registry_vram() -> Dict[str, int]:
    """读取注册表真显存大小，修正 AdapterRAM 32 位溢出。"""
    out: Dict[str, int] = {}
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CLASS_KEY)
    except Exception:
        return out
    try:
        index = 0
        while True:
            try:
                sub = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            if not sub.isdigit():
                continue
            try:
                key = winreg.OpenKey(root, sub)
            except Exception:
                continue
            try:
                desc = str(winreg.QueryValueEx(key, "DriverDesc")[0])
            except Exception:
                desc = ""
            size = 0
            for value_name in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                try:
                    raw = winreg.QueryValueEx(key, value_name)[0]
                except Exception:
                    continue
                if isinstance(raw, bytes):
                    size = int.from_bytes(raw, "little")
                else:
                    size = int(raw)
                break
            if desc and size:
                out[desc] = size
    finally:
        winreg.CloseKey(root)
    return out


def _nvml_vram() -> Dict[str, int]:
    out: Dict[str, int] = {}
    if pynvml is None:
        return out
    try:
        pynvml.nvmlInit()
    except Exception:
        return out
    try:
        for i in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            out[name] = int(pynvml.nvmlDeviceGetMemoryInfo(handle).total)
    except Exception:
        pass
    return out


@dataclass
class GpuInfo:
    name: str = ""
    vendor: str = ""
    vram: str = ""
    vram_type: str = ""
    bus_width: str = ""
    driver: str = ""
    stream_processors: str = ""
    device_id: str = ""
    adapter_ram_mb: Optional[float] = None

    def rows(self) -> List[Tuple[str, str]]:
        return [
            ("型号", self.name or "N/A"),
            ("厂商", self.vendor or "N/A"),
            ("显存容量", self.vram or "N/A"),
            ("显存类型", self.vram_type or "N/A"),
            ("位宽", self.bus_width or "N/A"),
            ("流处理器", self.stream_processors or "N/A"),
            ("驱动版本", self.driver or "N/A"),
            ("设备ID", self.device_id or "N/A"),
        ]

    def key_metrics(self) -> Dict[str, str]:
        return {
            "型号": self.name or "N/A",
            "显存": self.vram or "N/A",
            "驱动": self.driver or "N/A",
        }


def _vendor_of(name: str) -> str:
    low = (name or "").lower()
    if "nvidia" in low or "geforce" in low or "quadro" in low or "rtx" in low or "gtx" in low:
        return "NVIDIA"
    if "amd" in low or "radeon" in low or "rx " in low:
        return "AMD"
    if "intel" in low or "uhd" in low or "iris" in low or "arc" in low:
        return "Intel"
    return "未知"


class GpuDetector(HardwareDetector):
    name = "gpu"

    def detect(self) -> List[GpuInfo]:
        rows = safe_query(self.wmi, "SELECT * FROM Win32_VideoController")
        reg_vram = _registry_vram()
        nvml_vram = _nvml_vram()
        result: List[GpuInfo] = []
        for row in rows:
            name = str(row.get("Name") or "").strip()
            if not name:
                continue
            spec_type, bus_width, sp = match_spec(name)
            vram_bytes = reg_vram.get(name, 0)
            for nv_name, nv_size in nvml_vram.items():
                if nv_name and (nv_name.lower() in name.lower() or name.lower() in nv_name.lower()):
                    vram_bytes = max(vram_bytes, nv_size)
            if not vram_bytes:
                vram_bytes = to_int(row.get("AdapterRAM"), 0)
            info = GpuInfo(
                name=name,
                vendor=_vendor_of(name),
                vram=human_bytes(vram_bytes) if vram_bytes else "N/A",
                vram_type=spec_type if spec_type != _UNKNOWN_SPEC[0] else "",
                bus_width=f"{bus_width} bit" if bus_width else "",
                driver=str(row.get("DriverVersion") or "").strip(),
                stream_processors=str(sp) if sp else "",
                device_id=str(row.get("PNPDeviceID") or "").strip(),
                adapter_ram_mb=(vram_bytes / 1048576.0) if vram_bytes else None,
            )
            result.append(info)
        if not result:
            log.info("未检测到 Win32_VideoController")
        return result
