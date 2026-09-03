# -*- coding: utf-8 -*-
"""
LabelMe JSON 格式读写模块

定义 labelme 标注 JSON 的标准结构（与 labelme 5.x 完全一致），提供读取、
解析、构造与写入工具，供标注编辑器（canvas）与自动标注/格式转换链路复用。

数据结构（与 labelme 官方格式字段一一对应）：
    {
        "version": str,            # labelme 版本号
        "flags": {},               # 全局标志（labelme 保留）
        "shapes": [                # 标注对象列表
            {
                "label": str,               # 类别标签名
                "points": [[x, y], ...],    # 图像像素坐标（左上为原点）
                "group_id": int | None,     # 分组 id（pose 关键点归属同一框）
                "description": str,         # 附加描述（pose 可见性等）
                "shape_type": str,          # rectangle / point / polygon ...
                "flags": {},                # 单个形状标志
                "mask": None,               # 分割掩码（labelme 保留，本项目不使用）
            }
        ],
        "imagePath": str,          # 关联图像文件名
        "imageData": None,         # 内嵌图像（本项目使用外链 imagePath，恒为 None）
        "imageHeight": int,
        "imageWidth": int
    }

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-02 新增 collect_labels_from_files 后台批量汇总标签/关键点
更新: 2026-09-03 set_document_shapes 写入前剥离 "_" 前缀运行时字段（如 _visible），保证 JSON 与 labelme 标准格式一致
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from smart_annotator.config import LABELME_VERSION

# ===== 形状类型常量（与 labelme 一致）=====
SHAPE_RECTANGLE = "rectangle"
SHAPE_POINT = "point"
SHAPE_POLYGON = "polygon"

# 本编辑器支持的形状类型集合
SUPPORTED_SHAPES = (SHAPE_RECTANGLE, SHAPE_POINT, SHAPE_POLYGON)


def new_shape(
    label: str,
    points: List[List[float]],
    shape_type: str,
    group_id: Optional[int] = None,
    description: str = "",
) -> Dict[str, Any]:
    """构造一个 labelme 标准形状字典。

    Args:
        label: 类别标签名。
        points: 点的像素坐标列表 [[x, y], ...]。
        shape_type: 形状类型（rectangle / point / polygon）。
        group_id: 分组 id（pose 关键点归属同一检测框时使用）。
        description: 附加描述（如 pose 关键点可见性）。

    Returns:
        labelme 形状字典。
    """
    return {
        "label": label,
        "points": [list(p) for p in points],
        "group_id": group_id,
        "description": description,
        "shape_type": shape_type,
        "flags": {},
        "mask": None,
    }


def empty_document(
    image_path: str, image_width: int, image_height: int
) -> Dict[str, Any]:
    """构造一个空的 labelme 文档（不含任何形状）。

    Args:
        image_path: 关联图像文件名（存入 imagePath 字段）。
        image_width: 图像宽度（像素）。
        image_height: 图像高度（像素）。

    Returns:
        labelme 文档字典。
    """
    return {
        "version": LABELME_VERSION,
        "flags": {},
        "shapes": [],
        "imagePath": image_path,
        "imageData": None,
        "imageHeight": int(image_height),
        "imageWidth": int(image_width),
    }


def load_document(path) -> Dict[str, Any]:
    """从磁盘读取 labelme JSON 文档。

    Args:
        path: labelme JSON 文件路径。

    Returns:
        解析后的文档字典。

    Raises:
        FileNotFoundError: 文件不存在。
        json.JSONDecodeError: 文件不是合法 JSON。
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_document(doc: Dict[str, Any], path) -> None:
    """将 labelme 文档写入磁盘（UTF-8、2 空格缩进、保留中文）。

    Args:
        doc: labelme 文档字典。
        path: 输出 JSON 文件路径。
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)


def document_shapes(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """返回文档中的形状列表（缺失字段时安全返回空列表）。

    Args:
        doc: labelme 文档字典。

    Returns:
        形状字典列表。
    """
    return list(doc.get("shapes", []) or [])


def document_labels(doc: Dict[str, Any]) -> List[str]:
    """提取文档中出现的所有标签名（去重、按字典序排序）。

    Args:
        doc: labelme 文档字典。

    Returns:
        标签名列表。
    """
    labels = {shape.get("label", "") for shape in document_shapes(doc)}
    labels.discard("")
    return sorted(labels)


def set_document_shapes(doc: Dict[str, Any], shapes: List[Dict[str, Any]]) -> None:
    """替换文档中的形状列表（剥离运行时字段后写入）。

    约定：以 "_" 为前缀的键（如画布渲染可见性 "_visible"）为运行时
    视图状态，不属于 labelme 标准格式，写入文档前逐 shape 剥离，
    保证 JSON 输出与 labelme 官方格式完全一致。

    Args:
        doc: labelme 文档字典（就地更新）。
        shapes: 新的形状字典列表。
    """
    doc["shapes"] = [
        {k: v for k, v in shape.items() if not str(k).startswith("_")}
        for shape in shapes
    ]


def collect_labels_from_files(json_paths) -> Dict[str, List[str]]:
    """从多个 labelme JSON 文件汇总标签与关键点名称。

    供后台扫描线程调用（不阻塞 UI）：逐个解析 JSON，提取全部类别，
    并将 point 类型形状的标签归为关键点。无法解析的文件静默跳过。

    Args:
        json_paths: JSON 文件路径列表（可迭代）。

    Returns:
        {"labels": [标签...], "keypoints": [关键点标签...]}，均按字典序排序。
    """
    labels: set = set()
    keypoints: set = set()
    for path in json_paths:
        try:
            doc = load_document(path)
        except Exception:
            continue
        for shape in document_shapes(doc):
            label = shape.get("label", "")
            if not label:
                continue
            labels.add(label)
            if shape.get("shape_type") == SHAPE_POINT:
                keypoints.add(label)
    return {"labels": sorted(labels), "keypoints": sorted(keypoints)}