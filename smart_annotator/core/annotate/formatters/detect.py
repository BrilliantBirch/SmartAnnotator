# -*- coding: utf-8 -*-
"""
目标检测格式化器

作者: BaiBinnan
创建日期: 2026-08-10
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
        """格式化目标检测结果为 YOLO 行。"""
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
