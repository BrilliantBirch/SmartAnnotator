# -*- coding: utf-8 -*-
"""
右侧信息栏组件 - RightPanel

经典三栏布局的右栏（参考 labelme / X-Anylabel 风格），纵向堆叠多组列表：
    - 标签列表（b）：工作路径下全部标签（单击/双击设为当前绘制标签）
    - 标签对象列表（a，标题"标签"）：当前图片上的全部标注对象，
      支持多选与右键菜单（编辑属性/删除/进入编辑模式）
    - 文件列表：工作路径下全部图片
    - 关键点列表：Pose 等特殊任务动态显示/隐藏

四组列表以垂直分栏（QSplitter）堆叠，各列表高度可拖拽调节，尺寸变化
经 sizes_changed 信号交由主窗口持久化；面板宽度由主窗口水平分栏控制。
列表选择通过信号对外发射，由主窗口统一处理，保持左右栏与画布联动。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-03 对象列表更名"标签"、多选（ExtendedSelection）、右键上下文菜单
更新: 2026-09-03 移除标签列表"+"新增按钮与 add_label_requested 信号（新标签经属性弹窗键入创建）
更新: 2026-09-03 列表高度改为垂直分栏可拖拽调节（sizes_changed 信号 +
      set_section_heights 接口），宽度界限交由主窗口水平分栏控制
更新: 2026-09-03 对象/关键点列表加复选框（可见性控制）与行-形状下标映射，关键点列表重构为 point 形状对象列表（交互与对象列表一致），文件列表加只读已标注复选框；移除 keypoint_selected 标签名交互
"""

from typing import List

from PySide6.QtCore import Qt, Signal, QItemSelectionModel
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QFrame,
    QListWidgetItem,
    QListView,
    QMenu,
    QAbstractItemView,
    QSplitter,
)

