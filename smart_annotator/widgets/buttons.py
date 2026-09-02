# -*- coding: utf-8 -*-
"""
按钮控件 - PrimaryButton / SecondaryButton

按 UI 设计文档 §4 设计系统：黑白灰主色，12px 圆角。

作者: BaiBinnan
创建日期: 2026-08-10
"""

from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt


class PrimaryButton(QPushButton):
    """主按钮 - 深色背景 #18181b，白色文字 #fafafa。

    用于主要操作（开始转换、开始标注等）。
    """

    def __init__(self, text: str, parent=None):
        """初始化主按钮。

        Args:
            text: 按钮文字。
            parent: 父控件。
        """
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            """
            QPushButton {
                background-color: #18181b;
                color: #fafafa;
                border: 0;
                border-radius: 12px;
                padding: 8px 18px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #27272a; }
            QPushButton:pressed { background-color: #3f3f46; }
            QPushButton:disabled { background-color: #a1a1aa; color: #fafafa; }
        """
        )


class SecondaryButton(QPushButton):
    """次按钮 - 白色背景，灰色边框 #e4e4e7。

    用于次要操作（浏览、导入/导出配置、停止等）。
    """

    def __init__(self, text: str, parent=None):
        """初始化次按钮。

        Args:
            text: 按钮文字。
            parent: 父控件。
        """
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            """
            QPushButton {
                background-color: #ffffff;
                color: #18181b;
                border: 1px solid #e4e4e7;
                border-radius: 12px;
                padding: 8px 18px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #f4f4f5; }
            QPushButton:pressed { background-color: #e4e4e7; }
            QPushButton:disabled { color: #a1a1aa; border-color: #f4f4f5; }
        """
        )
