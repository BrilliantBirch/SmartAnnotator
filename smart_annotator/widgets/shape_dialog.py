# -*- coding: utf-8 -*-
"""
标注对象属性编辑对话框 - ShapeDialog（labelme 风格）

复刻 labelme LabelDialog 布局（参考截图）：
    - 顶部行：标签编辑框（可输入新标签，输入时过滤下方列表）+
      Group ID 可编辑下拉框（下拉项为画布已有分组，也可直接键入新组号）
    - 第二行：OK / Cancel 按钮
    - 中间：已有标签列表（QListWidget，单击选择，双击即确认）
    - 底部：Label description 描述输入框

即支持从列表选择已有标签，也支持直接键入新标签名称创建。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-03 重构为 labelme 风格布局（标签列表 + 顶部编辑过滤 + Group ID + 描述）
更新: 2026-09-03 Group ID 改为可编辑 QComboBox（下拉填充画布已有分组，去重升序），
      构造签名增加 group_ids 参数
更新: 2026-09-03 标签列表单击选中项同步 label 编辑框（选中即预览）
更新: 2026-09-07 修复复合标签双击失效：单击同步文本时阻断过滤信号（blockSignals），避免列表实时重排导致双击第二击落点漂移
更新: 2026-09-10 新增困难样本 (difficult) 复选框（第 4 行），result_values/get_shape_props 扩展为四元组，
      老 JSON 缺失 difficult 键时默认不勾选（兼容性）
"""

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

    def __init__(
        self,
        labels: List[str],
        shape: Dict[str, Any],
        group_ids: Optional[List[int]] = None,
        parent=None,
    ):
        """初始化对话框，回填当前形状属性并填充标签列表与分组下拉项。

        Args:
            labels: 已有类别名称列表（填充标签列表）。
            shape: 当前形状字典（labelme 格式）。
            group_ids: 画布现有分组编号集合（填充 Group ID 下拉项），可为 None。
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

        # Group ID 可编辑下拉框（空 = 无分组；整数 = 组号）
        self.group_edit = QComboBox()
        self.group_edit.setEditable(True)
        self.group_edit.setPlaceholderText("Group ID")
        self.group_edit.setMaximumWidth(110)
        # 下拉项：画布现有分组编号（去重、升序）
        gids = sorted({g for g in (group_ids or []) if isinstance(g, int) and g >= 0})
        for g in gids:
            self.group_edit.addItem(str(g))
        # 回填当前形状分组（可编辑框允许任意值，不要求存在于选项中）
        gid = shape.get("group_id")
        self.group_edit.setCurrentText(
            str(gid) if isinstance(gid, int) and gid >= 0 else ""
        )
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
        # 单击选中列表项：label 编辑框同步该项文本（选中即预览，双击仍为选择并确认）
        self.label_list.itemClicked.connect(self._on_item_clicked)
        grid.addWidget(self.label_list, 2, 0, 1, 2)

        # ===== 底部：描述输入框 =====
        self.desc_edit = QLineEdit(str(shape.get("description", "")))
        self.desc_edit.setPlaceholderText("Label description")
        grid.addWidget(self.desc_edit, 3, 0, 1, 2)

        # ===== 第 4 行：困难样本 (difficult) 复选框 =====
        # 老 JSON 无 difficult 键时默认不勾选（兼容历史标注文件）
        self.difficult_check = QCheckBox("困难样本 (difficult)")
        self.difficult_check.setChecked(bool(shape.get("difficult", False)))
        grid.addWidget(self.difficult_check, 4, 0, 1, 2)

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

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """单击标签列表项：同步 label 编辑框内容为该项文本。

        同步时阻断 textChanged（blockSignals），避免 setText 触发
        _filter_labels 实时过滤导致列表重排——双击的第一击 release 会先
        发出 itemClicked，若列表随即重排，第二击落点漂移将使
        itemDoubleClicked 无法触发（复合标签双击失效）；用户手动键入
        仍经 textChanged 正常过滤。

        Args:
            item: 被单击的列表项。
        """
        # 阻断 textChanged：单击同步文本不触发实时过滤，列表保持稳定
        self.label_edit.blockSignals(True)
        self.label_edit.setText(item.text())
        self.label_edit.blockSignals(False)

    def _on_item_double(self, item: QListWidgetItem) -> None:
        """双击标签项：填入编辑框并确认对话框。

        填入时与单击路径一致阻断 textChanged，保持同步行为统一，
        避免确认前列表被过滤重排。

        Args:
            item: 被双击的列表项。
        """
        # 阻断 textChanged：双击填入同样不触发实时过滤
        self.label_edit.blockSignals(True)
        self.label_edit.setText(item.text())
        self.label_edit.blockSignals(False)
        self.accept()

    # -------------------------- 结果读取 --------------------------
    def result_values(self) -> Tuple[str, str, Optional[int], bool]:
        """返回编辑后的属性值。

        Returns:
            (标签, 描述, 分组编号, 困难样本标记) 四元组；
            Group ID 为空或非整数时返回 None。
        """
        label = self.label_edit.text().strip()
        description = self.desc_edit.text().strip()
        gid_text = self.group_edit.currentText().strip()
        try:
            gid = int(gid_text) if gid_text else None
        except ValueError:
            gid = None
        return label, description, gid, self.difficult_check.isChecked()

    @staticmethod
    def get_shape_props(
        labels: List[str],
        shape: Dict[str, Any],
        group_ids: Optional[List[int]] = None,
        parent=None,
    ) -> Optional[Tuple[str, str, Optional[int], bool]]:
        """弹窗编辑形状属性，返回结果或 None（取消时）。

        Args:
            labels: 已有类别列表。
            shape: 形状字典。
            group_ids: 画布现有分组编号集合（填充 Group ID 下拉选项），可为 None。
            parent: 父控件。

        Returns:
            (标签, 描述, 分组编号, 困难样本标记) 或 None。
        """
        dialog = ShapeDialog(labels, shape, group_ids, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.result_values()
        return None
