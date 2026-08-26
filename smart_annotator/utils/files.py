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


def getModelClasses(model_path) -> dict:
    """从模型文件元数据中读取类别映射（不加载推理会话，轻量解析）。

    解析 ONNX 模型 metadata_props 中的 "names" 字段（YOLO 导出格式，
    形如 "{0: 'person', 1: 'car', ...}" 的字符串字面量）。
    TensorRT engine 文件不保留元数据，自动回退到同名 .onnx 文件。

    Args:
        model_path: 模型文件路径（.onnx 或 .engine）。

    Returns:
        类别映射 {class_id: name}；无法读取时返回空字典。
    """
    import ast

    path = Path(model_path) if model_path else None
    if path is None or not path.exists():
        return {}

    # engine 文件不含元数据，回退到同名 .onnx（onnx→engine 转换产物场景）
    if path.suffix.lower() == ".engine":
        onnx_path = path.with_suffix(".onnx")
        if onnx_path.exists():
            path = onnx_path
        else:
            return {}

    if path.suffix.lower() != ".onnx":
        return {}

    try:
        import onnx

        # load_external_data=False: 仅解析 proto 结构，不加载外部权重，速度极快
        model = onnx.load(str(path), load_external_data=False)
        for prop in model.metadata_props:
            if prop.key == "names":
                mapping = ast.literal_eval(prop.value)
                if isinstance(mapping, dict):
                    return {int(k): str(v) for k, v in mapping.items()}
                break
    except Exception:
        return {}

    return {}
