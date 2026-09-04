# -*- coding: utf-8 -*-
"""
配置模块 — 基于 dataclass 的配置定义与枚举

替换旧版 cfg/__init__.py，字段名对齐 UI 设计文档的 JSON schema（snake_case）。
提供 to_dict/from_dict 序列化与旧版 camelCase JSON 键的向后兼容迁移。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-03 新增 RenderConfig 画布渲染配置 dataclass（显示开关/线宽/不透明度/
      字号，及右栏宽度与四组列表高度的界面布局字段）
更新: 2026-09-03 RenderConfig 新增 auto_scan_labels（打开文件夹自动扫描偏好，默认关闭）
更新: 2026-09-04 ConvertConfig 字段重构：删除序列化字段 source_format/target_format，
      新增运行期字段 direction（"export"/"import"），input_dir/output_dir 改为
      运行期字段不再序列化；from_dict 改为序列化字段白名单过滤（旧版废弃键
      与运行期字段键静默忽略），并删除 _coerce_format 迁移逻辑
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ===== 应用级常量 =====
__APPNAME__ = "VAI_E_SmartAnnotator"
__VERSION__ = "1.2.0"
LABELME_VERSION = "5.4.1"
RANDOM_SEED = 42


# ===== 枚举 =====
class MODE(Enum):
    """任务模式（value 与 yolo_to_labelme 的 type 参数一致，勿改）"""

    DETECT = 0
    POSE = 1
    SEGMENT = 2
    OCR = 3


class DEVICE(Enum):
    """推理设备"""

    CPU = 0
    GPU = 1


class Format(Enum):
    """数据集格式（转换页源/目标格式）"""

    LABELME = 0
    YOLO = 1


# ===== 配置 dataclass =====
@dataclass
class ConvertConfig:
    """格式转换配置

    转换方向由页面实例决定（direction 运行期字段），源/目标格式不再持久化。

    Attributes:
        direction: 转换方向（运行期字段）："export"=LabelMe→YOLO 导出 /
            "import"=YOLO→LabelMe 导入。
        classes: 类别名称列表。
        kpt: 关键点信息 {name: {"isChecked": bool, "bbox_size": int}}。
        visualize: 是否可视化。
        export: 是否导出 YOLO 训练集目录结构。
        train_ratio: 训练集比例。
        val_ratio: 验证集比例。
        test_ratio: 测试集比例。
        input_dir: 输入目录（运行期，不序列化）。
        output_dir: 输出目录（运行期，不序列化）。
        annotation_files: 运行期扫描到的标注文件（不序列化）。
        image_files: 运行期扫描到的图片文件（不序列化）。
    """

    direction: str = None
    classes: list = field(default_factory=list)
    kpt: dict = field(default_factory=dict)
    visualize: bool = False
    export: bool = False
    train_ratio: float = 0.8
    val_ratio: float = 0.1
    test_ratio: float = 0.1
    # 运行期字段（不参与序列化）
    input_dir: str = field(default_factory=str, repr=False)
    output_dir: str = field(default_factory=str, repr=False)
    annotation_files: list = field(default_factory=list, repr=False)
    image_files: list = field(default_factory=list, repr=False)

    # 序列化字段集合（与 to_dict 输出键一致，新增序列化字段时两处同步更新）；
    # from_dict 仅恢复这些字段，运行期字段不从持久化数据恢复
    _SERIALIZED_FIELDS = frozenset(
        {
            "classes",
            "kpt",
            "visualize",
            "export",
            "train_ratio",
            "val_ratio",
            "test_ratio",
        }
    )

    def to_dict(self) -> dict:
        """序列化为可写入 JSON 的字典（排除运行期字段）。"""
        return {
            "classes": list(self.classes),
            "kpt": dict(self.kpt),
            "visualize": self.visualize,
            "export": self.export,
            "train_ratio": self.train_ratio,
            "val_ratio": self.val_ratio,
            "test_ratio": self.test_ratio,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConvertConfig":
        """从字典构造配置，非序列化键自动忽略（兼容旧版 JSON）。

        旧版 JSON 中的 source_format/target_format 等已废弃键，以及
        input_dir/output_dir 等运行期字段键，均被序列化字段白名单过滤
        静默忽略，不报错；序列化字段（classes/kpt/visualize/export/
        train_ratio/val_ratio/test_ratio）正常加载。

        Args:
            d: 字典（可为 to_dict 产物或旧版 JSON）。

        Returns:
            ConvertConfig 实例。
        """
        legacy = {
            "visualized": "visualize",
        }
        migrated = {}
        for k, v in d.items():
            migrated[legacy.get(k, k)] = v
        # 已知字段过滤：仅恢复序列化字段，废弃键与运行期字段键静默忽略
        filtered = {
            k: v for k, v in migrated.items() if k in cls._SERIALIZED_FIELDS
        }
        return cls(**filtered)


@dataclass
class AnnotateConfig:
    """自动标注配置

    Attributes:
        device: 推理设备（CPU/GPU，GPU 走 onnxruntime CUDA EP）。
        model_path: 模型文件路径（.onnx）。
        image_path: 输入图片/视频目录。
        dataset_path: 标注输出目录。
        conf: BBox 置信度阈值（0-1）。
        kpt_conf: 关键点置信度阈值（0-1）。
        nms: NMS 阈值（0-1）。
        frame_interval: 视频抽帧间隔。
        diff_threshold: 帧间差异阈值。
        task_type: 任务模式（DETECT/POSE/SEGMENT）。
        selected_classes: 用户选择检测的类别 id 列表；空列表表示不过滤（检测所有类别）。
        annotation_files: 运行期扫描到的图片文件（不序列化）。
        video_files: 运行期扫描到的视频文件（不序列化）。
    """

    device: DEVICE = DEVICE.GPU
    model_path: str = ""
    image_path: str = ""
    dataset_path: str = ""
    conf: float = 0.25
    kpt_conf: float = 0.5
    nms: float = 0.7
    frame_interval: int = 30
    diff_threshold: float = 10.0
    task_type: MODE = MODE.DETECT
    selected_classes: list = field(default_factory=list)
    # 运行期字段（不参与序列化）
    annotation_files: list = field(default_factory=list, repr=False)
    video_files: list = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        """序列化为可写入 JSON 的字典（枚举转名称，排除运行期字段）。"""
        return {
            "device": self.device.name,
            "model_path": self.model_path,
            "image_path": self.image_path,
            "dataset_path": self.dataset_path,
            "conf": self.conf,
            "kpt_conf": self.kpt_conf,
            "nms": self.nms,
            "frame_interval": self.frame_interval,
            "diff_threshold": self.diff_threshold,
            "task_type": self.task_type.name,
            "selected_classes": list(self.selected_classes),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AnnotateConfig":
        """从字典构造配置，兼容旧版 camelCase 键。

        Args:
            d: 字典（可为 to_dict 产物或旧版 JSON）。

        Returns:
            AnnotateConfig 实例。
        """
        legacy = {
            "modelPath": "model_path",
            "inputDir": "image_path",
            "outputDir": "dataset_path",
            "bboxConf": "conf",
            "kptConf": "kpt_conf",
            "frameInterval": "frame_interval",
            "diffThreshold": "diff_threshold",
        }
        migrated = {}
        for k, v in d.items():
            migrated[legacy.get(k, k)] = v
        if "device" in migrated:
            migrated["device"] = _coerce_device(migrated["device"])
        if "task_type" in migrated:
            migrated["task_type"] = _coerce_mode(migrated["task_type"])
        elif "mode" in migrated:
            migrated["task_type"] = _coerce_mode(migrated.pop("mode"))
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in migrated.items() if k in known}
        return cls(**filtered)


@dataclass
class SysConfig:
    """系统配置（聚合转换与标注配置）

    Attributes:
        task_type: 当前任务模式。
        convert_config: 格式转换配置。
        annotate_config: 自动标注配置。
    """

    task_type: MODE = MODE.DETECT
    convert_config: ConvertConfig = field(default_factory=ConvertConfig)
    annotate_config: AnnotateConfig = field(default_factory=AnnotateConfig)


@dataclass
class RenderConfig:
    """画布渲染配置（视图菜单可调，持久化于 %APPDATA%/BrilliantAnnotator/render_config.json）。

    Attributes:
        show_label: 是否在画布渲染形状标签文本。
        show_group: 是否在画布渲染形状组号（G{group_id}）。
        show_description: 是否在画布渲染形状描述文本。
        pen_width: 矩形/多边形描边线宽（像素，选中态为 pen_width + 2）。
        opacity: 多边形填充不透明度（0.0-1.0）。
        font_size: 渲染文本字号（磅）。
        panel_width: 右侧信息栏宽度（像素，水平分栏拖拽调节）。
        label_list_height: 标签列表高度（像素）。
        object_list_height: 对象列表高度（像素）。
        file_list_height: 文件列表高度（像素）。
        kpt_list_height: 关键点列表高度（像素）。
        auto_scan_labels: 是否打开文件夹后自动启动标签扫描统计。
    """

    show_label: bool = True
    show_group: bool = False
    show_description: bool = True
    pen_width: float = 2.0
    opacity: float = 0.3
    font_size: int = 12
    # ===== 界面布局尺寸（右栏宽度 + 四组列表高度，分栏拖拽调节）=====
    panel_width: int = 240
    label_list_height: int = 180
    object_list_height: int = 180
    file_list_height: int = 280
    kpt_list_height: int = 140
    # ===== 行为偏好（统计菜单"自动扫描"开关，打开文件夹即自动扫描）=====
    auto_scan_labels: bool = False

    def to_dict(self) -> dict:
        """序列化为字典（JSON 持久化用）。

        Returns:
            字段名字典。
        """
        return {
            "show_label": self.show_label,
            "show_group": self.show_group,
            "show_description": self.show_description,
            "pen_width": self.pen_width,
            "opacity": self.opacity,
            "font_size": self.font_size,
            "panel_width": self.panel_width,
            "label_list_height": self.label_list_height,
            "object_list_height": self.object_list_height,
            "file_list_height": self.file_list_height,
            "kpt_list_height": self.kpt_list_height,
            "auto_scan_labels": self.auto_scan_labels,
        }

    @staticmethod
    def _read_int(data: dict, key: str, default: int, lo: int, hi: int) -> int:
        """读取整数字段（排除 bool；越界钳制；非法/缺失回退默认值）。

        Args:
            data: 字段名字典。
            key: 字段名。
            default: 回退默认值。
            lo: 合法下界（含）。
            hi: 合法上界（含）。

        Returns:
            校验后的整数值。
        """
        value = data.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return min(hi, max(lo, int(value)))
        return default

    @classmethod
    def from_dict(cls, data: dict) -> "RenderConfig":
        """从字典构造（缺失/非法字段回退默认值）。

        逐字段校验类型（bool/int/float；bool 为 int 子类，整型校验需排除），
        数值越界时钳制到合法区间（opacity→[0,1]、pen_width→[0.5,10]、
        font_size→[6,72]、panel_width→[200,800]、列表高度→[80,2000]）。

        Args:
            data: 字段名字典。

        Returns:
            RenderConfig 实例。
        """
        # 以默认实例为基底，逐字段按校验结果覆盖
        cfg = cls()
        # 非字典输入直接返回默认配置
        if not isinstance(data, dict):
            return cfg

        # ===== 布尔字段校验 =====
        if isinstance(data.get("show_label"), bool):
            cfg.show_label = data["show_label"]
        if isinstance(data.get("show_group"), bool):
            cfg.show_group = data["show_group"]
        if isinstance(data.get("show_description"), bool):
            cfg.show_description = data["show_description"]
        if isinstance(data.get("auto_scan_labels"), bool):
            cfg.auto_scan_labels = data["auto_scan_labels"]

        # ===== 浮点字段校验（接受 int，排除 bool；越界钳制） =====
        pen_width = data.get("pen_width")
        if isinstance(pen_width, (int, float)) and not isinstance(pen_width, bool):
            cfg.pen_width = min(10.0, max(0.5, float(pen_width)))
        opacity = data.get("opacity")
        if isinstance(opacity, (int, float)) and not isinstance(opacity, bool):
            cfg.opacity = min(1.0, max(0.0, float(opacity)))

        # ===== 整数字段校验（排除 bool；越界钳制） =====
        font_size = data.get("font_size")
        if isinstance(font_size, int) and not isinstance(font_size, bool):
            cfg.font_size = min(72, max(6, int(font_size)))

        # ===== 界面布局字段（右栏宽度与四组列表高度）=====
        cfg.panel_width = cls._read_int(data, "panel_width", cfg.panel_width, 200, 800)
        cfg.label_list_height = cls._read_int(
            data, "label_list_height", cfg.label_list_height, 80, 2000
        )
        cfg.object_list_height = cls._read_int(
            data, "object_list_height", cfg.object_list_height, 80, 2000
        )
        cfg.file_list_height = cls._read_int(
            data, "file_list_height", cfg.file_list_height, 80, 2000
        )
        cfg.kpt_list_height = cls._read_int(
            data, "kpt_list_height", cfg.kpt_list_height, 80, 2000
        )
        return cfg


# ===== 枚举强制转换辅助函数 =====
def _coerce_mode(value: Any) -> MODE:
    """将值转换为 MODE 枚举（接受枚举、名称字符串、整数值）。"""
    if isinstance(value, MODE):
        return value
    if isinstance(value, str):
        try:
            return MODE[value]
        except KeyError:
            raise ValueError(f"未知任务模式: {value}")
    if isinstance(value, int):
        return MODE(value)
    raise ValueError(f"无法解析任务模式: {value}")


def _coerce_device(value: Any) -> DEVICE:
    """将值转换为 DEVICE 枚举（接受枚举、名称字符串、整数值）。"""
    if isinstance(value, DEVICE):
        return value
    if isinstance(value, str):
        try:
            return DEVICE[value]
        except KeyError:
            raise ValueError(f"未知设备: {value}")
    if isinstance(value, int):
        return DEVICE(value)
    raise ValueError(f"无法解析设备: {value}")