from .canvas import color_for_label
from .file_list_model import FileListModel


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
    """信息栏分组容器：标题行 + 可滚动列表（垂直分栏中的子项）。"""

    def __init__(self, title: str, parent=None):
        """初始化分组。

        Args:
            title: 分组标题。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setStyleSheet("QFrame { border: 1px solid #e4e4e7; border-radius: 8px; }")
        # 分栏子项的最小高度：防止拖拽时分组被压缩到不可用
        self.setMinimumHeight(80)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(8, 8, 8, 8)
        self.lay.setSpacing(6)

        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #71717a; font-weight: 600; border: 0;")
        header.addWidget(self.title_label)
        header.addStretch()
        self.lay.addLayout(header)

        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget { background-color: #fafafa; border: 0; }"
        )
        self.lay.addWidget(self.list, 1)


class RightPanel(QWidget):
    """右侧信息栏。

    Signals:
        label_selected(str): 用户在标签列表中选中/单击标签（设为当前绘制标签）。
        objects_selected(list): 用户在对象列表中选中对象集合（参数为形状下标列表）。
        file_selected(int): 用户在文件列表中选中文件（参数为文件下标）。
        sizes_changed(list): 四组列表高度变化（参数为 [标签, 对象, 文件,
            关键点] 高度列表，隐藏段保持记忆高度）。
        shape_visibility_requested(int, bool): 用户切换对象/关键点列表项复选框
            （参数为形状下标与是否可见）。
        keypoints_selected(list): 用户在关键点列表中选中关键点集合
            （参数为形状下标列表）。
        edit_object_requested(int): 对象列表右键请求编辑指定对象（参数为形状下标）。
        delete_objects_requested(list): 对象列表右键请求删除选中对象
            （参数为形状下标列表）。
        edit_keypoint_requested(int): 关键点列表右键请求编辑指定关键点
            （参数为形状下标）。
        delete_keypoints_requested(list): 关键点列表右键请求删除选中关键点
            （参数为形状下标列表）。
        enter_edit_mode_requested: 对象/关键点列表右键请求进入编辑模式。
    """

    label_selected = Signal(str)
    # 参数为对象下标列表（object 签名避免 QVariantList 转换）
    objects_selected = Signal(object)
    file_selected = Signal(int)
    # 参数为四组列表高度列表（object 签名避免 QVariantList 转换复制）
    sizes_changed = Signal(object)
    # 参数为形状下标 + 是否可见（对象/关键点列表复选框切换共用）
    shape_visibility_requested = Signal(int, bool)
    # 参数为形状下标列表（object 签名避免 QVariantList 转换）
    keypoints_selected = Signal(object)
    edit_object_requested = Signal(int)
    delete_objects_requested = Signal(object)
    edit_keypoint_requested = Signal(int)
    delete_keypoints_requested = Signal(object)
    enter_edit_mode_requested = Signal()

    def __init__(self, parent=None):
        """初始化四组列表（垂直分栏）与信号连接。"""
        super().__init__(parent)
        # 宽度界限：实际宽度由主窗口水平分栏拖拽控制（200-800 像素）
        self.setMinimumWidth(200)
        self.setMaximumWidth(800)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 8, 6, 8)
        root.setSpacing(8)

        # 四组列表以垂直分栏堆叠：拖拽分隔条调节各列表高度
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setHandleWidth(6)
        self.splitter.setChildrenCollapsible(False)
        # 记忆高度（持久化用；隐藏段不写入 0，恢复可见时回填）
        self._section_heights: List[int] = [180, 180, 280, 140]
        # 行号 → 形状下标映射（对象/关键点列表分离 point 形状后行号与
        # canvas.shapes() 下标不再一致，所有选中/编辑/删除交互均经此映射）
        self._object_indices: List[int] = []
        self._kpt_indices: List[int] = []

        # ===== 标签列表（b）=====
        self.label_section = _Section("标签列表")
        self.label_section.list.itemDoubleClicked.connect(self._on_label_double)
        # 单击即选中标签作为当前绘制标签（直接选择预设标签进行标注）
        self.label_section.list.itemClicked.connect(self._on_label_click)
        self.splitter.addWidget(self.label_section)

        # ===== 标签对象列表（a，标题"标签"）=====
        self.object_section = _Section("对象")
        self.object_section.list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.object_section.list.itemSelectionChanged.connect(
            self._on_object_selection_changed
        )
        # 复选框切换：发射形状可见性变化信号
        self.object_section.list.itemChanged.connect(self._on_object_item_changed)
        # 右键上下文菜单：编辑（仅单选）/删除（多选可用）/进入编辑模式
        self.object_section.list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.object_section.list.customContextMenuRequested.connect(
            self._on_object_context_menu
        )
        self.splitter.addWidget(self.object_section)

        # ===== 文件列表（QListView + 模型：UI 虚拟化，只读已标注复选框）=====
        self.file_section = _Section("文件列表")
        # 用 QListView 替换 _Section 默认的 QListWidget（大目录不逐项建 item）
        self.file_section.lay.removeWidget(self.file_section.list)
        self.file_section.list.deleteLater()
        self.file_model = FileListModel(self)
        self.file_section.list = QListView()
        self.file_section.list.setModel(self.file_model)
        self.file_section.list.setStyleSheet(
            "QListView { background-color: #fafafa; border: 0; }"
        )
        self.file_section.lay.addWidget(self.file_section.list, 1)
        # currentRowChanged 等价信号：当前行变化经 selectionModel 转发
        self.file_section.list.selectionModel().currentRowChanged.connect(
            lambda cur, _: self.file_selected.emit(cur.row() if cur.isValid() else -1)
        )
        self.splitter.addWidget(self.file_section)

        # ===== 关键点列表（默认隐藏；Pose 等任务的 point 形状对象列表）=====
        self.kpt_section = _Section("关键点列表")
        self.kpt_section.list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.kpt_section.list.itemSelectionChanged.connect(
            self._on_kpt_selection_changed
        )
        # 复选框切换：与对象列表共用形状可见性信号
        self.kpt_section.list.itemChanged.connect(self._on_kpt_item_changed)
        # 右键上下文菜单：编辑（仅单选）/删除（多选可用）/进入编辑模式
        self.kpt_section.list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.kpt_section.list.customContextMenuRequested.connect(
            self._on_kpt_context_menu
        )
        self.kpt_section.setVisible(False)
        self.splitter.addWidget(self.kpt_section)

        # 剩余空间的伸缩比例（沿用旧布局 1:1:2:1 的视觉权重）
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 2)
        self.splitter.setStretchFactor(3, 1)
        # 分隔条拖动：更新记忆高度并通知主窗口持久化
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        root.addWidget(self.splitter)

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
    def set_objects(self, items) -> None:
        """填充当前图片对象列表（非 point 形状），带可见性复选框与下标映射。

        清空与重建全程屏蔽信号：否则 clear() 会触发 itemSelectionChanged
        → objects_selected([]) → 反向清空画布选中集合（多选丢失），
        且设置复选框状态会触发 itemChanged → 误发射可见性信号。

        Args:
            items: (形状下标, 描述文本, 标签名, 是否可见) 四元组列表，
                如 [(0, "person (rectangle)", "person", True)]，
                形状下标为在 canvas.shapes() 中的真实下标。
        """
        lst = self.object_section.list
        lst.blockSignals(True)
        # 清空列表并同步重置行号 → 形状下标映射
        lst.clear()
        self._object_indices = []
        for shape_index, desc, label, visible in items:
            item = QListWidgetItem(str(desc))
            item.setIcon(_color_dot_icon(color_for_label(str(label))))
            # 复选框控制形状可见性（可由用户点击切换）
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
            )
            lst.addItem(item)
            self._object_indices.append(int(shape_index))
        lst.blockSignals(False)

    def _on_object_selection_changed(self) -> None:
        """对象列表选中集合变化：行号经映射转形状下标后发射。"""
        rows = sorted({idx.row() for idx in self.object_section.list.selectedIndexes()})
        self.objects_selected.emit([self._object_indices[r] for r in rows])

    def _on_object_item_changed(self, item: QListWidgetItem, *args) -> None:
        """对象列表项数据变化：复选框切换时发射形状可见性信号。

        PySide6 6.11.1 的 itemChanged 仅携带 item 参数（无 role），
        保留可选 role 参数以兼容带 role 的 Qt 版本（仅处理复选框角色）。

        Args:
            item: 数据变化的列表项。
            *args: 兼容携带 role 参数的 Qt 版本（当前版本不传，跳过检查）。
        """
        # role 检查不可用时跳过（当前 Qt 版本的 itemChanged 不携带 role）
        if args and args[0] != Qt.ItemDataRole.CheckStateRole:
            return
        row = self.object_section.list.row(item)
        if 0 <= row < len(self._object_indices):
            self.shape_visibility_requested.emit(
                self._object_indices[row],
                item.checkState() == Qt.CheckState.Checked,
            )

    def _on_object_context_menu(self, pos) -> None:
        """对象列表右键菜单入口：分派到共用实现。

        Args:
            pos: 右键位置（列表部件局部坐标）。
        """
        self._show_context_menu(
            self.object_section.list,
            self._object_indices,
            self.edit_object_requested,
            self.delete_objects_requested,
            pos,
        )

    def _on_kpt_context_menu(self, pos) -> None:
        """关键点列表右键菜单入口：分派到共用实现。

        Args:
            pos: 右键位置（列表部件局部坐标）。
        """
        self._show_context_menu(
            self.kpt_section.list,
            self._kpt_indices,
            self.edit_keypoint_requested,
            self.delete_keypoints_requested,
            pos,
        )

    def _show_context_menu(self, lst, index_map, edit_signal, delete_signal, pos) -> None:
        """对象/关键点列表共用的右键菜单：编辑（仅单选）/删除/进入编辑模式。

        右键未选中的项时先将其设为唯一选中（符合常规交互习惯）；
        多选时仅启用删除；单选时启用编辑与删除。编辑/删除发射的均为
        经行号 → 形状下标映射后的真实下标。

        Args:
            lst: 触发菜单的列表部件。
            index_map: 行号 → 形状下标映射列表。
            edit_signal: 编辑请求信号（参数为形状下标）。
            delete_signal: 删除请求信号（参数为形状下标列表）。
            pos: 右键位置（列表部件局部坐标）。
        """
        # 右键命中的项若不在当前选中集合中，改为单选该项
        item = lst.itemAt(pos)
        if item is not None and not item.isSelected():
            lst.clearSelection()
            item.setSelected(True)
            lst.setCurrentRow(lst.row(item))
        rows = sorted({idx.row() for idx in lst.selectedIndexes()})
        indices = [index_map[r] for r in rows]
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
            edit_signal.emit(indices[0])
        elif chosen is act_delete:
            delete_signal.emit(indices)
        elif chosen is act_enter:
            self.enter_edit_mode_requested.emit()

    def select_objects(self, indices) -> None:
        """程序化选中指定形状集合（画布多选联动，不发射信号）。

        按两列表的行号 → 形状下标映射分派：对象列表选中下标存在于
        _object_indices 的对应行，关键点列表选中存在于 _kpt_indices 的
        对应行；未命中任一映射的下标自动忽略；indices 为空时两列表全清。

        注意：不得调用 setCurrentRow 设置当前项——其内部选择命令会
        清除已设置的选中集合（ExtendedSelection 下实测破坏多选），
        必须以 NoUpdate 命令仅移动当前项。

        Args:
            indices: 形状下标列表（未出现在两映射中的下标自动忽略）。
        """
        wanted = set(indices)
        # 对象列表与关键点列表各自独立处理（选中行、当前项、屏蔽信号）
        for lst, index_map in (
            (self.object_section.list, self._object_indices),
            (self.kpt_section.list, self._kpt_indices),
        ):
            lst.blockSignals(True)
            lst.clearSelection()
            # 选中形状下标命中映射的行，并记录最小命中行作为当前项
            first_row = -1
            for row, shape_index in enumerate(index_map):
                if shape_index in wanted:
                    lst.item(row).setSelected(True)
                    if first_row < 0:
                        first_row = row
            # 仅移动当前项（NoUpdate：不改变选中集合）
            if first_row >= 0:
                lst.selectionModel().setCurrentIndex(
                    lst.model().index(first_row, 0),
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
            else:
                lst.setCurrentRow(-1)
            lst.blockSignals(False)

    def clear_object_selection(self) -> None:
        """清除对象与关键点列表选中态（不发射信号）。"""
        for lst in (self.object_section.list, self.kpt_section.list):
            lst.blockSignals(True)
            lst.clearSelection()
            lst.setCurrentRow(-1)
            lst.blockSignals(False)

    def selected_object_indices(self) -> List[int]:
        """返回对象列表当前选中行经映射的形状下标列表。

        Returns:
            形状下标列表（按行序升序）。
        """
        rows = sorted({idx.row() for idx in self.object_section.list.selectedIndexes()})
        return [self._object_indices[r] for r in rows]

    def selected_kpt_indices(self) -> List[int]:
        """返回关键点列表当前选中行经映射的形状下标列表。

        Returns:
            形状下标列表（按行序升序）。
        """
        rows = sorted({idx.row() for idx in self.kpt_section.list.selectedIndexes()})
        return [self._kpt_indices[r] for r in rows]

    # -------------------------- 文件列表 --------------------------
    def set_files(self, files, annotated=None) -> None:
        """填充文件列表（每项带只读"已标注"复选框）。

        复选框仅指示该文件是否已标注（勾选状态由主窗口在保存后经
        set_file_annotated 维护）；模型 flags 不含 ItemIsUserCheckable，
        用户不可点击切换。模型重置会自动清空选中态，无需屏蔽信号。

        Args:
            files: 图片绝对路径列表（显示为文件名）。
            annotated: 与 files 等长的已标注布尔列表（None 时全部 False）。
        """
        if annotated is None:
            annotated = [False] * len(files)
        self.file_model.set_files(files, annotated)

    def set_file_annotated(self, index: int, checked: bool) -> None:
        """更新指定文件的已标注勾选状态（不发射信号）。

        Args:
            index: 文件下标（越界时不操作）。
            checked: 是否已标注（True 勾选 / False 取消勾选）。
        """
        self.file_model.set_row_state(index, checked)

    def select_file(self, index: int) -> None:
        """程序化选中指定文件（不发射信号）。

        Args:
            index: 文件下标（越界时不操作）。
        """
        view = self.file_section.list
        if 0 <= index < self.file_model.count():
            view.selectionModel().blockSignals(True)
            view.setCurrentIndex(self.file_model.index(index))
            view.selectionModel().blockSignals(False)

    # -------------------------- 关键点列表 --------------------------
    def set_keypoints(self, items) -> None:
        """填充关键点列表（point 形状对象），带可见性复选框与下标映射。

        与 set_objects 同结构：全程屏蔽信号，防止 clear() 触发
        itemSelectionChanged 反向清空画布选中集合、设置复选框
        状态触发 itemChanged 误发射可见性信号。

        Args:
            items: (形状下标, 描述文本, 标签名, 是否可见) 四元组列表，
                形状下标为在 canvas.shapes() 中的真实下标。
        """
        lst = self.kpt_section.list
        lst.blockSignals(True)
        # 清空列表并同步重置行号 → 形状下标映射
        lst.clear()
        self._kpt_indices = []
        for shape_index, desc, label, visible in items:
            item = QListWidgetItem(str(desc))
            item.setIcon(_color_dot_icon(color_for_label(str(label))))
            # 复选框控制形状可见性（可由用户点击切换）
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
            )
            lst.addItem(item)
            self._kpt_indices.append(int(shape_index))
        lst.blockSignals(False)

    def _on_kpt_selection_changed(self) -> None:
        """关键点列表选中集合变化：行号经映射转形状下标后发射。"""
        rows = sorted({idx.row() for idx in self.kpt_section.list.selectedIndexes()})
        self.keypoints_selected.emit([self._kpt_indices[r] for r in rows])

    def _on_kpt_item_changed(self, item: QListWidgetItem, *args) -> None:
        """关键点列表项数据变化：复选框切换时发射形状可见性信号。

        与 _on_object_item_changed 同逻辑：PySide6 6.11.1 的
        itemChanged 仅携带 item 参数（无 role），保留可选 role 参数
        以兼容带 role 的 Qt 版本（仅处理复选框角色）。

        Args:
            item: 数据变化的列表项。
            *args: 兼容携带 role 参数的 Qt 版本（当前版本不传，跳过检查）。
        """
        # role 检查不可用时跳过（当前 Qt 版本的 itemChanged 不携带 role）
        if args and args[0] != Qt.ItemDataRole.CheckStateRole:
            return
        row = self.kpt_section.list.row(item)
        if 0 <= row < len(self._kpt_indices):
            self.shape_visibility_requested.emit(
                self._kpt_indices[row],
                item.checkState() == Qt.CheckState.Checked,
            )

    def set_kpt_visible(self, visible: bool) -> None:
        """设置关键点列表可见性（Pose 等任务显示）。

        关键点列表恢复可见时回填记忆高度（隐藏期间 Qt 已重分配其尺寸）。

        Args:
            visible: 是否可见。
        """
        self.kpt_section.setVisible(visible)
        if visible:
            # 恢复可见：按记忆高度重新分配四段尺寸
            self.splitter.setSizes(list(self._section_heights))

    # -------------------------- 分栏尺寸 --------------------------
    def set_section_heights(self, heights) -> None:
        """程序化设置四组列表的分栏高度（应用并记忆）。

        关键点列表隐藏时不参与本次分配（其记忆高度保留，
        恢复可见时由 set_kpt_visible 回填）。

        Args:
            heights: [标签, 对象, 文件, 关键点] 高度列表。
        """
        self._section_heights = [int(h) for h in heights[:4]]
        sizes = list(self._section_heights)
        if self.kpt_section.isHidden():
            sizes[3] = 0
        self.splitter.setSizes(sizes)

    def section_heights(self) -> List[int]:
        """返回四组列表的记忆高度列表。

        Returns:
            [标签, 对象, 文件, 关键点] 高度列表。
        """
        return list(self._section_heights)

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """列表分栏拖动：更新记忆高度并发射尺寸变化信号。

        隐藏段（关键点列表）保持记忆高度，不写入 0。

        Args:
            pos: 拖动位置（仅为信号签名，未使用）。
            index: 拖动的分隔条下标（仅为信号签名，未使用）。
        """
        sizes = self.splitter.sizes()
        sections = (
            self.label_section,
            self.object_section,
            self.file_section,
            self.kpt_section,
        )
        # 仅更新当前可见段的记忆高度（用 isHidden 判断自身显式隐藏态，
        # 避免父窗口未显示时 isVisible() 恒 False 的误判）
        for i, sec in enumerate(sections):
            if not sec.isHidden() and i < len(sizes):
                self._section_heights[i] = sizes[i]
        self.sizes_changed.emit(list(self._section_heights))