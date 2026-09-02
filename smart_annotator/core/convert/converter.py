# -*- coding: utf-8 -*-
"""
通用的转换器 - 使用策略模式消除多重 if-else

作者: BaiBinnan
创建日期: 2026-08-10
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


# region 转换器工厂配置
# 源格式 -> 任务模式 -> 转换器类的映射
# Format.LABELME（源为 json）→ YoloConverter 系列（json→txt）
# Format.YOLO（源为 txt）→ Yolo2JsonConverter 系列（txt→json）
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
}


# endregion


class Converter:
    """通用转换器，根据源格式和任务模式自动选择对应的转换器实现。"""

    def __init__(self, config: SysConfig):
        """初始化转换器。

        Args:
            config: 系统配置对象。

        Raises:
            ValueError: 当源格式或任务模式不支持时抛出。
        """
        self.source_format = config.convert_config.source_format
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
