# -*- coding: utf-8 -*-
"""
页面基类 - BasePage(QWidget)

提供页面标题接口与可滚动内容区。所有页面继承此类。

作者: BaiBinnan
创建日期: 2026-08-10
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea
from PySide6.QtCore import Qt


class BasePage(QWidget):
    """页面基类 - 提供标题接口与可滚动内容容器。

    子类通过 self.content_layout 添加控件，内容区自动支持滚动（小屏不溢出）。

    Attributes:
        content_layout: 内容区垂直布局（子类向其添加控件）。
    """

    def __init__(self, parent=None):
        """初始化页面，建立可滚动内容区。"""
        super().__init__(parent)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)

        # 可滚动内容区（UI 文档 §6.3：主内容用 QScrollArea 包裹）
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._content = QWidget()
        self.content_layout = QVBoxLayout(self._content)
        self.content_layout.setContentsMargins(24, 20, 24, 20)
        self.content_layout.setSpacing(16)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._scroll.setWidget(self._content)
        self._outer.addWidget(self._scroll)

    def title(self) -> str:
        """返回页面标题（子类重写）。

        Returns:
            页面标题字符串。
        """
        return ""

    def add_widget(self, widget) -> None:
        """向内容区添加控件。

        Args:
            widget: 待添加的控件。
        """
        self.content_layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        """向内容区添加子布局。

        Args:
            layout: 待添加的布局。
        """
        self.content_layout.addLayout(layout)
