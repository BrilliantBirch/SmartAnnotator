# -*- coding: utf-8 -*-
"""
文件列表与图像预览组件 - FilePreviewWidget

提供左右分栏布局：左侧文件列表（QListWidget），右侧图像预览（QLabel）。
支持选择文件、上一张/下一张切换、图像自适应缩放预览。

设计要点：
    - 图像使用 QPixmap 原生加载（jpg/jpeg/png/bmp），无需 cv2 依赖
    - 预览区随窗口缩放自适应（resizeEvent 中重新缩放原图）
    - 非图像文件显示占位提示，并尝试匹配同名图片预览
    - 与全局黑白灰风格一致（Card 内嵌使用）

作者: BaiBinnan
创建日期: 2026-08-11
更新: 2026-09-04 新增 A/D 快捷键切换上一张/下一张（WidgetWithChildrenShortcut
      作用域，仅本控件及其子控件聚焦时生效，不与全局快捷键冲突）
"""

import os
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap, QImage, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QSplitter,
    QSizePolicy,
)

# 支持预览的图片扩展名（小写）
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def _is_image(path: str) -> bool:
    """判断文件路径是否为支持的图片格式。

    Args:
        path: 文件路径。

    Returns:
        True 表示为可预览的图片格式。
    """
    return Path(path).suffix.lower() in _IMAGE_EXTS


