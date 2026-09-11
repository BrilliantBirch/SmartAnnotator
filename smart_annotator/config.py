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
更新: 2026-09-07 RenderConfig 尺寸持久化字段清理：删除随分栏布局废弃的
      panel_width 与 kpt_list_height（旧 JSON 键由 from_dict 静默忽略），
      新增 dock_state（QMainWindow 布局状态 base64，持久化工具栏与
      对象面板 Dock 的位置/尺寸）
更新: 2026-09-07 RenderConfig 新增删除/清空确认开关 confirm_delete_shapes/
      confirm_clear/confirm_delete_file（默认开启）与 point_size（关键点
      准星臂长，钳制 [1.0,20.0]）；删除三组列表高度字段（界面布局记忆
      统一由 dock_state 承担，旧 JSON 键由 from_dict 静默忽略）及仅
      服务它们的 _read_int 辅助；新增 DEFAULT_SHORTCUTS 默认快捷键表
      与 ShortcutsConfig dataclass（action_id 白名单过滤，键序列合法
      性由应用层经 QKeySequence 校验）
更新: 2026-09-08 RenderConfig 布局字段收口：删除三分区高度字段
      label_list_height/object_list_height/file_list_height 与
      right_panel_width（三分区独立 Dock 化后，Dock 堆叠高度与挂靠
      宽度统一由 dock_state 持久化承担，旧 JSON 键由 from_dict 静默
      忽略）；保留 auto_save 自动保存开关（默认开启，切换图片时自动
      落盘当前标注）
更新: 2026-09-08 RenderConfig 新增 text_shadow_opacity（形状标签文本
      阴影不透明度，0-100 整型校验越界钳制，默认 45 与原硬编码视觉
      一致；视图菜单档位可调，随配置持久化）
更新: 2026-09-09 删除持久化确认开关 confirm_delete_shapes/confirm_clear/
      confirm_delete_file（旧 JSON 键由 from_dict 白名单静默忽略）：
      删除确认的"不再提醒"改为应用运行期会话级记忆，不落盘，
      重启恢复默认提醒状态
更新: 2026-09-10 AnnotateConfig 新增 OCR 识别配置字段 rec_model_path（OCR
      识别模型 .onnx 路径）与 rec_dict_path（OCR 字典 .txt 路径），仅 OCR
      模式使用；纳入 to_dict 序列化与 from_dict 解析（None/非字符串容错
      回空串）
更新: 2026-09-10 新增 OCR 专属推理参数字段 ocr_thresh（概率图二值化阈值
      0.2）/ocr_box_thresh（检测框置信度阈值 0.45）/ocr_unclip_ratio（外扩
      比例 1.4），纳入 to_dict/from_dict（非数值容错回默认）
更新: 2026-09-10 DEFAULT_SHORTCUTS 新增三个自动标注动作默认键：
      annotate_single（标注当前图片 Ctrl+1）/annotate_all（标注所有图片
      Ctrl+2）/clear_shapes（清空当前标注 Ctrl+Shift+C），旧 shortcuts.json
      经白名单合并自动补齐默认绑定
更新: 2026-09-10 Format 枚举新增 PPOCR（PaddleOCR 标注格式，det_gt.txt 等，
      仅 OCR 任务导入时作为源格式）；ConvertConfig 新增 OCR 转换开关
      ocr_use_space_char（字典尾追加空格字符）与 ocr_gen_rec（同时生成
      rec 识别数据集），均仅 OCR 转换使用，纳入 to_dict 序列化与
      from_dict 非 bool 容错（非法值回字段默认）
更新: 2026-09-11 清理死代码：删除冲突的旧版 __VERSION__ 常量（版本单点
      迁移至 __init__.py 的 __version__）；删除零引用的
      AnnotateConfig.from_dict 类方法与 _coerce_device 辅助函数
      （_coerce_mode 保留，仍被转换页引用）
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


