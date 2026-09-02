# -*- coding: utf-8 -*-
"""
pages 子包 — 三页界面（欢迎/转换/标注）

按 UI 设计文档 §5 实现三页架构，每页继承 BasePage。

作者: BaiBinnan
创建日期: 2026-08-10
"""

from .base_page import BasePage
from .welcome_page import WelcomePage
from .convert_page import ConvertPage
from .annotate_page import AnnotatePage

__all__ = ["BasePage", "WelcomePage", "ConvertPage", "AnnotatePage"]
