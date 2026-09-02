# -*- coding: utf-8 -*-
"""
标注对象属性编辑对话框 - ShapeDialog

在单个标注对象绘制完成后自动弹出，用于快速编辑该对象的属性：
    - 标签：从已有类别列表中选择（可编辑输入，支持前缀/包含搜索筛选）
    - 描述：对象的附加描述信息（description）
    - 分组编号：pose 关键点等按组归属（group_id，-1 表示无分组）

作者: BaiBinnan
创建日期: 2026-09-02
"""

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QDialogButtonBox,
    QCompleter,
)


class ShapeDialog(QDialog):
    """标注对象属性编辑对话框（模态）。

    使用 get_shape_props 静态方法一键获取编辑结果，失败（取消）返回 None。
    """

    def __init__(self, labels: List[str], shape: Dict[str, Any], parent=None):
        """初始化对话框，回填当前形状属性。

        Args:
            labels: 已有类别名称列表（用于标签下拉与搜索筛选）。
            shape: 当前形状字典（labelme 格式）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setWindowTitle("标注对象属性")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 标签下拉（可编辑 + 搜索筛选）
        self.label_combo = QComboBox()
        self.label_combo.setEditable(True)
        self.label_combo.addItems([str(x) for x in labels])
        self.label_combo.setCurrentText(str(shape.get("label", "")))
        # 搜索：输入时按包含匹配筛选并弹出补全
        completer = self.label_combo.completer()
        if completer is not None:
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
        form.addRow("标签", self.label_combo)

        # 描述信息
        self.desc_edit = QLineEdit(str(shape.get("description", "")))
        self.desc_edit.setPlaceholderText("对象描述（可选）")
        form.addRow("描述", self.desc_edit)

        # 分组编号（-1 表示无分组）
        self.group_spin = QSpinBox()
        self.group_spin.setRange(-1, 9999)
        self.group_spin.setSpecialValueText("无分组")
        gid = shape.get("group_id")
        self.group_spin.setValue(gid if isinstance(gid, int) else -1)
        form.addRow("分组编号", self.group_spin)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_values(self) -> Tuple[str, str, Optional[int]]:
        """返回编辑后的属性值。

        Returns:
            (标签, 描述, 分组编号) 三元组；分组编号 -1 视作 None。
        """
        label = self.label_combo.currentText().strip()
        description = self.desc_edit.text().strip()
        gid = self.group_spin.value()
        return label, description, (gid if gid >= 0 else None)

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