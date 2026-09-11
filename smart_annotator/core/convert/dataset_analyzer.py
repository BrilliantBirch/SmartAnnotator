# -*- coding: utf-8 -*-
"""
数据集一键分析模块

扫描标注目录，实现三项分析：
    1. 标签提取：从 LabelMe JSON 标注的 shapes 中提取所有唯一标签
    2. 任务类型推断：按 shape 类型特征与文本证据推断 DETECT/POSE/
       SEGMENT/OCR
    3. 转换方向检测：按标注文件后缀推断源格式（JSON→任务数据集 或
       任务数据集→JSON；任务数据集按任务类型分发——YOLO TXT 或
       PaddleOCR det/rec 标注）

纯逻辑实现，无 Qt 依赖（供 AnalyzeWorker 在后台线程调用）。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-02 重写 TXT 任务类型推断：数据集级两遍扫描消解 POSE/SEGMENT
      字段数歧义（原逻辑将 5/8 顶点多边形误判为 POSE）；新增关键点数推断
更新: 2026-09-02 LabelMe 标签提取按 shape 类型分类：point 类型标签归入
      kpt_labels（关键点类别集合），不再混入普通类别列表
更新: 2026-09-10 适配 OCR 数据集推断：LabelMe 解析新增 text_shape_count
      统计（box 类形状中 description 非空的个数），推断规则新增 OCR 分支
      （无关键点、box 类形状过半携带非空文本 → MODE.OCR，优先级在 POSE
      之后、SEGMENT 之前），修复 OCR 文本框被误判为实例分割
更新: 2026-09-11 适配 PaddleOCR 导出结构（images/ 子目录 + 根目录 det 标注
      txt）的一键分析：新增 _analyze_ppocr_dets 逐行解析 det 标注（四点框
      归 polygon 组、transcription 非空计入文本证据、标签固定 text），
      按 PPOCR_STRUCTURE_MARK 分流，避免 det 行被当作 YOLO 格式误解析；
      修复 OCR 数据集导入方向"未检测到任何标注文件"
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from ...config import MODE, Format
from ...utils import LOGGER, PPOCR_STRUCTURE_MARK, scan_dataset_files


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
        labels: 唯一标签列表（按首次出现顺序，保持数据集原始顺序）；
            仅含非关键点标签（rectangle/polygon 等），point 标签归入 kpt_labels。
        label_counts: {标签: shape 出现次数}。
        kpt_labels: 关键点标签列表（shape 类型为 point/points 的标签，
            即 POSE 任务的"关键点类别集合"，按首次出现顺序）。
        shape_counts: {shape 分组: 出现次数}（rectangle/point/polygon）。
        text_shape_count: box 类形状（rectangle/polygon）中 description
            非空的个数（OCR 推断证据：OCR 文本框必然携带识别文本，检测/
            分割标注的 description 通常为空）。
        task_type: 推断的任务类型。
        source_format: 检测到的标注格式（LabelMe=JSON 输入 / YOLO=TXT 输入）；
            无标注文件时为 None。
        json_count / txt_count / image_count: 各类文件数量。
        error_files: 解析失败的标注文件路径列表。
        max_class_id: TXT 数据集检测到的最大类别索引（-1 表示未检测到）。
        kpt_count: POSE 数据集推断的关键点数（0 表示未推断到）。
        structure_desc: 数据集目录层级描述（label/image/dataset 层级或平铺）。
        anno_dir / image_dir: 解析出的标注/图片目录（层级识别结果）。
        orphan_annotations: 孤立标注文件路径列表（无对应同名图片的标注）。
    """

    labels: list = field(default_factory=list)
    label_counts: dict = field(default_factory=dict)
    kpt_labels: list = field(default_factory=list)
    shape_counts: dict = field(default_factory=dict)
    text_shape_count: int = 0
    task_type: MODE = MODE.DETECT
    source_format: Format = None
    json_count: int = 0
    txt_count: int = 0
    image_count: int = 0
    error_files: list = field(default_factory=list)
    max_class_id: int = -1
    kpt_count: int = 0
    structure_desc: str = ""
    anno_dir: str = ""
    image_dir: str = ""
    orphan_annotations: list = field(default_factory=list)


