"""
Description：标注格式化器基类
Author: BaiBinnan
Date: 2026/06/24
LastEdit: 2026/06/24
LastEditBy: BaiBinnan
E-mail: baibinnan@chuanfeng.com
"""

from typing import Dict, List, Any, Optional
import numpy as np


class BaseFormatter:
    """标注格式化器基类，所有具体格式化器需继承此类"""

    def format(
        self,
        pred: Dict[str, Any],
        kpt_conf: float = 0.5,
        class_mapping: Optional[Dict[int, str]] = None,
        kpt_shape: Optional[int] = None,
    ) -> List[str]:
        """
        将预测结果格式化为YOLO格式的行列表

        Args:
            pred: 单张图片的预测结果字典
            kpt_conf: 关键点置信度阈值
            class_mapping: 类别ID到名称的映射
            kpt_shape: 关键点形状

        Returns:
            YOLO格式的标注行列表
        """
        raise NotImplementedError("子类必须实现format方法")