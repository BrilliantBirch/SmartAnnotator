# -*- coding: utf-8 -*-
"""
文件操作工具 — 扫描目录下的图片/视频/标注文件

移植自旧版 utils/files.py，逻辑原样保留（纯标准库，无 Qt 依赖）。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-03 新增 getModelTaskType（按模型元数据/输出结构推导任务类型）
更新: 2026-09-08 冗余清理：删除全库零引用的死函数 checkAnnotationFiles
      （目录图片/标注对应性检查，无任何调用方；其内部使用的
      resolve_dataset_dirs 链为 scan_dataset_files 活代码，保留）
更新: 2026-09-10 _task_from_metadata 的 task 键白名单加入 OCR（大小写容错），
      支持 PaddleOCR det/rec 模型（无 names 元数据）按元数据识别任务类型
更新: 2026-09-10 重构任务推导链为"可信才锁定"：新增 OCR IO 结构特征识别
      （PP-OCR static 转换的 metadata "model" 键 / rec 输入固定高 48 /
      det 单通道概率图输出），names 类别元数据存在才默认 DETECT，
      均无法判定时返回 None 解锁手动选择（修复 OCR 模型被误锁 DETECT）；
      新增 getOcrModelRole 判定 OCR 模型角色（det/rec），供 UI 字段引导
更新: 2026-09-11 resolve_dataset_dirs 适配 PaddleOCR 导出结构：dataset
      层级仅有 images/ 子目录而无 labels/、且根目录存在 det 标注 txt 时
      （PPOCR2JsonConverter 导出产物），标注目录回退输入根目录（结构
      描述带 PPOCR_STRUCTURE_MARK 标记供分析器识别），修复 OCR 数据集
      一键分析"未检测到任何标注文件"
"""

import glob
import os
import shutil
from pathlib import Path


def getJsonFilesInDir(dirPath) -> list:
    """获取目录下所有 JSON 文件。"""
    if not os.path.isdir(dirPath):
        return []
    return glob.glob(os.path.join(dirPath, "*.json"))


def getTxtFilesInDir(dirPath) -> list:
    """获取目录下所有 txt 文件。"""
    if not os.path.isdir(dirPath):
        return []
    return glob.glob(os.path.join(dirPath, "*.txt"))


def getImageFilesInDir(dirPath) -> list:
    """获取目录下所有图片文件（jpg/jpeg/png/bmp）。"""
    if not os.path.isdir(dirPath):
        return []
    extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp"]
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(dirPath, ext)))
    return files


def getVideoFilesInDir(dirPath) -> list:
    """获取目录下所有视频文件（mp4/avi/mov）。"""
    if not os.path.isdir(dirPath):
        return []
    extensions = ["*.mp4", "*.avi", "*.mov"]
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(dirPath, ext)))
    return files


# ===== YOLO 数据集目录命名兼容（复数/单数均支持）=====
IMAGE_DIR_NAMES = ("images", "image")
LABEL_DIR_NAMES = ("labels", "label")
# PaddleOCR 导出结构的层级识别标记（拼入结构描述文本，供数据集分析器
# 识别 OCR 数据集并走 det 标注解析分支，避免被当作 YOLO TXT 逐行解析）
PPOCR_STRUCTURE_MARK = "PaddleOCR 结构"


def _first_existing_sibling(base: Path, names: tuple):
    """在 base 的兄弟目录中查找第一个存在的目录名。

    Args:
        base: 参照目录（其父目录下查找）。
        names: 候选目录名列表。

    Returns:
        找到的目录 Path；均不存在返回 None。
    """
    for name in names:
        candidate = base.parent / name
        if candidate.is_dir():
            return candidate
    return None


def _first_existing_subdir(base: Path, names: tuple):
    """在 base 的子目录中查找第一个存在的目录名。

    Args:
        base: 父目录。
        names: 候选子目录名列表。

    Returns:
        找到的目录 Path；均不存在返回 None。
    """
    for name in names:
        candidate = base / name
        if candidate.is_dir():
            return candidate
    return None


