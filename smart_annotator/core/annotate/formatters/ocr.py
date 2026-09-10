# -*- coding: utf-8 -*-
"""
OCR 标注格式化器 - 直出 labelme 形状字典列表

与其他格式化器（输出 YOLO 文本行、经 yolo_to_labelme 转换）不同，
OCR 结果为"每个文本行一个四点多边形形状"，直接构造 labelme 标准形状：
    - label 固定为 "text"（OCR 文本区域类别）
    - points 为 4 点像素坐标（polygon）
    - description 记录识别文本
    - score 记录识别置信度（PPOCRLabel 兼容字段）

作者: BaiBinnan
创建日期: 2026-09-10
更新: 2026-09-10 首次创建：OcrFormatter 直出 labelme 形状
"""

from typing import Any, Dict, List

from smart_annotator.core.labelme_io import SHAPE_POLYGON, new_shape

from .base import BaseFormatter


class OcrFormatter(BaseFormatter):
    """OCR 任务的结果格式化器（直出 labelme 形状字典列表）。"""

    def format(self, pred: Dict[str, Any], *args, **kwargs) -> List[Dict[str, Any]]:
        """将 OCR 预测结果格式化为 labelme 形状字典列表。

        与其他格式化器返回 YOLO 文本行不同，本格式化器直接返回
        labelme 形状（调用侧跳过 yolo_to_labelme 转换）——文本行的
        四点像素坐标、识别文本与置信度无法无损表达为 YOLO 行。
        兼容接受 annotator 统一传入的 kpt_conf/class_mapping/kpt_shape
        参数（OCR 无关键点与类别映射，忽略）。保留全部检测框
        （含空文本行），文本/置信度如实记录。

        Args:
            pred: 单张图片的 OCR 预测字典
                {"texts", "scores", "points", "det_scores"}。
            *args: 兼容占位（未使用）。
            **kwargs: 兼容占位（kpt_conf/class_mapping/kpt_shape，未使用）。

        Returns:
            labelme 形状字典列表；每个文本行一个 polygon 形状，
            额外携带 score 字段（识别置信度，PPOCRLabel 兼容）。
        """
        texts = pred.get("texts") or []
        scores = pred.get("scores") or []
        points = pred.get("points") or []

        shapes: List[Dict[str, Any]] = []
        for text, score, pts in zip(texts, scores, points):
            # 每个文本行一个四点多边形形状（label 固定 text，识别文本入 description）
            shape = new_shape(
                label="text",
                points=pts,
                shape_type=SHAPE_POLYGON,
                description=str(text),
            )
            # 识别置信度（PPOCRLabel 兼容字段）
            shape["score"] = float(score)
            shapes.append(shape)
        return shapes
