# -*- coding: utf-8 -*-
"""
标注线程 - 避免阻塞 UI 线程

在后台线程中运行自动标注任务。移植自旧版 core/annotate/__init__.py，
仅改 PyQt5 → PySide6、cfg → smart_annotator.config 导入。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-03 模型加载前发射进度描述（engine 反序列化耗时较长，
      进度窗口可显示"正在加载模型..."）
更新: 2026-09-11 修复任务异常中断（run 返回 False 且非手动停止）时
      未发 error_occurred 信号导致 UI 无法感知失败
"""

from smart_annotator.config import SysConfig
from smart_annotator.utils import LOGGER
from .base_worker import BaseWorker
from smart_annotator.core.annotate.annotator import Annotator
from PySide6.QtCore import QMutexLocker


class AnnotationWorker(BaseWorker):
    """标注线程 - 在后台线程中运行自动标注任务，避免阻塞 UI。"""

    def __init__(self):
        """初始化标注线程。"""
        super().__init__()
        self.config: "SysConfig | None" = None

    def setConfig(self, config: SysConfig) -> None:
        """设置标注配置。

        Args:
            config: 系统配置对象。
        """
        self.config = config

    def run(self) -> None:
        """线程主逻辑（安全响应暂停/停止）。"""
        try:
            # 初始检查：配置是否设置 + 是否已被停止
            with QMutexLocker(self.mutex):
                if self.config is None:
                    raise ValueError("标注配置未设置")
                if self.stopped:
                    return

            # 初始化标注器并执行任务（模型加载耗时较长，先发进度提示）
            self.progress_desc.emit("正在加载模型...")
            annotator = Annotator(self.config)
            continue_running = annotator.run(self.run_callback)

            # 任务结束：区分正常完成和被停止
            with QMutexLocker(self.mutex):
                if self.stopped:
                    self.progress_desc.emit("标注任务手动终止")
                    self.progress_updated.emit(0.0)
                elif continue_running:
                    self.progress_desc.emit("标注任务完成")
                    self.progress_updated.emit(1.0)
                else:
                    # annotator.run 返回 False 且非手动停止：任务异常中断，
                    # 必须发错误信号驱动 UI 收尾（否则进度窗口无法感知失败）
                    self.progress_desc.emit("标注任务异常中断")
                    self.error_occurred.emit("标注任务异常中断，详情见日志")

        except ValueError as e:
            LOGGER.error(f"标注配置错误: {str(e)}")
            self.error_occurred.emit(f"配置错误: {str(e)}")
        except RuntimeError as e:
            LOGGER.error(f"模型加载失败: {str(e)}")
            self.error_occurred.emit(f"模型加载失败: {str(e)}")
        except Exception as e:
            error_msg = f"标注线程执行异常: {str(e)}"
            LOGGER.error(error_msg)
            self.error_occurred.emit(error_msg)
        finally:
            self.task_finished.emit()
            # 清理工作：重置标志位（方便线程复用）
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False
