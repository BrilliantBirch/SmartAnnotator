# -*- coding: utf-8 -*-
"""
分割检测格式化器

作者: BaiBinnan
创建日期: 2026-08-10
"""

from typing import Dict, List, Any, Optional
from .base import BaseFormatter


class SegmentFormatter(BaseFormatter):
    """分割任务的结果格式化器"""

    def format(
        self,
        pred: Dict[str, Any],
        kpt_conf: float = 0.5,
        class_mapping: Optional[Dict[int, str]] = None,
        kpt_shape: Optional[int] = None,
    ) -> List[str]:
        """格式化分割结果为 YOLO-Seg 行（含多边形顶点）。"""
        lines: List[str] = []
        labels = pred["labels"]
        boundary_points = pred.get("boundary_points")

        if labels is None or boundary_points is None:
            return lines

        for classid, points in zip(labels, boundary_points):
            if points:
                line = f"{classid} {' '.join(map(str, points))}"
                lines.append(line)

        return lines
