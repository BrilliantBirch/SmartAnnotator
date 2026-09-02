# -*- coding: utf-8 -*-
"""
widgets 子包 — 公共控件封装

按 UI 设计文档 §4 封装基础控件，保持极简黑白灰风格统一。
    - buttons: PrimaryButton / SecondaryButton
    - cards: Card(QFrame) 含标题 + 内容区
    - fields: PathField / LabeledSpin / CustomItemWidget
    - dialogs: chooseDir / chooseFile / showMessageBox

作者: BaiBinnan
创建日期: 2026-08-10
"""

from .buttons import PrimaryButton, SecondaryButton
from .cards import Card
from .fields import PathField, LabeledSpin, CustomItemWidget, apply_click_to_focus
from .dialogs import chooseDir, chooseFile, showMessageBox
from .preview import FilePreviewWidget
from .canvas import Canvas
from .left_toolbar import LeftToolbar
from .right_panel import RightPanel
from .shape_dialog import ShapeDialog

__all__ = [
    "PrimaryButton",
    "SecondaryButton",
    "Card",
    "PathField",
    "LabeledSpin",
    "CustomItemWidget",
    "apply_click_to_focus",
    "FilePreviewWidget",
    "chooseDir",
    "chooseFile",
    "showMessageBox",
    "Canvas",
    "LeftToolbar",
    "RightPanel",
    "ShapeDialog",
]
