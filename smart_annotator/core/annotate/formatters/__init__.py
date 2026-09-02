# -*- coding: utf-8 -*-
"""
标注格式化器模块 - 使用策略模式消除多重 if-else 判断

作者: BaiBinnan
创建日期: 2026-08-10
"""

from .base import BaseFormatter
from .detect import DetectFormatter
from .pose import PoseFormatter
from .segment import SegmentFormatter
from .factory import FormatterFactory
