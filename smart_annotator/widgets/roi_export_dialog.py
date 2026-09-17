# -*- coding: utf-8 -*-
"""
感知区（ROI）导出对话框 - RoiExportDialog

手动触发感知区裁剪导出时的参数收集窗口，只收集不执行：
    - 导出范围：仅当前图片（默认）或 全部图片（批处理）；当前无打开图片
      （current_image 为空）时"当前图片"置灰且默认选"全部图片"；
    - 输出目录：默认 <工作目录>/ROI（roi_export.roi_output_dir），可经
      "浏览..."更改为任意目录，纯空白时不允许确定。

实际导出由主窗口接后台线程 RoiExportWorker 完成，调用方经
RoiExportDialog.get_settings 取回 {"scope", "out_dir"} 后启动线程。

作者: BaiBinnan
创建日期: 2026-09-17
更新: 2026-09-17 新建：收集导出范围与输出目录的对话框，校验后交后台线程执行
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ..core.roi_export import roi_output_dir
from .buttons import SecondaryButton
from .dialogs import showMessageBox


class RoiExportDialog(QDialog):
    """感知区数据导出对话框（范围 + 输出目录）。

    范围取值（scope）："current"（仅当前图片）/ "all"（全部图片批处理）。
    """

    def __init__(self, work_dir: str, current_image: str, parent=None):
        """初始化导出对话框。

        Args:
            work_dir: 数据集工作目录（原图与 JSON 所在目录），用于生成默认
                输出目录 <work_dir>/ROI。
            current_image: 当前打开的图片路径；为空字符串表示无当前图片
                （此时只能导出全部图片）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setWindowTitle("导出感知区数据")
        self.setMinimumWidth(480)

        # 当前图片路径（范围单选"当前图片"可用性的依据；保存以便后续复用）
        self._current_image = current_image or ""
        has_current = bool(self._current_image)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # ===== 提示文字（长文本自动换行）=====
        tip = QLabel("将按感知区（ROI）裁剪原图与标注，输出到指定目录。")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        # ===== 参数区：导出范围 + 输出目录 =====
        form = QFormLayout()
        form.setSpacing(10)

        # 导出范围：单选（当前图片 / 全部图片）
        scope_box = QWidget()
        scope_col = QVBoxLayout(scope_box)
        scope_col.setContentsMargins(0, 0, 0, 0)
        scope_col.setSpacing(6)
        self.rb_current = QRadioButton("当前图片")
        self.rb_all = QRadioButton("全部图片（批处理）")
        # 无当前图片时"当前图片"不可选，默认落到批处理
        self.rb_current.setEnabled(has_current)
        if has_current:
            self.rb_current.setChecked(True)
        else:
            self.rb_all.setChecked(True)
        scope_col.addWidget(self.rb_current)
        scope_col.addWidget(self.rb_all)
        form.addRow("导出范围:", scope_box)

        # 输出目录：输入框 + 浏览按钮（默认 <工作目录>/ROI）
        out_box = QWidget()
        out_row = QHBoxLayout(out_box)
        out_row.setContentsMargins(0, 0, 0, 0)
        out_row.setSpacing(6)
        self.out_edit = QLineEdit(str(roi_output_dir(work_dir)))
        self.out_edit.setPlaceholderText("选择感知区导出目录")
        out_row.addWidget(self.out_edit, 1)
        self.browse_btn = SecondaryButton("浏览...")
        self.browse_btn.clicked.connect(self._on_browse)
        out_row.addWidget(self.browse_btn)
        form.addRow("输出目录:", out_box)

        lay.addLayout(form)
        lay.addStretch()

        # ===== 按钮区 =====
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("开始导出")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    # -------------------------- 交互 --------------------------
    def _on_browse(self) -> None:
        """点击"浏览..."：选择输出目录并回填输入框。"""
        path = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.out_edit.text() or ""
        )
        if path:
            self.out_edit.setText(path)

    def accept(self) -> None:
        """确定前校验：输出目录不得为空或纯空白，否则提示且不关闭。"""
        if not self.out_edit.text().strip():
            showMessageBox(QMessageBox.Icon.Warning, "请选择输出目录")
            return
        super().accept()

    # -------------------------- 结果读取 --------------------------
    def scope(self) -> str:
        """返回导出范围。

        Returns:
            "current"（仅当前图片）或 "all"（全部图片批处理）。
        """
        return "current" if self.rb_current.isChecked() else "all"

    def output_dir(self) -> str:
        """返回输出目录（原样文本，未做去空白处理）。

        Returns:
            输出目录路径字符串。
        """
        return self.out_edit.text()

    @classmethod
    def get_settings(
        cls, work_dir: str, current_image: str, parent=None
    ) -> Optional[dict]:
        """模态弹出对话框并返回导出参数。

        Args:
            work_dir: 数据集工作目录。
            current_image: 当前打开的图片路径（可为空字符串）。
            parent: 父控件。

        Returns:
            {"scope": "current"|"all", "out_dir": str}；用户取消时返回 None。
        """
        dlg = cls(work_dir, current_image, parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return {"scope": dlg.scope(), "out_dir": dlg.output_dir()}