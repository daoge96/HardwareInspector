r"""CUDA 驱动 API 最小封装（纯 ctypes，不依赖 cupy / PyCUDA）。

为什么不用 cupy：本机开启了 Smart App Control（应用控制策略），
cupy 的 cupy_backends\cuda\api\_driver_enum*.pyd 会被策略拦截
（WinError 4551），整个 cupy 无法导入。而随显卡驱动安装的
nvcuda.dll 带 NVIDIA 签名、不受影响，所以这里直接用驱动 API。

内核以 PTX 形式内嵌（见 kdf_ptx.py），由驱动 JIT 编译，
因此运行时不需要 CUDA Toolkit / nvrtc。
"""
from __future__ import annotations

import ctypes
import os
import sys
from typing import List, Optional, Sequence, Tuple

# CUDA 常量
CU_DEVICE_ATTRIBUTE_MULTIPROCESSOR_COUNT = 16
CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR = 75
CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR = 76
# 注意：显存总量不是 device attribute，要用 cuDeviceTotalMem_v2
CU_DEVICE_ATTRIBUTE_MAX_BLOCK_DIM_X = 2
CU_DEVICE_ATTRIBUTE_NAME = 13

CUDA_SUCCESS = 0

_DLL_NAMES = ("nvcuda.dll", "nvcuda.dll")


class CudaError(RuntimeError):
    pass


class CudaDeviceInfo:
    __slots__ = ("index", "name", "cc_major", "cc_minor", "sm_count", "mem_total_mb")

    def __init__(self, index: int, name: str, cc_major: int, cc_minor: int,
                 sm_count: int, mem_total_mb: int) -> None:
        self.index = index
        self.name = name
        self.cc_major = cc_major
        self.cc_minor = cc_minor
        self.sm_count = sm_count
        self.mem_total_mb = mem_total_mb

    @property
    def cc(self) -> int:
        return self.cc_major * 10 + self.cc_minor

    @property
    def cc_text(self) -> str:
        return f"sm_{self.cc_major}{self.cc_minor}"


_driver = None
_driver_error: Optional[str] = None


def _load_driver():
    """加载 nvcuda.dll 并声明全部函数原型（必须声明，否则 64 位指针会被截断）。"""
    global _driver, _driver_error
    if _driver is not None or _driver_error is not None:
        return _driver
    try:
        dll = ctypes.WinDLL("nvcuda.dll")
    except OSError as exc:
        _driver_error = f"未找到 nvcuda.dll（未安装 NVIDIA 驱动？）: {exc}"
        return None

    p = ctypes.c_void_p
    dll.cuInit.argtypes = [ctypes.c_uint]
    dll.cuInit.restype = ctypes.c_int
    dll.cuDeviceGet.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    dll.cuDeviceGet.restype = ctypes.c_int
    dll.cuDeviceGetCount.argtypes = [ctypes.POINTER(ctypes.c_int)]
    dll.cuDeviceGetCount.restype = ctypes.c_int
    dll.cuDeviceGetAttribute.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int]
    dll.cuDeviceGetAttribute.restype = ctypes.c_int

    for name in ("cuCtxCreate_v2", "cuCtxCreate"):
        if hasattr(dll, name):
            fn = getattr(dll, name)
            fn.argtypes = [ctypes.POINTER(p), ctypes.c_uint, ctypes.c_int]
            fn.restype = ctypes.c_int
            break
    dll.cuCtxDestroy_v2.argtypes = [p]
    dll.cuCtxDestroy_v2.restype = ctypes.c_int
    dll.cuCtxSynchronize.argtypes = []
    dll.cuCtxSynchronize.restype = ctypes.c_int

    dll.cuModuleLoadDataEx.argtypes = [ctypes.POINTER(p), p, ctypes.c_uint, p, p]
    dll.cuModuleLoadDataEx.restype = ctypes.c_int
    dll.cuModuleGetFunction.argtypes = [ctypes.POINTER(p), p, ctypes.c_char_p]
    dll.cuModuleGetFunction.restype = ctypes.c_int
    dll.cuModuleUnload.argtypes = [p]
    dll.cuModuleUnload.restype = ctypes.c_int

    dll.cuMemAlloc_v2.argtypes = [ctypes.POINTER(p), ctypes.c_size_t]
    dll.cuMemAlloc_v2.restype = ctypes.c_int
    dll.cuMemFree_v2.argtypes = [p]
    dll.cuMemFree_v2.restype = ctypes.c_int
    dll.cuMemcpyHtoD_v2.argtypes = [p, p, ctypes.c_size_t]
    dll.cuMemcpyHtoD_v2.restype = ctypes.c_int
    dll.cuMemcpyDtoH_v2.argtypes = [p, p, ctypes.c_size_t]
    dll.cuMemcpyDtoH_v2.restype = ctypes.c_int

    dll.cuLaunchKernel.argtypes = [
        p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_uint, p, ctypes.POINTER(p), ctypes.POINTER(p),
    ]
    dll.cuLaunchKernel.restype = ctypes.c_int

    rc = dll.cuInit(0)
    if rc != CUDA_SUCCESS:
        _driver_error = f"cuInit 失败 (rc={rc})，通常是驱动异常"
        return None
    _driver = dll
    return _driver


