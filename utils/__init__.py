"""
Description：工具类
Author: Baibinnan
Date: 2025/8/25
LastEdit: 2026/2/4
E-mail: baibinnan@chuanfeng.com
update：

"""

from PyQt5.QtWidgets import QTextBrowser
from PyQt5.QtCore import QObject, pyqtSignal
import html
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import logging
import platform

ROOT = os.getcwd()
ASSET = os.path.join(ROOT, "Resources")
LOGGING_NAME = "VAI_E_SmartAnnotator"
MACOS, LINUX, WINDOWS = (platform.system() == x for x in ["Darwin", "Linux", "Windows"])


from .qt import chooseDir, chooseFile, showMessageBox, CustomItemWidget
from .files import checkAnnotationFiles, getImageFilesInDir
from .tool import (
    is_point_in_box,
    is_rect_inside,
    export,
    generate_labelme_file,
    resource_path,
)


class QTextBrowserLogger(QObject, logging.Handler):
    """自定义日志处理器，将日志输出到QTextBrowser控件"""

    log_signal = pyqtSignal(str)

    def __init__(self, text_browser: QTextBrowser, max_lines: int = 500):
        super().__init__()
        logging.Handler.__init__(self)
        self.text_browser = text_browser
        self.max_lines = max_lines

        # 连接信号与槽函数，确保在主线程更新UI
        self.log_signal.connect(self.append_log)

        # 为不同日志级别设置颜色
        self.level_colors = {
            logging.DEBUG: "#6c757d",  # 灰色
            logging.INFO: "#00695c",  # 深青色
            logging.WARNING: "#e65100",  # 深橙色
            logging.ERROR: "#c62828",  # 深红色
            logging.CRITICAL: "#b71c1c",  # 暗红色
        }

    def emit(self, record):
        """重写emit方法，处理日志记录"""
        try:
            # 使用日志记录器的格式化器
            msg = self.format(record)
            # 转义HTML特殊字符
            msg = html.escape(msg)
            # 获取对应级别的颜色
            level = record.levelno
            color = self.level_colors.get(level, "#000000")

            # 构建带颜色的HTML
            html_msg = f'<span style="color: {color};">{msg}</span><br>'

            # 发送信号到主线程更新UI
            self.log_signal.emit(html_msg)
        except Exception:
            self.handleError(record)

    def append_log(self, html_msg: str):
        """在QTextBrowser中添加日志，并控制最大行数"""
        # 添加新日志
        self.text_browser.insertHtml(html_msg)
        # 滚动到底部
        self.text_browser.moveCursor(self.text_browser.textCursor().End)

        # 检查行数并移除旧日志
        lines = self.text_browser.toPlainText().split("\n")
        if len(lines) > self.max_lines:
            # 计算需要删除的行数
            lines_to_remove = len(lines) - self.max_lines
            # 删除旧日志
            cursor = self.text_browser.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.movePosition(cursor.Down, cursor.MoveAnchor, lines_to_remove)
            cursor.movePosition(cursor.Start, cursor.KeepAnchor)
            cursor.removeSelectedText()
            # 确保光标在末尾
            self.text_browser.moveCursor(self.text_browser.textCursor().End)


def set_logging(name="LOGGING_NAME"):
    """
    设置日志记录器
    Args:
        name (str): 日志记录器的名称，默认为 "LOGGING_NAME"。

    Returns:
        (logging.Logger): 日志对象.

    Examples:
        >>> set_logging(name="VAI_E_xxx", verbose=True)
        >>> logger = logging.getLogger("VAI_E_xxx")
        >>> logger.info("示例日志")


    """
    level = logging.DEBUG

    class PrefixFormatter(logging.Formatter):
        def format(self, record):
            """Format log records with prefixes based on level."""
            if record.levelno == logging.WARNING:
                prefix = "⚠️"
                record.msg = f"{prefix} {record.msg}"
            elif record.levelno == logging.ERROR:
                prefix = "❌"
                record.msg = f"{prefix} {record.msg}"

            formatted_message = super().format(record)
            return formatted_message

    formatter = PrefixFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    if WINDOWS and hasattr(sys.stdout, "encoding") and sys.stdout.encoding != "utf-8":
        try:
            # Attempt to reconfigure stdout to use UTF-8 encoding if possible
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            # For environments where reconfigure is not available, wrap stdout in a TextIOWrapper
            elif hasattr(sys.stdout, "buffer"):
                import io

                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        except Exception:
            pass

    class ErrorFileFormatter(PrefixFormatter):
        def format(self, record):
            if record.levelno == logging.ERROR:
                # 检查 record.exc_info 是否为 None
                if record.exc_info and record.exc_info != (None, None, None):
                    # 若有异常信息，记录异常堆栈
                    exc_text = super().formatException(record.exc_info)
                    record.msg = f"{record.msg}\n{exc_text}"
            return super().format(record)

    # 创建日志目录
    log_dir = os.path.join(ROOT, "Logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        f"{log_dir}/{name}.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_formatter = ErrorFileFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(level)

    # Set up the logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def add_text_browser_handler(logger_name, text_browser=None, max_lines=500):
    """
    延后为日志记录器添加QTextBrowser处理器

    Args:
        logger_name (str): 日志记录器名称
        text_browser (QTextBrowser): 前端显示控件
        max_lines (int): 最大显示行数

    Returns:
        bool: 添加成功返回True，否则返回False
    """
    if not text_browser:
        return False

    # 获取已存在的日志记录器
    logger = logging.getLogger(logger_name)

    # 检查是否已添加过QTextBrowser处理器，避免重复添加
    for handler in logger.handlers:
        if isinstance(handler, QTextBrowserLogger):
            return False  # 已存在则返回False

    # 创建并添加前端处理器
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    browser_handler = QTextBrowserLogger(text_browser, max_lines)
    browser_handler.setFormatter(formatter)
    browser_handler.setLevel(logging.INFO)
    logger.addHandler(browser_handler)

    return True


# Set logger
LOGGER = set_logging(LOGGING_NAME)


import matplotlib.pyplot as plt
import numpy as np


def rainbow_fill(size=50):  # simpler way to generate rainbow color
    cmap = plt.get_cmap("jet")
    color_list = []

    for n in range(size):
        color = cmap(n / size)
        color_list.append(
            color[:3]
        )  # might need rounding? (round(x, 3) for x in color)[:3]

    return np.array(color_list)


COLORS = rainbow_fill(80).astype(np.float32).reshape(-1, 3)