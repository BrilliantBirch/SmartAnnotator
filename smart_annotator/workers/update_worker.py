# -*- coding: utf-8 -*-
"""
在线更新后台线程 - UpdateCheckWorker / UpdateDownloadWorker

检查更新：后台请求 Gitee 最新 Release 并与当前版本比较，避免在 UI
线程同步发起网络请求导致界面卡死；发现新版本经 update_found 信号
携带 ReleaseInfo 回传主窗口。

下载安装器：后台分块下载在线安装器 exe 到临时目录，经
progress_updated（0-1 浮点）驱动进度对话框，支持停止中断。

作者: BaiBinnan
创建日期: 2026-09-09
"""

import tempfile
from pathlib import Path

from PySide6.QtCore import Signal, QMutexLocker

from smart_annotator import __version__
from smart_annotator.core.updater import (
    ReleaseInfo,
    UpdaterError,
    download_file,
    fetch_latest_release,
    parse_version,
)
from smart_annotator.utils import LOGGER
from .base_worker import BaseWorker


class UpdateCheckWorker(BaseWorker):
    """检查更新线程。

    Signals:
        update_found(object): 发现新版本，参数为 ReleaseInfo。
        up_to_date(): 当前已是最新版本。
    """

    update_found = Signal(object)
    up_to_date = Signal()

    def __init__(self):
        """初始化检查更新线程（任务参数固定，无需 set_task）。"""
        super().__init__()

    def run(self) -> None:
        """线程主逻辑：请求最新 Release 并与 __version__ 比较。

        网络失败 / 响应异常经 error_occurred 回传（由 UI 按 quiet 标志
        决定是否弹窗）；线程被停止时不发射任何结果。
        """
        try:
            with QMutexLocker(self.mutex):
                if self.stopped:
                    return

            # 请求最新 Release（网络 IO 在后台线程执行）
            info = fetch_latest_release()

            # 停止检查：被停止后不再发射过期结果
            with QMutexLocker(self.mutex):
                if self.stopped:
                    return

            # 版本比较：远端 tag 版本大于当前版本才提示更新
            current = parse_version(__version__)
            if info.version > current:
                self.update_found.emit(info)
            else:
                self.up_to_date.emit()

        except UpdaterError as e:
            LOGGER.warning(f"检查更新失败: {e}")
            self.error_occurred.emit(str(e))
        except Exception as e:  # 兜底：任何异常都不允许拖垮后台线程
            LOGGER.error(f"检查更新异常: {e}")
            self.error_occurred.emit(f"检查更新异常: {e}")
        finally:
            self.task_finished.emit()
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False


class UpdateDownloadWorker(BaseWorker):
    """下载在线安装器线程。

    Signals:
        download_done(str): 下载完成，参数为安装器本地路径字符串。
    """

    download_done = Signal(str)

    def __init__(self):
        """初始化下载线程。"""
        super().__init__()
        self.url: str = ""
        self.dest: Path = Path(tempfile.gettempdir()) / "BrilliantAnnotator_OnlineSetup.exe"

    def set_task(self, url: str, dest: Path) -> None:
        """设置下载任务参数。

        Args:
            url: 在线安装器下载 URL。
            dest: 本地保存路径（临时目录）。
        """
        self.url = url
        self.dest = Path(dest)

    def run(self) -> None:
        """线程主逻辑：分块下载安装器并上报进度（可中断）。

        下载完成经 download_done 发射本地路径；被取消/网络失败经
        error_occurred 回传；进度经 progress_updated（0-1）上报。
        """
        try:
            with QMutexLocker(self.mutex):
                if self.stopped:
                    return

            self.progress_desc.emit("正在下载更新安装器...")

            # 分块下载：进度回调转 0-1 浮点，中断检查走 stopped 标志
            download_file(
                self.url,
                self.dest,
                progress_cb=lambda done, total: (
                    self.progress_updated.emit(done / total if total else 0.0)
                ),
                stop_check=lambda: self.stopped,
            )

            # 停止检查：被停止后不再发射结果
            with QMutexLocker(self.mutex):
                if self.stopped:
                    return

            self.download_done.emit(str(self.dest))

        except UpdaterError as e:
            LOGGER.warning(f"下载更新安装器失败: {e}")
            self.error_occurred.emit(str(e))
        except Exception as e:  # 兜底：任何异常都不允许拖垮后台线程
            LOGGER.error(f"下载更新安装器异常: {e}")
            self.error_occurred.emit(f"下载更新安装器异常: {e}")
        finally:
            self.task_finished.emit()
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False
