# -*- coding: utf-8 -*-
r"""构建期工具：用 NVRTC 把 cuda_source.CUDA_KDF_SRC 编译成多档 PTX 并内嵌。

用法：  .venv\Scripts\python.exe tools\gen_ptx.py
产物：  src/benchmark/kdf_ptx.py   （zlib+base64，运行时无需 nvrtc）
"""
from __future__ import annotations

import base64
import ctypes
import glob
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from src.benchmark.cuda_source import CUDA_KDF_SRC  # noqa: E402

SITE = os.path.join(sys.prefix, "Lib", "site-packages")
# 只要两档：75 覆盖 Turing~Hopper（PTX 向前兼容，驱动 JIT），120 覆盖 Blackwell
ARCHES = ["compute_75", "compute_120"]


def find_nvrtc() -> str:
    cands = glob.glob(os.path.join(SITE, "nvidia", "**", "nvrtc64_*.dll"), recursive=True)
    cands += glob.glob(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\**\nvrtc64_*.dll",
                       recursive=True) if os.name == "nt" else []
    if not cands:
        raise SystemExit("找不到 nvrtc64_*.dll，请先 pip install nvidia-cuda-nvrtc")
    return cands[0]


def main() -> int:
    path = find_nvrtc()
    os.add_dll_directory(os.path.dirname(path))
    os.environ["PATH"] = os.path.dirname(path) + os.pathsep + os.environ.get("PATH", "")
    nvrtc = ctypes.WinDLL(path)

    out: dict[str, bytes] = {}
    for arch in ARCHES:
        prog = ctypes.c_void_p()
        rc = nvrtc.nvrtcCreateProgram(ctypes.byref(prog), CUDA_KDF_SRC.encode(), b"kdf.cu", 0, None, None)
        if rc != 0:
            print("  create failed", rc)
            continue
        opts = [("--gpu-architecture=" + arch).encode(), b"--std=c++14"]
        arr = (ctypes.c_char_p * len(opts))(*opts)
        rc = nvrtc.nvrtcCompileProgram(prog, len(opts), arr)
        sz = ctypes.c_size_t()
        if rc != 0:
            nvrtc.nvrtcGetProgramLogSize(prog, ctypes.byref(sz))
            log = ctypes.create_string_buffer(sz.value)
            nvrtc.nvrtcGetProgramLog(prog, log)
            print(f"  {arch}: FAIL\n{log.value.decode('utf-8','replace')[:800]}")
            continue
        nvrtc.nvrtcGetPTXSize(prog, ctypes.byref(sz))
        buf = ctypes.create_string_buffer(sz.value)
        nvrtc.nvrtcGetPTX(prog, buf)
        out[arch.split("_")[1]] = buf.value
        print(f"  {arch}: OK  ptx={len(buf.value)} bytes")

    if not out:
        raise SystemExit("没有任何架构编译成功")

    # 内容相同的 PTX 只保留最低架构（PTX 向前兼容）
    seen: dict[bytes, str] = {}
    uniq: dict[str, bytes] = {}
    for k, v in sorted(out.items(), key=lambda kv: int(kv[0])):
        if v in seen:
            print(f"  arch {k} 与 {seen[v]} 内容相同，去重")
            continue
        seen[v] = k
        uniq[k] = v
    out = uniq

    lines = [
        '"""自动生成，请勿手改 —— 由 tools/gen_ptx.py 从 cuda_source.py 编译。"""',
        "from __future__ import annotations",
        "",
        "import base64",
        "import zlib",
        "",
        "# 键为 compute capability（如 '120' 表示 sm_120），值为 zlib+base64 的 PTX",
        "_PTX_B64: dict[str, str] = {",
    ]
    for k, v in sorted(out.items(), key=lambda kv: int(kv[0])):
        b64 = base64.b64encode(zlib.compress(v, 9)).decode("ascii")
        lines.append(f'    "{k}": (')
        for i in range(0, len(b64), 100):
            lines.append(f'        "{b64[i:i+100]}"')
        lines.append("    ),")
    lines += [
        "}",
        "",
        "",
        "def ptx_for(cc: int) -> tuple[str, bytes]:",
        '    """挑选不超过设备算力的最高档 PTX；都没有则用最低档（PTX 向前兼容）。"""',
        "    keys = sorted(int(k) for k in _PTX_B64)",
        "    chosen = None",
        "    for k in keys:",
        "        if k <= cc:",
        "            chosen = k",
        "    if chosen is None:",
        "        chosen = keys[0]",
        "    key = str(chosen)",
        "    return key, zlib.decompress(base64.b64decode(_PTX_B64[key]))",
        "",
    ]
    dest = os.path.join(ROOT, "src", "benchmark", "kdf_ptx.py")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("已写入", dest, os.path.getsize(dest), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
