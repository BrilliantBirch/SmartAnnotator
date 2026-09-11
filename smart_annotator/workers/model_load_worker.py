# -*- coding: utf-8 -*-
"""
模型预加载后台线程 - ModelLoadWorker

在用户于"模型加载 / 自动标注设置"对话框确认后，后台线程提前完成
模型加载与 warmup（经 predictor_cache 缓存，后续标注任务直接复用），
避免首次启动标注时长时间无响应。阶段进度（加载/预热）经既有信号
回传，由主窗口的进度弹窗实时显示。

作者: BaiBinnan
创建日期: 2026-09-11
更新: 2026-09-11 首次创建：确认配置后预加载 + 阶段进度上报
"""

from PySide6.QtCore import Signal, QMutexLocker

from smart_annotator.config import SysConfig
from smart_annotator.utils import LOGGER
from smart_annotator.core.annotate.predictor_cache import get_predictor, has_predictor
from .base_worker import BaseWorker


class ModelLoadWorker(BaseWorker):
    """模型预加载线程。

    Signals:
        load_done(): 模型加载与预热完成（或缓存命中已就绪）。
    """

    load_done = Signal()

    def __init__(self):
        """初始化预加载线程。"""
        super().__init__()
        self.config: "SysConfig | None" = None

    def set_task(self, config: SysConfig) -> None:
        """设置预加载配置。

        Args:
            config: 模型设置对话框确认后的系统配置对象。
        """
        self.config = config

    def run(self) -> None:
        """线程主逻辑：经 predictor_cache 加载模型并预热（可中断于阶段间）。"""
        try:
            with QMutexLocker(self.mutex):
                if self.config is None:
                    return
                if self.stopped:
                    return

            # 缓存命中（模型已加载过）：直接完成，不再弹预热流程
            if has_predictor(self.config.annotate_config):
                LOGGER.info("模型已缓存，跳过预加载")
                self.load_done.emit()
                return

            # 阶段进度回调：core 层 (描述, 0-1) → 进度弹窗显示
            def on_progress(desc: str, progress: float) -> None:
                """转发模型加载/预热阶段进度到 UI 信号。"""
                self.progress_desc.emit(desc)
                self.progress_updated.emit(progress)

            # 加载 + warmup（失败返回 None / 不支持抛 ValueError）
            predictor = get_predictor(self.config.annotate_config, on_progress)
            if predictor is None:
                self.error_occurred.emit(
                    f"模型加载失败: {self.config.annotate_config.model_path}，详情见日志"
                )
                return

            with QMutexLocker(self.mutex):
                if self.stopped:
                    return
            self.load_done.emit()

        except ValueError as e:
            LOGGER.error(f"模型预加载配置错误: {str(e)}")
            self.error_occurred.emit(f"配置错误: {str(e)}")
        except Exception as e:
            LOGGER.error(f"模型预加载异常: {str(e)}")
            self.error_occurred.emit(f"模型预加载异常: {str(e)}")
        finally:
            self.task_finished.emit()
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False
