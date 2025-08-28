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


def getJsonFilesInDir(dirPath: str) -> list:
    """
    获取目录下所有的JSON文件
    """
    if not os.path.isdir(dirPath):
        return []
    return glob.glob(os.path.join(dirPath, "*.json"))


def getImageFilesInDir(dirPath: str) -> list:
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


def checkAnnotationFiles(dirPath: str) -> tuple:
    """
    检查目录下的图片文件和标注文件是否一一对应，找出缺少图片的标注文件

    """

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
