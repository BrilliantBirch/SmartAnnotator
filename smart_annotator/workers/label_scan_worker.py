# -*- coding: utf-8 -*-
"""
后台标签扫描线程 - LabelScanWorker

在后台线程中批量解析目录下全部 labelme JSON 标注文件，汇总类别标签与
关键点名称，避免在 UI 线程同步遍历大量标注文件导致界面卡死（打开包含
标注文件的文件夹时尤为明显）。

作者: BaiBinnan
创建日期: 2026-09-02
"""

from PySide6.QtCore import Signal, QMutexLocker

from smart_annotator.core.labelme_io import collect_labels_from_files
from smart_annotator.utils import LOGGER
from .base_worker import BaseWorker


class LabelScanWorker(BaseWorker):
    """后台标签扫描线程。

    Signals:
        labels_ready(list, list): 扫描完成，参数为 (标签列表, 关键点列表)。
    """

    labels_ready = Signal(list, list)

    def __init__(self):
        """初始化标签扫描线程。"""
        super().__init__()
        self.json_paths: list = []

    def set_task(self, json_paths) -> None:
        """设置待扫描的 JSON 标注文件路径列表。

        Args:
            json_paths: JSON 文件路径列表（可迭代）。
        """
        self.json_paths = list(json_paths)

    def run(self) -> None:
        """线程主逻辑：批量解析 JSON 并汇总标签/关键点。"""
        try:
            with QMutexLocker(self.mutex):
                if self.stopped:
                    return
                paths = list(self.json_paths)

            result = collect_labels_from_files(paths)
            self.labels_ready.emit(result["labels"], result["keypoints"])

        except Exception as e:
            LOGGER.error(f"标签扫描异常: {str(e)}")
            self.error_occurred.emit(f"标签扫描异常: {str(e)}")
        finally:
            self.task_finished.emit()
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False