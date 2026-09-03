# -*- coding: utf-8 -*-
"""
单张自动标注线程 - SingleAnnotateWorker

在后台线程中对单张图片执行推理，返回 labelme 形状字典列表（不写文件），
供标注编辑器（主窗口）直接展示到画布。与批量 AnnotationWorker 复用同一
Annotator，保证与批量自动标注的类别过滤/格式化/坐标换算行为完全一致。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-03 中止后不再发射推理结果（加载/推理完成后检查停止标志）；
      模型加载与推理阶段分别发射进度描述
"""

from PySide6.QtCore import Signal, QMutexLocker

from smart_annotator.config import SysConfig
from smart_annotator.utils import LOGGER
from .base_worker import BaseWorker
from smart_annotator.core.annotate.annotator import Annotator


class SingleAnnotateWorker(BaseWorker):
    """单张自动标注线程。

    Signals:
        shapes_ready(list): 推理完成，返回 labelme 形状字典列表。
    """

    shapes_ready = Signal(list)

    def __init__(self):
        """初始化单张标注线程。"""
        super().__init__()
        self.config: "SysConfig | None" = None
        self.image_path: str = ""

    def set_task(self, config: SysConfig, image_path: str) -> None:
        """设置推理配置与目标图片路径。

        Args:
            config: 系统配置对象（含模型/任务类型/类别过滤等）。
            image_path: 待标注图片路径。
        """
        self.config = config
        self.image_path = image_path

    def run(self) -> None:
        """线程主逻辑：构建 Annotator 并对单张图片推理。"""
        try:
            with QMutexLocker(self.mutex):
                if self.config is None:
                    raise ValueError("标注配置未设置")
                if self.stopped:
                    return

            # 模型加载阶段（engine 反序列化耗时较长）
            self.progress_desc.emit("正在加载模型...")
            annotator = Annotator(self.config)
            with QMutexLocker(self.mutex):
                if self.stopped:
                    self.progress_desc.emit("单张标注已中止")
                    return

            # 推理阶段
            self.progress_desc.emit("正在推理...")
            shapes = annotator.annotate_image(self.image_path)
            # 中止后丢弃结果（不回填画布）
            with QMutexLocker(self.mutex):
                if self.stopped:
                    self.progress_desc.emit("单张标注已中止")
                    return
            self.shapes_ready.emit(shapes)
            self.progress_desc.emit(f"单张标注完成，共 {len(shapes)} 个对象")

        except ValueError as e:
            LOGGER.error(f"标注配置错误: {str(e)}")
            self.error_occurred.emit(f"配置错误: {str(e)}")
        except RuntimeError as e:
            LOGGER.error(f"模型加载失败: {str(e)}")
            self.error_occurred.emit(f"模型加载失败: {str(e)}")
        except Exception as e:
            error_msg = f"单张标注异常: {str(e)}"
            LOGGER.error(error_msg)
            self.error_occurred.emit(error_msg)
        finally:
            self.task_finished.emit()
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False