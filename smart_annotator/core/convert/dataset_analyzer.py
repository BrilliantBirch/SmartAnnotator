# -*- coding: utf-8 -*-
"""
数据集一键分析模块

扫描标注目录，实现三项分析：
    1. 标签提取：从 LabelMe JSON 标注的 shapes 中提取所有唯一标签
    2. 任务类型推断：按 shape 类型特征推断 DETECT/POSE/SEGMENT
    3. 转换方向检测：按标注文件后缀推断源格式（JSON→TXT 或 TXT→JSON）

纯逻辑实现，无 Qt 依赖（供 AnalyzeWorker 在后台线程调用）。

作者: BaiBinnan
创建日期: 2026-09-02
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from ...config import MODE, Format
from ...utils import LOGGER, getJsonFilesInDir, getTxtFilesInDir, getImageFilesInDir


# LabelMe shape_type → shape 分组（用于任务类型推断）
# point/points 归为 point 组；rectangle 为 box；polygon 为多边形
_SHAPE_GROUPS = {
    "rectangle": "rectangle",
    "point": "point",
    "points": "point",
    "polygon": "polygon",
}


@dataclass
class DatasetAnalysis:
    """数据集分析结果。

    Attributes:
        labels: 唯一标签列表（按首次出现顺序，保持数据集原始顺序）。
        label_counts: {标签: shape 出现次数}。
        shape_counts: {shape 分组: 出现次数}（rectangle/point/polygon）。
        task_type: 推断的任务类型。
        source_format: 检测到的标注格式（LabelMe=JSON 输入 / YOLO=TXT 输入）；
            无标注文件时为 None。
        json_count / txt_count / image_count: 各类文件数量。
        error_files: 解析失败的标注文件路径列表。
        max_class_id: TXT 数据集检测到的最大类别索引（-1 表示未检测到）。
    """

    labels: list = field(default_factory=list)
    label_counts: dict = field(default_factory=dict)
    shape_counts: dict = field(default_factory=dict)
    task_type: MODE = MODE.DETECT
    source_format: Format = None
    json_count: int = 0
    txt_count: int = 0
    image_count: int = 0
    error_files: list = field(default_factory=list)
    max_class_id: int = -1


def _infer_task_from_shapes(shape_counts: dict) -> MODE:
    """按 shape 分组特征推断任务类型（多类型共存时的优先级判断）。

    优先级机制（高 → 低）：
        point > polygon > rectangle
    依据：姿态数据集必含 box+point（box 不构成否定证据），
    分割数据集常含 box+polygon，故 point 最高、polygon 次之、
    仅 rectangle 时才判定为检测任务。

    Args:
        shape_counts: {shape 分组: 出现次数}。

    Returns:
        推断的任务类型（无任何 shape 时默认 DETECT）。
    """
    if shape_counts.get("point", 0) > 0:
        return MODE.POSE
    if shape_counts.get("polygon", 0) > 0:
        return MODE.SEGMENT
    return MODE.DETECT


def _analyze_labelme_jsons(json_files: list, result: DatasetAnalysis, progress_cb) -> None:
    """解析 LabelMe JSON 标注：提取标签、统计 shape 类型。

    解析失败的文件记入 error_files，不中断整体分析。

    Args:
        json_files: JSON 标注文件路径列表。
        result: 分析结果对象（就地更新）。
        progress_cb: 进度回调 callback(desc, progress)。
    """
    seen_lower = {}  # {小写标签: 首次出现的原始拼写}
    total = len(json_files)
    for idx, file_path in enumerate(json_files):
        progress_cb("解析 LabelMe 标注文件", (idx + 1) / total)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 结构校验：LabelMe 标注必须含 shapes 列表
            shapes = data.get("shapes")
            if not isinstance(shapes, list):
                raise ValueError("缺少合法的 shapes 字段")
            for shape in shapes:
                if not isinstance(shape, dict):
                    continue
                label = str(shape.get("label", "")).strip()
                if not label:
                    continue
                # 大小写不敏感去重（与转换端 JsonBaseConverter 行为一致），保留首次拼写
                lower = label.lower()
                if lower not in seen_lower:
                    seen_lower[lower] = label
                    result.labels.append(label)
                    result.label_counts[label] = 0
                result.label_counts[seen_lower[lower]] += 1
                group = _SHAPE_GROUPS.get(str(shape.get("shape_type", "")).lower())
                if group:
                    result.shape_counts[group] = result.shape_counts.get(group, 0) + 1
        except (ValueError, KeyError, OSError, UnicodeDecodeError) as ex:
            result.error_files.append(str(file_path))
            LOGGER.warning(f"解析标注文件失败（已跳过）: {file_path}: {ex}")


def _analyze_yolo_txts(txt_files: list, result: DatasetAnalysis, progress_cb) -> None:
    """解析 YOLO TXT 标注：按行字段数推断任务类型与最大类别索引。

    行字段数特征（与 json_converter 各转换器的格式一致）：
        - 5 个字段: class x y w h → rectangle（检测）
        - 5 + 3k 个字段（k>=1）: 检测框 + k 个关键点 → point（姿态）
        - 1 + 2N 个字段（N>=3，奇数）: 多边形顶点 → polygon（分割）
    多类型共存时沿用 _infer_task_from_shapes 的优先级。

    Args:
        txt_files: TXT 标注文件路径列表。
        result: 分析结果对象（就地更新）。
        progress_cb: 进度回调 callback(desc, progress)。
    """
    total = len(txt_files)
    for idx, file_path in enumerate(txt_files):
        progress_cb("解析 YOLO 标注文件", (idx + 1) / total)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 5:
                        continue
                    try:
                        class_id = int(parts[0])
                        values = [float(v) for v in parts[1:]]
                    except ValueError:
                        continue  # 非数值行（注释/空行等），跳过
                    result.max_class_id = max(result.max_class_id, class_id)
                    n = len(values) + 1
                    if n == 5:
                        group = "rectangle"
                    elif (n - 5) % 3 == 0:
                        group = "point"
                    elif n % 2 == 1:
                        group = "polygon"
                    else:
                        continue
                    result.shape_counts[group] = result.shape_counts.get(group, 0) + 1
        except (OSError, UnicodeDecodeError) as ex:
            result.error_files.append(str(file_path))
            LOGGER.warning(f"解析标注文件失败（已跳过）: {file_path}: {ex}")


def analyze_dataset(input_dir, progress_cb=None) -> DatasetAnalysis:
    """一键分析标注数据集：提取标签 + 推断任务类型 + 检测转换方向。

    转换方向检测规则：
        - 检测到 JSON 标注 → 源格式 LabelMe（json→txt 方向）
        - 仅检测到 TXT 标注 → 源格式 YOLO（txt→json 方向）
        - 两者共存 → 优先 JSON（LabelMe 标签信息更完整），并记录告警

    Args:
        input_dir: 标注数据集目录路径。
        progress_cb: 进度回调 callback(desc, progress)，无则不回调。

    Returns:
        DatasetAnalysis 分析结果对象。

    Raises:
        ValueError: 目录不存在时抛出（由调用方处理）。
    """
    if not progress_cb:
        # 空回调占位（保持主流程简洁）
        progress_cb = lambda desc, progress: None

    dir_path = Path(input_dir)
    if not dir_path.is_dir():
        raise ValueError(f"输入目录不存在或不是目录: {input_dir}")

    result = DatasetAnalysis()

    # ===== 步骤 1: 扫描文件（json / txt / 图片）=====
    progress_cb("扫描目录文件", 0.0)
    json_files = getJsonFilesInDir(str(dir_path))
    txt_files = getTxtFilesInDir(str(dir_path))
    image_files = getImageFilesInDir(str(dir_path))
    result.json_count = len(json_files)
    result.txt_count = len(txt_files)
    result.image_count = len(image_files)

    if result.json_count == 0 and result.txt_count == 0:
        # 无标注文件：不设置方向与任务，由界面提示用户
        return result

    # ===== 步骤 2: 检测转换方向（源格式）=====
    if result.json_count > 0:
        result.source_format = Format.LABELME
        if result.txt_count > 0:
            LOGGER.warning(
                f"目录中同时存在 JSON({result.json_count}) 与 TXT({result.txt_count}) 标注，"
                f"已优先按 LabelMe(JSON) 方向分析"
            )
    else:
        result.source_format = Format.YOLO

    # ===== 步骤 3: 解析标注内容 =====
    if result.source_format == Format.LABELME:
        _analyze_labelme_jsons(json_files, result, progress_cb)
    else:
        _analyze_yolo_txts(txt_files, result, progress_cb)

    # ===== 步骤 4: 推断任务类型 =====
    result.task_type = _infer_task_from_shapes(result.shape_counts)
    progress_cb("分析完成", 1.0)

    return result