def resolve_dataset_dirs(input_dir) -> tuple:
    """识别 YOLO 数据集目录层级，解析标注目录与图片目录。

    支持三种输入层级（目录名大小写不敏感，复数/单数均兼容）：
        1. label 层级: 输入目录名为 labels/label，标注在本目录，
           图片在兄弟 images/image 目录中查找
        2. image 层级: 输入目录名为 images/image，图片在本目录，
           标注在兄弟 labels/label 目录中查找
        3. dataset 层级: 输入目录含 images/image 与 labels/label 子目录，
           分别作为图片与标注目录；若仅有 images/ 子目录且根目录存在
           det 标注 txt（PaddleOCR 导出结构），标注目录回退输入根目录
    以上均不匹配时视为平铺结构（LabelMe 惯例），标注与图片均在输入目录本身。

    Args:
        input_dir: 用户输入目录路径。

    Returns:
        (标注目录或 None, 图片目录或 None, 结构描述文本) 三元组。
    """
    path = Path(input_dir)
    if not path.is_dir():
        return None, None, "目录不存在"

    name = path.name.lower()
    if name in LABEL_DIR_NAMES:
        image_dir = _first_existing_sibling(path, IMAGE_DIR_NAMES)
        struct = f"label 层级（图片目录: {image_dir.name if image_dir else '未找到'}）"
        return path, image_dir, struct
    if name in IMAGE_DIR_NAMES:
        anno_dir = _first_existing_sibling(path, LABEL_DIR_NAMES)
        struct = f"image 层级（标注目录: {anno_dir.name if anno_dir else '未找到'}）"
        return anno_dir, path, struct

    # dataset 层级：查找子目录
    image_dir = _first_existing_subdir(path, IMAGE_DIR_NAMES)
    anno_dir = _first_existing_subdir(path, LABEL_DIR_NAMES)
    if image_dir is not None or anno_dir is not None:
        # PaddleOCR 导出结构兼容（PPOCR2JsonConverter 导出产物）：仅有
        # images/ 子目录而无 labels/，det 标注 txt（det_gt.txt/train.txt
        # 等）位于根目录——此时标注目录回退输入根目录（getTxtFilesInDir
        # 非递归，不会误扫子目录），结构描述带标记供分析器识别 OCR 数据集
        if image_dir is not None and anno_dir is None:
            if getTxtFilesInDir(str(path)):
                return (
                    path,
                    image_dir,
                    f"dataset 层级（images 子目录 + 根目录 det 标注，{PPOCR_STRUCTURE_MARK}）",
                )
        return anno_dir, image_dir, "dataset 层级（images/labels 子目录）"

    # 平铺结构：标注与图片均在输入目录
    return path, path, "平铺结构"


def scan_dataset_files(input_dir) -> dict:
    """按目录层级识别结果扫描标注与图片文件。

    扫描规则：
        - JSON 标注: 始终扫描输入目录本身（LabelMe 平铺惯例）
        - TXT 标注: 扫描解析出的标注目录（label 层级/dataset 层级时为
          labels 子目录，平铺时为输入目录）
        - 图片: 扫描解析出的图片目录（image 层级/dataset 层级时为
          images 目录，平铺时为输入目录）

    Args:
        input_dir: 用户输入目录路径。

    Returns:
        字典 {anno_dir, image_dir, structure, json_files, txt_files, image_files}。
    """
    anno_dir, image_dir, structure = resolve_dataset_dirs(input_dir)
    return {
        "anno_dir": anno_dir,
        "image_dir": image_dir,
        "structure": structure,
        "json_files": getJsonFilesInDir(str(input_dir)),
        "txt_files": getTxtFilesInDir(str(anno_dir)) if anno_dir else [],
        "image_files": getImageFilesInDir(str(image_dir)) if image_dir else [],
    }


def move_files(filelist, splitname, output):
    """移动文件到 split 目录（保留 images/labels 结构）。"""
    for file_name in filelist:
        try:
            img_src = file_name
            lbl_src = os.path.splitext(file_name)[0] + ".txt"
            lbl_src = lbl_src.replace("images", "labels")
            file_basename = os.path.basename(file_name)
            img_dst = os.path.join(output, splitname, "images", file_basename)
            lbl_dst = os.path.join(output, splitname, "labels", os.path.basename(lbl_src))
            shutil.copy(img_src, img_dst)
            shutil.copy(lbl_src, lbl_dst)
        except Exception as ex:
            raise RuntimeError(f"移动文件{file_name}时失败：{str(ex)}")


