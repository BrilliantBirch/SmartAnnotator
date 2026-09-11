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
更新: 2026-09-03 collect_labels_from_files 支持逐文件中断检查与进度回调，标签强制
      转字符串（兼容数字标签，修复大目录冷缓存扫描不可中断/无进度反馈问题）
更新: 2026-09-03 collect_labels_from_files 新增实例计数 counts（不区分大小写合并，拼写取首次出现），labels/keypoints 与 counts 拼写一致
更新: 2026-09-04 collect_labels_from_files 返回值新增 shape_counts 分组计数
      （rectangle/point/polygon，分组规则与 dataset_analyzer 一致），
      供主窗口导出前置统计复用（推断任务类型与预填类别）
更新: 2026-09-08 冗余清理：删除全库零引用的死函数 document_labels
      （文档标签提取，与 collect_labels_from_files 的扫描链路功能重复）
      与未使用 import Path
更新: 2026-09-10 document_shapes 新增四点矩形归一：PPOCRLabel 等第三方
      工具写出的 rectangle 为四角点表示，统一取包围盒转为本项目画布的
      两点式语义（[左上, 右下]），修复外部 OCR 标注显示被压扁的问题
更新: 2026-09-10 collect_labels_from_files 返回值新增 text_shape_count
      （box 类形状中 description 非空的个数，OCR 推断文本证据），与
      dataset_analyzer 口径一致，供导出对话框预填任务类型复用
