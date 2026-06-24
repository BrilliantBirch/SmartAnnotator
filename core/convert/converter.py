"""
Description：通用的转换器 - 使用策略模式消除多重if-else
Author: BaiBinnan
Date: 2025/03/14
LastEdit: 2026/06/24
LastEditBy: BaiBinnan
E-mail: baibinnan@chuanfeng.com
update：
    1. 2026/06/24: 使用策略模式简化转换器初始化逻辑，消除嵌套if-else
"""

from typing import Dict, Any, Callable, Optional
from cfg import MODE, SysConfig, LOGGER
from .txtconverter import (
    YoloConverter,
    YoloPoseConverter,
    PPOCRConverter,
    YoloSegConverter,
)
from .jsonconverter import (
    Yolo2JsonConverter,
    YoloPose2JsonConverter,
    YoloSeg2JsonConverter,
)


# region 转换器工厂配置
# 源格式 -> 任务模式 -> 转换器类的映射
_CONVERTER_MAP: Dict[str, Dict[MODE, Any]] = {
    "json": {
        MODE.DETECT: YoloConverter,
        MODE.POSE: YoloPoseConverter,
        MODE.OCR: PPOCRConverter,
        MODE.SEGMENT: YoloSegConverter,
    },
    "txt": {
        MODE.DETECT: Yolo2JsonConverter,
        MODE.POSE: YoloPose2JsonConverter,
        MODE.SEGMENT: YoloSeg2JsonConverter,
    },
}


# endregion


class Converter:
    """通用转换器，根据源格式和任务模式自动选择对应的转换器实现"""

    def __init__(self, config: SysConfig):
        """
        初始化转换器

        Args:
            config: 系统配置对象

        Raises:
            ValueError: 当源格式或任务模式不支持时抛出
        """
        self.sourceFormat = config.convertConfig.sourceFormat
        self.mode = config.currentMode

        # 使用策略模式：通过映射表查找对应的转换器类
        source_mapping = _CONVERTER_MAP.get(self.sourceFormat)
        if source_mapping is None:
            raise ValueError(f"不支持的源格式: {self.sourceFormat}")

        converter_cls = source_mapping.get(self.mode)
        if converter_cls is None:
            raise ValueError(
                f"当源类型为{self.sourceFormat}时，转换类型不支持{self.mode.name}"
            )

        self.converter = converter_cls(config.convertConfig)

    def run(self, run_callback: Callable[[str, float], bool]) -> bool:
        """
        执行转换任务

        Args:
            run_callback: 进度回调函数

        Returns:
            任务是否成功完成
        """
        return self.converter.run(run_callback)


# endregion