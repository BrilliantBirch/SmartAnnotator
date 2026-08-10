# -*- coding: utf-8 -*-
"""
欢迎页 - WelcomePage

按 UI 文档 §5.1：居中图标 + 标题 + 版本 + 两主按钮（格式转换/自动标注）。

作者: BaiBinnan
创建日期: 2026-08-10
"""

from PySide6.QtWidgets import QLabel, QHBoxLayout
from PySide6.QtCore import Signal, Qt

from .base_page import BasePage
from ..widgets.buttons import PrimaryButton
from .. import __version__


class WelcomePage(BasePage):
    """欢迎页 - 应用入口，提供两个功能入口按钮。

    Signals:
        format_requested: 请求跳转格式转换页。
        annotate_requested: 请求跳转自动标注页。
    """

    format_requested = Signal()
    annotate_requested = Signal()

    def __init__(self, parent=None):
        """初始化欢迎页。"""
        super().__init__(parent)
        # 欢迎页不需滚动，使用居中布局
        self._scroll.setWidgetResizable(True)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 应用图标（使用 emoji 占位，可替换为 resources/images/welcome.png）
        icon = QLabel("✦")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 64px; color: #18181b; border: none;")

        # 标题
        title = QLabel("VAI_E_SmartAnnotator")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 28px; font-weight: 700; color: #18181b; border: none;"
        )

        # 版本号
        version = QLabel(f"版本 {__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("color: #71717a; font-size: 14px; border: none;")

        # 两主按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_format = PrimaryButton("格式转换")
        self.btn_annotate = PrimaryButton("自动标注")
        btn_layout.addWidget(self.btn_format)
        btn_layout.addWidget(self.btn_annotate)

        self.content_layout.addStretch()
        self.content_layout.addWidget(icon)
        self.content_layout.addWidget(title)
        self.content_layout.addWidget(version)
        self.content_layout.addLayout(btn_layout)
        self.content_layout.addStretch()

        # 连接按钮 → 页面跳转信号
        self.btn_format.clicked.connect(self.format_requested.emit)
        self.btn_annotate.clicked.connect(self.annotate_requested.emit)

    def title(self) -> str:
        """返回页面标题。"""
        return "欢迎"
