# -*- coding: utf-8 -*-
"""
BrilliantAnnotator - 程序入口

启动 PySide6 GUI 主窗口，提供 LabelMe↔YOLO 格式转换与 ONNX/TensorRT 自动标注功能。

支持两种运行方式：
    - 开发模式: python -m smart_annotator.main
    - 打包模式: BrilliantAnnotator.exe（PyInstaller 处理路径）

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-04 启动时安装 Qt 消息过滤器（抑制可编辑 QComboBox 触发的
      QFont::setPointSize(-1) 无害警告刷屏）
"""
import ctypes
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path（开发模式），打包后由 PyInstaller 处理
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from smart_annotator.app import MainWindow
from smart_annotator.utils.paths import resource_path
from smart_annotator.utils.qt_logger import install_qt_message_filter


def _resolve_icon_path() -> Path:
    """解析应用图标路径（兼容开发与打包两种模式）。

    打包模式下图标作为数据文件打包，位于 PyInstaller 的 _MEIPASS 内容目录；
    开发模式下使用 build 目录下的 app.ico。

    Returns:
        图标文件路径。
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app.ico"
    return Path(resource_path("app.ico"))


def main() -> None:
    """程序入口 — 创建 QApplication 并显示主窗口。"""
    # 尽早安装 Qt 消息过滤器（抑制 QSS px 字号下可编辑 QComboBox 的
    # QFont::setPointSize 无害警告，其余 Qt 消息保持默认输出）
    install_qt_message_filter()

    app = QApplication(sys.argv)
    app.setApplicationName("BrilliantAnnotator")
    app.setOrganizationName("BrilliantBirch")

    # 设置窗口/任务栏图标（Windows 下绑定 AppUserModelID，避免任务栏无图标/分组错误）
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "BrilliantBirch.BrilliantAnnotator"
            )
        except (AttributeError, OSError):
            pass  # 非 Windows 或设置失败时忽略，不影响主功能

    icon_path = _resolve_icon_path()
    if icon_path.exists():
        icon = QIcon(str(icon_path))
        app.setWindowIcon(icon)

    window = MainWindow()
    if icon_path.exists():
        window.set_window_icon(QIcon(str(icon_path)))
    # window.show()
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
