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
