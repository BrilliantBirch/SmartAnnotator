# -*- coding: utf-8 -*-
"""
使用说明书阅读窗 — 帮助菜单内置文档查看器

以 QTextBrowser 渲染 docs/manual.md（QTextDocument.setMarkdown，
GitHub 方言原生支持表格/代码块），不依赖外部 PDF 阅读器。
手册源文件经 resource_path 解析：开发态位于项目根 docs/，
打包态由 build.py --add-data 写入 PyInstaller 内容目录 docs/。

作者: BaiBinnan
创建日期: 2026-09-04
"""

from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
)

from ..utils import resource_path

# 手册源文件相对路径（项目根 docs/，打包后位于内容目录 docs/）
MANUAL_RELPATH = "docs/manual.md"

# 正文字体（中文文档使用系统自带微软雅黑）
BODY_FONT_FAMILY = "Microsoft YaHei"
BODY_FONT_SIZE = 10


class ManualDialog(QDialog):
    """使用说明书阅读窗：QTextBrowser 加载并渲染 Markdown 手册。"""

    def __init__(self, parent=None):
        """初始化阅读窗布局并加载手册内容。

        Args:
            parent: 父窗口（主窗口，随其销毁自动回收）。
        """
        super().__init__(parent)
        self.setWindowTitle("使用说明书")
        self.resize(920, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 文本浏览区：只读、可滚动、支持外部链接跳转
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFont(QFont(BODY_FONT_FAMILY, BODY_FONT_SIZE))
        layout.addWidget(self.browser, 1)

        # 底部关闭按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_manual()

    def _load_manual(self) -> None:
        """加载并渲染手册 Markdown；文件缺失/读取失败时显示提示文案。"""
        md_path = Path(resource_path(MANUAL_RELPATH))
        if md_path.is_file():
            try:
                self.browser.setMarkdown(md_path.read_text(encoding="utf-8"))
                # setMarkdown 会重置默认字体，渲染前重新指定中文字体
                self.browser.document().setDefaultFont(
                    QFont(BODY_FONT_FAMILY, BODY_FONT_SIZE)
                )
                return
            except (OSError, UnicodeDecodeError) as e:
                text = f"手册文件读取失败: {e}"
        else:
            text = f"未找到手册文件: {MANUAL_RELPATH}\n（请确认安装包完整）"
        self.browser.setPlainText(text)
