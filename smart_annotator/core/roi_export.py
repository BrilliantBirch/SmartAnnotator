# -*- coding: utf-8 -*-
"""
感知区（ROI）裁剪导出模块

按 labelme 文档顶层的感知区（ROI，字段结构见 labelme_io）逐框裁剪原图，
并同步裁剪标注：输出 `<原图stem>_ROI<id>.<原扩展名>` 与同名
`<原图stem>_ROI<id>.json`（labelme 格式，不含 ROI 字段，避免二次裁剪）。

坐标口径：
    - 裁剪框取整为整数像素边界（下界向下取整、上界向上取整并钳制到图像内），
      保证 crop 的 numpy 切片为整数边界且不丢边界像素；
    - 标注坐标统一平移（减去裁剪框左上角）后钳制到裁剪图范围内，保留 float
      （保留 2 位小数）；
    - 跨边界的矩形取交集后输出两点式 [[左上], [右下]]，完全出界的形状丢弃。

本模块仅供后台导出线程调用，无 Qt 依赖。

作者: BaiBinnan
创建日期: 2026-09-17
更新: 2026-09-17 新建：按感知区裁剪图片与标注并落盘（中文路径安全，无 Qt 依赖）
"""

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from smart_annotator.utils import LOGGER
from smart_annotator.core.labelme_io import (
    SHAPE_POINT,
    SHAPE_RECTANGLE,
    empty_document,
    document_shapes,
    load_document,
    save_document,
    set_document_shapes,
)

# ===== 导出子目录名（ROI 裁剪结果统一落在此目录下）=====
ROI_DIRNAME = "ROI"

# JPEG 裁剪图编码质量（仅 .jpg/.jpeg 生效，其余格式用默认参数）
_JPEG_QUALITY = 95


def roi_output_dir(work_dir) -> Path:
    """返回感知区裁剪导出的输出目录（不创建）。

    Args:
        work_dir: 数据集工作目录（原图与 JSON 所在目录）。

    Returns:
        `<work_dir>/ROI` 路径对象；目录的实际创建发生在导出时。
    """
    return Path(work_dir) / ROI_DIRNAME


def _as_point_pairs(points) -> Optional[List[Tuple[float, float]]]:
    """把 labelme 的 points 序列规范为 (x, y) float 元组列表。

    Args:
        points: 形状的点序列，形如 [[x, y], ...]。

    Returns:
        (x, y) float 元组列表；序列为空或结构非法（非二元坐标）时返回 None。
    """
    if not points:
        return None
    pairs: List[Tuple[float, float]] = []
    for point in points:
        # 每个点须为长度 >= 2 的可转 float 序列
        if isinstance(point, (str, bytes)) or not hasattr(point, "__len__"):
            return None
        if len(point) < 2:
            return None
        try:
            pairs.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            return None
    return pairs


