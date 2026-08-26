# -*- coding: utf-8 -*-
"""
对象类别选择组件 - ClassSelectorWidget

模型加载后展示模型可识别的对象类别列表（复选框形式），
支持"全选/取消全选"一键切换，选择状态通过勾选框直观呈现，
并对外发射 selection_changed 信号供页面联动。

作者: BaiBinnan
创建日期: 2026-08-26
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .buttons import SecondaryButton


class ClassSelectorWidget(QWidget):
    """对象类别选择组件。

    功能：
        - set_classes(): 填充类别列表（默认全选）
        - selected_ids(): 返回当前勾选的类别 id 列表
        - 全选/取消全选按钮：一键切换所有类别的勾选状态

    Signals:
        selection_changed(list): 任一类别勾选状态变化时发射，
            参数为当前已选类别 id 列表。
    """

    selection_changed = Signal(list)

    def __init__(self, parent=None):
        """初始化组件：顶部计数 + 切换按钮，下方可滚动类别列表。"""
        super().__init__(parent)
        self._classes: dict = {}  # {class_id: name}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # ===== 顶部行：已选计数 + 全选/取消全选按钮 =====
        top = QHBoxLayout()
        self.count_label = QLabel("请先选择模型文件")
        self.count_label.setStyleSheet("color: #71717a;")
        top.addWidget(self.count_label)
        top.addStretch()
        self.btn_toggle_all = SecondaryButton("全选")
        self.btn_toggle_all.setEnabled(False)
        self.btn_toggle_all.clicked.connect(self._on_toggle_all)
        top.addWidget(self.btn_toggle_all)
        lay.addLayout(top)

        # ===== 类别列表（复选框项，可滚动）=====
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.list_widget.setMaximumHeight(200)
        self.list_widget.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.list_widget)

    # -------------------------- 对外接口 --------------------------
    def set_classes(self, class_mapping) -> None:
        """填充类别列表并默认全选。

        Args:
            class_mapping: 类别映射 {class_id: name}，为空时
                显示"未提供类别信息"提示（推理不过滤类别）。
        """
        # 填充期间屏蔽 itemChanged，避免逐项触发信号
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self._classes = dict(class_mapping) if class_mapping else {}

        for cid in sorted(self._classes):
            item = QListWidgetItem(f"{cid}: {self._classes[cid]}")
            item.setData(Qt.ItemDataRole.UserRole, cid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)

        self.list_widget.blockSignals(False)

        has_classes = len(self._classes) > 0
        self.btn_toggle_all.setEnabled(has_classes)
        if has_classes:
            self.btn_toggle_all.setText("取消全选")
        else:
            self.btn_toggle_all.setText("全选")
        self._update_count()
        self.selection_changed.emit(self.selected_ids())

    def selected_ids(self) -> list:
        """返回当前勾选的类别 id 列表（按 id 升序）。

        Returns:
            已选类别 id 列表。
        """
        ids = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def set_selected_ids(self, ids) -> None:
        """按 id 列表恢复勾选状态（用于配置回填）。

        Args:
            ids: 类别 id 列表；为空时不改变当前状态（视为全选）。
        """
        if not ids:
            return
        id_set = set(ids)
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            checked = item.data(Qt.ItemDataRole.UserRole) in id_set
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
        self.list_widget.blockSignals(False)
        self._update_count()
        self.selection_changed.emit(self.selected_ids())

    def has_classes(self) -> bool:
        """当前是否已加载到类别列表。

        Returns:
            已加载类别返回 True，否则 False。
        """
        return len(self._classes) > 0

    # -------------------------- 内部逻辑 --------------------------
    def _on_toggle_all(self) -> None:
        """全选/取消全选一键切换：已全选则全取消，否则全选。"""
        all_checked = len(self.selected_ids()) == self.list_widget.count()
        new_state = (
            Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        )
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(new_state)
        self.list_widget.blockSignals(False)
        self._update_count()
        self.selection_changed.emit(self.selected_ids())

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """单个类别勾选状态变化：更新计数并发射信号。"""
        self._update_count()
        self.selection_changed.emit(self.selected_ids())

    def _update_count(self) -> None:
        """更新顶部计数文本与切换按钮文案。"""
        total = self.list_widget.count()
        if total == 0:
            self.count_label.setText("未提供类别信息，将检测所有类别")
            return
        selected = len(self.selected_ids())
        self.count_label.setText(f"已选 {selected} / 共 {total} 个类别")
        # 按钮文案：当前全选 → 显示"取消全选"，否则显示"全选"
        self.btn_toggle_all.setText("取消全选" if selected == total else "全选")
