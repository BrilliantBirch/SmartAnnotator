# -*- coding: utf-8 -*-
"""
配置模块 — 基于 dataclass 的配置定义与枚举

替换旧版 cfg/__init__.py，字段名对齐 UI 设计文档的 JSON schema（snake_case）。
提供 to_dict/from_dict 序列化与旧版 camelCase JSON 键的向后兼容迁移。

作者: BaiBinnan
创建日期: 2026-08-10
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

    Attributes:
        source_format: 源格式（LABELME/YOLO）。
        target_format: 目标格式（与源格式相反）。
        classes: 类别名称列表。
        kpt: 关键点信息 {name: {"isChecked": bool, "bbox_size": int}}。
        visualize: 是否可视化。
        export: 是否导出 YOLO 训练集目录结构。
        input_dir: 输入目录。
        output_dir: 输出目录。
        train_ratio: 训练集比例。
        val_ratio: 验证集比例。
        test_ratio: 测试集比例。
        annotation_files: 运行期扫描到的标注文件（不序列化）。
        image_files: 运行期扫描到的图片文件（不序列化）。
    """

    source_format: Format = Format.LABELME
    target_format: Format = Format.YOLO
    classes: list = field(default_factory=list)
    kpt: dict = field(default_factory=dict)
    visualize: bool = False
    export: bool = False
    input_dir: str = ""
    output_dir: str = ""
    train_ratio: float = 0.8
    val_ratio: float = 0.1
    test_ratio: float = 0.1
    # 运行期字段（不参与序列化）
    annotation_files: list = field(default_factory=list, repr=False)
    image_files: list = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        """序列化为可写入 JSON 的字典（枚举转名称，排除运行期字段）。"""
        return {
            "source_format": self.source_format.name,
            "target_format": self.target_format.name,
            "classes": list(self.classes),
            "kpt": dict(self.kpt),
            "visualize": self.visualize,
            "export": self.export,
            "input_dir": self.input_dir,
            "output_dir": self.output_dir,
            "train_ratio": self.train_ratio,
            "val_ratio": self.val_ratio,
            "test_ratio": self.test_ratio,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConvertConfig":
        """从字典构造配置，兼容旧版 camelCase 键。

        Args:
            d: 字典（可为 to_dict 产物或旧版 JSON）。

        Returns:
            ConvertConfig 实例。
        """
        legacy = {
            "sourceFormat": "source_format",
            "visualized": "visualize",
        }
        migrated = {}
        for k, v in d.items():
            migrated[legacy.get(k, k)] = v
        if "source_format" in migrated:
            migrated["source_format"] = _coerce_format(migrated["source_format"])
        if "target_format" in migrated:
            migrated["target_format"] = _coerce_format(migrated["target_format"])
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in migrated.items() if k in known}
        return cls(**filtered)


@dataclass
class AnnotateConfig:
    """自动标注配置

    Attributes:
        device: 推理设备（CPU/GPU）。
        model_path: 模型文件路径（.onnx/.engine）。
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
    """

    show_label: bool = True
    show_group: bool = False
    show_description: bool = True
    pen_width: float = 2.0
    opacity: float = 0.3
    font_size: int = 12

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
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RenderConfig":
        """从字典构造（缺失/非法字段回退默认值）。

        逐字段校验类型（bool/int/float；bool 为 int 子类，整型校验需排除），
        数值越界时钳制到合法区间（opacity→[0,1]、pen_width→[0.5,10]、
        font_size→[6,72]）。

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


def _coerce_format(value: Any) -> Format:
    """将值转换为 Format 枚举（接受枚举、名称字符串、整数值、旧版别名）。

    兼容旧版配置文件中的别名：
        - "json" / "JSON" → Format.LABELME（LabelMe 标注为 .json 文件）
        - "txt"  / "TXT"  → Format.YOLO（YOLO 标注为 .txt 文件）
        - "labelme" / "yolo"（大小写不敏感）→ 对应枚举
    """
    if isinstance(value, Format):
        return value
    if isinstance(value, str):
        # 旧版别名映射（参考 D:\\data\\CCA\\convert_config.json 的 source_format: "json"）
        _ALIAS = {
            "json": Format.LABELME,
            "txt": Format.YOLO,
            "labelme": Format.LABELME,
            "yolo": Format.YOLO,
        }
        key = value.strip().lower()
        if key in _ALIAS:
            return _ALIAS[key]
        try:
            return Format[value]
        except KeyError:
            raise ValueError(f"未知格式: {value}")
    if isinstance(value, int):
        return Format(value)
    raise ValueError(f"无法解析格式: {value}")