def clamp_shapes_to_box(
    shapes: List[Dict[str, Any]], box
) -> List[Dict[str, Any]]:
    """把标注形状裁剪并平移到感知区（ROI）框内（纯函数，无 IO）。

    处理规则（输出为深拷贝的新字典，保留 label/group_id/description/
    shape_type/flags/mask 等全部键，仅替换 points；以 "_" 为前缀的运行时
    键直接丢弃）：
        - rectangle：对全部点取包围盒后与 ROI 求交集，交集宽或高 <= 0 丢弃，
          输出两点式 [[左上], [右下]]；
        - point：闭区间判断点是否落在 ROI 内（含边界），框外的点丢弃，
          全部点都在框外则整个形状丢弃；
        - 其余类型（polygon 及未知类型）：先按包围盒与 ROI 判交（无交集丢弃），
          有交集则逐顶点钳制到 ROI 内。
    保留形状的坐标统一减去 ROI 左上角，再钳制到
    [0, crop_w] × [0, crop_h]，保留 float（2 位小数）。

    Args:
        shapes: labelme 形状字典列表。
        box: 感知区边界框 [x1, y1, x2, y2]（像素坐标，允许任意对角点顺序）。

    Returns:
        裁剪后的形状字典列表（保持输入顺序）；crop 宽或高 <= 0 时为空列表。
    """
    # 归一 ROI 框：逐轴取 min/max 后取整（下界向下、上界向上取整，下界不小于 0）
    coords = [float(v) for v in box]
    x1 = max(0, int(math.floor(min(coords[0], coords[2]))))
    y1 = max(0, int(math.floor(min(coords[1], coords[3]))))
    x2 = int(math.ceil(max(coords[0], coords[2])))
    y2 = int(math.ceil(max(coords[1], coords[3])))
    crop_w = x2 - x1
    crop_h = y2 - y1
    # ROI 无有效面积：任何形状都不可能有有效标注
    if crop_w <= 0 or crop_h <= 0:
        return []

    clamped: List[Dict[str, Any]] = []
    for shape in shapes:
        points = _as_point_pairs(shape.get("points"))
        if points is None:
            # 无点/点结构非法：无法裁剪，丢弃该形状
            continue
        shape_type = str(shape.get("shape_type", "") or "").lower()
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        bx1, bx2 = min(xs), max(xs)
        by1, by2 = min(ys), max(ys)
        new_points: Optional[List[List[float]]] = None

        if shape_type == SHAPE_RECTANGLE:
            # 矩形：包围盒与 ROI 求交集，无交集（宽或高 <= 0）丢弃
            ix1, iy1 = max(bx1, float(x1)), max(by1, float(y1))
            ix2, iy2 = min(bx2, float(x2)), min(by2, float(y2))
            if ix2 - ix1 > 0 and iy2 - iy1 > 0:
                # 平移后仍输出两点式（左上 / 右下）
                new_points = [
                    [round(ix1 - x1, 2), round(iy1 - y1, 2)],
                    [round(ix2 - x1, 2), round(iy2 - y1, 2)],
                ]
        elif shape_type == SHAPE_POINT:
            # 点：闭区间判断（含 ROI 边界），框外的点逐个丢弃
            kept = [
                [
                    round(min(max(px - x1, 0.0), float(crop_w)), 2),
                    round(min(max(py - y1, 0.0), float(crop_h)), 2),
                ]
                for px, py in points
                if x1 <= px <= x2 and y1 <= py <= y2
            ]
            if kept:
                new_points = kept
        else:
            # polygon 及未知类型兜底：包围盒无交集则丢弃
            if bx2 > x1 and bx1 < x2 and by2 > y1 and by1 < y2:
                # 有交集：逐顶点平移并钳制到裁剪图范围内
                new_points = [
                    [
                        round(min(max(px - x1, 0.0), float(crop_w)), 2),
                        round(min(max(py - y1, 0.0), float(crop_h)), 2),
                    ]
                    for px, py in points
                ]

        if new_points is None:
            continue
        # 深拷贝形状并替换 points；剥离 "_" 前缀运行时键（与 labelme 格式对齐）
        new_shape = {
            k: v for k, v in shape.items() if not str(k).startswith("_")
        }
        new_shape["points"] = new_points
        clamped.append(new_shape)
    return clamped


def _integer_crop_box(box, img_w: int, img_h: int) -> Tuple[int, int, int, int]:
    """把感知区框转为整数像素裁剪边界并钳制到图像范围内。

    Args:
        box: 感知区边界框 [x1, y1, x2, y2]（允许任意对角点顺序）。
        img_w: 图像宽度（像素）。
        img_h: 图像高度（像素）。

    Returns:
        (x1, y1, x2, y2) 整数像素边界；越界部分被钳制，宽或高可能 <= 0。
    """
    coords = [float(v) for v in box]
    x1 = max(0, int(math.floor(min(coords[0], coords[2]))))
    y1 = max(0, int(math.floor(min(coords[1], coords[3]))))
    x2 = min(img_w, int(math.ceil(max(coords[0], coords[2]))))
    y2 = min(img_h, int(math.ceil(max(coords[1], coords[3]))))
    return x1, y1, x2, y2


