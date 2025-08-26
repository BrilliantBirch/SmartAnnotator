"""
Description：工具类
Author: Baibinnan
Date: 2025/8/25
LastEdit: 2025/8/25
E-mail: baibinnan@chuanfeng.com
update：

"""

from logging.handlers import TimedRotatingFileHandler
import os
import sys
import logging
import platform

ROOT = os.getcwd()
ASSET = os.path.join(ROOT, "Resources")
LOGGING_NAME = "VAI_E_LabelTool"
MACOS, LINUX, WINDOWS = (platform.system() == x for x in ["Darwin", "Linux", "Windows"])


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


# Set logger
LOGGER = set_logging(LOGGING_NAME)
