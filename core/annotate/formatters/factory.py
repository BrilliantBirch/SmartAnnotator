"""
Description：格式化器工厂 - 根据任务类型创建对应的格式化器
Author: BaiBinnan
Date: 2026/06/24
LastEdit: 2026/06/24
LastEditBy: BaiBinnan
E-mail: baibinnan@chuanfeng.com
"""

from cfg import MODE, LOGGER
from .base import BaseFormatter
from .detect import DetectFormatter
from .pose import PoseFormatter
from .segment import SegmentFormatter


class FormatterFactory:
    """格式化器工厂，根据任务模式创建对应的格式化器"""

    _formatters = {
        MODE.DETECT: DetectFormatter,
        MODE.POSE: PoseFormatter,
        MODE.SEGMENT: SegmentFormatter,
    }

    @classmethod
    def create(cls, mode: MODE) -> BaseFormatter:
        """
        根据任务模式创建格式化器

        Args:
            mode: 任务模式枚举

        Returns:
            对应的格式化器实例

        Raises:
            ValueError: 当任务模式不支持时抛出
        """
        formatter_cls = cls._formatters.get(mode)
        if formatter_cls is None:
            error_msg = f"任务类型:{mode.name}暂不支持"
            LOGGER.warning(error_msg)
            raise ValueError(error_msg)
        return formatter_cls()