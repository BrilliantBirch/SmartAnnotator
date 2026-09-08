# -*- coding: utf-8 -*-
"""
自定义快捷键设置对话框 - ShortcutDialog

以表格列出全部可配置动作及当前绑定的快捷键，支持：
    - 选中行后在 QKeySequenceEdit 中录入新键序列，写回所选动作
    - 冲突检测：任意两个动作绑定相同（非空）键序列时红字提示并禁用"确定"
    - 单个动作 / 全部动作恢复默认（取 config.DEFAULT_SHORTCUTS）

三态语义：无冲突时点击"确定"返回编辑后的 bindings 字典（新字典，不污染调用方）；
点击"取消"返回 None；存在冲突时"确定"按钮被禁用，必须先消除冲突。

作者: BaiBinnan
创建日期: 2026-09-07
"""

from typing import Dict, Optional

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QKeySequenceEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..config import DEFAULT_SHORTCUTS


class ShortcutDialog(QDialog):
    """自定义快捷键设置对话框（模态）。

    用途：集中查看/修改应用快捷键绑定，实时检测冲突并阻止带冲突保存。
    三态语义：
        - 确定（无冲突）：返回编辑后的 bindings 字典副本；
        - 取消：返回 None；
        - 冲突：确定按钮禁用，必须先消除冲突才能保存。

    使用 get_shortcuts 静态方法一键弹出并获取结果。
    """

    def __init__(
        self,
        action_defs: Dict[str, str],
        bindings: Dict[str, str],
        parent=None,
    ):
        """初始化对话框，构建表格与录入控件并做首次冲突检测。

        Args:
            action_defs: action_id → 中文描述（有序，按传入顺序显示）。
            bindings: action_id → 当前键序列字符串（如 "Ctrl+S"）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setWindowTitle("自定义快捷键")
        self.setMinimumWidth(420)

        # 工作副本：编辑过程不影响调用方传入的字典，确定时才返回新字典
        self.bindings: Dict[str, str] = dict(bindings)
        # action_id → 中文描述（保存引用，冲突提示中据此显示动作名）
        self._action_defs: Dict[str, str] = dict(action_defs)
        # 表格行号 → action_id（按 action_defs 传入顺序）
        self._row_ids = list(action_defs.keys())

        # ===== 主垂直布局 =====
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ===== 顶部说明 =====
        tip = QLabel("双击条目或选中后点击“修改”，在输入框中按下新快捷键组合")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # ===== 中部：动作 / 当前快捷键 表格 =====
        self.table = QTableWidget(len(self._row_ids), 2, self)
        self.table.setHorizontalHeaderLabels(["动作", "当前快捷键"])
        # 只读、整行选择、单选
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # 关闭行号列，末列随窗口拉伸
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        # ===== 录入区：键序列编辑框 + 修改 / 恢复按钮 =====
        edit_row = QHBoxLayout()
        self.key_edit = QKeySequenceEdit(self)
        edit_row.addWidget(self.key_edit, 1)

        self.apply_btn = QPushButton("修改所选", self)
        self.apply_btn.clicked.connect(self._on_apply_change)
        edit_row.addWidget(self.apply_btn)

        self.restore_one_btn = QPushButton("恢复该动作默认", self)
        self.restore_one_btn.clicked.connect(self._on_restore_one)
        edit_row.addWidget(self.restore_one_btn)

        self.restore_all_btn = QPushButton("全部恢复默认", self)
        self.restore_all_btn.clicked.connect(self._on_restore_all)
        edit_row.addWidget(self.restore_all_btn)
        layout.addLayout(edit_row)

        # ===== 冲突提示（默认隐藏，红字）=====
        self.conflict_label = QLabel("", self)
        self.conflict_label.setStyleSheet("color: #dc2626;")
        self.conflict_label.setWordWrap(True)
        self.conflict_label.hide()
        layout.addWidget(self.conflict_label)

        # ===== 底部：确定 / 取消 =====
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        layout.addWidget(self.button_box)
        self.ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)

        # ===== 信号连接 =====
        # 选中行变化 → 录入框同步该行当前键
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        # 双击行 → 选中并聚焦录入框，方便直接按键
        self.table.cellDoubleClicked.connect(self._on_table_double)

        # 初始化：填充表格、选中首行、做首次冲突检测
        self._refresh_table()
        if self._row_ids:
            self.table.selectRow(0)
        self._check_conflicts()

    # -------------------------- 表格构建与刷新 --------------------------
    def _refresh_table(self) -> None:
        """按当前 bindings 刷新表格各行"当前快捷键"列文本。"""
        for row, action_id in enumerate(self._row_ids):
            # 第一列：动作中文描述
            name_item = QTableWidgetItem(self._action_defs.get(action_id, action_id))
            self.table.setItem(row, 0, name_item)
            # 第二列：当前键序列字符串
            seq_text = self.bindings.get(action_id, "")
            self.table.setItem(row, 1, QTableWidgetItem(seq_text))

    def _current_action_id(self) -> Optional[str]:
        """返回当前选中行对应的 action_id。

        Returns:
            选中的 action_id；无选中行时返回 None。
        """
        row = self.table.currentRow()
        if 0 <= row < len(self._row_ids):
            return self._row_ids[row]
        return None

    # -------------------------- 交互处理 --------------------------
    def _on_selection_changed(self) -> None:
        """选中行变化：录入框同步显示该行当前绑定的键序列。"""
        action_id = self._current_action_id()
        if action_id is None:
            return
        # 仅回显当前绑定，不清空用户已录入但未应用的内容以外的状态
        self.key_edit.setKeySequence(QKeySequence(self.bindings.get(action_id, "")))

    def _on_table_double(self, row: int, column: int) -> None:
        """双击表格行：选中该行并聚焦录入框，方便直接按下新快捷键。

        Args:
            row: 被双击的行号。
            column: 被双击的列号（忽略）。
        """
        if 0 <= row < len(self._row_ids):
            self.table.selectRow(row)
            self.key_edit.setFocus()

    def _on_apply_change(self) -> None:
        """点击"修改所选"：将录入框中的新键序列写回选中动作并检测冲突。

        录入为空（未按键）时忽略本次操作。
        """
        action_id = self._current_action_id()
        if action_id is None:
            return
        # 取录入框键序列并转为可持久化的 PortableText 字符串
        seq_text = self.key_edit.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if not seq_text:
            # 未录入新键，忽略
            return
        # 写回绑定并刷新该行显示
        self.bindings[action_id] = seq_text
        self._refresh_table()
        self._check_conflicts()

    def _on_restore_one(self) -> None:
        """点击"恢复该动作默认"：选中动作绑定回退为 DEFAULT_SHORTCUTS 默认值。

        无选中行或该动作不在默认表中时忽略。
        """
        action_id = self._current_action_id()
        if action_id is None or action_id not in DEFAULT_SHORTCUTS:
            return
        # 恢复默认并刷新 + 冲突检测
        self.bindings[action_id] = DEFAULT_SHORTCUTS[action_id]
        self._refresh_table()
        self._check_conflicts()

    def _on_restore_all(self) -> None:
        """点击"全部恢复默认"：全部绑定回退为 DEFAULT_SHORTCUTS 的副本。"""
        self.bindings = dict(DEFAULT_SHORTCUTS)
        self._refresh_table()
        self._check_conflicts()

    # -------------------------- 冲突检测 --------------------------
    def _check_conflicts(self) -> None:
        """检测键序列冲突并更新提示与确定按钮状态。

        遍历 bindings，任意两个动作的键序列经 PortableText 归一化后相同
        且非空即判定冲突：显示"快捷键冲突：{键} 已分配给 {A} 与 {B}"
        并禁用确定按钮；无冲突时隐藏提示并启用确定按钮。
        """
        # 归一化：action_id → PortableText 键序列（跳过空绑定）
        normalized: Dict[str, str] = {}
        for action_id, seq_text in self.bindings.items():
            text = QKeySequence(str(seq_text)).toString(
                QKeySequence.SequenceFormat.PortableText
            )
            if text:
                normalized[action_id] = text

        # 两两比对找第一处冲突
        ids = list(normalized.keys())
        conflict_pair: Optional[tuple] = None
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if normalized[ids[i]] == normalized[ids[j]]:
                    conflict_pair = (ids[i], ids[j])
                    break
            if conflict_pair:
                break

        if conflict_pair:
            # 冲突：红字提示 + 禁用确定
            id_a, id_b = conflict_pair
            desc_a = self._action_defs.get(id_a, id_a)
            desc_b = self._action_defs.get(id_b, id_b)
            self.conflict_label.setText(
                f"快捷键冲突：{normalized[id_a]} 已分配给 {desc_a} 与 {desc_b}"
            )
            self.conflict_label.show()
            self.ok_button.setEnabled(False)
        else:
            # 无冲突：隐藏提示 + 启用确定
            self.conflict_label.hide()
            self.ok_button.setEnabled(True)

    # -------------------------- 结果读取 --------------------------
    def get_bindings(self) -> Dict[str, str]:
        """返回编辑后的绑定字典副本。

        Returns:
            action_id → 键序列字符串的新字典（与传入字典相互独立）。
        """
        return dict(self.bindings)

    @staticmethod
    def get_shortcuts(
        action_defs: Dict[str, str],
        bindings: Dict[str, str],
        parent=None,
    ) -> Optional[Dict[str, str]]:
        """模态打开对话框，返回编辑结果或 None（取消时）。

        Args:
            action_defs: action_id → 中文描述（有序，按传入顺序显示）。
            bindings: action_id → 当前键序列字符串。
            parent: 父控件。

        Returns:
            确定（无冲突）时返回编辑后的 bindings 字典副本；取消时返回 None。
        """
        dialog = ShortcutDialog(action_defs, bindings, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_bindings()
        return None
