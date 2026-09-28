"""传感器聚合：多后端级联读取 CPU/GPU/内存实时指标。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .logger import get_logger
from .wmi_client import WmiClient

log = get_logger("sensors")

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

try:
    import pynvml
except Exception:  # pragma: no cover
    pynvml = None


@dataclass
class CpuReading:
    usage: Optional[float] = None
    temp: Optional[float] = None
    freq_mhz: Optional[float] = None
    power: Optional[float] = None


@dataclass
class GpuReading:
    index: int = 0
    name: str = ""
    usage: Optional[float] = None
    temp: Optional[float] = None
    mem_used_mb: Optional[float] = None
    mem_total_mb: Optional[float] = None
    clock_mhz: Optional[float] = None
    fan_percent: Optional[float] = None


@dataclass
class MemReading:
    total_mb: Optional[float] = None
    used_mb: Optional[float] = None
    percent: Optional[float] = None


class _NvmlBackend:
    """NVIDIA NVML 后端（无需 nvidia-smi.exe）。"""

    def __init__(self) -> None:
        self.ok = False
        self.count = 0
        if pynvml is None:
            return
        try:
            pynvml.nvmlInit()
            self.count = pynvml.nvmlDeviceGetCount()
            self.ok = True
        except Exception as exc:
            log.info("NVML 初始化失败: %s", exc)
            self.ok = False

    def read(self, index: int) -> Optional[GpuReading]:
        if not self.ok or index >= self.count:
            return None
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            reading = GpuReading(index=index)
            try:
                reading.name = pynvml.nvmlDeviceGetName(handle)
            except Exception:
                pass
            try:
                reading.temp = float(
                    pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                )
            except Exception:
                pass
            try:
                reading.usage = float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
            except Exception:
                pass
            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                reading.mem_used_mb = mem.used / 1048576.0
                reading.mem_total_mb = mem.total / 1048576.0
            except Exception:
                pass
            try:
                reading.clock_mhz = float(
                    pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)
                )
            except Exception:
                pass
            try:
                reading.fan_percent = float(pynvml.nvmlDeviceGetFanSpeed(handle))
            except Exception:
                pass
            return reading
        except Exception as exc:
            log.debug("NVML 读取失败: %s", exc)
            return None


class _LhmBackend:
    """LibreHardwareMonitor / OpenHardwareMonitor 的 WMI 传感器后端。"""

    NAMESPACES = ("root\\LibreHardwareMonitor", "root\\OpenHardwareMonitor")

    def __init__(self, wmi: WmiClient) -> None:
        self.wmi = wmi
        self.namespace: Optional[str] = None
        self._tried = False

    def _ensure(self) -> bool:
        if self.namespace:
            return True
        if self._tried:
            return False
        self._tried = True
        for ns in self.NAMESPACES:
            try:
                rows = self.wmi.query("SELECT * FROM Sensor", ns)
            except Exception:
                continue
            if rows:
                self.namespace = ns
                log.info("使用传感器后端: %s", ns)
                return True
        return False

    def _sensors(self) -> List[dict]:
        if not self._ensure():
            return []
        try:
            return self.wmi.query("SELECT * FROM Sensor", self.namespace)
        except Exception:
            self.namespace = None
            return []

    def cpu_temp(self) -> Optional[float]:
        best: Optional[float] = None
        for row in self._sensors():
            if row.get("SensorType") != "Temperature":
                continue
            ident = str(row.get("Identifier") or "").lower()
            name = str(row.get("Name") or "").lower()
            if "/cpu/" not in ident or "distance" in name:
                continue
            value = row.get("Value")
            if value is None:
                continue
            val = float(value)
            if "package" in name or name.startswith("cpu"):
                return val
            best = val if best is None else max(best, val)
        return best

    def cpu_power(self) -> Optional[float]:
        for row in self._sensors():
            if row.get("SensorType") != "Power":
                continue
            ident = str(row.get("Identifier") or "").lower()
            if "/cpu/" in ident and "package" in str(row.get("Name") or "").lower():
                value = row.get("Value")
                if value is not None:
                    return float(value)
        return None

    def gpu(self, index: int) -> Optional[GpuReading]:
        rows = [r for r in self._sensors() if "/gpu/" in str(r.get("Identifier") or "").lower()]
        if not rows:
            return None
        groups: dict = {}
        for row in rows:
            parts = str(row.get("Identifier") or "").split("/")
            key = parts[2] if len(parts) > 2 else "0"
            groups.setdefault(key, []).append(row)
        keys = sorted(groups.keys())
        if not keys:
            return None
        if index >= len(keys):
            index = 0
        reading = GpuReading(index=index)
        for row in groups[keys[index]]:
            sensor_type = row.get("SensorType")
            value = row.get("Value")
            if value is None:
                continue
            if sensor_type == "Temperature":
                reading.temp = float(value)
            elif sensor_type == "Load":
                reading.usage = float(value)
            elif sensor_type == "Clock":
                reading.clock_mhz = float(value)
            elif sensor_type == "Fan":
                reading.fan_percent = float(value)
            elif sensor_type == "SmallData" and "memory" in str(row.get("Name") or "").lower():
                reading.mem_used_mb = float(value)
        return reading


class _AcpiBackend:
    """ACPI 热区温度兜底。"""

    def __init__(self, wmi: WmiClient) -> None:
        self.wmi = wmi

    def cpu_temp(self) -> Optional[float]:
        try:
            rows = self.wmi.query(
                "SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature", "root\\wmi"
            )
        except Exception:
            return None
        temps: List[float] = []
        for row in rows:
            value = row.get("CurrentTemperature")
            if value is None:
                continue
            try:
                celsius = (float(value) / 10.0) - 273.15
            except Exception:
                continue
            if -20.0 < celsius < 150.0:
                temps.append(celsius)
        return max(temps) if temps else None


class SensorHub:
    _inst: Optional["SensorHub"] = None

    def __new__(cls) -> "SensorHub":
        if cls._inst is None:
            inst = super().__new__(cls)
            inst._init()
            cls._inst = inst
        return cls._inst

    def _init(self) -> None:
        self._wmi = WmiClient()
        self._nvml = _NvmlBackend()
        self._lhm = _LhmBackend(self._wmi)
        self._acpi = _AcpiBackend(self._wmi)

    def snapshot(self, gpu_count: int = 0) -> dict:
        return {
            "cpu": self._cpu(),
            "gpus": [self._gpu(i) for i in range(max(gpu_count, 0))],
            "mem": self._mem(),
        }

    def _wmi_cpu_freq(self) -> Optional[float]:
        try:
            rows = self._wmi.query("SELECT CurrentClockSpeed FROM Win32_Processor")
        except Exception:
            return None
        if rows and rows[0].get("CurrentClockSpeed"):
            try:
                return float(rows[0]["CurrentClockSpeed"])
            except Exception:
                return None
        return None

    def _cpu(self) -> CpuReading:
        reading = CpuReading()
        if psutil is not None:
            try:
                reading.usage = float(psutil.cpu_percent(interval=None))
            except Exception:
                pass
            try:
                freq = psutil.cpu_freq()
                if freq and freq.current:
                    reading.freq_mhz = float(freq.current)
            except Exception:
                pass
        if reading.freq_mhz is None:
            reading.freq_mhz = self._wmi_cpu_freq()
        reading.temp = self._lhm.cpu_temp()
        if reading.temp is None:
            reading.temp = self._acpi.cpu_temp()
        reading.power = self._lhm.cpu_power()
        return reading

    def _gpu(self, index: int) -> GpuReading:
        reading = self._nvml.read(index)
        if reading is not None:
            return reading
        reading = self._lhm.gpu(index)
        if reading is not None:
            reading.index = index
            return reading
        return GpuReading(index=index)

    def _mem(self) -> MemReading:
        if psutil is None:
            return MemReading()
        try:
            vm = psutil.virtual_memory()
            return MemReading(
                total_mb=vm.total / 1048576.0,
                used_mb=vm.used / 1048576.0,
                percent=float(vm.percent),
            )
        except Exception:
            return MemReading()