def unavailable_reason() -> Optional[str]:
    if _load_driver() is None:
        return _driver_error
    if not devices():
        return "未检测到可用的 CUDA 设备"
    return None


def total_mem_mb(dev) -> int:
    """设备显存总量（MB）—— 必须走 cuDeviceTotalMem，属性表里没有这一项。"""
    dll = _load_driver()
    if dll is None:
        return 0
    try:
        dll.cuDeviceTotalMem_v2.argtypes = [ctypes.POINTER(ctypes.c_size_t), ctypes.c_int]
        dll.cuDeviceTotalMem_v2.restype = ctypes.c_int
        n = ctypes.c_size_t(0)
        if dll.cuDeviceTotalMem_v2(ctypes.byref(n), dev) == CUDA_SUCCESS:
            return int(n.value) // (1024 * 1024)
    except Exception:
        pass
    return 0


def devices() -> List[CudaDeviceInfo]:
    dll = _load_driver()
    if dll is None:
        return []
    count = ctypes.c_int(0)
    if dll.cuDeviceGetCount(ctypes.byref(count)) != CUDA_SUCCESS or count.value <= 0:
        return []
    out: List[CudaDeviceInfo] = []
    for i in range(count.value):
        dev = ctypes.c_int(0)
        if dll.cuDeviceGet(ctypes.byref(dev), i) != CUDA_SUCCESS:
            continue

        def attr(a: int) -> int:
            v = ctypes.c_int(0)
            dll.cuDeviceGetAttribute(ctypes.byref(v), a, dev)
            return v.value

        name_buf = ctypes.create_string_buffer(128)
        # cuDeviceGetName
        try:
            dll.cuDeviceGetName.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
            dll.cuDeviceGetName.restype = ctypes.c_int
            dll.cuDeviceGetName(name_buf, 128, dev)
            name = name_buf.value.decode("utf-8", "replace")
        except Exception:
            name = f"CUDA Device {i}"
        out.append(CudaDeviceInfo(
            i, name,
            attr(CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR),
            attr(CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR),
            attr(CU_DEVICE_ATTRIBUTE_MULTIPROCESSOR_COUNT),
            total_mem_mb(dev),
        ))
    return out


