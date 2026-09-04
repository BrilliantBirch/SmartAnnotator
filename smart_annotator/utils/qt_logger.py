# -*- coding: utf-8 -*-
"""
Qt 日志处理器 — 通过 PySide6 Signal 将日志推送到主线程 QPlainTextEdit

独立于 logger.py（纯 Python），仅在 GUI 使用时导入，避免算法层强制依赖 PySide6。
工作线程产生的日志通过 log_signal 跨线程传递到主线程，符合 Qt 的 UI 线程约束。

另提供 install_qt_message_filter：过滤 Qt 内部已知无害的警告刷屏
（QSS 像素字号 + 可编辑 QComboBox 触发的 QFont::setPointSize <= 0）。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-04 修复 add_qt_handler 返回已销毁实例导致的崩溃：遍历已有
      handler 时用 shiboken6.isValid 检测底层 C++ 对象是否已销毁（parent 为
      临时页面时页面随对话框关闭被回收），失效实例先 removeHandler 再新建
更新: 2026-09-04 新增 install_qt_message_filter：抑制 QSS px 字号下可编辑
      QComboBox 触发的 QFont::setPointSize(-1) 无害警告（Qt 忽略该值后正常渲染）
"""

import logging
import os
import sys
from typing import Optional

import shiboken6
from PySide6.QtCore import QObject, Signal, QtMsgType, qInstallMessageHandler

from .logger import _MillisecondFormatter, LOGGING_NAME

# 需要静默的 Qt 内部警告前缀（均为已知无害、Qt 自行回退的场景）：
# - QFont::setPointSize：全局 QSS 以 px 定义字号时控件字体为 pixelSize 模式
#   （pointSize == -1），可编辑 QComboBox 显示时 Qt 内部以该值调 setPointSize
#   触发警告；Qt 忽略非法值并正常渲染，功能无损，故静默防刷屏。
_SUPPRESSED_WARNING_PREFIXES = (
    "QFont::setPointSize: Point size <= 0",
)

# Qt 消息类型 -> 默认 stderr 输出前缀（对齐 Qt 默认格式）
_MSG_TYPE_PREFIXES = {
    QtMsgType.QtDebugMsg: "Debug",
    QtMsgType.QtInfoMsg: "Info",
    QtMsgType.QtWarningMsg: "Warning",
    QtMsgType.QtCriticalMsg: "Critical",
    QtMsgType.QtFatalMsg: "Fatal",
    QtMsgType.QtSystemMsg: "System",
}


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

    遍历已有 handler 时先检测底层 C++ 对象是否已销毁（parent 为临时页面时，
    页面随对话框关闭被回收，handler 随之失效）：已销毁的实例从记录器移除并
    继续查找，避免向已销毁对象 connect 信号时抛出 RuntimeError。

    Args:
        logger_name: 日志记录器名称（默认为应用日志名）。
        parent: 父 QObject（应为长生命周期对象，如主窗口）。
        max_lines: 日志区最大行数。

    Returns:
        有效的 QtLogHandler 实例（已存在且未销毁则复用，否则新建）。
    """
    logger = logging.getLogger(logger_name)
    # 遍历副本：中途移除失效 handler 不影响迭代
    for handler in list(logger.handlers):
        if not isinstance(handler, QtLogHandler):
            continue
        # C++ 对象已销毁（parent 页面随对话框关闭被回收）→ 移除失效实例
        if not shiboken6.isValid(handler):
            logger.removeHandler(handler)
            continue
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


def _qt_message_filter(msg_type: QtMsgType, context, message: str) -> None:
    """Qt 全局消息回调：过滤已知无害警告，其余保持默认 stderr 输出。

    Args:
        msg_type: Qt 消息类型（Debug/Info/Warning/Critical/Fatal）。
        context: 消息上下文（C++ 源位置，可能为空）。
        message: 消息文本。
    """
    # 已知无害警告：静默（Qt 内部自行回退，无功能影响）
    if msg_type == QtMsgType.QtWarningMsg:
        for prefix in _SUPPRESSED_WARNING_PREFIXES:
            if message.startswith(prefix):
                return

    # 其余消息按 Qt 默认格式输出到 stderr
    prefix = _MSG_TYPE_PREFIXES.get(msg_type, "Unknown")
    sys.stderr.write(f"{prefix}: {message}\n")
    sys.stderr.flush()

    # Fatal 消息按 Qt 约定必须终止进程（否则行为未定义）
    if msg_type == QtMsgType.QtFatalMsg:
        os.abort()


def install_qt_message_filter() -> None:
    """安装 Qt 全局消息过滤器（程序入口调用一次，QApplication 创建前后均可）。

    抑制范围仅限 _SUPPRESSED_WARNING_PREFIXES 中列出的 Qt 内部无害警告，
    其余消息保持与 Qt 默认行为一致的 stderr 输出，不掩盖新问题。
    """
    qInstallMessageHandler(_qt_message_filter)