def _normalize_names(mapping) -> dict:
    """将类别映射统一为 {int: str} 格式。

    Args:
        mapping: 类别映射（onnx metadata 传入 ast.literal_eval 的产物，
            或模型元数据中的字符串字面量 '{"0": "person", ...}'）。

    Returns:
        {class_id: name} 字典；格式非法时返回空字典。
    """
    import ast
    import json

    # 字符串形式：先按 JSON 解开，失败再退回 Python 字面量解析
    if isinstance(mapping, str):
        try:
            mapping = json.loads(mapping)
        except json.JSONDecodeError:
            try:
                mapping = ast.literal_eval(mapping)
            except (ValueError, SyntaxError):
                return {}

    if not isinstance(mapping, dict):
        return {}
    try:
        return {int(k): str(v) for k, v in mapping.items()}
    except (ValueError, TypeError):
        return {}


def getModelClasses(model_path) -> dict:
    """从 ONNX 模型元数据中读取类别映射（不加载推理会话，轻量解析）。

    读取 metadata_props 中的 "names" 字段（YOLO 导出格式，
    形如 "{0: 'person', 1: 'car', ...}" 的字符串字面量）。

    Args:
        model_path: 模型文件路径（.onnx）。

    Returns:
        类别映射 {class_id: name}；无法读取时返回空字典。
    """
    import ast

    path = Path(model_path) if model_path else None
    if path is None or not path.exists():
        return {}

    if path.suffix.lower() != ".onnx":
        return {}

    try:
        import onnx

        # load_external_data=False: 仅解析 proto 结构，不加载外部权重，速度极快
        model = onnx.load(str(path), load_external_data=False)
        for prop in model.metadata_props:
            if prop.key == "names":
                return _normalize_names(ast.literal_eval(prop.value))
    except Exception:
        return {}

    return {}


