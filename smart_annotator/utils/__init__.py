# -*- coding: utf-8 -*-
"""
工具子包 — 日志、路径、文件操作、标注转换工具

导出：
    - LOGGER: 应用日志记录器（纯 Python，无 Qt 依赖）
    - ROOT, resource_path: 项目根目录与资源路径解析
    - COLORS: 类别可视化调色板（numpy）
    - 文件扫描: checkAnnotationFiles, getImageFilesInDir, getVideoFilesInDir 等
    - 标注工具: yolo_to_labelme, generate_labelme_file, export, split_data 等

注意：Qt 日志处理器（QtLogHandler）位于 qt_logger.py，需 PySide6，
仅 GUI 使用时显式导入，避免算法层强制依赖 PySide6。

作者: BaiBinnan
创建日期: 2026-08-10
"""

from .logger import LOGGER, LogManager, LOGGING_NAME
from .paths import ROOT, resource_path
from .colors import COLORS
from .files import (
    getJsonFilesInDir,
    getTxtFilesInDir,
    getImageFilesInDir,
    getVideoFilesInDir,
    checkAnnotationFiles,
    move_files,
)
from .tool import (
    is_point_in_box,
    is_rect_inside,
    detect_anomalies,
    classMapping,
    split_data,
    create_yaml,
    export,
    detect_to_labelme,
    pose_to_labelme,
    segment_to_labelme,
    yolo_to_labelme,
    generate_labelme_file,
    rotate_90_image,
)

__all__ = [
    "LOGGER",
    "LogManager",
    "LOGGING_NAME",
    "ROOT",
    "resource_path",
    "COLORS",
    "getJsonFilesInDir",
    "getTxtFilesInDir",
    "getImageFilesInDir",
    "getVideoFilesInDir",
    "checkAnnotationFiles",
    "move_files",
    "is_point_in_box",
    "is_rect_inside",
    "detect_anomalies",
    "classMapping",
    "split_data",
    "create_yaml",
    "export",
    "detect_to_labelme",
    "pose_to_labelme",
    "segment_to_labelme",
    "yolo_to_labelme",
    "generate_labelme_file",
    "rotate_90_image",
]