def _infer_task_from_shapes(shape_counts: dict, text_shape_count: int = 0) -> MODE:
    """按 shape 分组特征与文本证据推断任务类型（多类型共存时的优先级判断）。

    优先级机制（高 → 低）：
        point > OCR > polygon > rectangle
    依据：姿态数据集必含 box+point（box 不构成否定证据），point 最高；
    OCR 数据集全部为 box 类四点框且过半携带非空文本内容（PPOCRLabel/
    本编辑器 OCR 标注的强特征——检测/分割标注的 description 通常为空），
    判 OCR；分割数据集常含 box+polygon（description 为空，不满足 OCR
    文本证据）判 SEGMENT；仅 rectangle 时才判定为检测任务。

    Args:
        shape_counts: {shape 分组: 出现次数}。
        text_shape_count: box 类形状中 description 非空的个数（OCR 文本
            证据，LabelMe 数据集才有；默认 0 不触发 OCR 分支）。

    Returns:
        推断的任务类型（无任何 shape 时默认 DETECT）。
    """
    if shape_counts.get("point", 0) > 0:
        return MODE.POSE
    box_count = shape_counts.get("rectangle", 0) + shape_counts.get("polygon", 0)
    # OCR 分支：存在 box 类形状且过半携带非空文本内容（阈值取半数，
    # 兼容少量空文本框；纯检测/分割数据集 description 罕有过半非空）
    if box_count > 0 and text_shape_count * 2 >= box_count:
        return MODE.OCR
    if shape_counts.get("polygon", 0) > 0:
        return MODE.SEGMENT
    return MODE.DETECT


