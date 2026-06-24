"""
Description：目标检测格式化器
Author: BaiBinnan
Date: 2026/06/24
LastEdit: 2026/06/24
LastEditBy: BaiBinnan
E-mail: baibinnan@chuanfeng.com
"""

from typing import Dict, List, Any, Optional
from .base import BaseFormatter


class DetectFormatter(BaseFormatter):
    """目标检测任务的结果格式化器"""

    def format(
        self,
        pred: Dict[str, Any],
        kpt_conf: float = 0.5,
        class_mapping: Optional[Dict[int, str]] = None,
        kpt_shape: Optional[int] = None,
    ) -> List[str]:
        lines: List[str] = []
        bboxes = pred["bboxs"]
        labels = pred["labels"]

        if bboxes is None or labels is None:
            return lines

        for bbox, label in zip(bboxes, labels):
            x, y, w, h = bbox
            cls = label
            lines.append(f"{cls} {x} {y} {w} {h}\n")

        return lines