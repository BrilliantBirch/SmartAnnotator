# -*- coding: utf-8 -*-
"""
格式转换页 - ConvertPage

按 UI 文档 §5.2 与计划 §2.6：基础卡 + 数据集分析卡 + 高级卡 + 预览卡 + 进度卡。
源/目标格式交叉锁定（LABELME↔YOLO）。

数据集分析（2026-09-02 新增）：
    - 一键分析输入目录：提取 LabelMe 标签、推断任务类型（shape 特征）、
      自动识别转换方向（json→txt / txt→json）
    - 类别列表支持拖拽排序，行首数字即转换后的类别索引

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-02 新增"一键分析数据集"功能模块；类别列表升级为拖拽排序
更新: 2026-09-02 目录层级识别（label/image/dataset 层级自动解析标注与图片目录）；
      TXT→JSON 方向未配置类别时自动以类别索引作为标签名
更新: 2026-09-02 一键分析 POSE 推断结果自动填充关键点列表（按标注格式
      反推关键点数，默认名 kpt{i}_point{i}）
更新: 2026-09-02 类别/关键点列表高度自适应（按条目数与实际行高调整，
      最多显示 5/4 行后滚动），替代固定 200/140px 最小高度
更新: 2026-09-02 一键分析 LabelMe 方向 POSE 数据集时，point 类型标签
      归入关键点类别集合并自动填充关键点列表（不再混入普通类别列表）
"""

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QLabel,
    QComboBox,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QProgressBar,
    QPlainTextEdit,
    QMessageBox,
    QWidget,
    QFrame,
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Signal, Qt

from .base_page import BasePage
from ..widgets.buttons import PrimaryButton, SecondaryButton
from ..widgets.cards import Card
from ..widgets.drag_list import DragDropListWidget
from ..widgets.fields import PathField, LabeledSpin, CustomItemWidget, apply_click_to_focus
from ..widgets.preview import FilePreviewWidget
from ..widgets.dialogs import chooseDir, showMessageBox
from ..workers.analyze_worker import AnalyzeWorker
from ..core.convert.dataset_analyzer import DatasetAnalysis
from ..config import SysConfig, ConvertConfig, MODE, Format, RANDOM_SEED
from ..utils import LOGGER, scan_dataset_files
from ..utils.qt_logger import add_qt_handler


