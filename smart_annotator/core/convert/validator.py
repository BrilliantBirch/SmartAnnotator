# -*- coding: utf-8 -*-
"""
格式校验模块 - 转换前的输入文件格式预检

在 Converter 执行前对输入标注文件做逐文件格式预检，剔除非法文件并
汇总无效原因，避免转换中途因脏数据静默丢行或整批失败：
- validate_labelme_json: 单个 LabelMe JSON 校验（必需字段 / shapes 结构 /
  任务 shape_type 匹配 / 图像尺寸）
- validate_yolo_txt: 单个 YOLO TXT 校验（按任务模式的列数与数值范围）
- validate_annotation_files: 批量校验入口，按源格式分派到单文件校验，
  支持进度回调与提前停止

纯标准库实现（json/os），无 Qt 与第三方依赖（core 层约定）。

作者: BaiBinnan
创建日期: 2026-09-04
更新: 2026-09-10 批量校验入口新增 Format.PPOCR 源直通分支（PPOCR det 标注
      为行级自由格式且 det_gt/rec_gt/dict 共存目录，文件级 YOLO 行校验
      不适用；行级容错由转换器内部逐行处理），支撑 PPOCR→LabelMe 导入
"""

import json
import os

from smart_annotator.config import Format, MODE


# LabelMe JSON 必需顶层字段
_LABELME_REQUIRED_FIELDS = (
    "version",
    "shapes",
    "imagePath",
    "imageHeight",
    "imageWidth",
)

# POSE 任务允许的 shape_type（矩形框 + 单点/多点关键点）
_POSE_ALLOWED_SHAPE_TYPES = ("rectangle", "point", "points")


