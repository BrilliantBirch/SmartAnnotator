"""
Description：文件操作

Author: Baibinnan
Date: 2025/8/27
LastEdit: 2025/8/27
E-mail: baibinnan@chuanfeng.com
update：

"""

import glob
import os
import shutil
from pathlib import Path


def getJsonFilesInDir(dirPath: Path) -> list:
    """
    获取目录下所有的JSON文件
    """
    if not os.path.isdir(dirPath):
        return []
    return glob.glob(os.path.join(dirPath, "*.json"))


def getTxtFilesInDir(dirPath: Path) -> list:
    """
    获取目录下所有的txt文件
    """
    if not os.path.isdir(dirPath):
        return []
    return glob.glob(os.path.join(dirPath, "*.txt"))


def getImageFilesInDir(dirPath: Path) -> list:
    """
    获取目录下所有的图片文件
    """
    if not os.path.isdir(dirPath):
        return []
    # 支持多种图片格式
    image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.bmp"]
    files = []
    for ext in image_extensions:
        files.extend(glob.glob(os.path.join(dirPath, ext)))
    return files


def checkAnnotationFiles(dirPath: str, type) -> tuple:
    """
    检查目录下的图片文件和标注文件是否一一对应，找出缺少图片的标注文件

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


def move_files(filelist, splitname, output):
    for file_name in filelist:
        try:
            img_src = file_name
            lbl_src = os.path.splitext(file_name)[0] + ".txt"
            lbl_src = lbl_src.replace("images", "labels")
            file_basename = os.path.basename(file_name)
            img_dst = os.path.join(output, splitname, "images", file_basename)
            lbl_dst = os.path.join(
                output, splitname, "labels", os.path.basename(lbl_src)
            )
            shutil.copy(img_src, img_dst)
            shutil.copy(lbl_src, lbl_dst)
        except Exception as ex:
            raise RuntimeError(f"移动文件{file_name}时失败：{str(ex)}")
