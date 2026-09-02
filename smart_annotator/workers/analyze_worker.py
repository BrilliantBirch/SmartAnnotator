# -*- coding: utf-8 -*-
"""
数据集分析线程 - 避免阻塞 UI 线程

在后台线程中运行 dataset_analyzer.analyze_dataset，
通过信号回传进度、分析结果与错误信息。

作者: BaiBinnan
创建日期: 2026-09-02
"""

from PySide6.QtCore import Signal, QMutexLocker

from smart_annotator.utils import LOGGER
from .base_worker import BaseWorker
from smart_annotator.core.convert.dataset_analyzer import (
    analyze_dataset,
    DatasetAnalysis,
)


class AnalyzeWorker(BaseWorker):
    """数据集分析线程。

    信号：
        analysis_finished(object): 分析完成，参数为 DatasetAnalysis 对象。
        （progress_updated / error_occurred / task_finished 继承自 BaseWorker）
    """

    analysis_finished = Signal(object)

    def __init__(self, input_dir: str):
        """初始化分析线程。

        Args:
            input_dir: 待分析的标注数据集目录路径。
        """
        super().__init__()
        self.input_dir = input_dir

    def run(self) -> None:
        """线程主逻辑：执行数据集分析并回传结果。"""
        try:
            # 初始检查：是否已被停止
            with QMutexLocker(self.mutex):
                if self.stopped:
                    return

            result = analyze_dataset(self.input_dir, self.run_callback)

            # 任务结束：区分正常完成和被停止
            with QMutexLocker(self.mutex):
                if self.stopped:
                    self.progress_desc.emit("数据集分析已终止")
                else:
                    self.progress_desc.emit("数据集分析完成")
                    self.analysis_finished.emit(result)

        except ValueError as e:
            LOGGER.error(f"数据集分析参数错误: {str(e)}")
            self.error_occurred.emit(f"参数错误: {str(e)}")
        except Exception as e:
            error_msg = f"数据集分析线程执行异常: {str(e)}"
            LOGGER.error(error_msg)
            self.error_occurred.emit(error_msg)
        finally:
            self.task_finished.emit()
            # 清理工作：重置标志位（方便线程复用）
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False
