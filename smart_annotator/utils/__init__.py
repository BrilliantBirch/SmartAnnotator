# -*- coding: utf-8 -*-
"""
工具子包 — 日志、路径、文件操作、标注转换工具

导出：
    - LOGGER: 应用日志记录器（标准库 logging.getLogger，仅控制台输出，
      无本地日志文件、无 Qt 依赖；logger.py 已删除，定义内联于此）
    - LOGGING_NAME: 日志记录器名称（GUI 推送处理器按此挂接）
    - ROOT, resource_path: 项目根目录与资源路径解析
    - COLORS: 类别可视化调色板（numpy）
    - 文件扫描: checkAnnotationFiles, getImageFilesInDir, getVideoFilesInDir 等
    - 标注工具: yolo_to_labelme, generate_labelme_file, export, split_data 等

注意：Qt 日志处理器（QtLogHandler）位于 qt_logger.py，需 PySide6，
仅 GUI 使用时显式导入，避免算法层强制依赖 PySide6。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-04 删除 logger.py（LogManager/文件轮转/stdout 重定向全部
      移除），LOGGER 定义内联本文件：logging.getLogger + 单控制台
      StreamHandler（stderr），不再输出本地日志文件
"""

import logging
import sys
import time

from .paths import ROOT, resource_path
from .colors import COLORS
from .files import (
    getJsonFilesInDir,
    getTxtFilesInDir,
    getImageFilesInDir,
    getVideoFilesInDir,
    checkAnnotationFiles,
    move_files,
    getModelClasses,
    getModelTaskType,
    resolve_dataset_dirs,
    scan_dataset_files,
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

# ===== 日志（标准库 logging，仅控制台输出）=====
# 日志名称（GUI 推送处理器 qt_logger 按此名称挂接）
LOGGING_NAME = "BrilliantAnnotator"     


class _MillisecondFormatter(logging.Formatter):
    """毫秒级时间戳格式化器（保持既有日志格式，便于日志比对）。

    输出示例: 2026-08-10 12:00:00:123
    """

    def formatTime(self, record, datefmt=None):
        """格式化时间为"日期 时:分:秒:毫秒"。"""
        ct = self.converter(record.created)
        s = time.strftime(datefmt or "%Y-%m-%d %H:%M:%S", ct)
        return f"{s}:{int(record.msecs):03d}"


def _setup_logger() -> logging.Logger:
    """配置应用日志记录器（仅控制台 StreamHandler，无本地日志文件）。

    Returns:
        配置好的 logging.Logger 实例。
    """
    logger = logging.getLogger(LOGGING_NAME)
    # 避免重复配置（模块重导入/多次调用时 handler 叠加刷屏）
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    formatter = _MillisecondFormatter(
        "[%(asctime)s] [%(levelname)-8s] [%(threadName)-12s] "
        "%(name)s:%(lineno)d - %(message)s"
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    # 不向根记录器传播（避免根 handler 重复输出）
    logger.propagate = False
    return logger


# 模块级日志记录器（全项目统一 from smart_annotator.utils import LOGGER）
LOGGER = _setup_logger()

__all__ = [
    "LOGGER",
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
    "getModelClasses",
    "getModelTaskType",
    "resolve_dataset_dirs",
    "scan_dataset_files",
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
