# -*- coding: utf-8 -*-
"""
右侧信息栏组件 - RightPanel

经典三栏布局的右栏（参考 labelme / X-Anylabel 风格），纵向堆叠多组列表：
    - 标签列表（b）：工作路径下全部标签（单击/双击设为当前绘制标签，可新增）
    - 标签对象列表（a，标题"标签"）：当前图片上的全部标注对象，
      支持多选与右键菜单（编辑属性/删除/进入编辑模式）
    - 文件列表：工作路径下全部图片
    - 关键点列表：Pose 等特殊任务动态显示/隐藏

列表选择通过信号对外发射，由主窗口统一处理，保持左右栏与画布联动。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-03 对象列表更名"标签"、多选（ExtendedSelection）、右键上下文菜单
"""

from PySide6.QtCore import Qt, Signal, QItemSelectionModel
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QFrame,
    QListWidgetItem,
    QMenu,
    QAbstractItemView,
)

from .canvas import color_for_label


def _color_dot_icon(color: QColor) -> QIcon:
    """生成一个实心圆点图标，用于列表项前的类别颜色标识。

    Args:
        color: 圆点颜色。

    Returns:
        圆点图标。
    """
    pm = QPixmap(12, 12)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#9ca3af"), 1))
    painter.setBrush(color)
    painter.drawEllipse(1, 1, 10, 10)
    painter.end()
    return QIcon(pm)


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
        label_selected(str): 用户在标签列表中选中/单击标签（设为当前绘制标签）。
        objects_selected(list): 用户在对象列表中选中对象集合（参数为对象下标列表）。
        file_selected(int): 用户在文件列表中选中文件（参数为文件下标）。
        keypoint_selected(str): 用户在关键点列表中选中关键点。
        add_label_requested: 用户请求新增标签。
        edit_object_requested(int): 对象列表右键请求编辑指定对象（参数为下标）。
        delete_objects_requested(list): 对象列表右键请求删除选中对象（参数为下标列表）。
        enter_edit_mode_requested: 对象列表右键请求进入编辑模式。
    """

    label_selected = Signal(str)
    # 参数为对象下标列表（object 签名避免 QVariantList 转换）
    objects_selected = Signal(object)
    file_selected = Signal(int)
    keypoint_selected = Signal(str)
    add_label_requested = Signal()
    edit_object_requested = Signal(int)
    delete_objects_requested = Signal(object)
    enter_edit_mode_requested = Signal()

    def __init__(self, parent=None):
        """初始化四组列表与信号连接。"""
        super().__init__(parent)
        self.setFixedWidth(240)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 8, 6, 8)
        root.setSpacing(8)

        # ===== 标签列表（b）=====
        self.label_section = _Section("标签列表")
        btn_add = QPushButton("+")
        btn_add.setFixedSize(22, 22)
        btn_add.setToolTip("新增标签")
        btn_add.clicked.connect(self.add_label_requested.emit)
        self.label_section.add_header_widget(btn_add)
        self.label_section.list.itemDoubleClicked.connect(self._on_label_double)
        # 单击即选中标签作为当前绘制标签（直接选择预设标签进行标注）
        self.label_section.list.itemClicked.connect(self._on_label_click)
        root.addWidget(self.label_section, 1)

        # ===== 标签对象列表（a，标题"标签"）=====
        self.object_section = _Section("标签")
        self.object_section.list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.object_section.list.itemSelectionChanged.connect(
            self._on_object_selection_changed
        )
        # 右键上下文菜单：编辑（仅单选）/删除（多选可用）/进入编辑模式
        self.object_section.list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.object_section.list.customContextMenuRequested.connect(
            self._on_object_context_menu
        )
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
        """填充标签列表，每项前显示与类别框颜色一致的圆点。

        Args:
            labels: 标签名列表。
        """
        self.label_section.list.clear()
        for name in labels:
            item = QListWidgetItem(str(name))
            item.setIcon(_color_dot_icon(color_for_label(str(name))))
            self.label_section.list.addItem(item)

    def _on_label_double(self, item: QListWidgetItem) -> None:
        """双击标签：发射设为当前绘制标签信号。

        Args:
            item: 被双击的列表项。
        """
        self.label_selected.emit(item.text())

    def _on_label_click(self, item: QListWidgetItem) -> None:
        """单击标签：同样设为当前绘制标签（直接选择预设标签）。

        Args:
            item: 被单击的列表项。
        """
        self.label_selected.emit(item.text())

    # -------------------------- 对象列表 --------------------------
    def set_objects(self, entries) -> None:
        """填充当前图片对象列表，每项前显示与对象类别颜色一致的圆点。

        清空与重建全程屏蔽信号：否则 clear() 会触发 itemSelectionChanged
        → objects_selected([]) → 反向清空画布选中集合（多选丢失）。

        Args:
            entries: (描述文本, 标签名) 元组列表，如 [("person (rectangle)", "person")]。
        """
        lst = self.object_section.list
        lst.blockSignals(True)
        lst.clear()
        for desc, label in entries:
            item = QListWidgetItem(str(desc))
            item.setIcon(_color_dot_icon(color_for_label(str(label))))
            lst.addItem(item)
        lst.blockSignals(False)

    def _on_object_selection_changed(self) -> None:
        """对象列表选中集合变化：发射选中下标列表。"""
        rows = sorted({idx.row() for idx in self.object_section.list.selectedIndexes()})
        self.objects_selected.emit(rows)

    def _on_object_context_menu(self, pos) -> None:
        """对象列表右键菜单：编辑（仅单选）/删除/进入编辑模式。

        右键未选中的项时先将其设为唯一选中（符合常规交互习惯）；
        多选时仅启用删除；单选时启用编辑与删除。

        Args:
            pos: 右键位置（列表部件局部坐标）。
        """
        lst = self.object_section.list
        # 右键命中的项若不在当前选中集合中，改为单选该项
        item = lst.itemAt(pos)
        if item is not None and not item.isSelected():
            lst.clearSelection()
            item.setSelected(True)
            lst.setCurrentRow(lst.row(item))
        rows = sorted({idx.row() for idx in lst.selectedIndexes()})
        menu = QMenu(self)
        act_edit = menu.addAction("编辑")
        act_delete = menu.addAction("删除")
        menu.addSeparator()
        act_enter = menu.addAction("进入编辑模式")
        # 多选仅启用删除；单选启用编辑与删除；无选中全部禁用
        act_edit.setEnabled(len(rows) == 1)
        act_delete.setEnabled(bool(rows))
        chosen = menu.exec(lst.mapToGlobal(pos))
        if chosen is act_edit:
            self.edit_object_requested.emit(rows[0])
        elif chosen is act_delete:
            self.delete_objects_requested.emit(rows)
        elif chosen is act_enter:
            self.enter_edit_mode_requested.emit()

    def select_objects(self, indices) -> None:
        """程序化选中指定对象集合（用于画布多选联动，不发射信号）。

        注意：不得调用 setCurrentRow 设置当前项——其内部选择命令会
        清除已设置的选中集合（ExtendedSelection 下实测破坏多选），
        必须以 NoUpdate 命令仅移动当前项。

        Args:
            indices: 对象下标列表（越界项自动忽略）。
        """
        lst = self.object_section.list
        lst.blockSignals(True)
        lst.clearSelection()
        for i in indices:
            if 0 <= i < lst.count():
                lst.item(i).setSelected(True)
        # 仅移动当前项（NoUpdate：不改变选中集合）
        if indices:
            first = min(indices)
            if 0 <= first < lst.count():
                lst.selectionModel().setCurrentIndex(
                    lst.model().index(first, 0),
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
        else:
            lst.setCurrentRow(-1)
        lst.blockSignals(False)

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