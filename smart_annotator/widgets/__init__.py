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
更新: 2026-09-07 右侧三分区独立 Dock 化：RightPanel 聚合面板删除，改为
      导出 LabelSection / ObjectSection / FileSection 三个独立分区控件
更新: 2026-09-08 恢复导出 RightPanel 聚合面板（主窗口以单一 QDockWidget
      承载，内部垂直 QSplitter 纵向装载三分区）
"""

from .buttons import PrimaryButton, SecondaryButton
from .cards import Card
from .fields import PathField, LabeledSpin, CustomItemWidget, apply_click_to_focus
from .dialogs import chooseDir, chooseFile, showMessageBox
from .preview import FilePreviewWidget
from .canvas import Canvas
from .left_toolbar import LeftToolbar
from .right_panel import FileSection, LabelSection, ObjectSection, RightPanel
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
    "LabelSection",
    "ObjectSection",
    "FileSection",
    "RightPanel",
    "ShapeDialog",
]
