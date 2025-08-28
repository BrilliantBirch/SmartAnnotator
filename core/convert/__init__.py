from PyQt5.QtCore import QThread, pyqtSignal
import time
from cfg import LOGGER


class ConvertWorker(QThread):
    """
    转换线程--避免阻塞UI线程
    """

    # 定义信号：传递当前进度（0-100）
    progress_updated = pyqtSignal(int)
    # 定义信号：任务完成（无参数）
    task_finished = pyqtSignal()

    def run(self):
        """线程执行的核心逻辑：模拟耗时操作（如循环+sleep）"""
        try:
            # 模拟耗时任务（例如100步，每步sleep 0.1秒，共10秒）
            for progress in range(101):  # 0 ~ 100
                self.progress_updated.emit(progress)  # 发射进度信号
                time.sleep(0.1)  # 模拟耗时步骤（替换为实际业务逻辑）
            self.task_finished.emit()  # 任务完成，发射结束信号
        except Exception as e:
            # 若任务出错，可新增error信号传递异常（此处简化处理）
            LOGGER.error(f"线程执行失败：{e}")
