# -*- coding: utf-8 -*-
"""
标注对象属性编辑对话框 - ShapeDialog（labelme 风格）

复刻 labelme LabelDialog 布局（参考截图）：
    - 顶部行：标签编辑框（可输入新标签，输入时过滤下方列表）+ Group ID 输入框
    - 第二行：OK / Cancel 按钮
    - 中间：已有标签列表（QListWidget，单击选择，双击即确认）
    - 底部：Label description 描述输入框

即支持从列表选择已有标签，也支持直接键入新标签名称创建。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-03 重构为 labelme 风格布局（标签列表 + 顶部编辑过滤 + Group ID + 描述）
"""

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
)


class ShapeDialog(QDialog):
    """标注对象属性编辑对话框（模态，labelme 风格）。

    使用 get_shape_props 静态方法一键获取编辑结果，失败（取消）返回 None。
    """

    def __init__(self, labels: List[str], shape: Dict[str, Any], parent=None):
        """初始化对话框，回填当前形状属性并填充标签列表。

        Args:
            labels: 已有类别名称列表（填充标签列表）。
            shape: 当前形状字典（labelme 格式）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setWindowTitle("标注对象属性")
        self.setMinimumWidth(320)

        grid = QGridLayout(self)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(8)

        # ===== 顶部行：标签编辑框 + Group ID =====
        # 标签编辑框：显示当前标签；键入时过滤下方列表；可直接输入新标签
        self.label_edit = QLineEdit(str(shape.get("label", "")))
        self.label_edit.textChanged.connect(self._filter_labels)
        grid.addWidget(self.label_edit, 0, 0)

        # Group ID 输入框（空 = 无分组；整数 = 组号）
        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("Group ID")
        self.group_edit.setMaximumWidth(110)
        gid = shape.get("group_id")
        self.group_edit.setText(str(gid) if isinstance(gid, int) and gid >= 0 else "")
        grid.addWidget(self.group_edit, 0, 1)

        # ===== 第二行：OK / Cancel =====
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        grid.addWidget(buttons, 1, 0, 1, 2)

        # ===== 中间：标签列表（全部已有标签，当前标签高亮）=====
        self.label_list = QListWidget()
        for name in labels:
            self.label_list.addItem(QListWidgetItem(str(name)))
        # 双击列表项 = 选择并确认（与 labelme 一致）
        self.label_list.itemDoubleClicked.connect(self._on_item_double)
        grid.addWidget(self.label_list, 2, 0, 1, 2)

        # ===== 底部：描述输入框 =====
        self.desc_edit = QLineEdit(str(shape.get("description", "")))
        self.desc_edit.setPlaceholderText("Label description")
        grid.addWidget(self.desc_edit, 3, 0, 1, 2)

        # 回车确认（标签编辑框除外——回车仅确认对话框，labelme 同款行为）
        buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)

        # 初始高亮当前标签并滚动到可见
        current = str(shape.get("label", ""))
        matched = self.label_list.findItems(current, Qt.MatchFlag.MatchExactly)
        if matched:
            self.label_list.setCurrentItem(matched[0])
            self.label_list.scrollToItem(matched[0])

    # -------------------------- 交互处理 --------------------------
    def _filter_labels(self, text: str) -> None:
        """标签编辑框输入变化时过滤下方列表（包含匹配）。

        Args:
            text: 当前输入文本。
        """
        keyword = text.strip().lower()
        for i in range(self.label_list.count()):
            item = self.label_list.item(i)
            item.setHidden(bool(keyword) and keyword not in item.text().lower())

    def _on_item_double(self, item: QListWidgetItem) -> None:
        """双击标签项：填入编辑框并确认对话框。

        Args:
            item: 被双击的列表项。
        """
        self.label_edit.setText(item.text())
        self.accept()

    # -------------------------- 结果读取 --------------------------
    def result_values(self) -> Tuple[str, str, Optional[int]]:
        """返回编辑后的属性值。

        Returns:
            (标签, 描述, 分组编号) 三元组；Group ID 为空或非整数时返回 None。
        """
        label = self.label_edit.text().strip()
        description = self.desc_edit.text().strip()
        gid_text = self.group_edit.text().strip()
        try:
            gid = int(gid_text) if gid_text else None
        except ValueError:
            gid = None
        return label, description, gid

    @staticmethod
    def get_shape_props(
        labels: List[str], shape: Dict[str, Any], parent=None
    ) -> Optional[Tuple[str, str, Optional[int]]]:
        """弹窗编辑形状属性，返回结果或 None（取消时）。

        Args:
            labels: 已有类别列表。
            shape: 形状字典。
            parent: 父控件。

        Returns:
            (标签, 描述, 分组编号) 或 None。
        """
        dialog = ShapeDialog(labels, shape, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.result_values()
        return None
