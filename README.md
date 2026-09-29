# HardwareInspector

> Windows 硬件检测 · 基准测试 · 压力测试一体化桌面工具（PySide6 GUI）

HardwareInspector 是一款面向 Windows 10/11 的硬件信息与性能测试工具：一键检测 CPU / GPU / 内存 / 硬盘详细规格，提供**基于真实破译吞吐的 CPU/GPU 解密基准**、多线程综合基准、压力稳定性测试、实时功率/温度/主频/有效频率曲线，并可导出 HTML 评分报告，支持打包为单文件 exe（带管理员权限）。

## ⬇️ 下载

**[→ Releases v1.1.0](https://github.com/daoge96/HardwareInspector/releases/tag/v1.1.0)**

| 文件 | 说明 |
| --- | --- |
| HardwareInspector-1.1.0-portable.zip | **推荐**。解压后双击里面的 exe，启动约 2 秒 |
| HardwareInspector.exe | 单文件版 243MB，便于拷贝；首次启动要先自解压，约 10~30 秒 |

两个产物都跑过内置短自检（KDF 与 hashlib 逐字节对拍 + 32 进程 spawn + CUDA 内核自检），结果均为 PASS。

## 🆕 v1.1.0 主要变更

### 新增：解密基准（CPU / GPU）

算法取自 [硬解密码.py](https://github.com/daoge96) 文档密码破译器的核心校验环路 —— 也就是真正决定破译速度的那条链：

```
H  = SHA512(salt || password_utf16le)
H' = SHA512(u32le(i) || H)        重复 spin 次      ← 约 99.9% 的开销
k1 = SHA512(H || BLK_VERIFIER)[:32]
k2 = SHA512(H || BLK_VERIFIER_HASH)[:32]
校验 SHA512(AES256-CBC(evi,k1)[:16])[:16] == AES256-CBC(evh,k2)[:16]
```

指标是**每秒可尝试的候选密码数**，与真实破译吞吐同量纲。CPU 走多进程跑满全部逻辑核心，GPU 走 CUDA 内核。

参考机（R9 8945HX 32 线程 + RTX 5060 Laptop，spin=10 万）实测：

| 项目 | 速度 |
| --- | --- |
| GPU | 约 12 240 次/秒（占用 99%，速率波动 0.5%） |
| CPU 单核 | 约 16.6 次/秒 |
| CPU 全核（32 进程） | 约 180 次/秒 |
| 多核加速比 | 约 10.9x |

**评分基线：1000 分 = 上述参考机水平。**高于 1000 就是比它快。

测试强度可选快速 / 标准 / 严格，分别约 15 / 40 / 90 秒每项。

### 修复的 9 个问题

| # | 问题 | 处理 |
| --- | --- | --- |
| 1 | CPU 测不出多核性能：旧版用 `pool.map` 跑固定作业量，每进程仅约 15ms 的活，进程启动开销占大头，"加速比"基本是噪声 | 单核/全核各跑稳态窗口，用 ready/go 事件把 spawn 启动耗时挡在计时窗口外，输出真实加速比与并行效率 |
| 2 | 测试太短、不满载、不严谨 | 预热（不计分）+ 定时窗口 + 稳态取值；0.5s 采样占用做饱和校验；波动率与占用共同决定**可信度**，不达标自动降级 |
| 3 | 界面不精致 | 重做深色主题、顶部标题栏与状态徽章；卡片改原地更新（旧版每秒 `deleteLater` 重建全部标签，滚动位置与选中文本都会丢） |
| 4 | 需要按破译算法给 CPU/GPU 打分 | 见上方「解密基准」 |
| 5 | 所有基准收了 `stop_event` 却从不检查，"停止"按钮是假的 | CPU/内存/硬盘/GPU 全部响应停止，中止后已测数据仍有效 |
| 6 | "GPU 并行计算"其实是 numpy 的 `a@b`，跑在 CPU 的 BLAS 上 | 结果里显式标注执行设备；真正算力由 CUDA 内核给出 |
| 7 | 内存"读取带宽"测法错误：gather 在计时之外，只对已生成数组求和 | 整个 gather 计入，区分顺序写 / 顺序复制 / 随机读 / 指针追逐延迟 |
| 8 | 硬盘测试全打在页缓存上；2 万次随机写只在最后 fsync 一次，IOPS 虚高 | 读前刷页缓存测冷读；随机写分缓存口径与每 32 次落盘口径，成绩取落盘；另加 QD1/QD32 |
| 9 | 每项只测一遍，单次抖动直接进成绩 | 关键项重复取中位数，并给出速率波动率 |

## ✨ 功能特性

| 模块 | 检测 | 基准 | 压力/监控 |
| --- | --- | --- | --- |
| CPU | 型号/核心线程/主频睿频/L1-L3 缓存/架构制程 | **解密速度（多核 KDF）** + 单核·全核整数/浮点/压缩/加密 | 满载稳定性 + **功率/温度/主频/有效频率** 实时显示与曲线 |
| GPU | 型号/显存/驱动/流处理器 | **解密速度（CUDA KDF）** + OpenGL 渲染 | **功率/温度/主频/有效频率**/显存/风扇 实时曲线 |
| 内存 | 容量/通道/频率/时序/颗粒厂商 | 顺序写·复制 + 随机读 gather + 访问延迟 | 满载分配写入校验 |
| 硬盘 | 型号/容量/接口/SMART 健康 | 顺序读写（冷读）+ 4K 随机读写 + QD1/QD32 + 落盘 IOPS | 通电时间/累计写入/剩余寿命 |

- 主页实时刷新各硬件关键状态（含功率/温度），各模块独立页签，一键启动/停止
- 全部耗时测试在独立线程/子进程执行，**UI 永不卡顿**，可随时安全中止
- 结束自动汇总评分并导出 HTML 报告（含生成时的实时指标）
- 深色主题、高 DPI 适配

## 🔐 GPU 为什么不用 cupy

本机开启了 **Smart App Control**（应用控制策略），cupy 的
`cupy_backends\cuda\api\_driver_enum*.pyd` 被策略拦截报 `WinError 4551`，整个 cupy 无法导入，重装无效（属机器级策略）。

因此改为用 `ctypes` 直接调用随显卡驱动安装、带 NVIDIA 签名的 `nvcuda.dll`，CUDA 内核以 PTX 内嵌（`compute_75` / `compute_120` 两档，驱动 JIT 编译）。运行时既不需要 CUDA Toolkit 也不需要 nvrtc。

内核启动前会先与 `hashlib` 逐字节对拍（KDF 结果 + AES 校验分支），对拍不过直接判失败。

> 注意：这也意味着 GPU 解密基准只支持 NVIDIA 显卡。AMD/Intel 核显会显示"不可用"，CPU 部分不受影响。

## 🌡️ 功率 / 有效频率数据来源

- CPU/GPU 温度、功率、有效频率：优先读取 **LibreHardwareMonitor / OpenHardwareMonitor** 的 WMI 传感器
- NVIDIA 显卡的温度/功率/主频/有效频率（SM 时钟）优先走 **NVML**
- 缺失项显示 `N/A`（不静默跳过）

## 🔧 环境要求

- Windows 10 / 11 x64
- Python 3.10+（开发用 3.13）
- 建议以**管理员身份**运行，以读取温度 / 功率 / SMART
- 仅开发时需要：`nvidia-cuda-nvrtc` + `nvidia-cuda-runtime`（重新生成内嵌 PTX 用，非运行时依赖）

## 🚀 源码运行

```bat
python -m pip install -r requirements.txt
python make_icon.py
python main.py
```

## ✅ 自检（跑通即停，不会长时间压机器）

```bat
python main.py --selftest            # 只跑 2 秒窗口：KDF 对拍 + spawn 链路 + CUDA 自检
python main.py --selftest --cpu-only
```

结果写到 `%APPDATA%\HardwareInspector\logs\selftest.txt`，任一环节不过返回 FAIL。

## 📦 打包

```bat
build.bat
```

产物：`dist\HardwareInspector.exe`（单文件）。

改动过 `src/benchmark/cuda_source.py` 之后需要重新生成内嵌 PTX：

```bat
.venv\Scripts\python.exe tools\gen_ptx.py
```

## 📁 目录结构

```
main.py                     入口（freeze_support 放在 Qt 导入之前）
src/benchmark/
    crypto_bench.py         CPU/GPU 解密基准（本版核心）
    cuda_source.py          CUDA 内核源码（SHA512-KDF）
    cuda_driver.py          nvcuda.dll 的 ctypes 最小封装
    kdf_ptx.py              由 gen_ptx.py 生成的内嵌 PTX
    py_aes.py               纯 Python AES（只用于构造自检向量）
    _sampler.py             占用率采样（饱和校验）
    cpu_bench.py            单核/全核综合基准
    mem_bench.py  disk_bench.py  gpu_bench.py
src/ui/                     各页面与控件
tools/gen_ptx.py            重新生成内嵌 PTX
tools/check_kdf.py          与参考实现对拍
```

## 📜 免责声明

评分基于内置参考基准，仅用于横向比较，不代表绝对性能；温度/功率/SMART 读数受主板与驱动器固件影响，缺失时显示 `N/A`。MIT License。
