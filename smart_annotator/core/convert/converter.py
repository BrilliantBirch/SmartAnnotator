# -*- coding: utf-8 -*-
"""
通用的转换器 - 使用策略模式消除多重 if-else

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-04 源格式改由 ConvertConfig.direction 推导（新增模块级函数
      direction_to_source_format），不再读取已删除的 source_format 字段
更新: 2026-09-10 direction_to_source_format 新增 task_type 可选参数
      （import + MODE.OCR → Format.PPOCR），_CONVERTER_MAP 新增
      Format.PPOCR → PPOCR2JsonConverter（PaddleOCR det 标注导入 LabelMe）
"""

from typing import Dict, Any, Callable
from smart_annotator.config import MODE, SysConfig, Format
from .txt_converter import (
    YoloConverter,
    YoloPoseConverter,
    PPOCRConverter,
    YoloSegConverter,
)
from .json_converter import (
    Yolo2JsonConverter,
    YoloPose2JsonConverter,
    YoloSeg2JsonConverter,
)
from .ppocr_converter import PPOCR2JsonConverter


# region 转换器工厂配置
# 源格式 -> 任务模式 -> 转换器类的映射
# Format.LABELME（源为 json）→ YoloConverter 系列（json→txt）
# Format.YOLO（源为 txt）→ Yolo2JsonConverter 系列（txt→json）
# Format.PPOCR（源为 PaddleOCR det 标注）→ PPOCR2JsonConverter（det_gt→json，仅 OCR）
_CONVERTER_MAP: Dict[Format, Dict[MODE, Any]] = {
    Format.LABELME: {
        MODE.DETECT: YoloConverter,
        MODE.POSE: YoloPoseConverter,
        MODE.OCR: PPOCRConverter,
        MODE.SEGMENT: YoloSegConverter,
    },
    Format.YOLO: {
        MODE.DETECT: Yolo2JsonConverter,
        MODE.POSE: YoloPose2JsonConverter,
        MODE.SEGMENT: YoloSeg2JsonConverter,
    },
    Format.PPOCR: {
        MODE.OCR: PPOCR2JsonConverter,
    },
}


# endregion


def direction_to_source_format(direction: str, task_type: MODE = None) -> Format:
    """将转换方向推导为源格式。

    Args:
        direction: 转换方向（"export"=LabelMe→YOLO 导出 /
            "import"=YOLO→LabelMe 导入）。
        task_type: 任务模式（可选）；"import" 且 MODE.OCR 时源格式为
            Format.PPOCR（PaddleOCR det 标注），其余组合不受影响。

    Returns:
        对应的源格式枚举（export→Format.LABELME，import→Format.YOLO，
        import+OCR→Format.PPOCR）。

    Raises:
        ValueError: 当方向值不受支持时抛出。
    """
    if direction == "export":
        return Format.LABELME
    if direction == "import":
        if task_type == MODE.OCR:
            return Format.PPOCR
        return Format.YOLO
    raise ValueError(f"不支持的转换方向: {direction}")


class Converter:
    """通用转换器，根据转换方向和任务模式自动选择对应的转换器实现。"""

    def __init__(self, config: SysConfig):
        """初始化转换器。

        源格式由 ConvertConfig.direction 推导（export=LabelMe 源，
        import=YOLO 源；import 且任务为 OCR 时源为 PPOCR det 标注，
        走 PPOCR2JsonConverter）。

        Args:
            config: 系统配置对象。

        Raises:
            ValueError: 当转换方向或任务模式不支持时抛出。
        """
        # 由转换方向推导源格式（OCR 导入走 PPOCR 源）
        self.source_format = direction_to_source_format(
            config.convert_config.direction, config.task_type
        )
        self.mode = config.task_type

        # 使用策略模式：通过映射表查找对应的转换器类
        source_mapping = _CONVERTER_MAP.get(self.source_format)
        if source_mapping is None:
            raise ValueError(f"不支持的源格式: {self.source_format}")

        converter_cls = source_mapping.get(self.mode)
        if converter_cls is None:
            raise ValueError(
                f"当源类型为{self.source_format}时，转换类型不支持{self.mode.name}"
            )

        self.converter = converter_cls(config.convert_config)

    def run(self, run_callback: Callable[[str, float], bool]) -> bool:
        """执行转换任务。

        Args:
            run_callback: 进度回调函数。

        Returns:
            任务是否成功完成。
        """
        return self.converter.run(run_callback)


# endregion
