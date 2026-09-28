"""硬盘检测与 SMART 解析。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..core.logger import get_logger
from ..core.utils import human_bytes, to_int
from .base import HardwareDetector, safe_query

log = get_logger("hardware.disk")

_SMART_NAMES = {
    5: "重映射扇区",
    9: "通电时间",
    12: "上电次数",
    187: "无法校正错误",
    194: "温度",
    197: "待映射扇区",
    198: "不可校正扇区",
    231: "SSD 剩余寿命",
    233: "SSD 剩余寿命(厂商)",
    241: "总 LBAs 写入",
    246: "总 LBAs 写入(厂商)",
}


def parse_smart(raw) -> Dict[int, Tuple[int, int]]:
    """解析 MSStorageDriver_ATAPISmartData.VendorSpecific 原始字节。"""
    attrs: Dict[int, Tuple[int, int]] = {}
    if raw is None:
        return attrs
    try:
        data = bytes(bytearray(int(x) & 0xFF for x in raw))
    except Exception:
        try:
            data = bytes(raw)
        except Exception:
            return attrs
    if len(data) < 14:
        return attrs
    count = (len(data) - 2) // 12
    for i in range(count):
        off = 2 + i * 12
        attr_id = data[off]
        if attr_id == 0:
            continue
        value = data[off + 3]
        raw_value = int.from_bytes(data[off + 5 : off + 11], "little")
        attrs[attr_id] = (value, raw_value)
    return attrs


@dataclass
class SmartInfo:
    available: bool = False
    health: str = "未知"
    power_on_hours: Optional[int] = None
    written_tb: Optional[float] = None
    life_percent: Optional[int] = None
    note: str = ""

    def rows(self) -> List[Tuple[str, str]]:
        return [
            ("SMART 健康", self.health),
            ("通电时间", f"{self.power_on_hours} 小时" if self.power_on_hours is not None else "N/A"),
            ("累计写入", f"{self.written_tb:.2f} TB" if self.written_tb is not None else "N/A"),
            ("剩余寿命", f"{self.life_percent}%" if self.life_percent is not None else "N/A"),
        ]


@dataclass
class DiskInfo:
    model: str = ""
    size: str = ""
    size_bytes: int = 0
    interface: str = ""
    serial: str = ""
    media_type: str = ""
    status: str = ""
    smart: SmartInfo = field(default_factory=SmartInfo)

    def rows(self) -> List[Tuple[str, str]]:
        base = [
            ("型号", self.model or "N/A"),
            ("容量", self.size or "N/A"),
            ("接口", self.interface or "N/A"),
            ("介质类型", self.media_type or "N/A"),
            ("序列号", self.serial or "N/A"),
            ("设备状态", self.status or "N/A"),
        ]
        base.extend(self.smart.rows())
        if self.smart.note:
            base.append(("备注", self.smart.note))
        return base

    def key_metrics(self) -> Dict[str, str]:
        return {
            "型号": self.model or "N/A",
            "容量": self.size or "N/A",
            "健康": self.smart.health,
        }


def _build_smart(raw_attrs: Dict[int, Tuple[int, int]], predict_failure: Optional[bool]) -> SmartInfo:
    smart = SmartInfo()
    if not raw_attrs and predict_failure is None:
        smart.health = "未知"
        smart.note = "SMART 不可用(可能为 NVMe/RAID 或权限不足)"
        return smart
    smart.available = True
    if predict_failure is True:
        smart.health = "警告(预测故障)"
    elif predict_failure is False:
        smart.health = "正常"
    else:
        smart.health = "正常" if raw_attrs else "未知"
    hours = raw_attrs.get(9)
    if hours:
        smart.power_on_hours = hours[1]
    for aid in (231, 233):
        if aid in raw_attrs:
            value = raw_attrs[aid][0]
            if 0 <= value <= 100:
                smart.life_percent = value
                break
    written = raw_attrs.get(241) or raw_attrs.get(246)
    if written:
        smart.written_tb = written[1] * 512 / 1e12
    bad = (raw_attrs.get(5, (0, 0))[1] or 0) + (raw_attrs.get(197, (0, 0))[1] or 0)
    if bad and smart.health == "正常":
        smart.note = f"存在 {bad} 个异常/待映射扇区"
    return smart


class DiskDetector(HardwareDetector):
    name = "disk"

    def detect(self) -> List[DiskInfo]:
        drives = safe_query(self.wmi, "SELECT * FROM Win32_DiskDrive")
        smart_rows = safe_query(self.wmi, "SELECT * FROM MSStorageDriver_ATAPISmartData", "root\\wmi")
        predict_rows = safe_query(self.wmi, "SELECT * FROM MSStorageDriver_FailurePredictStatus", "root\\wmi")
        result: List[DiskInfo] = []
        for idx, row in enumerate(drives):
            size_bytes = to_int(row.get("Size"), 0)
            info = DiskInfo(
                model=str(row.get("Model") or "").strip(),
                size=human_bytes(size_bytes) if size_bytes else "N/A",
                size_bytes=size_bytes,
                interface=str(row.get("InterfaceType") or "").strip(),
                serial=str(row.get("SerialNumber") or "").strip(),
                media_type=str(row.get("MediaType") or "").strip(),
                status=str(row.get("Status") or "").strip(),
            )
            raw_attrs: Dict[int, Tuple[int, int]] = {}
            if idx < len(smart_rows):
                raw_attrs = parse_smart(smart_rows[idx].get("VendorSpecific"))
            predict_failure: Optional[bool] = None
            if idx < len(predict_rows):
                value = predict_rows[idx].get("PredictFailure")
                if value is not None:
                    predict_failure = bool(value)
            info.smart = _build_smart(raw_attrs, predict_failure)
            if info.status.upper() == "OK":
                info.status = "正常"
            result.append(info)
        if not result:
            log.info("未检测到 Win32_DiskDrive")
        return result
