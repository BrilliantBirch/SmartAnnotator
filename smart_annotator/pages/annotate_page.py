# -*- coding: utf-8 -*-
"""
自动标注页 - AnnotatePage

按 UI 文档 §5.3 与计划 §2.6：6 卡片布局。
1. 运行设备：CPU/GPU 单选（默认 GPU 若 CUDA 可用，否则 CPU 并禁用 GPU）
2. 路径设置：模型路径 / 图片目录 / 输出目录
3. 检测类别：模型加载后自动读取元数据类别，复选列表 + 全选/取消全选
4. 推理参数：BBox 置信度、NMS、关键点置信度(POSE)、抽帧间隔、差异阈值(视频)
5. 操作区：导入/导出配置、任务类型、开始/停止
6. 进度与日志：进度条 + 日志面板

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-08-26 新增检测类别卡片（模型元数据解析 + 类别选择 + 后端过滤）
"""

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QLabel,
    QComboBox,
    QHBoxLayout,
    QGridLayout,
    QRadioButton,
    QButtonGroup,
    QProgressBar,
    QPlainTextEdit,
    QMessageBox,
    QWidget,
    QFileDialog,
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Signal, Qt

from .base_page import BasePage
from ..widgets.buttons import PrimaryButton, SecondaryButton
from ..widgets.cards import Card
from ..widgets.class_selector import ClassSelectorWidget
from ..widgets.fields import PathField, LabeledSpin, apply_click_to_focus
from ..widgets.preview import FilePreviewWidget
from ..widgets.dialogs import showMessageBox
from ..config import SysConfig, AnnotateConfig, MODE, DEVICE
from ..utils import LOGGER, getImageFilesInDir, getVideoFilesInDir, getModelClasses
from ..utils.qt_logger import add_qt_handler


def _cuda_available() -> bool:
    """检测当前环境是否存在可用的 CUDA 推理后端。

    GPU 模式依赖两个组件：
    1. tensorrt（GPU 模式实际使用 TensorRT engine 推理）
    2. cuda-python（cuda.bindings.cydriver / cyruntime，TensorRT 后端 CUDA 内存操作）

    onnxruntime 仅用于 CPU 模式推理（CPUExecutionProvider），
    不依赖 onnxruntime CUDA EP，只需确认可导入即可。
    任一组件缺失则返回 False，并在日志中记录缺失项。

    Returns:
        True 表示 TensorRT + cuda-python 均可用，否则 False。
    """
    # 检查 onnxruntime 可导入（CPU 模式推理 / GPU 模式回退使用）
    try:
        import onnxruntime as ort  # noqa: F401
    except Exception as e:
        LOGGER.warning(f"CUDA 检测: onnxruntime 导入失败: {e}")
        return False

    # 检查 TensorRT（GPU 模式推理引擎）
    try:
        import tensorrt  # noqa: F401
    except Exception as e:
        LOGGER.warning(f"CUDA 检测: tensorrt 导入失败: {e}，GPU 模式不可用")
        return False

    # 检查 cuda-python（TensorRT 后端依赖 from cuda import cuda, cudart）
    try:
        from cuda import cuda, cudart  # noqa: F401
    except Exception as e:
        LOGGER.warning(
            f"CUDA 检测: cuda-python 导入失败: {e}，"
            f"GPU 模式不可用（缺少 cuda.bindings.cydriver）"
        )
        return False

    return True


