# -*- coding: utf-8 -*-
"""
标签扫描统计对话框 - ScanProgressDialog / ScanStatsDialog

标签扫描链路的两个 UI 组件：
    - ScanProgressDialog: 扫描进度对话框（非模态，进度条 + 中止按钮，
      点击"中止"、标题栏关闭与 Esc 均视为中止，只发射一次 canceled 信号）
    - ScanStatsDialog: 统计结果窗口（非模态，表格展示各标签实例个数，
      计数已由扫描链路合并大小写）

作者: BaiBinnan
创建日期: 2026-09-03
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .buttons import SecondaryButton


class ScanProgressDialog(QDialog):
    """标签扫描进度对话框（非模态，带进度条与中止按钮）。

    Signals:
        canceled: 用户请求中止扫描（点击"中止"按钮或直接关闭对话框）。
    """

    canceled = Signal()

    def __init__(self, work_dir: str, parent=None):
        """初始化进度对话框。

        Args:
            work_dir: 当前扫描的工作目录路径（展示用）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setWindowTitle("标签扫描统计")
        self.setModal(False)  # 非模态：扫描期间不阻塞标注编辑主窗口
        self.setMinimumWidth(420)

        # 防重复发射标志：canceled 只发射一次
        self._canceled_emitted = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ===== 目录路径（弱化灰字，长路径自动换行）=====
        self.dir_label = QLabel(f"扫描目录: {work_dir}")
        self.dir_label.setStyleSheet("color: #71717a;")
        self.dir_label.setWordWrap(True)
        lay.addWidget(self.dir_label)

        # ===== 进度条（文件数与百分比，药丸形样式来自全局 QSS）=====
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(True)
        lay.addWidget(self.progress)

        # ===== 中止按钮（右对齐）=====
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.abort_btn = SecondaryButton("中止")
        self.abort_btn.clicked.connect(self._emit_canceled)
        btn_row.addWidget(self.abort_btn)
        lay.addLayout(btn_row)

    # -------------------------- 对外接口 --------------------------
    def update_progress(self, done: int, total: int) -> None:
        """更新进度条（文件数与百分比）。

        Args:
            done: 已完成文件数。
            total: 总文件数。
        """
        # 总数非法（<= 0）时置 0%，避免除零
        if total <= 0:
            self.progress.setValue(0)
            self.progress.setFormat(f"已扫描 {done}/0 个标注文件")
            return
        self.progress.setValue(round(done / total * 100))
        self.progress.setFormat(f"已扫描 {done}/{total} 个标注文件")

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
        # 注意：不在此处调用 _emit_canceled（其内部的 close() 会造成
        # closeEvent 嵌套），仅发射信号，关闭动作交给事件默认处理
        self._notify_canceled()
        super().closeEvent(event)

    def reject(self) -> None:
        """Esc 键视为中止（发射信号后按默认行为关闭对话框）。"""
        self._notify_canceled()
        super().reject()


class ScanStatsDialog(QDialog):
    """标签统计结果窗口（非模态，表格展示各标签实例个数）。

    计数已由扫描链路合并大小写（如 person 与 Person 计入同一行，
    行标签取首次出现的拼写）。
    """

    def __init__(self, work_dir: str, parent=None):
        """初始化统计窗口。

        Args:
            work_dir: 扫描的工作目录路径（展示用）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setWindowTitle("标签统计")
        self.setModal(False)  # 非模态：可边查看统计边继续编辑
        self.resize(420, 480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ===== 标题区：目录路径 + 汇总信息 =====
        self.dir_label = QLabel(f"扫描目录: {work_dir}")
        self.dir_label.setStyleSheet("color: #71717a;")
        self.dir_label.setWordWrap(True)
        lay.addWidget(self.dir_label)

        self.summary_label = QLabel("暂无统计结果")
        lay.addWidget(self.summary_label)

        # ===== 统计表格（只读、整行选择、紧凑行高、无垂直表头）=====
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["标签", "实例个数"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        # 列宽：标签列自适应拉伸，个数列按内容收缩
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)

        # ===== 关闭按钮（右对齐）=====
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.close_btn = SecondaryButton("关闭")
        self.close_btn.clicked.connect(self.close)
        btn_row.addWidget(self.close_btn)
        lay.addLayout(btn_row)

    # -------------------------- 对外接口 --------------------------
    def set_counts(self, counts: list, file_total: int = 0) -> None:
        """填充统计表格与汇总信息。

        Args:
            counts: [标签, 实例个数] 二元组列表（已按个数降序、同数按
                标签字典序排序）。
            file_total: 扫描的标注文件总数（汇总展示，0 表示未知）。
        """
        # 逐行填充：标签列默认左对齐，个数列右对齐
        self.table.setRowCount(len(counts))
        for row, pair in enumerate(counts):
            name_item = QTableWidgetItem(str(pair[0]))
            count_item = QTableWidgetItem(str(int(pair[1])))
            count_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, count_item)

        # 汇总信息：标签种类 + 实例总数（标注文件总数已知时附加）
        if not counts:
            self.summary_label.setText("暂无统计结果")
            return
        total_instances = sum(int(pair[1]) for pair in counts)
        summary = f"标签种类 {len(counts)} 种 · 实例总数 {total_instances} 个"
        if file_total > 0:
            summary += f" · 标注文件 {file_total} 个"
        self.summary_label.setText(summary)