# ===== 应用级常量 =====
__APPNAME__ = "BrilliantAnnotator"
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
    PPOCR = 2  # PaddleOCR 标注格式（det_gt.txt 等，仅 OCR 任务导入时作为源格式）


# ===== 配置 dataclass =====
@dataclass
class ConvertConfig:
    """格式转换配置

    转换方向由页面实例决定（direction 运行期字段），源/目标格式不再持久化。

    Attributes:
        direction: 转换方向（运行期字段）："export"=LabelMe→YOLO 导出 /
            "import"=YOLO→LabelMe 导入（OCR 任务时源格式为 PPOCR）。
        classes: 类别名称列表。
        kpt: 关键点信息 {name: {"isChecked": bool, "bbox_size": int}}。
        visualize: 是否可视化。
        export: 是否导出 YOLO 训练集目录结构。
        ocr_use_space_char: 字典尾追加空格字符（仅 OCR 转换使用）。
        ocr_gen_rec: 同时生成 rec 识别数据集（裁剪文本行图 + rec_gt，
            仅 OCR 转换使用）。
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
    # OCR 专属转换开关（仅 OCR 转换使用）
    ocr_use_space_char: bool = True  # 字典尾追加空格字符（use_space_char=True）
    ocr_gen_rec: bool = True  # 同时生成 rec 识别数据集（裁剪文本行图 + rec_gt）
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
            "ocr_use_space_char",
            "ocr_gen_rec",
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
            "ocr_use_space_char": self.ocr_use_space_char,
            "ocr_gen_rec": self.ocr_gen_rec,
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
        # OCR 转换开关：非 bool 值容错丢弃（回 dataclass 字段默认值）
        for key in ("ocr_use_space_char", "ocr_gen_rec"):
            if key in filtered and not isinstance(filtered[key], bool):
                filtered.pop(key)
        return cls(**filtered)


@dataclass
class AnnotateConfig:
    """自动标注配置

    Attributes:
        device: 推理设备（CPU/GPU，GPU 走 onnxruntime CUDA EP）。
        model_path: 模型文件路径（.onnx）。
        rec_model_path: OCR 识别模型路径（.onnx，仅 OCR 模式使用）。
        rec_dict_path: OCR 识别字典路径（.txt，仅 OCR 模式使用）。
        image_path: 输入图片/视频目录。
        dataset_path: 标注输出目录。
        conf: BBox 置信度阈值（0-1）。
        kpt_conf: 关键点置信度阈值（0-1）。
        nms: NMS 阈值（0-1）。
        frame_interval: 视频抽帧间隔。
        diff_threshold: 帧间差异阈值。
        task_type: 任务模式（DETECT/POSE/SEGMENT/OCR）。
        selected_classes: 用户选择检测的类别 id 列表；空列表表示不过滤（检测所有类别）。
        annotation_files: 运行期扫描到的图片文件（不序列化）。
        video_files: 运行期扫描到的视频文件（不序列化）。
    """

    device: DEVICE = DEVICE.GPU
    model_path: str = ""
    # OCR 识别配置（仅 OCR 模式使用）：识别模型与字典路径，持久化序列化
    rec_model_path: str = ""  # OCR 识别模型 .onnx 路径
    rec_dict_path: str = ""  # OCR 识别字典 .txt 路径
    # OCR 专属推理参数（仅 OCR 模式使用，对应 DB 文本检测后处理）
    ocr_thresh: float = 0.2  # 检测概率图二值化阈值
    ocr_box_thresh: float = 0.45  # 检测框置信度阈值（框内平均分过滤）
    ocr_unclip_ratio: float = 1.4  # 检测框外扩比例（unclip）
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
            "rec_model_path": self.rec_model_path,
            "rec_dict_path": self.rec_dict_path,
            "ocr_thresh": self.ocr_thresh,
            "ocr_box_thresh": self.ocr_box_thresh,
            "ocr_unclip_ratio": self.ocr_unclip_ratio,
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

    窗口布局（dock_state，含三个列表 Dock 的位置/堆叠高度/挂靠宽度/
    显隐）与自动保存开关均随渲染配置持久化，启动时恢复。

    Attributes:
        show_label: 是否在画布渲染形状标签文本。
        show_group: 是否在画布渲染形状组号（G{group_id}）。
        show_description: 是否在画布渲染形状描述文本。
        pen_width: 矩形/多边形描边线宽（像素，选中态为 pen_width + 2）。
        point_size: 关键点准星臂长（场景单位，钳制 [1.0, 20.0]）。
        opacity: 多边形填充不透明度（0.0-1.0）。
        font_size: 渲染文本字号（磅）。
        text_shadow_opacity: 形状标签文本阴影不透明度（0-100，钳制；
            0 = 不渲染阴影，100 = 全不透明阴影，随配置持久化）。
        dock_state: QMainWindow 布局状态（saveState 产物的 base64 字符串，
            持久化顶部工具栏与三个列表 Dock 的位置/尺寸/显隐；
            空串 = 默认布局）。
        auto_scan_labels: 是否打开文件夹后自动启动标签扫描统计。
        auto_save: 自动保存（文件菜单勾选）默认开启，切换图片时自动
            落盘当前标注。
    """

    show_label: bool = True
    show_group: bool = False
    show_description: bool = True
    pen_width: float = 2.0
    point_size: float = 4.0
    opacity: float = 0.3
    font_size: int = 12
    text_shadow_opacity: int = 45  # 文本阴影不透明度（0-100，0=不渲染阴影）
    # ===== 窗口布局状态（Dock 布局 base64，QMainWindow 拖拽调整）=====
    dock_state: str = ""  # QMainWindow 布局状态（saveState 产物 base64，空串=默认布局）
    # ===== 行为偏好（统计菜单"自动扫描"开关 / 文件菜单"自动保存"开关）=====
    auto_scan_labels: bool = False  # 打开文件夹后自动启动标签扫描统计
    auto_save: bool = True  # 自动保存（默认开启），切换图片时自动落盘当前标注

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
            "point_size": self.point_size,
            "opacity": self.opacity,
            "font_size": self.font_size,
            "text_shadow_opacity": self.text_shadow_opacity,
            "dock_state": self.dock_state,
            "auto_scan_labels": self.auto_scan_labels,
            "auto_save": self.auto_save,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RenderConfig":
        """从字典构造（缺失/非法字段回退默认值）。

        逐字段校验类型（bool/int/float/str；bool 为 int 子类，整型校验需排除），
        数值越界时钳制到合法区间（opacity→[0,1]、pen_width→[0.5,10]、
        point_size→[1.0,20.0]、font_size→[6,72]）。
        旧版 JSON 中的 panel_width/kpt_list_height/label_list_height/
        object_list_height/file_list_height/right_panel_width 等
        已废弃键被静默忽略，不报错。

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
        if isinstance(data.get("auto_save"), bool):
            cfg.auto_save = data["auto_save"]

        # ===== 浮点字段校验（接受 int，排除 bool；越界钳制） =====
        pen_width = data.get("pen_width")
        if isinstance(pen_width, (int, float)) and not isinstance(pen_width, bool):
            cfg.pen_width = min(10.0, max(0.5, float(pen_width)))
        point_size = data.get("point_size")
        if isinstance(point_size, (int, float)) and not isinstance(point_size, bool):
            cfg.point_size = min(20.0, max(1.0, float(point_size)))
        opacity = data.get("opacity")
        if isinstance(opacity, (int, float)) and not isinstance(opacity, bool):
            cfg.opacity = min(1.0, max(0.0, float(opacity)))

        # ===== 整数字段校验（排除 bool；越界钳制） =====
        font_size = data.get("font_size")
        if isinstance(font_size, int) and not isinstance(font_size, bool):
            cfg.font_size = min(72, max(6, int(font_size)))
        # 文本阴影不透明度：越界钳制 [0, 100]
        text_shadow_opacity = data.get("text_shadow_opacity")
        if isinstance(text_shadow_opacity, int) and not isinstance(
            text_shadow_opacity, bool
        ):
            cfg.text_shadow_opacity = min(100, max(0, int(text_shadow_opacity)))

        # ===== 字符串字段校验（窗口布局状态 base64，非法类型回退空串） =====
        if isinstance(data.get("dock_state"), str):
            cfg.dock_state = data["dock_state"]
        return cfg


# ===== 默认快捷键表与快捷键配置 =====
# 默认快捷键表（action_id -> QKeySequence 可解析的字符串；应用层经 QKeySequence 校验）
DEFAULT_SHORTCUTS: Dict[str, str] = {
    "open": "Ctrl+O",
    "open_file": "Ctrl+Shift+O",
    "save": "Ctrl+S",
    "save_as": "Ctrl+Shift+S",
    "edit_mode": "Ctrl+E",
    "undo": "Ctrl+Z",
    "redo": "Ctrl+Shift+Z",
    "copy": "Ctrl+C",
    "paste": "Ctrl+V",
    "tool_select": "V",
    "tool_rectangle": "R",
    "tool_point": "P",
    "tool_polygon": "G",
    "delete": "Delete",
    "delete_image": "Shift+Delete",
    "prev_image": "A",
    "next_image": "D",
    "fit_window": "Ctrl+0",
    # 自动标注动作（OCR/检测等全模式通用；槽内自带防呆与确认框）
    "annotate_single": "Ctrl+1",  # 标注当前图片
    "annotate_all": "Ctrl+2",  # 标注所有图片
    "clear_shapes": "Ctrl+Shift+C",  # 清空当前标注
}


@dataclass
class ShortcutsConfig:
    """快捷键配置（持久化于 %APPDATA%/BrilliantAnnotator/shortcuts.json）。

    仅持久化 action_id -> 快捷键字符串 的绑定表。键序列合法性
    （QKeySequence 可解析性）由应用层校验，config 层只做值类型与
    action_id 白名单过滤（未知动作 id 丢弃，缺失动作回退默认绑定）。

    Attributes:
        bindings: 动作 id 到快捷键字符串的映射（始终包含全部默认动作）。
    """

    bindings: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SHORTCUTS))

    def to_dict(self) -> dict:
        """序列化为可写入 JSON 的字典。

        Returns:
            {"bindings": {action_id: 快捷键字符串}} 字典。
        """
        return {"bindings": dict(self.bindings)}

    @classmethod
    def from_dict(cls, data: dict) -> "ShortcutsConfig":
        """从字典构造，非法条目丢弃，缺失动作回退默认绑定。

        bindings 仅接受键存在于 DEFAULT_SHORTCUTS（action_id 白名单）
        且值为非空 str 的条目；未知 action_id 与非 str 值静默丢弃；
        未覆盖的动作保留默认绑定（合并而非整体替换）。

        Args:
            data: 字典（可为 to_dict 产物或手工编辑的 JSON）。

        Returns:
            ShortcutsConfig 实例。
        """
        # 以默认绑定表为基底
        cfg = cls()
        # 非字典输入直接返回默认配置
        if not isinstance(data, dict):
            return cfg
        raw = data.get("bindings")
        # bindings 缺失或类型非法时整体回退默认绑定
        if not isinstance(raw, dict):
            return cfg
        # 白名单与类型过滤：仅保留已知动作 id 的非空字符串绑定
        valid = {
            k: v
            for k, v in raw.items()
            if k in DEFAULT_SHORTCUTS and isinstance(v, str) and v
        }
        # 合并而非替换：用户未覆盖的动作保留默认绑定
        cfg.bindings = {**DEFAULT_SHORTCUTS, **valid}
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
