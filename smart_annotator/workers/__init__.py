# -*- coding: utf-8 -*-
"""
workers 子包 — PySide6 后台工作线程

包含：
    - BaseWorker: 基础线程类（暂停/恢复/停止 + run_callback 适配器）
    - ConvertWorker: 格式转换线程
    - AnnotationWorker: 自动标注线程
    - AnalyzeWorker: 数据集一键分析线程
    - LabelScanWorker: 标签扫描统计线程
    - SingleAnnotateWorker: 单张图片自动标注线程
    - UpdateCheckWorker / UpdateDownloadWorker: 更新检查与下载线程

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-11 docstring 补全为实际全部 worker 清单（本包 __all__
      维持基础三件套导出，其余 worker 按模块路径按需导入）
"""

from .base_worker import BaseWorker
from .convert_worker import ConvertWorker
from .annotate_worker import AnnotationWorker

__all__ = ["BaseWorker", "ConvertWorker", "AnnotationWorker"]
