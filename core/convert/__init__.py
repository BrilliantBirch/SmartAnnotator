from PyQt5.QtCore import QThread, pyqtSignal
from cfg import LOGGER, SysConfig
from .converter import Converter


class ConvertWorker(QThread):
    """
    转换线程--避免阻塞UI线程
    """

    # 定义信号：传递当前进度（0-100）
    progress_updated = pyqtSignal(int)
    # 定义信号：任务完成（无参数）
    task_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    convert_progress_desc = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.config = None

    def setConfig(self, config: SysConfig):
        self.config = config

    def run(self):
        """线程执行的核心逻辑：模拟耗时操作（如循环+sleep）"""
        try:

            if self.config is None:
                raise ValueError("转换配置未设置")

            converter = Converter(self.config)
            converter.run(self.run_callback)
            self.task_finished.emit()  # 任务完成，发射结束信号
        except Exception as e:
            # 若任务出错，可新增error信号传递异常（此处简化处理）
            LOGGER.error(f"线程执行失败：{e}")
            self.error_occurred.emit(str(e))  # 任务完成，发射结束信号

    # def stop(self):
    #     self.terminate()

    def run_callback(self, desc, progress):
        self.progress_updated.emit(progress)
        self.convert_progress_desc.emit(desc)
