"""全局常量与单位约定。"""
from __future__ import annotations

APP_NAME = "HardwareInspector"
APP_DISPLAY_NAME = "硬件检测与基准测试工具"
APP_VERSION = "1.0.0"
ORG_NAME = "HardwareInspector"

# 单位
UNIT_C = "°C"
UNIT_MHZ = "MHz"
UNIT_MB = "MB"
UNIT_MBPS = "MB/s"
UNIT_GBPS = "GB/s"
UNIT_IOPS = "IOPS"
UNIT_NS = "ns"
UNIT_PERCENT = "%"
UNIT_SCORE = "分"

# 采样
DEFAULT_SAMPLE_INTERVAL_MS = 1000
DEFAULT_CHART_POINTS = 120

# 计分等级阈值（总分 0-10000）
GRADE_BANDS = (
    (9000, "S", "旗舰级"),
    (7500, "A", "高性能"),
    (6000, "B", "主流"),
    (4000, "C", "入门"),
    (0, "D", "基础"),
)

# Windows 处理器架构码映射
ARCH_MAP = {
    0: "x86",
    1: "MIPS",
    2: "Alpha",
    3: "PowerPC",
    5: "ARM",
    6: "Itanium",
    9: "x64",
    12: "ARM64",
}