class Context:
    """CUDA 上下文（不可重入，一个进程一份）。"""

    def __init__(self, index: int = 0) -> None:
        self._ctx = ctypes.c_void_p()
        self._dll = _load_driver()
        if self._dll is None:
            raise CudaError(_driver_error or "CUDA 驱动不可用")
        dev = ctypes.c_int(0)
        if self._dll.cuDeviceGet(ctypes.byref(dev), index) != CUDA_SUCCESS:
            raise CudaError(f"找不到 CUDA 设备 {index}")
        create = getattr(self._dll, "cuCtxCreate_v2", None) or getattr(self._dll, "cuCtxCreate")
        rc = create(ctypes.byref(self._ctx), 0, dev)
        if rc != CUDA_SUCCESS:
            raise CudaError(f"cuCtxCreate 失败 (rc={rc})")

    def __enter__(self) -> "Context":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._ctx:
            try:
                self._dll.cuCtxDestroy_v2(self._ctx)
            except Exception:
                pass
            self._ctx = None

    def set_current(self) -> None:
        """把上下文绑定到调用线程（内核在子线程里跑时必须先调一次）。"""
        try:
            self._dll.cuCtxSetCurrent.argtypes = [ctypes.c_void_p]
            self._dll.cuCtxSetCurrent.restype = ctypes.c_int
            self._dll.cuCtxSetCurrent(self._ctx)
        except Exception:
            pass

    def sync(self) -> None:
        rc = self._dll.cuCtxSynchronize()
        if rc != CUDA_SUCCESS:
            raise CudaError(f"cuCtxSynchronize 失败 (rc={rc})")

    def alloc(self, nbytes: int) -> ctypes.c_void_p:
        ptr = ctypes.c_void_p()
        rc = self._dll.cuMemAlloc_v2(ctypes.byref(ptr), max(int(nbytes), 1))
        if rc != CUDA_SUCCESS:
            raise CudaError(f"cuMemAlloc 失败 ({nbytes} 字节, rc={rc})")
        return ptr

    def free(self, ptr) -> None:
        if ptr:
            try:
                self._dll.cuMemFree_v2(ptr)
            except Exception:
                pass

    def to_device(self, data: bytes) -> ctypes.c_void_p:
        ptr = self.alloc(len(data))
        if data:
            self._dll.cuMemcpyHtoD_v2(ptr, ctypes.c_char_p(data), len(data))
        return ptr

    def from_device(self, ptr, nbytes: int) -> bytes:
        buf = ctypes.create_string_buffer(nbytes)
        self._dll.cuMemcpyDtoH_v2(buf, ptr, nbytes)
        return buf.raw

    def load_module(self, ptx: bytes) -> ctypes.c_void_p:
        mod = ctypes.c_void_p()
        rc = self._dll.cuModuleLoadDataEx(ctypes.byref(mod), ctypes.c_char_p(ptx), 0, None, None)
        if rc != CUDA_SUCCESS:
            raise CudaError(f"cuModuleLoadData 失败 (rc={rc})：PTX 可能不被当前驱动接受")
        return mod

    def get_function(self, mod, name: str) -> ctypes.c_void_p:
        fn = ctypes.c_void_p()
        rc = self._dll.cuModuleGetFunction(ctypes.byref(fn), mod, name.encode())
        if rc != CUDA_SUCCESS:
            raise CudaError(f"内核 {name} 未找到 (rc={rc})")
        return fn

    def launch(self, fn, grid: Tuple[int, int, int], block: Tuple[int, int, int],
               args: Sequence, shared: int = 0) -> None:
        holders = []
        for a in args:
            if isinstance(a, ctypes.c_void_p):
                holders.append(a)
            elif isinstance(a, int):
                holders.append(ctypes.c_longlong(a))
            else:
                holders.append(a)
        arr = (ctypes.c_void_p * len(holders))(
            *[ctypes.cast(ctypes.byref(h), ctypes.c_void_p) for h in holders]
        )
        rc = self._dll.cuLaunchKernel(
            fn, grid[0], grid[1], grid[2], block[0], block[1], block[2], shared, None, arr, None
        )
        if rc != CUDA_SUCCESS:
            raise CudaError(f"cuLaunchKernel 失败 (rc={rc})")
