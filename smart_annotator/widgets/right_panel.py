# -*- coding: utf-8 -*-
"""
右侧信息栏组件 - RightPanel

经典三栏布局的右栏（参考 labelme / X-Anylabel 风格），纵向堆叠多组列表：
    - 标签列表：工作路径下全部标签（双击设为当前绘制标签，可新增）
    - 图片对象列表：当前图片上的全部标注对象
    - 文件列表：工作路径下全部图片
    - 关键点列表：Pose 等特殊任务动态显示/隐藏

列表选择通过信号对外发射，由主窗口统一处理，保持左右栏与画布联动。

作者: BaiBinnan
创建日期: 2026-09-02
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QFrame,
    QListWidgetItem,
)


class _Section(QFrame):
    """信息栏分组容器：标题行 + 可滚动列表。"""

    def __init__(self, title: str, parent=None):
        """初始化分组。

        Args:
            title: 分组标题。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setStyleSheet("QFrame { border: 1px solid #e4e4e7; border-radius: 8px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #71717a; font-weight: 600; border: 0;")
        header.addWidget(self.title_label)
        header.addStretch()
        self._extra = QHBoxLayout()
        header.addLayout(self._extra)
        lay.addLayout(header)

        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget { background-color: #fafafa; border: 0; }"
        )
        lay.addWidget(self.list, 1)

    def add_header_widget(self, widget: QWidget) -> None:
        """在标题行右侧添加一个控件（如"+"新增按钮）。"""
        self._extra.addWidget(widget)


class RightPanel(QWidget):
    """右侧信息栏。

    Signals:
        label_selected(str): 用户在标签列表中选中/双击标签（设为当前绘制标签）。
        object_selected(int): 用户在对象列表中选中对象（参数为对象下标）。
        file_selected(int): 用户在文件列表中选中文件（参数为文件下标）。
        keypoint_selected(str): 用户在关键点列表中选中关键点。
        add_label_requested: 用户请求新增标签。
    """

    label_selected = Signal(str)
    object_selected = Signal(int)
    file_selected = Signal(int)
    keypoint_selected = Signal(str)
    add_label_requested = Signal()

    def __init__(self, parent=None):
        """初始化四组列表与信号连接。"""
        super().__init__(parent)
        self.setFixedWidth(240)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 8, 6, 8)
        root.setSpacing(8)

        # ===== 标签列表 =====
        self.label_section = _Section("标签列表")
        btn_add = QPushButton("+")
        btn_add.setFixedSize(22, 22)
        btn_add.setToolTip("新增标签")
        btn_add.clicked.connect(self.add_label_requested.emit)
        self.label_section.add_header_widget(btn_add)
        self.label_section.list.itemDoubleClicked.connect(self._on_label_double)
        root.addWidget(self.label_section, 1)

        # ===== 图片对象列表 =====
        self.object_section = _Section("图片对象")
        self.object_section.list.currentRowChanged.connect(self.object_selected.emit)
        root.addWidget(self.object_section, 1)

        # ===== 文件列表 =====
        self.file_section = _Section("文件列表")
        self.file_section.list.currentRowChanged.connect(self.file_selected.emit)
        root.addWidget(self.file_section, 2)

        # ===== 关键点列表（默认隐藏）=====
        self.kpt_section = _Section("关键点列表")
        self.kpt_section.list.itemClicked.connect(self._on_kpt_click)
        self.kpt_section.setVisible(False)
        root.addWidget(self.kpt_section, 1)

    # -------------------------- 标签列表 --------------------------
    def set_labels(self, labels) -> None:
        """填充标签列表。

        Args:
            labels: 标签名列表。
        """
        self.label_section.list.clear()
        for name in labels:
            self.label_section.list.addItem(str(name))

    def _on_label_double(self, item: QListWidgetItem) -> None:
        """双击标签：发射设为当前绘制标签信号。

        Args:
            item: 被双击的列表项。
        """
        self.label_selected.emit(item.text())

    # -------------------------- 对象列表 --------------------------
    def set_objects(self, descriptions) -> None:
        """填充当前图片对象列表。

        Args:
            descriptions: 对象描述文本列表（如 "person (rectangle)"）。
        """
        self.object_section.list.clear()
        for desc in descriptions:
            self.object_section.list.addItem(str(desc))

    def select_object(self, index: int) -> None:
        """程序化选中指定对象（用于画布选中与对象列表联动）。

        Args:
            index: 对象下标（越界时不操作）。
        """
        if 0 <= index < self.object_section.list.count():
            self.object_section.list.blockSignals(True)
            self.object_section.list.setCurrentRow(index)
            self.object_section.list.blockSignals(False)

    def clear_object_selection(self) -> None:
        """清除对象列表选中态（不发射信号）。"""
        self.object_section.list.blockSignals(True)
        self.object_section.list.clearSelection()
        self.object_section.list.setCurrentRow(-1)
        self.object_section.list.blockSignals(False)

    # -------------------------- 文件列表 --------------------------
    def set_files(self, files) -> None:
        """填充文件列表。

        Args:
            files: 图片绝对路径列表（显示为文件名）。
        """
        self.file_section.list.clear()
        for path in files:
            item = QListWidgetItem(str(path.split("\\")[-1].split("/")[-1]))
            item.setToolTip(str(path))
            self.file_section.list.addItem(item)

    def select_file(self, index: int) -> None:
        """程序化选中指定文件（不发射信号）。

        Args:
            index: 文件下标（越界时不操作）。
        """
        if 0 <= index < self.file_section.list.count():
            self.file_section.list.blockSignals(True)
            self.file_section.list.setCurrentRow(index)
            self.file_section.list.blockSignals(False)

    # -------------------------- 关键点列表 --------------------------
    def set_keypoints(self, keypoints) -> None:
        """填充关键点列表。

        Args:
            keypoints: 关键点名称列表。
        """
        self.kpt_section.list.clear()
        for name in keypoints:
            self.kpt_section.list.addItem(str(name))

    def set_kpt_visible(self, visible: bool) -> None:
        """设置关键点列表可见性（Pose 等任务显示）。

        Args:
            visible: 是否可见。
        """
        self.kpt_section.setVisible(visible)

    def _on_kpt_click(self, item: QListWidgetItem) -> None:
        """点击关键点名称：发射信号。

        Args:
            item: 被点击的列表项。
        """
        self.keypoint_selected.emit(item.text())