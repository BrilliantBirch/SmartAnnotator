# -*- coding: utf-8 -*-
"""
日志管理器 — 统一日志记录、轮转、清理（纯 Python，无 Qt 依赖）

移植自 VAI_MemGenerator/common/log/logger.py 的 LogManager（文件轮转+过期清理+毫秒格式化）。
Qt 界面推送处理器（QtLogHandler）位于 qt_logger.py，需 PySide6，仅在 GUI 使用时导入，
保证算法层可无头测试（不依赖 PySide6）。

作者: BaiBinnan
创建日期: 2026-08-10
"""

import logging
import logging.handlers
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional


# 日志名称（影响日志文件名与 logger 名称）
LOGGING_NAME = "VAI_E_SmartAnnotator"


class _StreamRedirector:
    """将 stdout/stderr 重定向到日志系统的内部类。"""

    def __init__(self, logger: logging.Logger, level: int, original_stream):
        self._logger = logger
        self._level = level
        self._original_stream = original_stream
        self._lock = threading.Lock()

    def write(self, message: str):
        if message and message.strip():
            with self._lock:
                self._logger.log(self._level, message.rstrip())

    def flush(self):
        pass

    def fileno(self):
        return self._original_stream.fileno()

    def isatty(self):
        return False


class _CleanupHandler(logging.handlers.TimedRotatingFileHandler):
    """带过期清理功能的定时轮转日志处理器。"""

    def __init__(self, filename, when="midnight", interval=1, backup_count=7,
                 retention_days=30, encoding="utf-8"):
        self._retention_days = retention_days
        super().__init__(filename, when=when, interval=interval,
                         backupCount=backup_count, encoding=encoding)

    def doRollover(self):
        super().doRollover()
        self._cleanup_expired()

    def _cleanup_expired(self):
        """清理超过保留天数的日志文件。"""
        log_dir = os.path.dirname(self.baseFilename)
        base_name = os.path.basename(self.baseFilename)
        cutoff_time = time.time() - self._retention_days * 86400
        for entry in os.scandir(log_dir):
            if not entry.is_file():
                continue
            if not entry.name.startswith(base_name):
                continue
            if entry.stat().st_mtime < cutoff_time:
                try:
                    os.remove(entry.path)
                except OSError:
                    pass


class _MillisecondFormatter(logging.Formatter):
    """支持毫秒级时间戳的日志格式化器。

    重写 formatTime，在 strftime 基础上手动追加 3 位毫秒（冒号分隔）。
    输出示例: 2026-08-10 12:00:00:123
    """

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        s = time.strftime(datefmt or "%Y-%m-%d %H:%M:%S", ct)
        return f"{s}:{int(record.msecs):03d}"


class LogManager:
    """日志管理器 — 统一管理应用的日志输出。

    功能：自定义日志名称/存储路径/保留时间/格式；stdout/stderr 重定向；
    按天轮转；自动清理过期日志。
    """

    DEFAULT_FORMAT = (
        "[%(asctime)s] [%(levelname)-8s] [%(threadName)-12s] "
        "%(name)s:%(lineno)d - %(message)s"
    )
    DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        log_name: str = LOGGING_NAME,
        log_dir: str = "./Log",
        log_level: int = logging.DEBUG,
        retention_days: int = 30,
        rotate_when: str = "midnight",
        rotate_interval: int = 1,
        backup_count: int = 30,
        log_format: Optional[str] = None,
        date_format: Optional[str] = None,
        console_output: bool = True,
        redirect_stdout: bool = True,
        redirect_stderr: bool = True,
    ):
        """初始化日志管理器。

        Args:
            log_name: 日志名称，影响日志文件名。
            log_dir: 日志存储目录。
            log_level: 日志级别。
            retention_days: 日志保留天数，超期自动删除。
            rotate_when: 轮转触发条件（"midnight"/"H"/"D"）。
            rotate_interval: 轮转间隔。
            backup_count: 保留的轮转文件数量。
            log_format: 自定义日志格式字符串。
            date_format: 自定义日期格式字符串。
            console_output: 是否同时输出到控制台。
            redirect_stdout: 是否重定向 stdout 到日志。
            redirect_stderr: 是否重定向 stderr 到日志。
        """
        self._log_name = log_name
        self._log_dir = Path(log_dir)
        self._log_level = log_level
        self._retention_days = retention_days
        self._rotate_when = rotate_when
        self._rotate_interval = rotate_interval
        self._backup_count = backup_count
        self._log_format = log_format or self.DEFAULT_FORMAT
        self._date_format = date_format or self.DEFAULT_DATE_FORMAT
        self._console_output = console_output
        self._redirect_stdout = redirect_stdout
        self._redirect_stderr = redirect_stderr

        self._redirector_stdout: Optional[_StreamRedirector] = None
        self._redirector_stderr: Optional[_StreamRedirector] = None
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr

        self._logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """配置并返回日志记录器。"""
        self._log_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(self._log_name)
        logger.setLevel(self._log_level)
        logger.handlers.clear()

        formatter = _MillisecondFormatter(self._log_format, self._date_format)

        file_handler = _CleanupHandler(
            filename=str(self._log_dir / f"{self._log_name}.log"),
            when=self._rotate_when,
            interval=self._rotate_interval,
            backup_count=self._backup_count,
            retention_days=self._retention_days,
            encoding="utf-8",
        )
        file_handler.setLevel(self._log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        if self._console_output and self._original_stdout is not None:
            console_handler = logging.StreamHandler(self._original_stdout)
            console_handler.setLevel(self._log_level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        return logger

    def get_logger(self) -> logging.Logger:
        """获取配置好的日志记录器。"""
        return self._logger

    def enable_redirect(self) -> None:
        """启用 stdout/stderr 重定向到日志。"""
        if self._redirect_stdout and self._redirector_stdout is None:
            self._redirector_stdout = _StreamRedirector(
                self._logger, logging.INFO, self._original_stdout
            )
            sys.stdout = self._redirector_stdout
        if self._redirect_stderr and self._redirector_stderr is None:
            self._redirector_stderr = _StreamRedirector(
                self._logger, logging.ERROR, self._original_stderr
            )
            sys.stderr = self._redirector_stderr

    def disable_redirect(self) -> None:
        """恢复 stdout/stderr 原始输出。"""
        if self._redirector_stdout is not None:
            sys.stdout = self._original_stdout
            self._redirector_stdout = None
        if self._redirector_stderr is not None:
            sys.stderr = self._original_stderr
            self._redirector_stderr = None

    def set_level(self, level: int) -> None:
        """动态修改日志级别。"""
        self._log_level = level
        self._logger.setLevel(level)
        for handler in self._logger.handlers:
            handler.setLevel(level)

    def close(self) -> None:
        """关闭日志管理器，清理资源。"""
        self.disable_redirect()
        for handler in self._logger.handlers:
            handler.close()
            self._logger.removeHandler(handler)


# ===== 模块级日志记录器 =====
# 打包后（--windowed）无控制台，关闭 console_output；开发模式开启
_is_frozen = getattr(sys, "frozen", False)
if _is_frozen:
    _log_dir = os.path.join(os.path.dirname(sys.executable), "Log")
else:
    # smart_annotator/utils/logger.py → 上溯三级为项目根
    _log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "Log",
    )
_log_manager = LogManager(
    log_name=LOGGING_NAME,
    log_dir=_log_dir,
    console_output=not _is_frozen,
    redirect_stdout=not _is_frozen,
    redirect_stderr=not _is_frozen,
)
LOGGER = _log_manager.get_logger()