class AnnotatePage(BasePage):
    """自动标注页 - 模型推理 + LabelMe 标注输出。

    Signals:
        task_started: 任务开始（用于禁用导航）。
        task_finished: 任务结束（用于恢复导航）。
    """

    task_started = Signal()
    task_finished = Signal()

    def __init__(self, parent=None):
        """初始化自动标注页，构建 5 张卡片。"""
        super().__init__(parent)
        self._worker = None
        self._cuda_ok = _cuda_available()

        self._build_device_card()
        self._build_path_card()
        self._build_class_card()
        self._build_param_card()
        self._build_action_card()
        self._build_preview_card()
        self._build_progress_card()

        # 初始状态：同步参数可见性与设备可用性
        self._on_task_changed()
        self._sync_device_state()
        # 焦点策略：所有数值控件改为点击获焦，防止悬停滚轮误改值
        apply_click_to_focus(self)

    # -------------------------- 卡片构建 --------------------------
    def _build_device_card(self) -> None:
        """构建运行设备卡：CPU/GPU 单选。"""
        self.device_card = Card("运行设备")
        dev_row = QHBoxLayout()
        self.device_group = QButtonGroup(self)
        self.rb_cpu = QRadioButton("CPU")
        self.rb_gpu = QRadioButton("GPU")
        self.device_group.addButton(self.rb_cpu)
        self.device_group.addButton(self.rb_gpu)
        # 默认选中：CUDA 可用时 GPU，否则 CPU
        if self._cuda_ok:
            self.rb_gpu.setChecked(True)
        else:
            self.rb_cpu.setChecked(True)
        dev_row.addWidget(self.rb_cpu)
        dev_row.addWidget(self.rb_gpu)
        dev_row.addStretch()
        self.device_hint = QLabel("")
        self.device_hint.setStyleSheet("color: #71717a;")
        dev_row.addWidget(self.device_hint)
        self.device_card.addLayout(dev_row)
        self.add_widget(self.device_card)

    def _build_path_card(self) -> None:
        """构建路径设置卡：模型/图片目录/输出目录。"""
        self.path_card = Card("路径设置")
        self.model_field = PathField(
            browse_type="file",
            file_filter="模型文件 (*.onnx *.engine)",
            placeholder="选择 ONNX 或 TensorRT engine 模型",
        )
        self.path_card.addWidget(self._labeled("模型路径", self.model_field))
        self.image_field = PathField(browse_type="dir", placeholder="选择图片/视频所在目录")
        self.image_field.path_changed.connect(self._on_input_changed)
        self.path_card.addWidget(self._labeled("图片目录", self.image_field))
        self.output_field = PathField(browse_type="dir", placeholder="选择标注输出目录")
        self.path_card.addWidget(self._labeled("输出目录", self.output_field))
        # 模型路径变化时自动读取类别
        self.model_field.path_changed.connect(self._on_model_changed)
        self.add_widget(self.path_card)

    def _build_class_card(self) -> None:
        """构建检测类别卡：模型类别复选列表 + 全选/取消全选。"""
        self.class_card = Card("检测类别")
        self.class_selector = ClassSelectorWidget()
        self.class_card.addWidget(self.class_selector)
        self.add_widget(self.class_card)

    def _build_param_card(self) -> None:
        """构建推理参数卡：置信度/NMS/抽帧/差异阈值/关键点置信度。"""
        self.param_card = Card("推理参数")
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.spin_conf = LabeledSpin("BBox 置信度", "double", 0, 1, 0.01, 0.25)
        self.spin_nms = LabeledSpin("NMS", "double", 0, 1, 0.05, 0.7)
        self.spin_kpt_conf = LabeledSpin("关键点置信度", "double", 0, 1, 0.01, 0.5)
        self.spin_frame_interval = LabeledSpin("抽帧间隔", "int", 1, 9999, 1, 30)
        self.spin_diff_threshold = LabeledSpin("差异阈值", "double", 0, 9999, 0.1, 10.0)

        grid.addWidget(self.spin_conf, 0, 0)
        grid.addWidget(self.spin_nms, 0, 1)
        grid.addWidget(self.spin_kpt_conf, 1, 0)
        grid.addWidget(self.spin_frame_interval, 1, 1)
        grid.addWidget(self.spin_diff_threshold, 2, 0)
        self.param_card.addLayout(grid)
        self.add_widget(self.param_card)

    def _build_action_card(self) -> None:
        """构建操作卡：导入/导出配置、任务类型、开始/停止。"""
        self.action_card = Card("操作")
        # 左侧：导入/导出配置
        left_row = QHBoxLayout()
        self.btn_import = SecondaryButton("导入配置")
        self.btn_export = SecondaryButton("导出配置")
        self.btn_import.clicked.connect(self._on_import_config)
        self.btn_export.clicked.connect(self._on_export_config)
        left_row.addWidget(self.btn_import)
        left_row.addWidget(self.btn_export)
        left_row.addStretch()
        self.action_card.addLayout(left_row)

        # 右侧：任务类型 + 开始/停止
        right_row = QHBoxLayout()
        right_row.addWidget(QLabel("任务类型"))
        self.task_combo = QComboBox()
        self.task_combo.addItem("目标检测 (DETECT)", MODE.DETECT)
        self.task_combo.addItem("姿态估计 (POSE)", MODE.POSE)
        self.task_combo.addItem("实例分割 (SEGMENT)", MODE.SEGMENT)
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)
        right_row.addWidget(self.task_combo)
        right_row.addStretch()
        self.btn_start = PrimaryButton("开始标注")
        self.btn_stop = SecondaryButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        right_row.addWidget(self.btn_stop)
        right_row.addWidget(self.btn_start)
        self.action_card.addLayout(right_row)
        self.add_widget(self.action_card)

    def _build_preview_card(self) -> None:
        """构建文件列表与图像预览卡。

        扫描输入目录后展示图片与视频文件列表，支持选择预览。
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

    # -------------------------- 状态联动 --------------------------
    def _sync_device_state(self) -> None:
        """根据 CUDA 可用性同步 GPU 选项可用性与提示文本。"""
        if self._cuda_ok:
            self.rb_gpu.setEnabled(True)
            self.device_hint.setText("已检测到 CUDA，推荐使用 GPU")
        else:
            self.rb_gpu.setEnabled(False)
            self.device_hint.setText("未检测到 CUDA，仅支持 CPU")
            self.rb_cpu.setChecked(True)

    def _on_task_changed(self) -> None:
        """任务类型变化时切换关键点置信度可见性。"""
        is_pose = self.task_combo.currentData() == MODE.POSE
        self.spin_kpt_conf.setVisible(is_pose)
        self.spin_kpt_conf.label.setVisible(is_pose)

    def _on_model_changed(self, path: str) -> None:
        """模型路径变化时读取模型元数据中的类别信息并填充选择组件。

        Args:
            path: 模型文件路径。
        """
        if not path or not Path(path).exists():
            self.class_selector.set_classes({})
            return
        classes = getModelClasses(path)
        if classes:
            self.class_selector.set_classes(classes)
            LOGGER.info(f"已加载模型类别，共 {len(classes)} 个类别")
        else:
            self.class_selector.set_classes({})
            LOGGER.warning(
                f"未能从模型元数据读取类别信息: {path}（将检测所有类别）"
            )

    def _on_input_changed(self, path: str) -> None:
        """输入目录变化时统计图片/视频数量、切换视频参数可见性并填充预览列表。"""
        if not path or not Path(path).exists():
            self.spin_frame_interval.setVisible(True)
            self.spin_frame_interval.label.setVisible(True)
            self.spin_diff_threshold.setVisible(True)
            self.spin_diff_threshold.label.setVisible(True)
            self.preview_widget.clear()
            return
        images = getImageFilesInDir(path)
        videos = getVideoFilesInDir(path)
        has_video = len(videos) > 0
        # 视频参数仅在有视频时显示
        self.spin_frame_interval.setVisible(has_video)
        self.spin_frame_interval.label.setVisible(has_video)
        self.spin_diff_threshold.setVisible(has_video)
        self.spin_diff_threshold.label.setVisible(has_video)
        # 填充文件预览列表（图片 + 视频，去重排序）
        all_files = sorted(set(images + videos))
        self.preview_widget.set_files(all_files)
        LOGGER.info(f"扫描目录: {len(images)} 张图片, {len(videos)} 个视频")

    # -------------------------- 配置读写 --------------------------
    def collect_config(self, sys_config: SysConfig) -> None:
        """从界面收集配置写入 sys_config。

        Args:
            sys_config: 系统配置对象（就地更新）。
        """
        sys_config.task_type = self.task_combo.currentData()
        ac = sys_config.annotate_config
        ac.device = DEVICE.GPU if self.rb_gpu.isChecked() else DEVICE.CPU
        ac.model_path = self.model_field.path()
        ac.image_path = self.image_field.path()
        ac.dataset_path = self.output_field.path()
        ac.conf = self.spin_conf.value()
        ac.kpt_conf = self.spin_kpt_conf.value()
        ac.nms = self.spin_nms.value()
        ac.frame_interval = int(self.spin_frame_interval.value())
        ac.diff_threshold = self.spin_diff_threshold.value()
        ac.task_type = sys_config.task_type
        # 用户选择的检测类别（空 = 不过滤全部检测）
        ac.selected_classes = self.class_selector.selected_ids()
        # 扫描输入目录的图片与视频文件
        self._scan_input_files(ac)

    def _scan_input_files(self, ac: AnnotateConfig) -> None:
        """扫描输入目录的图片与视频文件，填入运行期字段。

        Args:
            ac: 标注配置对象。
        """
        ac.annotation_files = []
        ac.video_files = []
        if not ac.image_path or not Path(ac.image_path).exists():
            return
        ac.annotation_files = getImageFilesInDir(ac.image_path)
        ac.video_files = getVideoFilesInDir(ac.image_path)

    def apply_config(self, sys_config: SysConfig) -> None:
        """从 sys_config 回填界面控件。

        Args:
            sys_config: 系统配置对象。
        """
        ac = sys_config.annotate_config
        # 设备
        if ac.device == DEVICE.GPU and self._cuda_ok:
            self.rb_gpu.setChecked(True)
        else:
            self.rb_cpu.setChecked(True)
        # 任务类型
        tidx = self.task_combo.findData(sys_config.task_type)
        if tidx >= 0:
            self.task_combo.setCurrentIndex(tidx)
        self._on_task_changed()
        # 路径
        self.model_field.set_path(ac.model_path)
        self.image_field.set_path(ac.image_path)
        self.output_field.set_path(ac.dataset_path)
        if ac.image_path:
            self._on_input_changed(ac.image_path)
        # 检测类别（set_path 不触发信号，需手动读取模型类别再回填勾选）
        if ac.model_path:
            self._on_model_changed(ac.model_path)
        if ac.selected_classes:
            self.class_selector.set_selected_ids(ac.selected_classes)
        # 参数
        self.spin_conf.set_value(ac.conf)
        self.spin_kpt_conf.set_value(ac.kpt_conf)
        self.spin_nms.set_value(ac.nms)
        self.spin_frame_interval.set_value(ac.frame_interval)
        self.spin_diff_threshold.set_value(ac.diff_threshold)

    # -------------------------- 配置导入导出 --------------------------
    def _on_import_config(self) -> None:
        """导入 JSON 配置文件并回填界面。

        兼容旧版 ``mode`` 键与新版 ``task_type`` 键。
        """
        path, _ = QFileDialog.getOpenFileName(
            None, "导入标注配置", "", "JSON 配置 (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ac = AnnotateConfig.from_dict(data)
            sys_config = SysConfig()
            sys_config.annotate_config = ac
            # 任务类型兼容：优先 task_type（新版），回退 mode（旧版），再回退 ac.task_type
            from ..config import _coerce_mode

            if "task_type" in data:
                sys_config.task_type = _coerce_mode(data["task_type"])
            elif "mode" in data:
                sys_config.task_type = _coerce_mode(data["mode"])
            else:
                sys_config.task_type = ac.task_type
            self.apply_config(sys_config)
            self.append_log(f"[配置] 已导入配置: {path}")
        except Exception as e:
            LOGGER.error(f"导入标注配置失败: {e}")
            self.append_log(f"[错误] 导入配置失败: {e}")
            showMessageBox(QMessageBox.Icon.Critical, f"导入配置失败:\n{e}")

    def _on_export_config(self) -> None:
        """收集界面配置并导出为 JSON 文件。

        同时写入 ``mode`` 与 ``task_type`` 以兼容旧版与新版配置读取。
        """
        path, _ = QFileDialog.getSaveFileName(
            None, "导出标注配置", "annotate_config.json", "JSON 配置 (*.json)"
        )
        if not path:
            return
        try:
            sys_config = SysConfig()
            self.collect_config(sys_config)
            data = sys_config.annotate_config.to_dict()
            # 同时写入 mode（旧版兼容）与 task_type（新版）
            data["mode"] = sys_config.task_type.name
            data["task_type"] = sys_config.task_type.name
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.append_log(f"[配置] 已导出配置至: {path}")
        except Exception as e:
            LOGGER.error(f"导出标注配置失败: {e}")
            self.append_log(f"[错误] 导出配置失败: {e}")

    # -------------------------- worker 集成 --------------------------
    def set_worker(self, worker) -> None:
        """绑定标注 worker 并连接信号。

        Args:
            worker: AnnotationWorker 实例。
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
        """开始标注任务。"""
        if self._worker is None:
            return
        sys_config = SysConfig()
        self.collect_config(sys_config)
        # 校验必填项
        ac = sys_config.annotate_config
        if not ac.model_path:
            showMessageBox(QMessageBox.Icon.Warning, "请选择模型文件")
            return
        if not ac.image_path:
            showMessageBox(QMessageBox.Icon.Warning, "请选择图片目录")
            return
        if not ac.dataset_path:
            showMessageBox(QMessageBox.Icon.Warning, "请选择输出目录")
            return
        if not ac.annotation_files and not ac.video_files:
            showMessageBox(QMessageBox.Icon.Warning, "输入目录未扫描到图片或视频")
            return
        # 已加载类别但一个都没选时阻止开始（防止误操作产出空标注）
        if self.class_selector.has_classes() and not ac.selected_classes:
            showMessageBox(
                QMessageBox.Icon.Warning, "请至少选择一个检测类别（或点击全选）"
            )
            return
        self._worker.setConfig(sys_config)
        self.progress_bar.setValue(0)
        self.log_edit.clear()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.task_started.emit()
        self._worker.start()

    def _on_stop(self) -> None:
        """停止标注任务。"""
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
        return "自动标注"
