# -*- coding: utf-8 -*-
"""
卡片控件 - Card(QFrame)

按 UI 设计文档 §4：白底、1px 边框 #e4e4e7、12px 圆角。
卡片含标题 QLabel（muted #71717a）+ 内容区垂直布局。

作者: BaiBinnan
创建日期: 2026-08-10
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget, QLayout
from PySide6.QtCore import Qt


class Card(QFrame):
    """卡片容器 - 带标题与内容区的白色圆角面板。

    Attributes:
        title_label: 卡片标题标签（muted 颜色）。
        content_layout: 内容区垂直布局，外部通过 addWidget 添加控件。
    """

    def __init__(self, title: str = "", parent=None):
        """初始化卡片。

        Args:
            title: 卡片标题，空字符串时不显示标题。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setStyleSheet(
            """
            Card {
                background-color: #ffffff;
                border: 1px solid #e4e4e7;
                border-radius: 12px;
            }
        """
        )

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(20, 16, 20, 16)
        self._main_layout.setSpacing(12)

        # 标题
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            "color: #71717a; font-size: 13px; font-weight: 600; border: none;"
        )
        if title:
            self._main_layout.addWidget(self.title_label)
        else:
            self.title_label.hide()

        # 内容区
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        self._main_layout.addLayout(self.content_layout)

    def addWidget(self, widget: QWidget) -> None:
        """向内容区添加控件。

        Args:
            widget: 待添加的控件。
        """
        self.content_layout.addWidget(widget)

    def addLayout(self, layout: QLayout) -> None:
        """向内容区添加子布局。

        Args:
            layout: 待添加的布局。
        """
        self.content_layout.addLayout(layout)
