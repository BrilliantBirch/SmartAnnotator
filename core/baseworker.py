from PyQt5.QtCore import QThread, pyqtSignal, QWaitCondition, QMutex, QMutexLocker


class BaseWorker(QThread):
    """
    基础线程类--避免阻塞UI线程
    """

    # 定义信号：传递当前进度（0-100）
    progress_updated = pyqtSignal(float)
    # 定义信号：任务完成（无参数）
    task_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    convert_progress_desc = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        # 线程同步
        self.mutex = QMutex()  # 保护标志位的互斥锁
        self.wait_condition = QWaitCondition()  # 暂停时的等待条件变量
        # 暂停标志位
        self.paused = False
        self.stopped = False

    # -------------------------- 外部控制接口（主线程调用） --------------------------
    def pause(self):
        """暂停任务"""
        with QMutexLocker(self.mutex):  # 自动加锁，退出时自动解锁
            self.paused = True

    def resume(self):
        """恢复任务"""
        with QMutexLocker(self.mutex):
            self.paused = False
            self.wait_condition.wakeOne()  # 唤醒暂停的线程

    def stop(self):
        """停止任务"""
        with QMutexLocker(self.mutex):
            self.convert_progress_desc.emit("正在停止任务...")
            self.stopped = True
            self.paused = False  # 先恢复暂停，避免线程卡在等待状态
            self.wait_condition.wakeOne()  # 唤醒线程，让它检查停止标志

    def run(self):
        """线程执行的核心逻辑"""
        pass

    def run_callback(self, desc, progress):
        """
        转换器回调函数（每步进度更新时触发）
        返回 True：继续处理；返回 False：停止处理
        """
        # 1. 先检查是否需要停止（优先级最高）
        with QMutexLocker(self.mutex):
            if self.stopped:
                return False  # 告知转换器停止后续处理

            # 2. 检查是否需要暂停（若暂停，阻塞等待唤醒）
            while self.paused:
                # 释放锁并等待（避免占用 CPU），唤醒后重新加锁
                self.wait_condition.wait(self.mutex)
                # 唤醒后再次检查是否停止（防止暂停时被停止）
                if self.stopped:
                    return False

        # 3. 正常更新进度
        self.progress_updated.emit(progress)
        self.convert_progress_desc.emit(desc)
        return True  # 告知转换器继续处理
