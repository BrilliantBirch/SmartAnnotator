# -*- coding: utf-8 -*-
"""
颜色调色板 — 用 numpy 生成彩虹色（替代旧版 matplotlib 依赖）

供转换器为不同类别分配可视化颜色。COLORS 为 (N, 3) float32 数组，取值 0-1。

作者: BaiBinnan
创建日期: 2026-08-10
"""

import numpy as np


def _hsv_to_rgb(h: np.ndarray, s: float = 1.0, v: float = 1.0) -> np.ndarray:
    """HSV → RGB 转换（向量化）。

    Args:
        h: 色相数组（0-1）。
        s: 饱和度。
        v: 明度。

    Returns:
        (N, 3) RGB 数组，取值 0-1。
    """
    h = np.asarray(h, dtype=np.float32)
    i = np.floor(h * 6.0).astype(np.int32) % 6
    f = h * 6.0 - np.floor(h * 6.0)
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    # 按 sextant 索引选取各通道值（np.choose 实现查表，避免掩码广播问题）
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def rainbow_fill(size: int = 80) -> np.ndarray:
    """生成彩虹色列表（替代 matplotlib jet colormap）。

    Args:
        size: 颜色数量。

    Returns:
        (size, 3) float32 数组，取值 0-1。
    """
    hues = np.linspace(0.0, 1.0, size, endpoint=False).astype(np.float32)
    return _hsv_to_rgb(hues)


# 模块级调色板，供转换器使用（与旧版 COLORS 形状/用法一致）
COLORS = rainbow_fill(80).astype(np.float32).reshape(-1, 3)
