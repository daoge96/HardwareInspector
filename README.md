# HardwareInspector

> Windows 硬件检测 · 基准测试 · 压力测试一体化桌面工具（PySide6 GUI）

HardwareInspector 是一款面向 Windows 10/11 的硬件信息与性能测试工具：一键检测 CPU / GPU / 内存 / 硬盘详细规格，提供多线程基准跑分、压力稳定性测试、实时温度/频率/占用曲线，并可导出 HTML 评分报告，支持打包为单文件 exe（带管理员权限）。

## ✨ 功能特性

| 模块 | 检测 | 基准 | 压力/监控 |
| --- | --- | --- | --- |
| CPU | 型号/核心线程/主频睿频/L1-L3 缓存/架构制程 | 单核·多核 整数/浮点/压缩/加密 | 满载稳定性 + 温度/频率/占用实时曲线 |
| GPU | 型号/显存/驱动/流处理器 | OpenGL 渲染 + 并行计算 | 核心频率/显存/温度/风扇实时曲线 |
| 内存 | 容量/通道/频率/时序/颗粒厂商 | 读/写/复制带宽 + 访问延迟 | 满载分配写入校验 |
| 硬盘 | 型号/容量/接口/SMART 健康 | 顺序读写 + 4K 随机读写 + IOPS | 通电时间/累计写入/剩余寿命 |

- 主页实时刷新各硬件关键状态，各模块独立页签，一键启动/停止
- 全部耗时测试在独立线程/子进程执行，**UI 永不卡顿**，可随时安全中止
- 结束自动汇总评分并导出 HTML 报告
- 深色主题、高 DPI 适配

## 🖼️ 界面截图

> 截图占位（运行后自行补充到 docs/ 目录）

```
docs/home.png      主页实时监控
docs/cpu.png       CPU 页签
docs/report.png    HTML 报告示例
```

## 🔧 环境要求

- Windows 10 / 11 x64
- Python 3.11（推荐；3.10 可用）
- 建议以**管理员身份**运行，以读取温度 / SMART

## 🚀 源码运行

```bat
python -m pip install -r requirements.txt
python main.py
```

## 📦 打包单文件 exe

一键脚本：

```bat
build.bat
```

其等价的完整 PyInstaller 命令为：

```bat
python make_icon.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin ^
  --name HardwareInspector ^
  --icon assets\icon.ico ^
  --version-file version_info.txt ^
  --add-data "assets;assets" ^
  --add-data "src/report/template.html;src/report" ^
  --hidden-import PySide6.QtCharts ^
  --hidden-import PySide6.QtOpenGL ^
  --hidden-import PySide6.QtOpenGLWidgets ^
  --collect-submodules PySide6 ^
  main.py
```

产物位于 `dist\HardwareInspector.exe`。

## 📜 免责声明

评分基于内置参考基准，仅用于横向比较，不代表绝对性能；温度/SMART 读数受主板与驱动器固件影响，缺失时显示 `N/A`。