class FilePreviewWidget(QWidget):
    """文件列表 + 图像预览组合控件。

    左侧 QListWidget 展示文件列表，右侧 QLabel 展示选中图片的预览。
    选择文件时发射 file_selected 信号；非图片文件尝试匹配同名图片预览。

    Attributes:
        file_list: 文件列表控件。
        preview_label: 图像预览标签。
        btn_prev: 上一张按钮。
        btn_next: 下一张按钮。
    """

    # 选中文件时发射（参数为文件绝对路径，可能为空字符串）
    file_selected = Signal(str)

    def __init__(self, parent=None):
        """初始化文件预览控件，构建左右分栏布局。"""
        super().__init__(parent)
        self._files: list[str] = []  # 文件路径列表
        self._current_pixmap: QPixmap | None = None  # 当前原始图像（用于缩放）

        # ===== 主布局：水平分割（左列表 + 右预览）=====
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ===== 左侧：文件列表 + 导航按钮 =====
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(220)
        self.file_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.file_list.currentRowChanged.connect(self._on_row_changed)
        left_layout.addWidget(self.file_list, 1)

        # 上一张 / 下一张导航
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)
        self.btn_prev = QPushButton("◀ 上一张")
        self.btn_next = QPushButton("下一张 ▶")
        self.btn_prev.clicked.connect(self._on_prev)
        self.btn_next.clicked.connect(self._on_next)
        nav_row.addWidget(self.btn_prev)
        nav_row.addStretch()
        nav_row.addWidget(self.btn_next)
        left_layout.addLayout(nav_row)

        splitter.addWidget(left_panel)

        # ===== 右侧：图像预览区 =====
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self.preview_label = QLabel("请选择文件以预览")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet(
            "background-color: #fafafa; border: 1px solid #e4e4e7; border-radius: 8px;"
            "color: #71717a;"
        )
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_label.setMinimumSize(320, 240)
        right_layout.addWidget(self.preview_label, 1)

        # 文件信息标签（文件名 + 尺寸）
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #71717a; font-size: 12px;")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.info_label)

        splitter.addWidget(right_panel)
        # 预览区占更大比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)

        # ===== A/D 快捷键：上一张 / 下一张 =====
        # 作用域限定为本控件及其子控件（WidgetWithChildrenShortcut），
        # 仅在预览区聚焦时生效，避免抢占主窗口全局快捷键
        self._shortcut_prev = QShortcut(QKeySequence("A"), self)
        self._shortcut_prev.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._shortcut_prev.activated.connect(self._on_prev)
        self._shortcut_next = QShortcut(QKeySequence("D"), self)
        self._shortcut_next.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._shortcut_next.activated.connect(self._on_next)

        # 初始导航按钮状态
        self._update_nav_state()

    # -------------------------- 公共接口 --------------------------
    def set_files(self, files: list[str]) -> None:
        """设置文件列表并填充到列表控件。

        Args:
            files: 文件绝对路径列表。
        """
        self._files = list(files)
        self.file_list.clear()
        self._current_pixmap = None
        for path in self._files:
            name = os.path.basename(path)
            item = QListWidgetItem(name)
            item.setToolTip(path)  # 悬停显示完整路径
            self.file_list.addItem(item)
        # 选中第一个文件（若有）
        if self._files:
            self.file_list.setCurrentRow(0)
        else:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("无文件")
            self.info_label.setText("")
            self._update_nav_state()

    def clear(self) -> None:
        """清空文件列表与预览。"""
        self.set_files([])

    def current_file(self) -> str:
        """返回当前选中文件路径（无选中时返回空字符串）。"""
        row = self.file_list.currentRow()
        if 0 <= row < len(self._files):
            return self._files[row]
        return ""

    # -------------------------- 内部逻辑 --------------------------
    def _on_row_changed(self, row: int) -> None:
        """列表选中行变化时加载预览。"""
        self._update_nav_state()
        if not (0 <= row < len(self._files)):
            self.file_selected.emit("")
            return
        path = self._files[row]
        self.file_selected.emit(path)
        self._load_preview(path)

    def _on_prev(self) -> None:
        """切换到上一张。"""
        row = self.file_list.currentRow()
        if row > 0:
            self.file_list.setCurrentRow(row - 1)

    def _on_next(self) -> None:
        """切换到下一张。"""
        row = self.file_list.currentRow()
        if 0 <= row < self.file_list.count() - 1:
            self.file_list.setCurrentRow(row + 1)

    def _update_nav_state(self) -> None:
        """根据当前选中位置更新上一张/下一张按钮可用性。"""
        row = self.file_list.currentRow()
        count = self.file_list.count()
        self.btn_prev.setEnabled(row > 0)
        self.btn_next.setEnabled(0 <= row < count - 1)

    def _load_preview(self, path: str) -> None:
        """加载指定文件的预览。

        图片文件直接加载；非图片文件尝试匹配同目录同名图片预览，
        匹配失败时显示占位提示。

        Args:
            path: 文件路径。
        """
        target = path
        if not _is_image(path):
            # 非图片：尝试匹配同目录同名图片（标注文件对应原图）
            target = self._find_matching_image(path)

        if target and _is_image(target):
            pixmap = QPixmap(target)
            if not pixmap.isNull():
                self._current_pixmap = pixmap
                self._scale_and_show(target)
                return
        # 加载失败或无匹配图片
        self._current_pixmap = None
        self.preview_label.setPixmap(QPixmap())
        if _is_image(path):
            self.preview_label.setText("无法加载图片")
        else:
            self.preview_label.setText("非图片文件\n（无同名图片可预览）")
        self.info_label.setText(os.path.basename(path))

    def _find_matching_image(self, path: str) -> str:
        """为非图片文件查找同目录同名的图片。

        Args:
            path: 标注文件路径。

        Returns:
            匹配到的图片路径，未找到返回空字符串。
        """
        stem = Path(path).stem
        parent = Path(path).parent
        for ext in _IMAGE_EXTS:
            candidate = parent / f"{stem}{ext}"
            if candidate.exists():
                return str(candidate)
        return ""

    def _scale_and_show(self, source_path: str = "") -> None:
        """按预览区尺寸缩放当前图像并显示。

        Args:
            source_path: 源文件路径（仅用于信息标签显示）。
        """
        if self._current_pixmap is None or self._current_pixmap.isNull():
            return
        # 预留边距，避免图片撑满贴边
        avail = self.preview_label.size()
        scaled = self._current_pixmap.scaled(
            avail.width() - 16,
            avail.height() - 16,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        if source_path:
            w = self._current_pixmap.width()
            h = self._current_pixmap.height()
            self.info_label.setText(
                f"{os.path.basename(source_path)}  ·  {w}×{h}"
            )

    def resizeEvent(self, event) -> None:
        """窗口尺寸变化时重新缩放预览图像。

        Args:
            event: 尺寸变化事件。
        """
        super().resizeEvent(event)
        if self._current_pixmap is not None:
            self._scale_and_show(self.current_file())