"""

import json
from typing import Any, Dict, List, Optional

from smart_annotator.config import LABELME_VERSION

# ===== 形状类型常量（与 labelme 一致）=====
SHAPE_RECTANGLE = "rectangle"
SHAPE_POINT = "point"
SHAPE_POLYGON = "polygon"

# 本编辑器支持的形状类型集合
SUPPORTED_SHAPES = (SHAPE_RECTANGLE, SHAPE_POINT, SHAPE_POLYGON)

# LabelMe shape_type → shape 分组（与 dataset_analyzer 的 _SHAPE_GROUPS 规则
# 保持一致：point/points 归为 point 组，rectangle 为 box，polygon 为多边形），
# 供任务类型推断（point>0→POSE、polygon>0→SEGMENT、否则 DETECT）
SHAPE_GROUPS = {
    SHAPE_RECTANGLE: "rectangle",
    SHAPE_POINT: "point",
    "points": "point",
    SHAPE_POLYGON: "polygon",
}


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


def _normalize_rectangle_shape(shape: Dict[str, Any]) -> Dict[str, Any]:
    """将非两点式矩形形状归一为本项目画布的两点式语义（[左上, 右下]）。

    PPOCRLabel 等第三方标注工具写出的 rectangle 为四角点表示，而本编辑器
    的渲染/编辑/保存链路统一按 labelme 标准两点语义处理（points[0]=左上、
    points[1]=右下）。读取文档时对矩形全部顶点取包围盒，输出
    [[minx, miny], [maxx, maxy]]，轴对齐显示下与原四角点完全等价。

    Args:
        shape: 形状字典。

    Returns:
        归一后的新形状字典；两点式矩形与非矩形形状原样返回。
    """
    points = shape.get("points") or []
    if shape.get("shape_type") != SHAPE_RECTANGLE or len(points) <= 2:
        return shape
    # 对全部顶点取包围盒（容忍顶点顺序任意/重复），重构为左上+右下两点
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    normalized = dict(shape)
    normalized["points"] = [[min(xs), min(ys)], [max(xs), max(ys)]]
    return normalized


def document_shapes(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """返回文档中的形状列表（缺失字段时安全返回空列表）。

    矩形形状统一经 _normalize_rectangle_shape 归一为两点式（四点矩形
    取包围盒），保证画布渲染/编辑端点/hover 掩码等链路的一致语义。

    Args:
        doc: labelme 文档字典。

    Returns:
        形状字典列表。
    """
    return [
        _normalize_rectangle_shape(shape)
        for shape in list(doc.get("shapes", []) or [])
    ]


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


def collect_labels_from_files(json_paths, should_stop=None, on_progress=None) -> Dict[str, Any]:
    """从多个 labelme JSON 文件汇总标签、关键点名称、实例计数与 shape 分组计数。

    供后台扫描线程调用（不阻塞 UI）：逐个解析 JSON，提取全部类别，
    并将 point 类型形状的标签归为关键点。无法解析的文件静默跳过。

    实例计数不区分大小写合并：以 label.lower() 为合并键累加个数，
    输出键取该组首次出现的原拼写（如 "person"/"PERSON" 计入同一项，
    显示 "person"——首次出现的拼写）。labels/keypoints 输出合并后的
    拼写，与 counts 键一致。

    shape 分组计数与 dataset_analyzer 的分组规则完全一致：shape_type
    小写归一后按 SHAPE_GROUPS 映射（rectangle→rectangle、point/points
    →point、polygon→polygon），空标签形状不计入（与分析器口径一致），
    供导出对话框按 point>0→POSE、polygon>0→SEGMENT 推断任务类型。

    大目录冷缓存时逐文件读取可能耗时数十秒，故支持：
        - should_stop: 每个文件前检查的中断回调（返回 True 时提前结束），
          供切换文件夹重启扫描时及时终止旧任务；
        - on_progress: 进度回调 (已完成数, 总数)，供 UI 进度条驱动。
    标签统一强制转为字符串（兼容数字标签的 JSON，避免混合类型排序崩溃）。

    Args:
        json_paths: JSON 文件路径列表（可迭代）。
        should_stop: 中断检查回调（可选）。
        on_progress: 进度回调（可选，每 500 个文件触发一次）。

    Returns:
        {"labels": [标签...], "keypoints": [关键点...],
         "counts": {标签: 实例个数},
         "shape_counts": {"rectangle": n, "point": n, "polygon": n},
         "text_shape_count": box 类形状中 description 非空的个数}，
        labels/keypoints 按字典序排序，counts 键为合并大小写后的标签拼写，
        shape_counts 为 shape 分组出现次数（仅含出现过的分组）。
    """
    # 合并键（小写）-> 首次出现的原拼写
    first_spelling: Dict[str, str] = {}
    # 合并键（小写）-> 实例个数
    counts: Dict[str, int] = {}
    # 合并键（小写）-> 是否为关键点（point 形状）
    is_keypoint: Dict[str, bool] = {}
    # shape 分组（rectangle/point/polygon）-> 出现次数
    shape_counts: Dict[str, int] = {}
    # box 类形状中 description 非空的个数（OCR 推断文本证据）
    text_shape_count = 0
    # 物化为列表以获取总数（json_paths 可能是生成器）
    paths = list(json_paths)
    total = len(paths)
    done = 0
    for path in paths:
        # 中断检查：外部请求停止（如扫描任务被重启）时提前结束
        if should_stop is not None and should_stop():
            break
        try:
            doc = load_document(path)
        except Exception:
            doc = None
        if doc is not None:
            for shape in document_shapes(doc):
                # 标签强制转字符串：兼容第三方工具写出的数字标签，
                # 避免与字符串混合排序时抛 TypeError
                label = str(shape.get("label", "") or "")
                if not label:
                    continue
                # 不区分大小写合并：以小写为键计数，拼写取首次出现
                key = label.lower()
                counts[key] = counts.get(key, 0) + 1
                if key not in first_spelling:
                    first_spelling[key] = label
                if shape.get("shape_type") == SHAPE_POINT:
                    is_keypoint[key] = True
                # shape 分组计数（与分析器一致：小写归一后映射，未识别类型跳过）
                group = SHAPE_GROUPS.get(str(shape.get("shape_type", "")).lower())
                if group:
                    shape_counts[group] = shape_counts.get(group, 0) + 1
                    # OCR 文本证据（与分析器口径一致：box 类 + 非空 description）
                    if (
                        group in ("rectangle", "polygon")
                        and str(shape.get("description", "") or "").strip()
                    ):
                        text_shape_count += 1
        done += 1
        # 进度上报（每 500 个文件一次，避免高频回调开销）
        if on_progress is not None and done % 500 == 0:
            on_progress(done, total)
    # 以首次出现的拼写作为输出键（labels/keypoints/counts 三者一致）
    labels = sorted(first_spelling.values())
    keypoints = sorted(first_spelling[k] for k in is_keypoint)
    merged_counts = {first_spelling[k]: n for k, n in counts.items()}
    return {
        "labels": labels,
        "keypoints": keypoints,
        "counts": merged_counts,
        "shape_counts": shape_counts,
        "text_shape_count": text_shape_count,
    }