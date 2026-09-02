# -*- coding: utf-8 -*-
"""
pages 子包 — 页面模块（转换/标注）

每页继承 BasePage，作为标注编辑器主窗口的对话框复用。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-02 删除欢迎页
"""

from .base_page import BasePage
from .convert_page import ConvertPage
from .annotate_page import AnnotatePage

__all__ = ["BasePage", "ConvertPage", "AnnotatePage"]