def _dim_int(shape_dim) -> "int | None":
    """提取 onnx 维度中的固定 int 值。

    Args:
        shape_dim: onnx 张量维度的单个 dim 对象（TensorShapeProto.Dimension）。

    Returns:
        固定 int 维返回其值；动态维（dim_param 字符串）或无效维返回 None。
    """
    try:
        v = int(shape_dim.dim_value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _load_onnx_signature(model_path):
    """轻量解析 ONNX 模型的元数据与输入输出签名（不加载权重）。

    Args:
        model_path: 模型文件路径（.onnx）。

    Returns:
        (metadata 字典, 首输入 dims 列表, 首输出 dims 列表, 全部输出数)；
        解析失败返回 None。dims 元素为固定 int 或 None（动态维）。
    """
    try:
        import onnx

        model = onnx.load(str(model_path), load_external_data=False)
        meta = {prop.key: prop.value for prop in model.metadata_props}
        inputs = model.graph.input
        outputs = model.graph.output
        # 首输入/首输出 dims（空张量时返回空列表）
        in_dims = (
            [_dim_int(d) for d in inputs[0].type.tensor_type.shape.dim]
            if inputs
            else []
        )
        out_dims = (
            [_dim_int(d) for d in outputs[0].type.tensor_type.shape.dim]
            if outputs
            else []
        )
        return meta, in_dims, out_dims, len(outputs)
    except Exception:
        return None


def _ocr_role_from_signature(meta, in_dims, out_dims) -> "str | None":
    """按元数据与 IO 结构特征判定 OCR 模型角色（det 检测 / rec 识别）。

    特征依据（实测 PP-OCRv6 系列模型）：
        - PP-OCR static 转换版 metadata 含 "model" 键（如
          "PP-OCRv6_medium_det"/"PP-OCRv6_medium_rec"），按键名区分；
        - rec 识别模型：输入 4 维 NCHW 且固定高（dim2）== 48
          （CRNN/SVTR 序列识别的特征性高度，YOLO 等检测输入不会为 48）；
        - det 检测模型：单输出 4 维且 dim1==dim2==1（DBNet 单通道概率图）。

    Args:
        meta: 模型元数据键值字典。
        in_dims: 首输入维度列表（int 或 None）。
        out_dims: 首输出维度列表（int 或 None）。

    Returns:
        "det" / "rec"；无法判定返回 None。
    """
    # PP-OCR static 转换版的 model 键（如 "PP-OCRv6_medium_det"）
    model_key = str(meta.get("model", "")).lower()
    if "rec" in model_key:
        return "rec"
    if "det" in model_key:
        return "det"
    # rec：输入 NCHW 且固定高 == 48（序列识别特征高度）
    if len(in_dims) == 4 and in_dims[2] == 48:
        return "rec"
    # det：单输出 N,1,1,H,W 形态（DBNet 概率图）
    if len(out_dims) == 4 and out_dims[1] == 1 and out_dims[2] == 1:
        return "det"
    return None


def getOcrModelRole(model_path):
    """判定 OCR 模型角色（det 检测 / rec 识别），供 UI 字段引导与状态提示。

    与 getModelTaskType 的 OCR 结构特征同源：依据 PP-OCR static 转换的
    metadata "model" 键、rec 输入固定高 48、det 单通道概率图输出判定。
    无任何特征的模型（如 PP-OCRv6 动态版 det）返回 None——此时无法
    区分角色，仅提示用户手动归位。

    Args:
        model_path: 模型文件路径（.onnx）。

    Returns:
        "det"（检测模型）/ "rec"（识别模型）；无法判定返回 None。
    """
    path = Path(model_path) if model_path else None
    if path is None or not path.exists():
        return None
    if path.suffix.lower() != ".onnx":
        return None
    sig = _load_onnx_signature(path)
    if sig is None:
        return None
    meta, in_dims, out_dims, _ = sig
    return _ocr_role_from_signature(meta, in_dims, out_dims)


def getModelTaskType(model_path):
    """从模型元数据与输入输出结构推导任务类型（不加载推理会话，轻量解析）。

    推导原则："可信才锁定"——仅当存在明确证据时返回任务类型，
    否则返回 None 解锁手动选择（避免误锁）。

    推导顺序（命中即返回）：
        1. metadata 中的显式 "task" 键（值为 DETECT/POSE/SEGMENT/OCR，
           大小写不敏感）
        2. metadata 含 "kpt_shape" → POSE（YOLO pose 导出约定）
        3. 图输出张量数量 >= 2 → SEGMENT（分割模型输出 predictions + proto）
        4. OCR 结构特征（PP-OCR static 的 metadata "model" 键 / rec 输入
           固定高 48 / det 单通道概率图输出）→ OCR
        5. metadata 含 "names" 类别表（YOLO 导出约定）→ DETECT
        6. 均无证据（如 PP-OCR 动态版 det：无元数据且 IO 全动态）→ None

    Args:
        model_path: 模型文件路径（.onnx）。

    Returns:
        任务类型名称字符串 "DETECT" / "POSE" / "SEGMENT" / "OCR"；
        无法可信推导返回 None（交由用户手动选择）。
    """
    path = Path(model_path) if model_path else None
    if path is None or not path.exists():
        return None

    if path.suffix.lower() != ".onnx":
        return None

    sig = _load_onnx_signature(path)
    if sig is None:
        return None
    meta, in_dims, out_dims, output_count = sig
    # 1/2. 元数据显式声明优先（task 键 / kpt_shape）
    task = _task_from_metadata(meta)
    if task is not None:
        return task
    # 3. 分割模型多输出（predictions + proto 等）
    if output_count >= 2:
        return "SEGMENT"
    # 4. OCR 结构特征（static 转换键 / rec 高 48 / det 概率图）
    if _ocr_role_from_signature(meta, in_dims, out_dims) is not None:
        return "OCR"
    # 5. YOLO 导出约定：names 类别表存在才默认 DETECT
    if "names" in meta:
        return "DETECT"
    # 6. 无证据：返回 None 解锁手动选择
    return None


def _task_from_metadata(metadata: dict):
    """按元数据字典判定任务类型（task 键优先，其次 kpt_shape）。

    Args:
        metadata: 元数据键值字典。

    Returns:
        任务类型名称字符串；无法判定返回 None。
    """
    if not isinstance(metadata, dict):
        return None
    # 显式 task 键（大小写不敏感，DETECT/POSE/SEGMENT/OCR 均命中）
    task = str(metadata.get("task", "")).strip().upper()
    if task in ("DETECT", "POSE", "SEGMENT", "OCR"):
        return task
    # YOLO pose 导出约定：metadata 含 kpt_shape
    if "kpt_shape" in metadata:
        return "POSE"
    return None
