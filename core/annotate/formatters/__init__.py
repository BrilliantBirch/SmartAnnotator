"""
Description：标注格式化器模块 - 使用策略模式消除多重if-else判断
Author: BaiBinnan
Date: 2025/06/09
LastEdit: 2026/06/24
LastEditBy: BaiBinnan
E-mail: baibinnan@chuanfeng.com
"""

from .base import BaseFormatter
from .detect import DetectFormatter
from .pose import PoseFormatter
from .segment import SegmentFormatter
from .factory import FormatterFactory