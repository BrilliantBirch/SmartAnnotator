from cfg import LOGGER, SysConfig
from .converter import Converter
from ..baseworker import BaseWorker
from PyQt5.QtCore import QMutexLocker


class ConvertWorker(BaseWorker):
    """
    转换线程--避免阻塞UI线程
    """

    def __init__(self):
        super().__init__()
        self.config = None

    def setConfig(self, config: SysConfig):
        self.config = config

    def run(self):
        """线程主逻辑（安全响应暂停/停止）"""
        converter = None
        try:
            # 初始检查：配置是否设置 + 是否已被停止
            with QMutexLocker(self.mutex):
                if self.config is None:
                    raise ValueError("转换配置未设置")
                if self.stopped:
                    return

            # 初始化转换器并执行任务
            converter = Converter(self.config)
            # converter.run() 会循环调用 run_callback，且根据返回值决定是否继续
            continue_running = converter.run(self.run_callback)

            # 任务结束：区分“正常完成”和“被停止”
            with QMutexLocker(self.mutex):
                if self.stopped:
                    self.progress_desc.emit("任务手动终止")
                    self.progress_updated.emit(0.0)
                elif continue_running:
                    self.progress_desc.emit("转换任务完成")
                else:
                    self.progress_desc.emit("转换任务异常中断")

        except Exception as e:
            # 异常处理：记录日志 + 通知 UI
            error_msg = f"线程执行失败：{str(e)}"
            LOGGER.error(error_msg)
            self.error_occurred.emit(error_msg)

        finally:
            self.task_finished.emit()
            # 清理工作：重置标志位（方便线程复用）
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False
