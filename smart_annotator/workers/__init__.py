# -*- coding: utf-8 -*-
"""
workers 子包 — PySide6 后台工作线程

包含：
    - BaseWorker: 基础线程类（暂停/恢复/停止 + run_callback 适配器）
    - ConvertWorker: 格式转换线程
    - AnnotationWorker: 自动标注线程

作者: BaiBinnan
创建日期: 2026-08-10
"""

from .base_worker import BaseWorker
from .convert_worker import ConvertWorker
from .annotate_worker import AnnotationWorker

__all__ = ["BaseWorker", "ConvertWorker", "AnnotationWorker"]