def _analyze_labelme_jsons(json_files: list, result: DatasetAnalysis, progress_cb) -> None:
    """解析 LabelMe JSON 标注：提取标签、统计 shape 类型。

    类别分类规则：shape 类型为 point/points 的标签归入关键点类别集合
    （kpt_labels，供 POSE 任务填充关键点列表），其余标签归入普通类别
    （labels）。解析失败的文件记入 error_files，不中断整体分析。

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
                group = _SHAPE_GROUPS.get(str(shape.get("shape_type", "")).lower())
                # 大小写不敏感去重（与转换端 JsonBaseConverter 行为一致），保留首次拼写
                lower = label.lower()
                if lower not in seen_lower:
                    seen_lower[lower] = label
                    if group == "point":
                        # point 类型 → 关键点类别集合（不进入普通类别列表）
                        result.kpt_labels.append(label)
                    else:
                        result.labels.append(label)
                # 出现次数统计（关键点标签同样计数，便于排查）
                result.label_counts[seen_lower[lower]] = (
                    result.label_counts.get(seen_lower[lower], 0) + 1
                )
                if group:
                    result.shape_counts[group] = result.shape_counts.get(group, 0) + 1
                    # OCR 文本证据：box 类形状带非空 description（识别文本）
                    if (
                        group in ("rectangle", "polygon")
                        and str(shape.get("description", "") or "").strip()
                    ):
                        result.text_shape_count += 1
        except (ValueError, KeyError, OSError, UnicodeDecodeError) as ex:
            result.error_files.append(str(file_path))
            LOGGER.warning(f"解析标注文件失败（已跳过）: {file_path}: {ex}")


def _analyze_yolo_txts(txt_files: list, result: DatasetAnalysis, progress_cb) -> None:
    """解析 YOLO TXT 标注：按行字段数分布推断任务类型、最大类别索引与关键点数。

    各任务标准行格式（字段数 n 含类别 id）：
        - DETECT:  classid x y w h → n = 5
        - POSE:    classid x y w h (x y c) × k → n = 5 + 3k（k≥1）
        - SEGMENT: classid (x y) × N → n = 1 + 2N（N≥3，恒为奇数）

    歧义消解（数据集级两遍扫描）：
        - n 为偶数且 (n-5)%3==0 → 仅可能是 POSE（SEGMENT 恒为奇数）
        - n 为奇数且 (n-5)%3!=0（n≥7）→ 仅可能是 SEGMENT
        - n 为奇数且 (n-5)%3==0（n=11,17,...）→ POSE（偶数关键点数）与
          SEGMENT（顶点数 ≡ 2 mod 3 的多边形）格式歧义，按顺序消解：
            1. 数据集中存在 POSE 独有字段数且无 SEGMENT 独有字段数 → 判 POSE
            2. 数值特征：关键点可见性位（每 3 字段一组的第 3 个值）全部为
               0/1/2 → POSE 强特征（SEGMENT 多边形顶点坐标不可能恰好全为
               0/1/2），该字段数全部行满足时判 POSE
            3. 其余（含多字段数共存：SEGMENT 顶点数可变而 POSE 关键点数固定）
               → 默认判 SEGMENT（N 顶点多边形远比偶数关键点姿态常见）

    Args:
        txt_files: TXT 标注文件路径列表。
        result: 分析结果对象（就地更新）。
        progress_cb: 进度回调 callback(desc, progress)。
    """
    # ===== 第一遍：统计各字段数行数分布与最大类别索引 =====
    field_stats = {}  # {字段数 n: 行数}
    pose_like = {}  # {歧义字段数 n: 可见性位全为 0/1/2 的行数}
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
                    n = len(parts)
                    field_stats[n] = field_stats.get(n, 0) + 1
                    # 歧义字段数行：检测 POSE 可见性特征（每 3 字段一组的
                    # 第 3 个值全为 0/1/2），values[6::3] 即各关键点的可见性位
                    if n >= 11 and n % 2 == 1 and (n - 5) % 3 == 0:
                        if all(v in (0.0, 1.0, 2.0) for v in values[6::3]):
                            pose_like[n] = pose_like.get(n, 0) + 1
        except (OSError, UnicodeDecodeError) as ex:
            result.error_files.append(str(file_path))
            LOGGER.warning(f"解析标注文件失败（已跳过）: {file_path}: {ex}")

    if not field_stats:
        return  # 无有效标注行

    # ===== 第二遍：数据集级歧义消解，写入 shape 分组统计 =====
    # POSE 独有：偶数字段数且满足 5+3k；SEGMENT 独有：奇数且不满足 5+3k
    has_pose_only = any(
        n > 5 and n % 2 == 0 and (n - 5) % 3 == 0 for n in field_stats
    )
    has_seg_only = any(
        n >= 7 and n % 2 == 1 and (n - 5) % 3 != 0 for n in field_stats
    )
    # 歧义字段数判 POSE 的条件：有 POSE 独有证据，或可见性特征全部命中
    pose_evidence_ns = {
        n for n, cnt in pose_like.items() if field_stats.get(n, 0) == cnt
    }
    ambiguous_as_pose = (has_pose_only and not has_seg_only) or bool(pose_evidence_ns)
    pose_kpts = set()  # 各 point 行反推的关键点数（全部一致时才有效）
    for n, cnt in field_stats.items():
        if n == 5:
            # 检测格式：classid x y w h
            group = "rectangle"
        elif n % 2 == 0 and (n - 5) % 3 == 0:
            # 偶数字段数 → 仅可能是姿态（检测框 + 奇数个关键点）
            group = "point"
            pose_kpts.add((n - 5) // 3)
        elif (n - 5) % 3 == 0:
            # 奇数歧义字段数：姿态（偶数关键点）或分割（多边形顶点）
            # 判 POSE 条件：数据集整体有 POSE 独有证据，或该字段数可见性
            # 特征全部命中（per-n 独立判定，避免误伤无证据的歧义字段数）
            if ambiguous_as_pose or n in pose_evidence_ns:
                group = "point"
                pose_kpts.add((n - 5) // 3)
            else:
                group = "polygon"
        elif n >= 7:
            # 奇数且非 5+3k → 仅可能是分割多边形
            group = "polygon"
        else:
            # 不符合任何任务标准格式（如 6 字段），跳过并告警
            LOGGER.warning(
                f"[分析] 字段数 {n} 不符合任何 YOLO 标准格式，已跳过 {cnt} 行"
            )
            continue
        result.shape_counts[group] = result.shape_counts.get(group, 0) + cnt

    # ===== 歧义字段数消解结果说明（便于用户核查误判）=====
    ambiguous_ns = [
        n for n in field_stats if n >= 7 and n % 2 == 1 and (n - 5) % 3 == 0
    ]
    if ambiguous_ns:
        pose_hit = [n for n in ambiguous_ns if n in pose_evidence_ns]
        if pose_hit:
            LOGGER.info(
                f"[分析] 字段数 {pose_hit} 兼容 POSE/SEGMENT 格式，"
                f"已依据关键点可见性特征（0/1/2）判定为 POSE"
            )
            seg_left = [n for n in ambiguous_ns if n not in pose_evidence_ns]
            if seg_left:
                LOGGER.info(
                    f"[分析] 字段数 {seg_left} 兼容 POSE/SEGMENT 格式且无可见性"
                    f"特征，已判定为 SEGMENT"
                )
        elif ambiguous_as_pose:
            LOGGER.info(
                f"[分析] 字段数 {ambiguous_ns} 兼容 POSE/SEGMENT 格式，"
                f"已依据数据集整体特征判定为 POSE"
            )
        else:
            LOGGER.info(
                f"[分析] 字段数 {ambiguous_ns} 兼容 POSE/SEGMENT 格式，"
                f"已默认判定为 SEGMENT；若实际为姿态数据请手动切换任务类型"
            )

    # ===== POSE 关键点数：所有 point 行关键点数一致时才写入结果 =====
    if len(pose_kpts) == 1:
        result.kpt_count = pose_kpts.pop()
    elif len(pose_kpts) > 1:
        LOGGER.warning(
            f"[分析] 检测到多种关键点数 {sorted(pose_kpts)}，数据集格式不一致，"
            f"未推断关键点数"
        )


def _analyze_ppocr_dets(txt_files: list, result: DatasetAnalysis, progress_cb) -> None:
    """解析 PaddleOCR det 标注 txt：统计形状数与文本证据，确证 OCR 任务。

    det 标注行格式：`{图片相对路径}\t[{"transcription": 文本, "points":
    [[x,y]...], "difficult": bool}, ...]`。四点框归入 polygon 分组（与
    本编辑器 OCR 标注的导出口径一致）；transcription 非空计入
    text_shape_count（OCR 推断证据）；标签固定为 "text"（导入生成的
    LabelMe JSON 即该标签）。rec_gt（纯文本行）/dict（字符表）等非 det
    格式行经 JSON 解析失败自然跳过。

    Args:
        txt_files: det 标注 txt 文件路径列表。
        result: 分析结果对象（就地更新）。
        progress_cb: 进度回调 callback(desc, progress)。
    """
    total = len(txt_files)
    text_label_added = False
    for idx, file_path in enumerate(txt_files):
        progress_cb("解析 PaddleOCR det 标注", (idx + 1) / total)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\r\n")
                    if not line or "\t" not in line:
                        continue
                    _image_path, arr = line.split("\t", 1)
                    try:
                        items = json.loads(arr)
                    except (ValueError, TypeError):
                        continue  # rec_gt 纯文本行/dict 字符行等非 det 格式
                    if not isinstance(items, list):
                        continue
                    if not text_label_added:
                        # OCR 导入生成的 LabelMe JSON 标签固定为 text
                        result.labels.append("text")
                        result.label_counts["text"] = 0
                        text_label_added = True
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        points = item.get("points")
                        if not isinstance(points, list) or not points:
                            continue
                        result.shape_counts["polygon"] = (
                            result.shape_counts.get("polygon", 0) + 1
                        )
                        result.label_counts["text"] += 1
                        if str(item.get("transcription", "") or "").strip():
                            result.text_shape_count += 1
        except (OSError, UnicodeDecodeError) as ex:
            result.error_files.append(str(file_path))
            LOGGER.warning(f"解析标注文件失败（已跳过）: {file_path}: {ex}")


def analyze_dataset(input_dir, progress_cb=None) -> DatasetAnalysis:
    """一键分析标注数据集：提取标签 + 推断任务类型 + 检测转换方向。

    目录层级识别（YOLO 数据集 dataset-image-label 结构）：
        - label/image 层级输入 → 自动在兄弟目录查找对应图片/标注
        - dataset 层级输入 → 遍历 images/labels 子目录
        - 均不匹配 → 平铺结构（输入目录本身）

    转换方向检测规则：
        - 检测到 JSON 标注 → 源格式 LabelMe（JSON→任务数据集方向）
        - 仅检测到 TXT 标注 → 源格式 YOLO（任务数据集→JSON方向）
        - 两者共存 → 优先 JSON（LabelMe 标签信息更完整），并记录告警

    孤立标注检测：无对应同名图片的标注文件逐个记入日志（详细信息），
    并汇总至结果 orphan_annotations 字段。

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

    # ===== 步骤 1: 目录层级识别 + 扫描文件（json / txt / 图片）=====
    progress_cb("扫描目录文件", 0.0)
    scan = scan_dataset_files(str(dir_path))
    json_files = scan["json_files"]
    txt_files = scan["txt_files"]
    image_files = scan["image_files"]
    result.json_count = len(json_files)
    result.txt_count = len(txt_files)
    result.image_count = len(image_files)
    result.structure_desc = scan["structure"]
    result.anno_dir = str(scan["anno_dir"]) if scan["anno_dir"] else ""
    result.image_dir = str(scan["image_dir"]) if scan["image_dir"] else ""
    LOGGER.info(
        f"[分析] 目录层级识别: {result.structure_desc}，"
        f"标注目录: {result.anno_dir or '无'}，图片目录: {result.image_dir or '无'}"
    )

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

    # ===== 步骤 3: 孤立标注检测（仅 LabelMe JSON 方向）=====
    # LabelMe 惯例 JSON 与图片同名配对，无配对图片即无法转换；YOLO/PPOCR
    # 方向的 txt 文件与图片非同名对应关系（det_gt 集中索引），不适用该检测
    if result.source_format == Format.LABELME:
        image_stems = {Path(f).stem for f in image_files}
        for f in json_files:
            if Path(f).stem not in image_stems:
                result.orphan_annotations.append(f)
    if result.orphan_annotations:
        LOGGER.warning(
            f"[分析] 检测到 {len(result.orphan_annotations)} 个孤立标注文件"
            f"（缺失对应图片，将无法转换），详细信息："
        )
        for f in result.orphan_annotations:
            LOGGER.warning(f"[分析] 孤立标注: {f}")

    # ===== 步骤 4: 解析标注内容 =====
    if result.source_format == Format.LABELME:
        _analyze_labelme_jsons(json_files, result, progress_cb)
    elif PPOCR_STRUCTURE_MARK in result.structure_desc:
        # PaddleOCR 导出结构（images/ 子目录 + 根目录 det 标注）：det 行
        # 为"路径\tJSON数组"格式，不符合任何 YOLO 标准行格式，须走专用解析
        _analyze_ppocr_dets(txt_files, result, progress_cb)
    else:
        _analyze_yolo_txts(txt_files, result, progress_cb)

    # ===== 步骤 5: 推断任务类型（box 类形状文本证据参与 OCR 分支判定）=====
    result.task_type = _infer_task_from_shapes(
        result.shape_counts, result.text_shape_count
    )
    if result.task_type == MODE.OCR:
        LOGGER.info(
            f"[分析] box 类形状 {result.shape_counts.get('rectangle', 0) + result.shape_counts.get('polygon', 0)} 个中 "
            f"{result.text_shape_count} 个携带非空文本内容，判定为 OCR 数据集"
        )
    progress_cb("分析完成", 1.0)

    return result
