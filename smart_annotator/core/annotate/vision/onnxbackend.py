# -*- coding: utf-8 -*-
"""
ONNX 推理后端（onnxruntime，CPU / CUDA Execution Provider）

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-04 修复 device 参数判断失效问题（DEVICE 为 IntEnum，
      原 `device != "cpu"` 恒为 True 导致 CPU 模式误建 CUDA 会话）；
      GPU 推理由 TensorRT engine 全面切换为 onnxruntime CUDA EP
      （providers 配置为 CUDA 优先 + CPU 回退，避免无 CUDA 机器直接崩溃）；
      新增 _ensure_cuda_dlls 自动定位 cuDNN（nvidia-cudnn-cu12 / torch
      自带 / conda Library\bin）并注册 DLL 搜索目录，免去用户手动配 PATH
"""

import os
import sys
import sysconfig
from pathlib import Path

import onnxruntime as ort

from smart_annotator.utils import LOGGER


_cuda_dlls_registered = False


def _ensure_cuda_dlls() -> bool:
    """注册 CUDA EP 全部依赖 DLL 的搜索目录（幂等，进程内仅执行一次）。

    onnxruntime_providers_cuda.dll 的依赖链：
        cudnn64_9.dll（cuDNN 9）+ cublas64_12/cublasLt64_12（cuBLAS）
        + cufft64_11（cuFFT）+ cudart64_12（CUDA Runtime）
    这些 DLL 不随 onnxruntime-gpu 安装，且用户程序启动环境的 PATH 可能
    不含 CUDA Toolkit bin，须显式注册搜索目录。候选位置：
        1. pip 包 nvidia-*-cu12: site-packages/nvidia/<组件>/bin（推荐，
           安装 nvidia-cudnn/cublas/cufft/cuda-runtime-cu12 即可）
        2. PyTorch 自带: site-packages/torch/lib
        3. conda 环境: <env>/Library/bin
        4. PyInstaller 打包后: exe 同级目录

    Args:
        无。

    Returns:
        至少注册一个含 CUDA 运行库的目录返回 True；否则 False。
    """
    global _cuda_dlls_registered
    if _cuda_dlls_registered:
        return True
    # 仅 Windows 支持 add_dll_directory
    if not hasattr(os, "add_dll_directory"):
        return False

    purelib = Path(sysconfig.get_paths()["purelib"])
    candidates: list[Path] = []
    # pip 包 nvidia/*/bin（cudnn/cublas/cufft/cuda_runtime 等各组件）
    nvidia_root = purelib / "nvidia"
    if nvidia_root.is_dir():
        candidates.extend(sorted(nvidia_root.glob("*/bin")))
    candidates.extend(
        [
            purelib / "torch" / "lib",  # PyTorch 自带 CUDA 运行库
            Path(sys.prefix) / "Library" / "bin",  # conda install cudnn 等
            Path(sys.executable).parent,  # PyInstaller 打包后（exe 同级目录）
        ]
    )

    registered = False
    for dll_dir in candidates:
        try:
            # 目录存在且含 .dll 才注册（nvidia 包子目录均为纯 DLL 目录）
            if dll_dir.is_dir() and any(dll_dir.glob("*.dll")):
                # 双通道注册：add_dll_directory 覆盖带 USER_DIRS 标志的
                # LoadLibraryEx 调用；PATH 追加覆盖 onnxruntime 加载
                # provider DLL 的传统 PATH 搜索（实测其不使用 USER_DIRS）
                os.add_dll_directory(str(dll_dir))
                os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")
                # LOGGER.info(f"CUDA DLL 目录已注册: {dll_dir}")
                registered = True
        except OSError as e:
            LOGGER.warning(f"注册 CUDA DLL 目录失败({dll_dir}): {e}")

    _cuda_dlls_registered = registered
    return registered


class ONNXInfer:
    """ONNX 模型推理封装（基于 onnxruntime，支持 CPU 与 CUDA EP）。"""

    def __init__(self, model_path, device="cpu"):
        """初始化 ONNX 推理会话。

        Args:
            model_path: ONNX 模型文件路径。
            device: 推理设备。字符串 "cpu" 或 DEVICE 枚举（CPU/GPU）；
                GPU 时使用 CUDAExecutionProvider（不可用时回退 CPU）。
        """
        # 统一判断设备类型（兼容字符串与 DEVICE 枚举两种传参）
        is_cpu = device == "cpu" or str(device) == "DEVICE.CPU"
        if is_cpu:
            providers = ["CPUExecutionProvider"]
        else:
            # CUDA EP 依赖 cuDNN：尝试自动定位并注册 DLL 目录（幂等）
            _ensure_cuda_dlls()
            # CUDA 优先 + CPU 回退：CUDA EP 初始化失败时 onnxruntime
            # 自动降级到列表中后续的 provider（日志会有告警但不中断）
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(model_path), providers=providers)
        # GPU 模式下记录实际生效的 provider（CUDA 不可用回退 CPU 时提示用户）
        if not is_cpu:
            active = self.session.get_providers()
            if "CUDAExecutionProvider" not in active:
                LOGGER.warning(
                    "CUDAExecutionProvider 不可用，GPU 模式已回退 CPU 推理。"
                    "请确认已安装 cuDNN 9.x（如 pip install nvidia-cudnn-cu12）"
                    "且显卡驱动支持 CUDA 12.x"
                )
        self.input_name = self.session.get_inputs()[0].name
        # 获取输入数据类型
        input_tensor = self.session.get_inputs()[0]
        input_type = input_tensor.type  # ONNX 类型字符串，如 "tensor(float16)"
        self.metadata = self.session.get_modelmeta().custom_metadata_map
        self.metadata["fp16"] = (
            "float16" in input_type.lower() or "half" in input_type.lower()
        )
        self.output_name = [x.name for x in self.session.get_outputs()]
        self.imgsz = self.metadata.get("imgsz", "[640,640]")
        self.imgsz = tuple(eval(self.imgsz))

    def predict(self, img):
        """执行推理。

        Args:
            img: 预处理后的输入张量。

        Returns:
            模型输出列表。
        """
        y = self.session.run(self.output_name, {self.input_name: img})
        return y
