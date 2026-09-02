# -*- coding: utf-8 -*-
"""
文件操作工具 — 扫描目录下的图片/视频/标注文件

移植自旧版 utils/files.py，逻辑原样保留（纯标准库，无 Qt 依赖）。

作者: BaiBinnan
创建日期: 2026-08-10
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
           分别作为图片与标注目录
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


def checkAnnotationFiles(dirPath: str, type) -> tuple:
    """检查目录下图片与标注文件是否一一对应，找出缺少图片的标注文件。

    Args:
        dirPath: 数据集目录。
        type: "json"（LabelMe 平铺结构）或 "txt"（YOLO images/labels 结构）。

    Returns:
        (annotationFiles, imageFiles, lostAnnoFiles) 元组。
    """
    if type == "json":
        imageFiles = getImageFilesInDir(dirPath)
        annotationFiles = getJsonFilesInDir(dirPath)
        image_basenames = {os.path.splitext(os.path.basename(f))[0] for f in imageFiles}
        annotation_basenames = {
            os.path.splitext(os.path.basename(f))[0] for f in annotationFiles
        }
        return (
            annotationFiles,
            imageFiles,
            list(annotation_basenames - image_basenames),
        )
    elif type == "txt":
        imageFiles = getImageFilesInDir(Path(dirPath) / "images")
        annotationFiles = getTxtFilesInDir(Path(dirPath) / "labels")
        image_basenames = {os.path.splitext(os.path.basename(f))[0] for f in imageFiles}
        annotation_basenames = {
            os.path.splitext(os.path.basename(f))[0] for f in annotationFiles
        }
        return (
            annotationFiles,
            imageFiles,
            list(annotation_basenames - image_basenames),
        )
    return ([], [], [])


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


def _parse_engine_metadata(engine_path) -> dict:
    """从 engine 文件头部的自定义 metadata 段解析元数据字典。

    engine 文件格式（见 onnx2engine.Onnx2Engine.run 写入逻辑）：
        [4 字节小端有符号整数: metadata JSON 字节长度][metadata JSON][engine 序列化数据]

    其中 "names" 字段为 JSON 字典字符串（键为字符串形式的类别 id）。

    Args:
        engine_path: .engine 文件路径。

    Returns:
        元数据字典；无 metadata 段或解析失败时返回空字典。
    """
    import json

    try:
        raw = Path(engine_path).read_bytes()
        if len(raw) < 4:
            return {}
        meta_len = int.from_bytes(raw[:4], byteorder="little", signed=True)
        # 长度合理性校验：负数或超出文件范围说明该 engine 未写入 metadata
        if meta_len <= 0 or meta_len > len(raw) - 4:
            return {}
        return json.loads(raw[4 : 4 + meta_len].decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        return {}


def _normalize_names(mapping) -> dict:
    """将类别映射统一为 {int: str} 格式。

    Args:
        mapping: 类别映射。onnx 路径传入 ast.literal_eval 的产物（dict）；
            engine 路径传入 JSON 字符串（onnx2engine 写入时对 "names" 值
            做过一次 json.dumps，形成 '{"0": "person", ...}' 字符串），
            本函数内部先解开该层字符串。

    Returns:
        {class_id: name} 字典；格式非法时返回空字典。
    """
    import ast
    import json

    # engine 路径：names 为 JSON 字符串，先解开一层
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
    """从模型文件元数据中读取类别映射（不加载推理会话，轻量解析）。

    解析逻辑：
        - .onnx: 读取 metadata_props 中的 "names" 字段（YOLO 导出格式，
          形如 "{0: 'person', 1: 'car', ...}" 的字符串字面量）
        - .engine: 读取文件头部自定义 metadata 段（onnx2engine 转换时写入）
    .engine 解析失败时回退到同名 .onnx 文件（兼容旧版无 metadata 的 engine）。

    Args:
        model_path: 模型文件路径（.onnx 或 .engine）。

    Returns:
        类别映射 {class_id: name}；无法读取时返回空字典。
    """
    import ast

    path = Path(model_path) if model_path else None
    if path is None or not path.exists():
        return {}

    suffix = path.suffix.lower()

    # ===== engine：直接解析内嵌 metadata，失败回退同名 .onnx =====
    if suffix == ".engine":
        metadata = _parse_engine_metadata(path)
        names = _normalize_names(metadata.get("names"))
        if names:
            return names
        # 回退：旧版 engine 未写入 metadata，尝试同名 .onnx
        onnx_path = path.with_suffix(".onnx")
        if onnx_path.exists():
            path = onnx_path
            suffix = ".onnx"
        else:
            return {}

    if suffix != ".onnx":
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
