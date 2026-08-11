# -*- coding: utf-8 -*-
"""
格式转换页 - ConvertPage

按 UI 文档 §5.2 与计划 §2.6：基础卡 + 高级卡。
源/目标格式交叉锁定（LABELME↔YOLO），目标为 YOLO 时启用高级卡。

作者: BaiBinnan
创建日期: 2026-08-10
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
from ..widgets.fields import PathField, LabeledSpin, CustomItemWidget, apply_click_to_focus
from ..widgets.preview import FilePreviewWidget
from ..widgets.dialogs import chooseDir, showMessageBox
from ..config import SysConfig, ConvertConfig, MODE, Format, RANDOM_SEED
from ..utils import LOGGER, getJsonFilesInDir, getTxtFilesInDir, getImageFilesInDir
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
        self._class_items = []  # 类别 CustomItemWidget 引用
        self._kpt_items = []  # 关键点 CustomItemWidget 引用

        self._build_basic_card()
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

    def _build_advanced_card(self) -> None:
        """构建高级卡：类别/关键点编辑器、分割比例、可视化/导出、配置导入导出。"""
        self.advanced_card = Card("高级设置（目标为 YOLO 时生效）")

        # 类别编辑器
        class_row = QHBoxLayout()
        class_row.addWidget(QLabel("类别列表"))
        class_row.addStretch()
        self.btn_add_class = SecondaryButton("+ 添加类别")
        self.btn_add_class.clicked.connect(self._on_add_class)
        class_row.addWidget(self.btn_add_class)
        self.advanced_card.addLayout(class_row)

        self.class_list = QListWidget()
        # 最小高度 200px，确保类别项清晰展示（约 6 项），避免内容被压缩
        self.class_list.setMinimumHeight(200)
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
        self.kpt_list.setMinimumHeight(140)
        kpt_layout.addWidget(self.kpt_list)
        self.advanced_card.addWidget(self.kpt_container)

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
        # 高级卡仅目标为 YOLO 时启用
        enabled = target == Format.YOLO
        self.advanced_card.setEnabled(enabled)
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
        """输入目录变化时统计文件数量并填充预览列表。"""
        if not path or not Path(path).exists():
            self.count_label.setText("未选择目录")
            self.preview_widget.clear()
            return
        source = self.source_combo.currentData()
        if source == Format.LABELME:
            anno_files = getJsonFilesInDir(path)
            label = "JSON 标注"
        else:
            anno_files = getTxtFilesInDir(path)
            label = "TXT 标注"
        image_files = getImageFilesInDir(path)
        self.count_label.setText(
            f"已扫描到 {len(anno_files)} 个 {label} 文件，{len(image_files)} 张图片"
        )
        # 合并标注与图片文件（去重后按名称排序），填充预览列表
        all_files = sorted(set(anno_files + image_files))
        self.preview_widget.set_files(all_files)

    # -------------------------- 类别/关键点编辑器 --------------------------
    def _on_add_class(self) -> None:
        """添加一个类别编辑项。"""
        item = QListWidgetItem()
        widget = CustomItemWidget("", self.class_list, check=False)
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

        Args:
            cc: 转换配置对象。
        """
        cc.annotation_files = []
        cc.image_files = []
        if not cc.input_dir or not Path(cc.input_dir).exists():
            return
        if cc.source_format == Format.LABELME:
            cc.annotation_files = getJsonFilesInDir(cc.input_dir)
        else:
            cc.annotation_files = getTxtFilesInDir(cc.input_dir)
        cc.image_files = getImageFilesInDir(cc.input_dir)

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
        if cc.target_format == Format.YOLO and not cc.classes:
            showMessageBox(QMessageBox.Icon.Warning, "目标为 YOLO 时至少添加一个类别")
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