class ConvertPage(BasePage):
    """格式转换页 - LabelMe ↔ YOLO 双向转换。

    Signals:
        task_started: 任务开始（用于禁用导航）。
        task_finished: 任务结束（用于恢复导航）。
    """

    task_started = Signal()
    task_finished = Signal()

    def __init__(self, parent=None):
        """初始化格式转换页。"""
        super().__init__(parent)
        self._worker = None
        self._analyze_worker = None  # 数据集分析线程（一次性，用后销毁）
        self._class_items = []  # 类别 CustomItemWidget 引用
        self._kpt_items = []  # 关键点 CustomItemWidget 引用

        self._build_basic_card()
        self._build_analysis_card()
        self._build_advanced_card()
        self._build_preview_card()
        self._build_progress_card()

        # 初始状态：同步目标格式、高级卡可见性与任务类型联动（关键点列表仅 POSE 显示）
        self._on_source_changed()
        self._on_task_changed()
        # 焦点策略：所有数值控件改为点击获焦，防止悬停滚轮误改值
        apply_click_to_focus(self)

    def _build_basic_card(self) -> None:
        """构建基础卡：源/目标格式、任务类型、输入输出目录、开始/停止。"""
        self.basic_card = Card("基础设置")

        # 源格式 / 目标格式
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("源格式"))
        self.source_combo = QComboBox()
        self.source_combo.addItem("LabelMe (JSON)", Format.LABELME)
        self.source_combo.addItem("YOLO (TXT)", Format.YOLO)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        fmt_row.addWidget(self.source_combo)
        fmt_row.addSpacing(20)
        fmt_row.addWidget(QLabel("目标格式"))
        self.target_combo = QComboBox()
        self.target_combo.setEnabled(False)  # 目标格式由源格式决定
        fmt_row.addWidget(self.target_combo)
        fmt_row.addStretch()
        self.basic_card.addLayout(fmt_row)

        # 任务类型
        task_row = QHBoxLayout()
        task_row.addWidget(QLabel("任务类型"))
        self.task_combo = QComboBox()
        self.task_combo.addItem("目标检测 (DETECT)", MODE.DETECT)
        self.task_combo.addItem("姿态估计 (POSE)", MODE.POSE)
        self.task_combo.addItem("实例分割 (SEGMENT)", MODE.SEGMENT)
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)
        task_row.addWidget(self.task_combo)
        task_row.addStretch()
        self.basic_card.addLayout(task_row)

        # 输入目录
        self.input_field = PathField(browse_type="dir", placeholder="选择标注/图片所在目录")
        self.input_field.path_changed.connect(self._on_input_changed)
        self.basic_card.addWidget(self._labeled("输入目录", self.input_field))

        # 输出目录
        self.output_field = PathField(browse_type="dir", placeholder="选择输出目录")
        self.basic_card.addWidget(self._labeled("输出目录", self.output_field))

        # 文件计数 + 开始/停止
        action_row = QHBoxLayout()
        self.count_label = QLabel("未选择目录")
        self.count_label.setStyleSheet("color: #71717a;")
        action_row.addWidget(self.count_label)
        action_row.addStretch()
        self.btn_start = PrimaryButton("开始转换")
        self.btn_stop = SecondaryButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        action_row.addWidget(self.btn_stop)
        action_row.addWidget(self.btn_start)
        self.basic_card.addLayout(action_row)

        self.add_widget(self.basic_card)

    def _build_analysis_card(self) -> None:
        """构建数据集分析卡：一键分析按钮 + 进度条 + 结果摘要。

        分析自动完成：转换方向识别、任务类型推断、标签提取（填入类别列表）。
        """
        self.analysis_card = Card("数据集分析")

        # 操作行：分析按钮 + 进度条
        action_row = QHBoxLayout()
        self.btn_analyze = PrimaryButton("一键分析数据集")
        self.btn_analyze.clicked.connect(self._on_analyze)
        action_row.addWidget(self.btn_analyze)
        self.analysis_progress = QProgressBar()
        self.analysis_progress.setRange(0, 100)
        self.analysis_progress.setValue(0)
        self.analysis_progress.setMaximumWidth(240)
        action_row.addWidget(self.analysis_progress)
        action_row.addStretch()
        self.analysis_card.addLayout(action_row)

        # 结果摘要（多行富文本）
        self.analysis_summary = QLabel(
            "点击按钮分析输入目录：自动识别转换方向、推断任务类型、提取标签列表。"
        )
        self.analysis_summary.setWordWrap(True)
        self.analysis_summary.setStyleSheet("color: #3f3f46;")
        self.analysis_card.addWidget(self.analysis_summary)

        # 拖拽排序提示
        hint = QLabel(
            "提示：分析后类别列表自动填充至下方高级设置，支持拖拽调整顺序，"
            "行首数字即转换后的类别索引。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #71717a;")
        self.analysis_card.addWidget(hint)

        self.add_widget(self.analysis_card)

    # -------------------------- 数据集分析 --------------------------
    def _on_analyze(self) -> None:
        """启动数据集分析线程（后台执行，避免阻塞界面）。"""
        path = self.input_field.path()
        if not path or not Path(path).exists():
            showMessageBox(QMessageBox.Icon.Warning, "请先选择有效的输入目录")
            return
        # 防重复启动
        if self._analyze_worker is not None and self._analyze_worker.isRunning():
            return
        self.btn_analyze.setEnabled(False)
        self.analysis_progress.setValue(0)
        self.append_log(f"[分析] 开始分析数据集: {path}")
        self._analyze_worker = AnalyzeWorker(path)
        self._analyze_worker.progress_updated.connect(
            lambda p: self.analysis_progress.setValue(int(p * 100))
        )
        self._analyze_worker.progress_desc.connect(self.append_log)
        self._analyze_worker.analysis_finished.connect(self._on_analysis_finished)
        self._analyze_worker.error_occurred.connect(self._on_analysis_error)
        self._analyze_worker.task_finished.connect(self._on_analyze_done)
        self._analyze_worker.start()

    def _on_analyze_done(self) -> None:
        """分析线程结束（含异常终止）：恢复分析按钮。"""
        self.btn_analyze.setEnabled(True)

    def _on_analysis_error(self, message: str) -> None:
        """分析线程异常回调。"""
        self.append_log(f"[错误] {message}")
        showMessageBox(QMessageBox.Icon.Critical, f"数据集分析失败:\n{message}")

    def _on_analysis_finished(self, result: DatasetAnalysis) -> None:
        """分析完成回调：应用转换方向、任务类型并填充类别列表。

        自动推测结果均为界面默认值，用户可手动覆盖（下拉框保持可编辑）。

        Args:
            result: 数据集分析结果对象。
        """
        # 无标注文件：仅提示，不改动任何设置
        if result.json_count == 0 and result.txt_count == 0:
            self.analysis_summary.setText(
                f"未检测到标注文件（JSON/TXT 均为 0），请检查输入目录。"
                f"当前目录仅含图片 {result.image_count} 张。"
            )
            self.append_log("[分析] 未检测到任何标注文件")
            return

        # ===== 1. 转换方向自动识别（json→txt 或 txt→json）=====
        if result.source_format == Format.LABELME:
            direction_text = "LabelMe (JSON) → YOLO (TXT)"
            combo_idx = self.source_combo.findData(Format.LABELME)
        else:
            direction_text = "YOLO (TXT) → LabelMe (JSON)"
            combo_idx = self.source_combo.findData(Format.YOLO)
        if combo_idx >= 0:
            self.source_combo.setCurrentIndex(combo_idx)  # 触发 _on_source_changed

        # ===== 2. 任务类型推断 =====
        task_idx = self.task_combo.findData(result.task_type)
        if task_idx >= 0:
            self.task_combo.setCurrentIndex(task_idx)  # 触发 _on_task_changed
        task_names = {
            MODE.DETECT: "目标检测 (DETECT)",
            MODE.POSE: "姿态估计 (POSE)",
            MODE.SEGMENT: "实例分割 (SEGMENT)",
        }
        shape_text = "、".join(
            f"{k} {v} 个" for k, v in result.shape_counts.items()
        )

        # ===== 3. 标签提取：填充类别列表与关键点类别集合 =====
        if result.labels or result.kpt_labels:
            # LabelMe 方向：直接使用标注中的标签名。
            # POSE 数据集：point 类型标签属于关键点类别集合，单独填充
            # 关键点列表，不混入普通类别列表（否则转换时关键点全部丢失）
            if result.kpt_labels:
                kpt_lower = {k.lower() for k in result.kpt_labels}
                box_labels = [
                    l for l in result.labels if l.lower() not in kpt_lower
                ]
                self._fill_class_list(box_labels)
                self._fill_kpt_list(result.kpt_labels)
                labels_text = (
                    f"提取类别 {len(box_labels)} 个、关键点 {len(result.kpt_labels)} 个，"
                    f"已分别填充至类别列表与关键点列表（可修改）"
                )
            elif result.labels:
                self._fill_class_list(result.labels)
                labels_text = (
                    f"提取标签 {len(result.labels)} 个: " + ", ".join(result.labels)
                )
            else:
                labels_text = "仅提取到关键点标签，未检测到普通类别（矩形框）"
        elif result.source_format == Format.YOLO:
            # TXT 方向：标注不含标签名，类别列表为空时按类别索引自动填充
            # （默认使用索引作为标签名，用户可在下方列表中修改）
            if self._collect_classes():
                labels_text = "已保留当前类别列表（可在高级设置中修改名称与顺序）"
            else:
                index_names = [str(i) for i in range(result.max_class_id + 1)]
                if index_names:
                    self._fill_class_list(index_names)
                    labels_text = (
                        f"TXT 标注不含标签名，已按类别索引自动填充 {len(index_names)} 个类别，"
                        f"请在转换前按实际需求修改名称"
                    )
                else:
                    labels_text = "TXT 标注为空，未填充类别"
        else:
            labels_text = "未从标注中提取到标签"

        # ===== 3.5 POSE 任务：按推断关键点数自动填充关键点列表 =====
        kpt_text = ""
        if (
            result.source_format == Format.YOLO
            and result.task_type == MODE.POSE
            and result.kpt_count > 0
            and not self._collect_kpt()
        ):
            # 关键点名称须以 _point{序号} 结尾（默认 kpt{i}_point{i}，可修改）
            self._fill_kpt_list(
                [f"kpt{i}_point{i}" for i in range(result.kpt_count)]
            )
            kpt_text = (
                f"已按标注格式推断关键点 {result.kpt_count} 个并自动填充，"
                f"请按实际含义修改名称（须以 _point{{序号}} 结尾）"
            )

        # ===== 4. 汇总展示 =====
        lines = [
            f"目录层级: {result.structure_desc}",
            f"检测到 JSON 标注 {result.json_count} 个、TXT 标注 {result.txt_count} 个、"
            f"图片 {result.image_count} 张",
            f"转换方向（自动识别）: {direction_text}，可手动修改",
            f"任务类型（自动推断）: {task_names.get(result.task_type, '未知')}"
            + (f"（标注形状: {shape_text}）" if shape_text else ""),
            labels_text,
        ]
        if kpt_text:
            lines.append(kpt_text)
        if result.orphan_annotations:
            lines.append(
                f"警告: 检测到 {len(result.orphan_annotations)} 个孤立标注文件"
                f"（缺失对应图片，无法转换），详细信息已输出至日志"
            )
        if result.error_files:
            lines.append(
                f"警告: {len(result.error_files)} 个标注文件解析失败（已跳过），详见日志"
            )
            for err_file in result.error_files[:5]:
                self.append_log(f"[分析] 解析失败: {err_file}")
            showMessageBox(
                QMessageBox.Icon.Warning,
                f"{len(result.error_files)} 个标注文件格式异常已跳过：\n"
                + "\n".join(Path(f).name for f in result.error_files[:5])
                + ("..." if len(result.error_files) > 5 else ""),
            )
        self.analysis_summary.setText("\n".join(lines))
        self.append_log(f"[分析] 完成: 方向={direction_text}, "
                        f"任务={result.task_type.name}, 标签数={len(result.labels)}")

    def _fill_class_list(self, labels: list) -> None:
        """用分析出的标签列表重填类别编辑器（带行首索引）。

        Args:
            labels: 标签名列表（列表顺序即类别索引顺序）。
        """
        self.class_list.clear()
        self._class_items.clear()
        for name in labels:
            self._on_add_class()
            self._class_items[-1].edit.setText(name)
        self.class_list.refresh_indices()

    def _fill_kpt_list(self, names: list) -> None:
        """用关键点名称列表重填关键点编辑器。

        Args:
            names: 关键点名称列表（顺序即关键点索引顺序）。
        """
        self.kpt_list.clear()
        self._kpt_items.clear()
        for name in names:
            self._on_add_kpt()
            self._kpt_items[-1].edit.setText(name)

    def _build_advanced_card(self) -> None:
        """构建高级卡：类别/关键点编辑器、分割比例、可视化/导出、配置导入导出。"""
        self.advanced_card = Card("高级设置（分割比例与导出选项仅目标为 YOLO 时生效）")

        # 类别编辑器（支持拖拽排序：行首数字即转换后的类别索引）
        class_row = QHBoxLayout()
        class_row.addWidget(QLabel("类别列表"))
        class_row.addStretch()
        self.btn_add_class = SecondaryButton("+ 添加类别")
        self.btn_add_class.clicked.connect(self._on_add_class)
        class_row.addWidget(self.btn_add_class)
        self.advanced_card.addLayout(class_row)

        self.class_list = DragDropListWidget()
        # 高度自适应：随条目数调整（见 _adjust_list_height），最多显示 5 行
        self.advanced_card.addWidget(self.class_list)

        # 关键点编辑器（仅 POSE 显示，整体包装为容器便于显隐）
        self.kpt_container = QFrame()
        self.kpt_container.setStyleSheet("QFrame { border: 0; }")
        kpt_layout = QVBoxLayout(self.kpt_container)
        kpt_layout.setContentsMargins(0, 0, 0, 0)
        kpt_layout.setSpacing(8)
        self.kpt_label = QLabel("关键点列表（须以 _point{idx} 结尾）")
        self.kpt_label.setStyleSheet("color: #71717a;")
        kpt_layout.addWidget(self.kpt_label)
        kpt_row = QHBoxLayout()
        kpt_row.addStretch()
        self.btn_add_kpt = SecondaryButton("+ 添加关键点")
        self.btn_add_kpt.clicked.connect(self._on_add_kpt)
        kpt_row.addWidget(self.btn_add_kpt)
        kpt_layout.addLayout(kpt_row)
        self.kpt_list = QListWidget()
        # 高度自适应：随条目数调整（见 _adjust_list_height），最多显示 4 行
        kpt_layout.addWidget(self.kpt_list)
        self.advanced_card.addWidget(self.kpt_container)

        # 列表行结构变化（增删/拖拽排序/重填）时同步调整高度
        self.class_list.model().rowsInserted.connect(self._adjust_list_height)
        self.class_list.model().rowsRemoved.connect(self._adjust_list_height)
        self.kpt_list.model().rowsInserted.connect(self._adjust_list_height)
        self.kpt_list.model().rowsRemoved.connect(self._adjust_list_height)
        # 初始高度（空列表最小高度）
        self._adjust_list_height()

        # 分割比例
        ratio_row = QHBoxLayout()
        self.spin_train = LabeledSpin("训练集", "double", 0, 1, 0.05, 0.8)
        self.spin_val = LabeledSpin("验证集", "double", 0, 1, 0.05, 0.1)
        self.spin_test = LabeledSpin("测试集", "double", 0, 1, 0.05, 0.1)
        ratio_row.addWidget(self.spin_train)
        ratio_row.addWidget(self.spin_val)
        ratio_row.addWidget(self.spin_test)
        self.advanced_card.addLayout(ratio_row)

        # 可视化 / 导出
        opt_row = QHBoxLayout()
        self.chk_visualize = QCheckBox("可视化标注结果")
        self.chk_export = QCheckBox("导出 YOLO 数据集目录结构")
        opt_row.addWidget(self.chk_visualize)
        opt_row.addWidget(self.chk_export)
        opt_row.addStretch()
        self.advanced_card.addLayout(opt_row)

        # 导入/导出配置
        cfg_row = QHBoxLayout()
        cfg_row.addStretch()
        self.btn_import = SecondaryButton("导入配置")
        self.btn_export = SecondaryButton("导出配置")
        self.btn_import.clicked.connect(self._on_import_config)
        self.btn_export.clicked.connect(self._on_export_config)
        cfg_row.addWidget(self.btn_import)
        cfg_row.addWidget(self.btn_export)
        self.advanced_card.addLayout(cfg_row)

        self.add_widget(self.advanced_card)

    def _build_preview_card(self) -> None:
        """构建文件列表与图像预览卡。

        扫描输入目录后展示标注文件与图片文件列表，支持选择预览。
        预览区自适应缩放，适配不同屏幕分辨率。
        """
        self.preview_card = Card("文件列表与图像预览")
        self.preview_widget = FilePreviewWidget()
        self.preview_widget.setMinimumHeight(280)
        self.preview_card.addWidget(self.preview_widget)
        self.add_widget(self.preview_card)

    def _build_progress_card(self) -> None:
        """构建进度与日志卡。"""
        self.progress_card = Card("进度与日志")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_card.addWidget(self.progress_bar)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 10))
        self.log_edit.setMinimumHeight(160)
        self.progress_card.addWidget(self.log_edit)
        self.add_widget(self.progress_card)

    def _labeled(self, text: str, widget: QWidget) -> QWidget:
        """包装标签 + 控件为水平行容器。"""
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(text)
        lab.setMinimumWidth(72)
        lay.addWidget(lab)
        lay.addWidget(widget)
        return container

    # -------------------------- 格式联动 --------------------------
    def _on_source_changed(self) -> None:
        """源格式变化时同步目标格式与高级卡可见性。"""
        source = self.source_combo.currentData()
        target = Format.YOLO if source == Format.LABELME else Format.LABELME
        self.target_combo.clear()
        self.target_combo.addItem(
            "YOLO (TXT)" if target == Format.YOLO else "LabelMe (JSON)", target
        )
        # 类别/关键点列表双向转换均需要（txt→json 的 class_mapping 同样来自类别列表），
        # 高级卡保持可用；分割比例与导出选项仅目标为 YOLO 时参与转换
        self.advanced_card.setEnabled(True)
        self.advanced_card.setVisible(True)

    def _on_task_changed(self) -> None:
        """任务类型变化时切换关键点编辑器可见性。

        仅 POSE 任务显示关键点列表；DETECT/SEGMENT 等任务整体隐藏，
        避免残留空白区域。
        """
        mode = self.task_combo.currentData()
        is_pose = mode == MODE.POSE
        self.kpt_container.setVisible(is_pose)

    def _on_input_changed(self, path: str) -> None:
        """输入目录变化时统计文件数量并填充预览列表。

        按 YOLO 数据集目录层级自动识别（label/image/dataset 层级或平铺），
        标注与图片分别从解析出的对应目录扫描。
        """
        if not path or not Path(path).exists():
            self.count_label.setText("未选择目录")
            self.preview_widget.clear()
            return
        # 目录层级识别 + 分目录扫描（label 层级自动找兄弟 images 目录等）
        scan = scan_dataset_files(path)
        source = self.source_combo.currentData()
        if source == Format.LABELME:
            anno_files, label = scan["json_files"], "JSON 标注"
        else:
            anno_files, label = scan["txt_files"], "TXT 标注"
        image_files = scan["image_files"]
        self.count_label.setText(
            f"[{scan['structure']}] 已扫描到 {len(anno_files)} 个 {label}，"
            f"{len(image_files)} 张图片"
        )
        # 合并标注与图片文件（去重后按名称排序），填充预览列表
        all_files = sorted(set(anno_files + image_files))
        self.preview_widget.set_files(all_files)

    # -------------------------- 类别/关键点编辑器 --------------------------
    def _adjust_list_height(self, *args) -> None:
        """按条目数自适应调整类别/关键点列表高度。

        高度 = min(条目数, 最大可见行数) × 实际行高 + 内边距，
        超出部分由列表内部滚动；行高取自实际渲染度量，随分辨率/DPI
        缩放自然适配。超过最大可见行数时列表可滚动。

        Args:
            *args: 兼容 Qt 行结构信号的位置参数（忽略）。
        """
        # (列表, 最大可见行数, 空列表时的最小高度)
        configs = [
            (self.class_list, 5, 44),
            (self.kpt_list, 4, 44),
        ]
        for lst, max_visible, min_h in configs:
            count = lst.count()
            if count == 0:
                lst.setFixedHeight(min_h)
                continue
            # 取首/末行的实际渲染行高（随字体与 DPI 缩放）
            row_h = max(lst.sizeHintForRow(0), lst.sizeHintForRow(count - 1))
            if row_h <= 0:
                row_h = lst.itemWidget(lst.item(0)).sizeHint().height()
            visible = min(count, max_visible)
            # +12px：列表上下内边距与边框
            lst.setFixedHeight(max(min_h, visible * row_h + 12))

    def _on_add_class(self) -> None:
        """添加一个类别编辑项（带行首索引标签，支持拖拽排序）。"""
        item = QListWidgetItem()
        widget = CustomItemWidget("", self.class_list, check=False, show_index=True)
        item.setSizeHint(widget.sizeHint())
        self.class_list.addItem(item)
        self.class_list.setItemWidget(item, widget)
        self._class_items.append(widget)

    def _on_add_kpt(self) -> None:
        """添加一个关键点编辑项。"""
        item = QListWidgetItem()
        widget = CustomItemWidget("", self.kpt_list, check=True, checked=False)
        item.setSizeHint(widget.sizeHint())
        self.kpt_list.addItem(item)
        self.kpt_list.setItemWidget(item, widget)
        self._kpt_items.append(widget)

    def _collect_classes(self) -> list:
        """收集类别列表。"""
        classes = []
        for i in range(self.class_list.count()):
            item = self.class_list.item(i)
            widget = self.class_list.itemWidget(item)
            if widget and widget.get_text().strip():
                classes.append(widget.get_text().strip())
        return classes

    def _collect_kpt(self) -> dict:
        """收集关键点配置 {name: {"isChecked": bool, "bbox_size": int}}。"""
        kpt = {}
        for i in range(self.kpt_list.count()):
            item = self.kpt_list.item(i)
            widget = self.kpt_list.itemWidget(item)
            if widget and widget.get_text().strip():
                name = widget.get_text().strip()
                try:
                    bbox_size = int(widget.get_check_size())
                except (ValueError, AttributeError):
                    bbox_size = 10
                kpt[name] = {"isChecked": widget.get_check_status(), "bbox_size": bbox_size}
        return kpt

    # -------------------------- 配置读写 --------------------------
    def collect_config(self, sys_config: SysConfig) -> None:
        """从界面收集配置写入 sys_config。

        Args:
            sys_config: 系统配置对象（就地更新）。
        """
        sys_config.task_type = self.task_combo.currentData()
        cc = sys_config.convert_config
        cc.source_format = self.source_combo.currentData()
        cc.target_format = self.target_combo.currentData()
        cc.input_dir = self.input_field.path()
        cc.output_dir = self.output_field.path()
        cc.classes = self._collect_classes()
        cc.kpt = self._collect_kpt()
        cc.visualize = self.chk_visualize.isChecked()
        cc.export = self.chk_export.isChecked()
        cc.train_ratio = self.spin_train.value()
        cc.val_ratio = self.spin_val.value()
        cc.test_ratio = self.spin_test.value()
        # 扫描输入目录的标注与图片文件
        self._scan_input_files(cc)

    def _scan_input_files(self, cc: ConvertConfig) -> None:
        """扫描输入目录的标注与图片文件，填入运行期字段。

        按目录层级识别结果分目录扫描（label 层级自动取兄弟 images 目录
        的图片、image 层级自动取兄弟 labels 目录的标注等）。

        Args:
            cc: 转换配置对象。
        """
        cc.annotation_files = []
        cc.image_files = []
        if not cc.input_dir or not Path(cc.input_dir).exists():
            return
        scan = scan_dataset_files(cc.input_dir)
        if cc.source_format == Format.LABELME:
            cc.annotation_files = scan["json_files"]
        else:
            cc.annotation_files = scan["txt_files"]
        cc.image_files = scan["image_files"]

    def apply_config(self, sys_config: SysConfig) -> None:
        """从 sys_config 回填界面控件。

        Args:
            sys_config: 系统配置对象。
        """
        cc = sys_config.convert_config
        # 源格式
        idx = self.source_combo.findData(cc.source_format)
        if idx >= 0:
            self.source_combo.setCurrentIndex(idx)
        # 任务类型
        tidx = self.task_combo.findData(sys_config.task_type)
        if tidx >= 0:
            self.task_combo.setCurrentIndex(tidx)
        self._on_source_changed()
        self._on_task_changed()
        # 路径
        self.input_field.set_path(cc.input_dir)
        self.output_field.set_path(cc.output_dir)
        if cc.input_dir:
            self._on_input_changed(cc.input_dir)
        # 类别
        self.class_list.clear()
        self._class_items.clear()
        for name in cc.classes:
            self._on_add_class()
            self._class_items[-1].edit.setText(name)
        # 关键点
        self.kpt_list.clear()
        self._kpt_items.clear()
        for name, info in cc.kpt.items():
            self._on_add_kpt()
            w = self._kpt_items[-1]
            w.edit.setText(name)
            if w.check:
                w.check.setChecked(info.get("isChecked", False))
            if w.checkEdit:
                w.checkEdit.setText(str(info.get("bbox_size", 10)))
        # 比例与选项
        self.spin_train.set_value(cc.train_ratio)
        self.spin_val.set_value(cc.val_ratio)
        self.spin_test.set_value(cc.test_ratio)
        self.chk_visualize.setChecked(cc.visualize)
        self.chk_export.setChecked(cc.export)

    # -------------------------- 配置导入导出 --------------------------
    def _on_import_config(self) -> None:
        """导入 JSON 配置文件并回填界面。

        兼容旧版配置（参考 D:\\data\\CCA\\convert_config.json）：
            - ``mode`` 键作为任务类型（旧版），``task_type`` 键（新版），两者均接受
            - ``source_format`` 接受 "json"/"txt" 别名或 "LABELME"/"YOLO" 枚举名
            - 旧版 camelCase 键（sourceFormat/visualized）自动迁移
        """
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            None, "导入转换配置", "", "JSON 配置 (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cc = ConvertConfig.from_dict(data)
            sys_config = SysConfig()
            sys_config.convert_config = cc
            # 任务类型兼容：优先 task_type（新版），回退 mode（旧版参考标准）
            from ..config import _coerce_mode

            if "task_type" in data:
                sys_config.task_type = _coerce_mode(data["task_type"])
            elif "mode" in data:
                sys_config.task_type = _coerce_mode(data["mode"])
            self.apply_config(sys_config)
            self.append_log(f"[配置] 已导入配置: {path}")
        except Exception as e:
            LOGGER.error(f"导入转换配置失败: {e}")
            self.append_log(f"[错误] 导入配置失败: {e}")
            showMessageBox(QMessageBox.Icon.Critical, f"导入配置失败:\n{e}")

    def _on_export_config(self) -> None:
        """收集界面配置并导出为 JSON 文件。

        同时写入 ``mode`` 与 ``task_type`` 以兼容旧版与新版配置读取。
        """
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            None, "导出转换配置", "convert_config.json", "JSON 配置 (*.json)"
        )
        if not path:
            return
        try:
            sys_config = SysConfig()
            self.collect_config(sys_config)
            data = sys_config.convert_config.to_dict()
            # 同时写入 mode（旧版兼容）与 task_type（新版）
            data["mode"] = sys_config.task_type.name
            data["task_type"] = sys_config.task_type.name
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.append_log(f"[配置] 已导出配置至: {path}")
        except Exception as e:
            LOGGER.error(f"导出转换配置失败: {e}")
            self.append_log(f"[错误] 导出配置失败: {e}")

    # -------------------------- worker 集成 --------------------------
    def set_worker(self, worker) -> None:
        """绑定转换 worker 并连接信号。

        Args:
            worker: ConvertWorker 实例。
        """
        self._worker = worker
        self._worker.progress_updated.connect(self.update_progress)
        self._worker.progress_desc.connect(self.append_log)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.task_finished.connect(self._on_task_finished)
        # 接入 Qt 日志处理器，将 LOGGER 输出推送到日志面板
        qt_handler = add_qt_handler(parent=self, max_lines=500)
        if qt_handler is not None:
            qt_handler.log_signal.connect(self.append_log)

    def _on_start(self) -> None:
        """开始转换任务。"""
        if self._worker is None:
            return
        sys_config = SysConfig()
        self.collect_config(sys_config)
        # 校验必填项
        cc = sys_config.convert_config
        if not cc.input_dir:
            showMessageBox(QMessageBox.Icon.Warning, "请选择输入目录")
            return
        if not cc.output_dir:
            showMessageBox(QMessageBox.Icon.Warning, "请选择输出目录")
            return
        # json→txt 方向必须提供类别列表（生成类别索引映射）；
        # txt→json 方向允许为空：转换器自动以类别索引作为标签名（可在转换前于界面修改）
        if not cc.classes and cc.source_format == Format.LABELME:
            showMessageBox(QMessageBox.Icon.Warning, "请至少添加一个类别（可使用一键分析自动填充）")
            return
        self._worker.setConfig(sys_config)
        self.progress_bar.setValue(0)
        self.log_edit.clear()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.task_started.emit()
        self._worker.start()

    def _on_stop(self) -> None:
        """停止转换任务。"""
        if self._worker is not None:
            self._worker.stop()

    def update_progress(self, progress: float) -> None:
        """更新进度条。

        Args:
            progress: 进度值 0-1。
        """
        self.progress_bar.setValue(int(progress * 100))

    def append_log(self, message: str) -> None:
        """追加一行日志并自动滚动到底部。

        Args:
            message: 日志文本。
        """
        self.log_edit.appendPlainText(message)
        self.log_edit.verticalScrollBar().setValue(
            self.log_edit.verticalScrollBar().maximum()
        )

    def _on_error(self, message: str) -> None:
        """处理错误信号。"""
        self.append_log(f"[错误] {message}")
        showMessageBox(QMessageBox.Icon.Critical, message)

    def _on_task_finished(self) -> None:
        """任务结束回调。"""
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.task_finished.emit()

    def title(self) -> str:
        """返回页面标题。"""
        return "格式转换"
