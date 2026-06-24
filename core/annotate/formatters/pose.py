"""
Description：姿态估计格式化器
Author: BaiBinnan
Date: 2026/06/24
LastEdit: 2026/06/24
LastEditBy: BaiBinnan
E-mail: baibinnan@chuanfeng.com
"""

from typing import Dict, List, Any, Optional
from .base import BaseFormatter


class PoseFormatter(BaseFormatter):
    """姿态估计任务的结果格式化器"""

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
        kpt = pred["keypoints"]

        if bboxes is None or labels is None or kpt is None:
            return lines

        for bbox, label, keypoints in zip(bboxes, labels, kpt):
            x, y, w, h = bbox
            cls = label
            kpt_str = " ".join(
                [
                    (
                        f"{k[0]} {k[1]} 2"
                        if k[2] > kpt_conf
                        else "0 0 0"
                    )
                    for k in keypoints
                ]
            )
            lines.append(f"{cls} {x} {y} {w} {h} {kpt_str}\n")

        return lines