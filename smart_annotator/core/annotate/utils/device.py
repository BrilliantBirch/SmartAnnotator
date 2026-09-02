# -*- coding: utf-8 -*-
"""
设备信息采集 - CPU/GPU/内存

作者: BaiBinnan
创建日期: 2026-08-10
"""

import platform
import psutil
from smart_annotator.utils import LOGGER


def get_gpu_info():
    """获取 GPU 信息。

    Returns:
        int: 1-成功，-1-失败。
    """
    LOGGER.info("使用CUDA")
    if platform.system() == "Windows":
        try:
            import pynvml

            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpu_name = pynvml.nvmlDeviceGetName(handle)
                total_memory = info.total / (1024**3)  # 转换为 GB
                LOGGER.info(f"显卡型号: {gpu_name}, 显存大小: {total_memory:.2f} GB")
            pynvml.nvmlShutdown()
            return 1
        except pynvml.NVMLError as e:
            LOGGER.error(f"NVIDIA 显卡信息获取失败: {e}")
            return -1


def get_cpu_info():
    """获取 CPU 信息。

    Returns:
        int: 1-成功，-1-失败。
    """
    LOGGER.info("使用CPU")
    cpu_info = {}
    try:
        # 获取 CPU 型号
        cpu_info["型号"] = platform.processor()
        if not cpu_info["型号"]:
            cpu_info["型号"] = psutil.cpu_info().brand_raw

        # 获取物理核心数
        cpu_info["物理核心数"] = psutil.cpu_count(logical=False)

        # 获取逻辑核心数（线程数）
        cpu_info["逻辑核心数"] = psutil.cpu_count(logical=True)

        # 获取 CPU 频率
        cpu_freq = psutil.cpu_freq()
        cpu_info["当前频率"] = f"{cpu_freq.current:.2f} MHz"
        cpu_info["最小频率"] = f"{cpu_freq.min:.2f} MHz"
        cpu_info["最大频率"] = f"{cpu_freq.max:.2f} MHz"
        for key, value in cpu_info.items():
            LOGGER.info(f"{key}: {value}")
        return 1
    except Exception as e:
        LOGGER.error(f"获取 CPU 信息时出错: {e}")
        return -1


def get_total_memory():
    """获取内存信息。

    Returns:
        int: 1-成功，-1-失败。
    """
    try:
        # 获取系统内存信息
        memory_info = psutil.virtual_memory()
        # 获取总内存大小，单位为字节
        total_memory_bytes = memory_info.total
        # 将字节转换为 GB，保留两位小数
        total_memory_gb = round(total_memory_bytes / (1024**3), 2)
        LOGGER.info(f"系统内存大小：{total_memory_gb}GB")
        return 1
    except Exception as e:
        LOGGER.error(f"获取内存大小时出错: {e}")
        return -1
