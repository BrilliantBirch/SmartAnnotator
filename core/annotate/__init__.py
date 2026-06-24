"""
Description：标注线程 - 避免阻塞UI线程
Author: BaiBinnan
Date: 2025/06/09
LastEdit: 2026/06/24
LastEditBy: BaiBinnan
E-mail: baibinnan@chuanfeng.com
update：
    1. 2026/06/24: 完善错误处理，添加finally清理逻辑，统一描述文案
"""

from cfg import LOGGER, SysConfig
from ..baseworker import BaseWorker
from PyQt5.QtCore import QMutexLocker
from .annotator import Annotator


class AnnotateWorker(BaseWorker):
    """标注线程 - 在后台线程中运行自动标注任务，避免阻塞UI"""

    def __init__(self):
        super().__init__()
        self.config: "SysConfig | None" = None

    def setConfig(self, config: SysConfig) -> None:
        """设置标注配置"""
        self.config = config

    def run(self) -> None:
        """线程主逻辑（安全响应暂停/停止）"""
        try:
            # 初始检查：配置是否设置 + 是否已被停止
            with QMutexLocker(self.mutex):
                if self.config is None:
                    raise ValueError("标注配置未设置")
                if self.stopped:
                    return

            # 初始化标注器并执行任务
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
                    self.progress_desc.emit("标注任务异常中断")

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