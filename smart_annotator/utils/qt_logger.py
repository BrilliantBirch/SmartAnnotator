# -*- coding: utf-8 -*-
"""
Qt 日志处理器 — 通过 PySide6 Signal 将日志推送到主线程 QPlainTextEdit

独立于 logger.py（纯 Python），仅在 GUI 使用时导入，避免算法层强制依赖 PySide6。
工作线程产生的日志通过 log_signal 跨线程传递到主线程，符合 Qt 的 UI 线程约束。

作者: BaiBinnan
创建日期: 2026-08-10
"""

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal

from .logger import _MillisecondFormatter, LOGGING_NAME


class QtLogHandler(QObject, logging.Handler):
    """Qt 日志处理器 — 通过 Signal 将日志推送到主线程的 QPlainTextEdit。

    Attributes:
        log_signal: 日志文本信号，连接到 QPlainTextEdit.appendPlainText。
    """

    log_signal = Signal(str)

    def __init__(self, parent: Optional[QObject] = None, max_lines: int = 500):
        """初始化 Qt 日志处理器。

        Args:
            parent: 父 QObject（通常为 MainWindow），确保处理器生命周期与窗口一致。
            max_lines: 日志区最大行数（由调用方负责裁剪）。
        """
        QObject.__init__(self, parent)
        logging.Handler.__init__(self)
        self._max_lines = max_lines

    def emit(self, record: logging.LogRecord) -> None:
        """重写 emit，将格式化后的日志文本通过信号发出。

        Args:
            record: 日志记录。
        """
        try:
            msg = self.format(record)
            self.log_signal.emit(msg)
        except Exception:
            self.handleError(record)


def add_qt_handler(logger_name: str = LOGGING_NAME, parent: Optional[QObject] = None,
                   max_lines: int = 500) -> Optional[QtLogHandler]:
    """为已存在的日志记录器添加 Qt 日志处理器。

    Args:
        logger_name: 日志记录器名称（默认为应用日志名）。
        parent: 父 QObject（MainWindow）。
        max_lines: 日志区最大行数。

    Returns:
        新增的 QtLogHandler 实例；若已存在则返回已有实例。
    """
    logger = logging.getLogger(logger_name)
    for handler in logger.handlers:
        if isinstance(handler, QtLogHandler):
            return handler
    formatter = _MillisecondFormatter(
        "[%(asctime)s] [%(levelname)-8s] %(message)s",
        "%H:%M:%S",
    )
    qt_handler = QtLogHandler(parent, max_lines)
    qt_handler.setFormatter(formatter)
    qt_handler.setLevel(logging.INFO)
    logger.addHandler(qt_handler)
    return qt_handler
