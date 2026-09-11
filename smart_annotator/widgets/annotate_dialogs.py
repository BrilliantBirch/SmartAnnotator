# -*- coding: utf-8 -*-
"""
自动标注对话框 - AnnotateOptionsDialog / AnnotateProgressDialog

自动标注链路的两个 UI 组件：
    - AnnotateOptionsDialog: 批量标注前选择已标注图片的处理方式
      （跳过已标注 / 重新标注覆盖）
    - AnnotateProgressDialog: 标注进度对话框（模态，进度条 + 日志区 +
      暂停/恢复 + 中止按钮）。模态保证标注期间主窗口不可预览/编辑；中止
      语义复用 ScanProgressDialog 的"只发射一次 canceled"模式（中止按钮、
      标题栏关闭与 Esc 三条路径共用）；暂停/恢复经 pause_requested 信号
      由调用方接到 BaseWorker.pause/resume（run_callback 阻塞挂起，
      任务不中断）

作者: BaiBinnan
创建日期: 2026-09-03
更新: 2026-09-11 新增暂停/恢复按钮（pause_requested(bool) 信号，文案
      "暂停标注"↔"恢复标注"切换），对接 BaseWorker 既有暂停原语
"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QRadioButton,
    QVBoxLayout,
)

from .buttons import SecondaryButton


class AnnotateOptionsDialog(QDialog):
    """已标注图片处理方式选择对话框（跳过 / 覆盖）。

    批量标注前弹出；两种模式：
        - skip: 跳过已有标注文件的图片（仅标注未标注图片）
        - overwrite: 删除原标注文件后重新生成（覆盖模式）
    """

    def __init__(self, parent=None):
        """初始化选项对话框（单选组 + 确定/取消）。"""
        super().__init__(parent)
        self.setWindowTitle("自动标注选项")
        self.setMinimumWidth(440)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # ===== 提示文字（长文本自动换行）=====
        tip = QLabel("检测到已有标注文件，请选择已标注图片的处理方式：")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        # ===== 处理方式单选 =====
        self.rb_skip = QRadioButton("跳过已标注的图片（保留现有标注文件，仅标注未标注图片）")
        self.rb_overwrite = QRadioButton("重新标注并覆盖（删除原标注文件后重新生成）")
        self.rb_skip.setChecked(True)
        lay.addWidget(self.rb_skip)
        lay.addWidget(self.rb_overwrite)

        # ===== 按钮区 =====
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("开始标注")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    @staticmethod
    def get_mode(parent=None):
        """弹出对话框并返回处理方式。

        Args:
            parent: 父控件。

        Returns:
            "skip"（跳过）/ "overwrite"（覆盖）/ None（用户取消）。
        """
        dlg = AnnotateOptionsDialog(parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return "overwrite" if dlg.rb_overwrite.isChecked() else "skip"


class AnnotateProgressDialog(QDialog):
    """自动标注进度对话框（模态：进度条 + 日志区 + 暂停/恢复 + 中止按钮）。

    Signals:
        canceled: 用户请求中止标注（点击"中止"按钮或直接关闭对话框）。
        pause_requested(bool): 用户点击暂停/恢复按钮（True=请求暂停，
            False=请求恢复）；由调用方连接到 worker 的 pause()/resume()。
    """

    canceled = Signal()
    pause_requested = Signal(bool)

    def __init__(self, title: str, target: str, parent=None):
        """初始化进度对话框。

        Args:
            title: 窗口标题（如"自动标注 - 所有图片"）。
            target: 任务目标描述（图片数/视频数/输出目录，弱化灰字展示）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)  # 模态：标注期间阻塞主窗口的预览与编辑
        self.setMinimumSize(500, 340)

        # 防重复发射标志：canceled 只发射一次
        self._canceled_emitted = False
        # 暂停状态（按钮文案切换依据）
        self._paused = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ===== 任务目标（弱化灰字，长路径自动换行）=====
        self.target_label = QLabel(target)
        self.target_label.setStyleSheet("color: #71717a;")
        self.target_label.setWordWrap(True)
        lay.addWidget(self.target_label)

        # ===== 进度条 =====
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(True)
        lay.addWidget(self.progress)

        # ===== 日志区（只读，限制最大块数防止长任务内存膨胀）=====
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        lay.addWidget(self.log, 1)

        # ===== 暂停/恢复 + 中止按钮（右对齐）=====
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.pause_btn = SecondaryButton("暂停标注")
        self.pause_btn.clicked.connect(self._toggle_pause)
        btn_row.addWidget(self.pause_btn)
        self.abort_btn = SecondaryButton("中止标注")
        self.abort_btn.clicked.connect(self._emit_canceled)
        btn_row.addWidget(self.abort_btn)
        lay.addLayout(btn_row)

    # -------------------------- 对外接口 --------------------------
    def update_progress(self, ratio: float) -> None:
        """更新进度条（比例钳制到 0-1）。

        Args:
            ratio: 进度比例（0-1）。
        """
        ratio = max(0.0, min(1.0, float(ratio)))
        self.progress.setValue(int(round(ratio * 100)))

    def append_log(self, msg: str) -> None:
        """向日志区追加一行进度信息。

        Args:
            msg: 进度描述文本。
        """
        self.log.appendPlainText(msg)

    # -------------------------- 暂停/恢复 --------------------------
    def _toggle_pause(self) -> None:
        """暂停/恢复按钮入口：切换文案并广播请求。

        worker 层经 BaseWorker.pause/resume 实现挂起/唤醒（run_callback
        阻塞等待，任务不中断）；任务完成/中止后由调用方关闭对话框。
        """
        self._paused = not self._paused
        self.pause_btn.setText("恢复标注" if self._paused else "暂停标注")
        self.pause_requested.emit(self._paused)

    # -------------------------- 中止处理 --------------------------
    def _notify_canceled(self) -> None:
        """仅发射 canceled 信号（防重复），不关闭窗口。

        中止按钮、标题栏关闭与 Esc 三条路径共用，保证信号只发射一次。
        """
        if not self._canceled_emitted:
            self._canceled_emitted = True
            self.canceled.emit()

    def _emit_canceled(self) -> None:
        """中止按钮入口：发射 canceled 信号并关闭自身（重复调用不生效）。"""
        if self._canceled_emitted:
            return
        self._notify_canceled()
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        """标题栏直接关闭窗口同样视为中止。

        Args:
            event: 关闭事件。
        """
        # 不调用 _emit_canceled（其内部 close() 会造成嵌套），仅发射信号
        self._notify_canceled()
        super().closeEvent(event)

    def reject(self) -> None:
        """Esc 键视为中止（发射信号后按默认行为关闭对话框）。"""
        self._notify_canceled()
        super().reject()