def export_image_rois(
    image_path, json_path, rois, out_dir
) -> Dict[str, Any]:
    """按感知区（ROI）列表裁剪单张原图并导出裁剪图与裁剪标注。

    逐 ROI 输出 `<原图stem>_ROI<id><原扩展名>`（保持原图格式，JPEG 质量 95）
    与 `<原图stem>_ROI<id>.json`（labelme 格式，不含 ROI 字段）。原图标注经
    clamp_shapes_to_box 裁剪平移后写入裁剪 JSON；原 JSON 缺失/读取失败时按
    空标注处理（仅导出裁剪图）。单个 ROI 的处理异常计入 skipped 并记日志，
    不中断整批。输出目录不存在时自动创建；rois 为空时直接返回且不创建目录。

    Args:
        image_path: 原图路径（中文路径安全）。
        json_path: 原图对应的 labelme JSON 路径（可为 None/不存在）。
        rois: 感知区字典列表，元素形如 {"id": int, "box": [x1, y1, x2, y2]}。
        out_dir: 输出目录（通常为 roi_output_dir 的返回值）。

    Returns:
        {"exported": 成功导出的 ROI 个数, "skipped": 跳过个数, "error": ""}；
        图片解码失败或目录创建失败时 error 为非空描述（exported/skipped 为 0）。
    """
    result: Dict[str, Any] = {"exported": 0, "skipped": 0, "error": ""}
    roi_list = list(rois or [])
    # 无感知区：直接返回，不创建输出目录
    if not roi_list:
        return result

    image_path = Path(image_path)
    # 读原图（np.fromfile + cv2.imdecode 支持中文路径）
    try:
        image = cv2.imdecode(
            np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR
        )
    except Exception as exc:
        LOGGER.error(f"读取图片失败 {image_path}: {exc}")
        image = None
    if image is None:
        return {
            "exported": 0,
            "skipped": 0,
            "error": f"图片解码失败: {image_path}",
        }

    # 读取原图标注（失败按空标注处理，不影响裁剪图导出）
    shapes: List[Dict[str, Any]] = []
    if json_path and Path(json_path).exists():
        try:
            shapes = document_shapes(load_document(json_path))
        except Exception as exc:
            LOGGER.warning(f"读取标注失败，按空标注处理 {json_path}: {exc}")
            shapes = []

    # 创建输出目录（rois 非空时）
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        LOGGER.error(f"创建输出目录失败 {out_dir}: {exc}")
        return {
            "exported": 0,
            "skipped": 0,
            "error": f"创建输出目录失败: {out_dir}",
        }

    img_h, img_w = image.shape[:2]
    # 扩展名取自原图后缀（保持原格式），文件名沿用原图主干
    ext = image_path.suffix or ".png"
    # 编码用的扩展名小写归一（OpenCV 编码器按格式名分发）
    encode_ext = ext.lower()
    encode_params = (
        [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY]
        if encode_ext in (".jpg", ".jpeg")
        else []
    )
    stem = image_path.stem

    for roi in roi_list:
        roi_id = None
        try:
            roi_id = int(roi.get("id"))
            # ROI 取整并钳制到图像范围内；无效面积计入 skipped
            x1, y1, x2, y2 = _integer_crop_box(roi.get("box"), img_w, img_h)
            if x2 - x1 <= 0 or y2 - y1 <= 0:
                result["skipped"] += 1
                LOGGER.warning(f"感知区越界或无效，跳过 {image_path}#{roi_id}")
                continue

            # 裁剪原图（整数切片）
            crop = image[y1:y2, x1:x2]
            crop_h, crop_w = crop.shape[:2]

            # 写裁剪图：cv2.imencode 的 tofile 支持中文路径
            ok, buffer = cv2.imencode(encode_ext, crop, encode_params)
            if not ok:
                result["skipped"] += 1
                LOGGER.error(f"编码裁剪图失败，跳过 {image_path}#{roi_id}")
                continue
            image_name = f"{stem}_ROI{roi_id}{ext}"
            buffer.tofile(str(out_dir / image_name))

            # 写裁剪标注：平移钳制后的形状 + 裁剪图尺寸（不写 ROI 字段）
            cropped_shapes = clamp_shapes_to_box(shapes, [x1, y1, x2, y2])
            doc = empty_document(image_name, crop_w, crop_h)
            set_document_shapes(doc, cropped_shapes)
            save_document(doc, out_dir / f"{stem}_ROI{roi_id}.json")
            result["exported"] += 1
        except Exception as exc:
            # 单个 ROI 处理异常：计入 skipped 并记日志，不中断整批
            result["skipped"] += 1
            LOGGER.error(f"导出感知区失败 {image_path}#{roi_id}: {exc}")
    return result