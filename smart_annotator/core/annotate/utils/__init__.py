# -*- coding: utf-8 -*-
"""annotate 内部工具子包 - 设备信息与坐标变换"""

from .device import get_cpu_info, get_gpu_info, get_total_memory
from .opreate import resize_image, scale_boxes, scale_coords, process_mask, scale_image

__all__ = [
    "get_cpu_info",
    "get_gpu_info",
    "scale_coords",
    "get_total_memory",
    "resize_image",
    "scale_boxes",
    "process_mask",
    "scale_image",
]
