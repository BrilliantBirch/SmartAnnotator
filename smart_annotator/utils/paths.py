# -*- coding: utf-8 -*-
"""
路径工具 — 资源路径解析与项目根目录

修复旧版 resource_path 依赖 os.path.abspath(".") 的脆弱性：
开发模式用包根目录，打包后用 sys._MEIPASS。

作者: BaiBinnan
创建日期: 2026-08-10
"""

import os
import sys
from pathlib import Path


# 项目根目录（开发模式为 smart_annotator/ 的父目录，打包后为 exe 所在目录）
def _compute_root() -> Path:
    """计算项目根目录。

    打包后（PyInstaller）sys.frozen 为 True，根目录为 exe 所在目录；
    开发模式下取 smart_annotator 包的父目录。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # smart_annotator/utils/paths.py → 上溯两级为项目根
    return Path(__file__).resolve().parent.parent.parent


ROOT = str(_compute_root())


def resource_path(relative_path: str) -> str:
    """获取打包后资源的绝对路径。

    开发模式：基于包根目录解析（不依赖 cwd）。
    打包模式（PyInstaller onefile/dir）：基于 sys._MEIPASS 解析。

    Args:
        relative_path: 资源相对路径（如 "app.ico"）。

    Returns:
        资源绝对路径字符串。
    """
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path is not None:
        return os.path.join(base_path, relative_path)
    # 开发模式：资源位于项目根目录下
    return os.path.join(ROOT, relative_path)
