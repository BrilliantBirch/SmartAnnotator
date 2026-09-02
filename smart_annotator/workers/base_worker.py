# -*- coding: utf-8 -*-
"""
基础线程类 - 避免阻塞 UI 线程

提供暂停/恢复/停止控制与 run_callback 适配器（算法回调的基石）。
移植自旧版 core/baseworker.py，仅改 PyQt5 → PySide6（pyqtSignal → Signal）。

作者: BaiBinnan
创建日期: 2026-08-10
"""

from PySide6.QtCore import QThread, Signal, QWaitCondition, QMutex, QMutexLocker


class BaseWorker(QThread):
    """基础线程类 - 避免阻塞 UI 线程。

    信号：
        progress_updated(float): 当前进度（0-1）。
        task_finished(): 任务结束（无参数）。
        error_occurred(str): 错误信息。
        progress_desc(str): 当前步骤描述。
    """

    # 定义信号：传递当前进度（0-1）
    progress_updated = Signal(float)
    # 定义信号：任务完成（无参数）
    task_finished = Signal()
    error_occurred = Signal(str)
    progress_desc = Signal(str)

    def __init__(self):
        """初始化线程同步原语与控制标志。"""
        super().__init__()
        # 线程同步
        self.mutex = QMutex()  # 保护标志位的互斥锁
        self.wait_condition = QWaitCondition()  # 暂停时的等待条件变量
        # 暂停标志位
        self.paused = False
        self.stopped = False

    # -------------------------- 外部控制接口（主线程调用） --------------------------
    def pause(self):
        """暂停任务。"""
        with QMutexLocker(self.mutex):  # 自动加锁，退出时自动解锁
            self.paused = True

    def resume(self):
        """恢复任务。"""
        with QMutexLocker(self.mutex):
            self.paused = False
            self.wait_condition.wakeOne()  # 唤醒暂停的线程

    def stop(self):
        """停止任务。"""
        with QMutexLocker(self.mutex):
            self.progress_desc.emit("正在停止任务...")
            self.stopped = True
            self.paused = False  # 先恢复暂停，避免线程卡在等待状态
            self.wait_condition.wakeOne()  # 唤醒线程，让它检查停止标志

    def run(self):
        """线程执行的核心逻辑（子类重写）。"""
        pass

    def run_callback(self, desc, progress):
        """转换器/标注器回调函数（每步进度更新时触发）。

        返回 True：继续处理；返回 False：停止处理。

        Args:
            desc: 当前步骤描述。
            progress: 当前进度（0-1）。

        Returns:
            是否继续处理。
        """
        # 1. 先检查是否需要停止（优先级最高）
        with QMutexLocker(self.mutex):
            if self.stopped:
                return False  # 告知算法停止后续处理

            # 2. 检查是否需要暂停（若暂停，阻塞等待唤醒）
            while self.paused:
                # 释放锁并等待（避免占用 CPU），唤醒后重新加锁
                self.wait_condition.wait(self.mutex)
                # 唤醒后再次检查是否停止（防止暂停时被停止）
                if self.stopped:
                    return False

        # 3. 正常更新进度
        self.progress_updated.emit(progress)
        self.progress_desc.emit(desc)
        return True  # 告知算法继续处理