def _is_positive_number(value) -> bool:
    """判断值是否为正数（int/float，排除 bool）。

    Args:
        value: 待判断的值。

    Returns:
        是否为正数。
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
    )


def _check_yolo_columns(task_type, kpt_count: int, n_cols: int) -> tuple[bool, str]:
    """校验 YOLO 单行 split 后的列数是否符合任务模式要求。

    Args:
        task_type: 任务模式（MODE 枚举）。
        kpt_count: 关键点数量（POSE 任务用，0 表示未提供）。
        n_cols: 实际列数。

    Returns:
        (是否合法, 期望列数描述)。期望描述用于拼接错误信息（如 "5"、"5+3n"）。
    """
    if task_type == MODE.DETECT:
        # 检测: classid cx cy w h 固定 5 列
        return n_cols == 5, "5"
    if task_type == MODE.POSE:
        if kpt_count > 0:
            # 姿态: 5 基础列 + 每个关键点 3 列（x y visible）
            expected = 5 + 3 * kpt_count
            return n_cols == expected, str(expected)
        # 未提供关键点数量时仅校验结构: >=5 且关键点部分为 3 的倍数
        return n_cols >= 5 and (n_cols - 5) % 3 == 0, "5+3n"
    if task_type == MODE.SEGMENT:
        # 分割: classid + n 对坐标（n>=3），列数为奇数且 >=7
        return n_cols >= 7 and n_cols % 2 == 1, "奇数且>=7"
    # 其余任务（OCR 已在入口直接通过）不做列数校验
    return True, ""


def _check_yolo_values(line_no: int, parts: list, task_type) -> tuple[bool, str]:
    """校验 YOLO 单行数值（classid 非负整数，其余列 float 且范围合法）。

    POSE 行第 6 列起每 3 列为一组关键点（x y visible），其中每组第三列
    visible 合法范围为 0-2，坐标列仍须落在 [0,1]。

    Args:
        line_no: 行号（1 起）。
        parts: split 后的列列表。
        task_type: 任务模式（MODE 枚举）。

    Returns:
        (是否合法, 错误信息)；合法时错误信息为空串。
    """
    # 第 1 列: classid 须为非负整数
    try:
        class_id = int(parts[0])
    except ValueError:
        return False, f"第{line_no}行数值非法: 第1列 '{parts[0]}' 不是整数"
    if class_id < 0:
        return False, f"第{line_no}行数值非法: 第1列 classid {class_id} 为负数"

    # 其余列: 可解析为 float 且在合法范围内
    for j in range(1, len(parts)):
        col_no = j + 1
        try:
            value = float(parts[j])
        except ValueError:
            return (
                False,
                f"第{line_no}行数值非法: 第{col_no}列 '{parts[j]}' 不是数值",
            )
        # POSE 关键点 visible 列（第 6 列起每组第 3 列）范围 [0,2]，其余列 [0,1]
        # 链式比较可同时拦截 NaN（NaN 参与比较恒为 False）
        is_visible = task_type == MODE.POSE and j >= 5 and (j - 5) % 3 == 2
        upper = 2 if is_visible else 1
        if not (0 <= value <= upper):
            return (
                False,
                f"第{line_no}行数值非法: 第{col_no}列 {parts[j]} 超出 [0,{upper}] 范围",
            )
    return True, ""


def validate_labelme_json(path: str, task_type, kpt_count: int = 0) -> tuple[bool, str]:
    """校验单个 LabelMe JSON 标注文件格式。

    校验项（按序执行）：
        1. JSON 可解析且顶层为对象；
        2. 必需顶层字段 version/shapes/imagePath/imageHeight/imageWidth；
        3. shapes 为列表，且每个 shape 的 label/points/shape_type 合法；
        4. shape_type 与任务模式匹配（DETECT→rectangle、SEGMENT→polygon、
           POSE→rectangle/point/points；OCR 接口预留直接通过）；
        5. imageHeight/imageWidth 为正数（OCR 在第 4 步已提前通过）。

    Args:
        path: JSON 文件路径。
        task_type: 任务模式（MODE 枚举）。
        kpt_count: 关键点数量（保留参数；POSE 不强制关键点数量校验，
            关键点可有可无，转换器自行处理 0 0 0 填充）。

    Returns:
        (是否合法, 错误信息)；合法时错误信息为空串。
    """
    # ===== 阶段 1: 读取并解析 JSON =====
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, f"JSON 解析失败: {e}"

    if not isinstance(data, dict):
        return False, "JSON 顶层结构非法: 期望对象"

    # ===== 阶段 2: 必需顶层字段 =====
    for field_name in _LABELME_REQUIRED_FIELDS:
        if field_name not in data:
            return False, f"缺失必需字段: {field_name}"

    # ===== 阶段 3: shapes 结构（每个 shape 的必需键） =====
    shapes = data["shapes"]
    if not isinstance(shapes, list):
        return False, "shapes 字段非法: 期望列表"
    for i, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            return False, f"第{i}个 shape 非法: 期望对象"
        label = shape.get("label")
        if not isinstance(label, str) or not label:
            return False, f"第{i}个 shape 缺失/非法 label"
        points = shape.get("points")
        if not isinstance(points, list) or not points:
            return False, f"第{i}个 shape 缺失/非法 points"
        shape_type = shape.get("shape_type")
        if not isinstance(shape_type, str) or not shape_type:
            return False, f"第{i}个 shape 缺失/非法 shape_type"

    # ===== 阶段 4: 任务匹配（shape_type 与任务模式） =====
    if task_type == MODE.OCR:
        # OCR 校验接口预留，直接通过
        return True, ""
    for shape in shapes:
        shape_type = shape["shape_type"]
        if task_type == MODE.DETECT and shape_type != "rectangle":
            return False, f"DETECT 任务要求 rectangle，发现 {shape_type}"
        if task_type == MODE.SEGMENT and shape_type != "polygon":
            return False, f"SEGMENT 任务要求 polygon，发现 {shape_type}"
        if task_type == MODE.POSE and shape_type not in _POSE_ALLOWED_SHAPE_TYPES:
            return (
                False,
                f"POSE 任务要求 rectangle/point/points，发现 {shape_type}",
            )

    # ===== 阶段 5: 图像尺寸须为正数 =====
    if not _is_positive_number(data["imageHeight"]):
        return False, f"imageHeight 须为正数: {data['imageHeight']}"
    if not _is_positive_number(data["imageWidth"]):
        return False, f"imageWidth 须为正数: {data['imageWidth']}"

    # 全部校验通过
    return True, ""


def validate_yolo_txt(path: str, task_type, kpt_count: int = 0) -> tuple[bool, str]:
    """校验单个 YOLO TXT 标注文件格式。

    逐行校验（跳过空行；全部为空行的文件视为合法空标注，转换器会
    产出空 shapes）：
        1. 列数按任务模式校验（DETECT 固定 5 列；POSE 为 5+3*kpt_count
           列，kpt_count=0 时仅要求 >=5 且 (列数-5)%3==0；SEGMENT 为
           奇数列且 >=7；OCR 接口预留直接通过）；
        2. 第 1 列 classid 须为非负整数，其余列可解析为 float 且在
           [0,1] 范围内（POSE 关键点 visible 列放宽到 [0,2]）。

    Args:
        path: TXT 文件路径。
        task_type: 任务模式（MODE 枚举）。
        kpt_count: 关键点数量（POSE 任务用，默认 0）。

    Returns:
        (是否合法, 错误信息)；合法时错误信息为空串。
    """
    # OCR 校验接口预留，直接通过
    if task_type == MODE.OCR:
        return True, ""

    # ===== 逐行读取（读取失败按无效文件处理） =====
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        return False, f"文件读取失败: {e}"

    # ===== 逐行校验列数与数值 =====
    for line_no, raw_line in enumerate(lines, start=1):
        parts = raw_line.strip().split()
        if not parts:
            continue  # 跳过空行
        # 列数校验
        ok, expected = _check_yolo_columns(task_type, kpt_count, len(parts))
        if not ok:
            return (
                False,
                f"第{line_no}行列数错误: 期望{expected}列, 实际{len(parts)}列",
            )
        # 数值校验
        ok, msg = _check_yolo_values(line_no, parts, task_type)
        if not ok:
            return False, msg

    # 全部为空行也视为合法（空标注）
    return True, ""


def validate_annotation_files(
    files: list, source_format, task_type, kpt_count: int = 0, progress_cb=None
) -> tuple[list, list]:
    """批量校验输入标注文件，返回有效文件列表与无效原因报告。

    按源格式分派到 validate_labelme_json / validate_yolo_txt 逐文件校验。

    Args:
        files: 待校验文件路径列表。
        source_format: 源格式（Format.LABELME / Format.YOLO）。
        task_type: 任务模式（MODE 枚举）。
        kpt_count: 关键点数量（POSE 任务用，默认 0）。
        progress_cb: 进度回调，签名 callback(desc, ratio) -> bool（desc 为
            步骤描述，ratio 为 0-1 校验进度，与 BaseWorker.run_callback
            约定一致）；每校验一个文件前调用一次，返回 False 时提前停止
            并返回已校验结果。默认 None 不回调。

    Returns:
        (valid_files, invalid_reports): 有效文件路径列表；无效报告列表，
        每条格式为 "文件名: 原因"。
    """
    valid_files = []
    invalid_reports = []
    total = len(files)

    # ===== 逐文件校验 =====
    for idx, file_path in enumerate(files):
        # 进度回调（返回 False 提前停止，返回已校验结果）
        if progress_cb is not None:
            ratio = (idx + 1) / total if total > 0 else 1.0
            if not progress_cb("格式校验中", ratio):
                break
        # 按源格式分派到单文件校验
        if source_format == Format.PPOCR:
            # OCR 校验接口预留：PPOCR det 标注为行级自由格式，且 det_gt/
            # rec_gt/dict 共存于同一目录，文件级 YOLO 行校验不适用；
            # 行级容错（分隔符缺失/JSON 解析失败）由转换器内部逐行处理
            valid_files.append(file_path)
        elif source_format == Format.LABELME:
            ok, msg = validate_labelme_json(file_path, task_type, kpt_count)
            # 汇总结果（无效报告以文件名定位）
            if ok:
                valid_files.append(file_path)
            else:
                invalid_reports.append(f"{os.path.basename(str(file_path))}: {msg}")
        else:
            ok, msg = validate_yolo_txt(file_path, task_type, kpt_count)
            # 汇总结果（无效报告以文件名定位）
            if ok:
                valid_files.append(file_path)
            else:
                invalid_reports.append(f"{os.path.basename(str(file_path))}: {msg}")

    return valid_files, invalid_reports
