# -*- coding: utf-8 -*-
"""
自动标注页 - AnnotatePage（精简版：模型加载 + 推理参数设置）

模型加载窗口职责收敛：
    1. 运行设备：CPU/GPU 单选（默认 GPU 若 CUDA 可用，否则 CPU 并禁用 GPU）
    2. 模型路径：.onnx（GPU 模式经 onnxruntime CUDAExecutionProvider 推理）
    3. 任务类型：模型加载后自动读取元数据推导（task 键 / kpt_shape / 输出
       结构），无法推导时允许用户手动选择
    4. 检测类别：模型元数据解析，复选列表 + 全选/取消全选
    5. 推理参数：BBox 置信度、NMS、关键点置信度(POSE)
已移除（前端控件）：图片目录/输出目录、导入导出配置、文件列表与图像
预览、进度与日志、开始/停止按钮——后端 worker 逻辑保留，由主窗口复用。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-08-26 新增检测类别卡片（模型元数据解析 + 类别选择 + 后端过滤）
更新: 2026-09-03 精简为模型加载 + 推理参数设置窗口：移除图片/输出目录、
      导入导出配置、文件预览、进度日志等控件（后端逻辑保留供复用）；
      任务类型改为模型元数据自动推导（无法推导时允许手动选择）
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QLabel,
    QComboBox,
    QHBoxLayout,
    QGridLayout,
    QRadioButton,
    QButtonGroup,
    QWidget,
)
from PySide6.QtCore import Signal

from .base_page import BasePage
from ..widgets.cards import Card
from ..widgets.class_selector import ClassSelectorWidget
from ..widgets.fields import PathField, LabeledSpin, apply_click_to_focus
from ..config import SysConfig, AnnotateConfig, MODE, DEVICE
from ..utils import LOGGER, getModelClasses, getModelTaskType


def _cuda_available() -> bool:
    """检测当前环境是否存在可用的 CUDA 推理后端。

    GPU 模式使用 onnxruntime CUDAExecutionProvider 推理：
    onnxruntime-gpu 安装后 CUDA EP 会出现在 get_available_providers()
    列表中；若运行机器无 NVIDIA 驱动，会话创建时自动回退 CPU（见
    onnxbackend.ONNXInfer，不崩溃仅降速）。

    Returns:
        True 表示 onnxruntime 提供 CUDAExecutionProvider，否则 False。
    """
    try:
        import onnxruntime as ort
    except Exception as e:
        LOGGER.warning(f"CUDA 检测: onnxruntime 导入失败: {e}")
        return False

    providers = ort.get_available_providers()
    if "CUDAExecutionProvider" not in providers:
        LOGGER.warning(
            f"CUDA 检测: onnxruntime 未提供 CUDAExecutionProvider（当前 "
            f"providers: {providers}），GPU 模式不可用。"
            f"如需 GPU 推理请安装 onnxruntime-gpu。"
        )
        return False
    return True


class AnnotatePage(BasePage):
    """自动标注页 - 模型加载与推理参数设置（精简版）。

    Signals:
        model_loaded(str): 模型路径确认加载（供主窗口复用模型路径）。
    """

    model_loaded = Signal(str)

    def __init__(self, parent=None):
        """初始化自动标注页，构建 4 张卡片。"""
        super().__init__(parent)
        self._cuda_ok = _cuda_available()

        self._build_device_card()
        self._build_model_card()
        self._build_class_card()
        self._build_param_card()

        # 初始状态：同步设备可用性与任务类型联动
        self._sync_device_state()
        self._on_task_changed()
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

    def _build_model_card(self) -> None:
        """构建模型加载卡：模型路径 + 任务类型（自动推导）。"""
        self.model_card = Card("模型")
        self.model_field = PathField(
            browse_type="file",
            file_filter="模型文件 (*.onnx)",
            placeholder="选择 ONNX 模型",
        )
        # 模型路径变化时自动读取类别并推导任务类型
        self.model_field.path_changed.connect(self._on_model_changed)
        self.model_card.addWidget(self._labeled("模型路径", self.model_field))

        # 任务类型：模型加载后自动推导（推导失败时可手动选择）
        task_row = QHBoxLayout()
        task_lab = QLabel("任务类型")
        task_lab.setMinimumWidth(72)
        task_row.addWidget(task_lab)
        self.task_combo = QComboBox()
        self.task_combo.addItem("目标检测 (DETECT)", MODE.DETECT)
        self.task_combo.addItem("姿态估计 (POSE)", MODE.POSE)
        self.task_combo.addItem("实例分割 (SEGMENT)", MODE.SEGMENT)
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)
        task_row.addWidget(self.task_combo)
        self.task_hint = QLabel("")
        self.task_hint.setStyleSheet("color: #71717a;")
        task_row.addWidget(self.task_hint)
        task_row.addStretch()
        self.model_card.addLayout(task_row)
        self.add_widget(self.model_card)

    def _build_class_card(self) -> None:
        """构建检测类别卡：模型类别复选列表 + 全选/取消全选。"""
        self.class_card = Card("检测类别")
        self.class_selector = ClassSelectorWidget()
        self.class_card.addWidget(self.class_selector)
        self.add_widget(self.class_card)

    def _build_param_card(self) -> None:
        """构建推理参数卡：置信度/NMS/关键点置信度。"""
        self.param_card = Card("推理参数")
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.spin_conf = LabeledSpin("BBox 置信度", "double", 0, 1, 0.01, 0.25)
        self.spin_nms = LabeledSpin("NMS", "double", 0, 1, 0.05, 0.7)
        self.spin_kpt_conf = LabeledSpin("关键点置信度", "double", 0, 1, 0.01, 0.5)

        grid.addWidget(self.spin_conf, 0, 0)
        grid.addWidget(self.spin_nms, 0, 1)
        grid.addWidget(self.spin_kpt_conf, 1, 0)
        self.param_card.addLayout(grid)
        self.add_widget(self.param_card)

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
        """模型路径变化：读取类别元数据并推导任务类型。

        任务类型优先从模型元数据/输出结构推导（getModelTaskType），
        推导成功自动选中并锁定（提示"自动识别"）；无法推导时解锁
        下拉框交由用户手动选择（提示"未能识别，请手动选择"）。

        Args:
            path: 模型文件路径。
        """
        if not path or not Path(path).exists():
            self.class_selector.set_classes({})
            # 无有效模型：解锁任务类型交由用户选择（清空提示）
            self.task_combo.setEnabled(True)
            self.task_hint.setText("")
            return
        # 类别元数据
        classes = getModelClasses(path)
        if classes:
            self.class_selector.set_classes(classes)
            LOGGER.info(f"已加载模型类别，共 {len(classes)} 个类别")
        else:
            self.class_selector.set_classes({})
            LOGGER.warning(
                f"未能从模型元数据读取类别信息: {path}（将检测所有类别）"
            )
        # 任务类型推导
        task_name = getModelTaskType(path)
        if task_name:
            mode = MODE[task_name]
            idx = self.task_combo.findData(mode)
            if idx >= 0:
                self.task_combo.setCurrentIndex(idx)
            # 推导成功：锁定下拉框（自动识别，无需用户干预）
            self.task_combo.setEnabled(False)
            self.task_hint.setText("已按模型元数据自动识别")
        else:
            # 无法推导：解锁交由用户选择
            self.task_combo.setEnabled(True)
            self.task_hint.setText("未能识别，请手动选择")
            LOGGER.warning(f"无法从模型推导任务类型: {path}")

    # -------------------------- 配置读写 --------------------------
    def collect_config(self, sys_config: SysConfig) -> None:
        """从界面收集配置写入 sys_config（后端逻辑保留，供 worker 复用）。

        Args:
            sys_config: 系统配置对象（就地更新）。
        """
        sys_config.task_type = self.task_combo.currentData()
        ac = sys_config.annotate_config
        ac.device = DEVICE.GPU if self.rb_gpu.isChecked() else DEVICE.CPU
        ac.model_path = self.model_field.path()
        ac.conf = self.spin_conf.value()
        ac.kpt_conf = self.spin_kpt_conf.value()
        ac.nms = self.spin_nms.value()
        ac.task_type = sys_config.task_type
        # 用户选择的检测类别（空 = 不过滤全部检测）
        ac.selected_classes = self.class_selector.selected_ids()
        # 图片/输出目录由主窗口工作区提供，此处不再收集（保留字段清空）
        ac.image_path = ""
        ac.dataset_path = ""
        ac.annotation_files = []
        ac.video_files = []

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
        # 任务类型（随后模型加载会重新推导并锁定）
        tidx = self.task_combo.findData(sys_config.task_type)
        if tidx >= 0:
            self.task_combo.setCurrentIndex(tidx)
        self._on_task_changed()
        # 模型路径（set_path 不触发信号，需手动读取类别并推导任务类型）
        self.model_field.set_path(ac.model_path)
        if ac.model_path:
            self._on_model_changed(ac.model_path)
        if ac.selected_classes:
            self.class_selector.set_selected_ids(ac.selected_classes)
        # 参数
        self.spin_conf.set_value(ac.conf)
        self.spin_kpt_conf.set_value(ac.kpt_conf)
        self.spin_nms.set_value(ac.nms)

    def title(self) -> str:
        """返回页面标题。"""
        return "自动标注"
