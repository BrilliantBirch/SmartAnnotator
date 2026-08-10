# -*- coding: utf-8 -*-
"""
主窗口 - MainWindow

按 UI 设计文档 §3/§6 与计划 §2.7 组装应用主界面：
- 无固定尺寸：启动取屏幕可用区 80%，最小 960×640
- TopBar（应用品牌 + 状态徽章）
- ContentStack（QStackedWidget 三页：欢迎/格式转换/自动标注）
- Sidebar（宽≥768px）/ BottomTabBar（窄屏）互斥导航
- resizeEvent 在 768px 阈值切换导航形态
- closeEvent：停止运行中 worker 并等待退出
- 初始化 ConvertWorker + AnnotationWorker，连接信号一次

作者: BaiBinnan
创建日期: 2026-08-10
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QLabel,
    QPushButton,
    QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from . import __appname__, __version__
from .styles import GLOBAL_QSS
from .pages import WelcomePage, ConvertPage, AnnotatePage
from .workers.convert_worker import ConvertWorker
from .workers.annotate_worker import AnnotationWorker

# 侧边栏与底部标签栏切换的宽度阈值（px）
SIDEBAR_THRESHOLD = 768


class NavButton(QPushButton):
    """导航按钮 - 侧边栏/底部标签栏共用。

    选中态高亮（深色背景），未选中态透明。扁平无圆角，适配两种容器。

    Attributes:
        page_index: 点击后切换到的页面索引。
    """

    def __init__(self, text: str, page_index: int, parent=None):
        """初始化导航按钮。

        Args:
            text: 按钮文字。
            page_index: 目标页面索引。
            parent: 父控件。
        """
        super().__init__(text, parent)
        self.page_index = page_index
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: 0;
                border-radius: 8px;
                padding: 10px 16px;
                text-align: left;
                font-weight: 500;
                color: #71717a;
            }
            QPushButton:hover { background-color: #f4f4f5; color: #18181b; }
            QPushButton:checked {
                background-color: #18181b;
                color: #fafafa;
            }
        """
        )


class MainWindow(QMainWindow):
    """应用主窗口 - 组装 TopBar + 导航 + 三页内容栈。

    Attributes:
        stack: 页面栈（欢迎/格式转换/自动标注）。
        sidebar: 桌面端侧边栏（宽≥768px 显示）。
        bottom_bar: 窄屏底部标签栏（宽<768px 显示）。
        convert_worker: 格式转换后台线程。
        annotate_worker: 自动标注后台线程。
    """

    def __init__(self):
        """初始化主窗口，构建所有界面元素并连接信号。"""
        super().__init__()
        self.setWindowTitle(__appname__)
        self.setMinimumSize(960, 640)

        # 启动尺寸：屏幕可用区 80%
        screen = self.screen().availableGeometry()
        self.resize(int(screen.width() * 0.8), int(screen.height() * 0.8))

        # 后台线程（生命周期与窗口一致）
        self.convert_worker = ConvertWorker()
        self.annotate_worker = AnnotationWorker()

        # 构建界面
        self._build_ui()
        self._connect_signals()

        # 应用全局样式
        self.setStyleSheet(GLOBAL_QSS)

        # 默认显示欢迎页
        self.stack.setCurrentIndex(0)
        self._update_nav_state(0)

    # -------------------------- 界面构建 --------------------------
    def _build_ui(self) -> None:
        """构建主窗口布局：TopBar + (Sidebar + ContentStack) / BottomTabBar。"""
        central = QWidget()
        self.setCentralWidget(central)
        self._root_layout = QVBoxLayout(central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        # TopBar
        self._build_topbar()

        # 主体：侧边栏 + 内容栈
        self.body_widget = QWidget()
        self._body_layout = QHBoxLayout(self.body_widget)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)

        # 侧边栏（桌面端）
        self.sidebar = self._build_sidebar()
        self._body_layout.addWidget(self.sidebar)

        # 内容栈
        self.stack = QStackedWidget()
        self.welcome_page = WelcomePage()
        self.convert_page = ConvertPage()
        self.annotate_page = AnnotatePage()
        self.stack.addWidget(self.welcome_page)
        self.stack.addWidget(self.convert_page)
        self.stack.addWidget(self.annotate_page)
        self._body_layout.addWidget(self.stack, 1)

        self._root_layout.addWidget(self.body_widget, 1)

        # 底部标签栏（窄屏）
        self.bottom_bar = self._build_bottom_bar()
        self._root_layout.addWidget(self.bottom_bar)

    def _build_topbar(self) -> None:
        """构建顶部栏：应用品牌 + 状态徽章。"""
        topbar = QFrame()
        topbar.setFixedHeight(56)
        topbar.setStyleSheet(
            "QFrame { background-color: #ffffff; border-bottom: 1px solid #e4e4e7; }"
        )
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(8)

        # 应用品牌
        brand = QLabel(__appname__)
        brand.setStyleSheet("font-size: 16px; font-weight: 700; color: #18181b; border: 0;")
        layout.addWidget(brand)
        layout.addStretch()

        # 状态徽章（版本号）
        self.status_badge = QLabel(f"v{__version__}")
        self.status_badge.setStyleSheet(
            "background-color: #f4f4f5; color: #71717a; border-radius: 10px;"
            "padding: 2px 10px; font-size: 12px; border: 0;"
        )
        layout.addWidget(self.status_badge)

        self._root_layout.addWidget(topbar)

    def _build_sidebar(self) -> QWidget:
        """构建侧边栏（桌面端垂直导航）。"""
        sidebar = QFrame()
        sidebar.setFixedWidth(180)
        sidebar.setStyleSheet(
            "QFrame { background-color: #ffffff; border-right: 1px solid #e4e4e7; }"
        )
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(4)

        self.sidebar_buttons = []
        labels = ["欢迎", "格式转换", "自动标注"]
        for idx, text in enumerate(labels):
            btn = NavButton(text, idx)
            btn.clicked.connect(lambda checked=False, i=idx: self._navigate_to(i))
            layout.addWidget(btn)
            self.sidebar_buttons.append(btn)

        layout.addStretch()
        return sidebar

    def _build_bottom_bar(self) -> QWidget:
        """构建底部标签栏（窄屏水平导航）。"""
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet(
            "QFrame { background-color: #ffffff; border-top: 1px solid #e4e4e7; }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        self.bottom_buttons = []
        labels = ["欢迎", "格式转换", "自动标注"]
        for idx, text in enumerate(labels):
            btn = NavButton(text, idx)
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: transparent;
                    border: 0;
                    border-radius: 8px;
                    padding: 8px 12px;
                    font-weight: 500;
                    color: #71717a;
                }
                QPushButton:hover { background-color: #f4f4f5; color: #18181b; }
                QPushButton:checked {
                    background-color: #18181b;
                    color: #fafafa;
                }
            """
            )
            btn.clicked.connect(lambda checked=False, i=idx: self._navigate_to(i))
            layout.addWidget(btn)
            self.bottom_buttons.append(btn)

        return bar

    # -------------------------- 信号连接 --------------------------
    def _connect_signals(self) -> None:
        """连接页面跳转信号与 worker 信号。"""
        # 欢迎页按钮 → 跳转
        self.welcome_page.format_requested.connect(lambda: self._navigate_to(1))
        self.welcome_page.annotate_requested.connect(lambda: self._navigate_to(2))

        # 绑定 worker 到对应页面
        self.convert_page.set_worker(self.convert_worker)
        self.annotate_page.set_worker(self.annotate_worker)

        # 任务开始/结束时禁用/恢复导航
        self.convert_page.task_started.connect(self._on_task_started)
        self.convert_page.task_finished.connect(self._on_task_finished)
        self.annotate_page.task_started.connect(self._on_task_started)
        self.annotate_page.task_finished.connect(self._on_task_finished)

    # -------------------------- 导航 --------------------------
    def _navigate_to(self, index: int) -> None:
        """切换到指定页面并同步导航按钮选中态。

        Args:
            index: 目标页面索引（0=欢迎, 1=格式转换, 2=自动标注）。
        """
        self.stack.setCurrentIndex(index)
        self._update_nav_state(index)

    def _update_nav_state(self, index: int) -> None:
        """同步侧边栏与底部标签栏的选中态。

        Args:
            index: 当前页面索引。
        """
        for btn in self.sidebar_buttons:
            btn.setChecked(btn.page_index == index)
        for btn in self.bottom_buttons:
            btn.setChecked(btn.page_index == index)

    def _on_task_started(self) -> None:
        """任务开始：禁用导航按钮，防止切换页面。"""
        for btn in self.sidebar_buttons + self.bottom_buttons:
            btn.setEnabled(False)

    def _on_task_finished(self) -> None:
        """任务结束：恢复导航按钮。"""
        for btn in self.sidebar_buttons + self.bottom_buttons:
            btn.setEnabled(True)

    # -------------------------- 响应式 --------------------------
    def resizeEvent(self, event) -> None:
        """窗口尺寸变化时在 768px 阈值切换侧边栏/底部标签栏。

        Args:
            event: 尺寸变化事件。
        """
        super().resizeEvent(event)
        use_sidebar = self.width() >= SIDEBAR_THRESHOLD
        self.sidebar.setVisible(use_sidebar)
        self.bottom_bar.setVisible(not use_sidebar)

    # -------------------------- 关闭处理 --------------------------
    def closeEvent(self, event) -> None:
        """关闭窗口时停止运行中的 worker 并等待其退出。

        Args:
            event: 关闭事件。
        """
        stopped_any = False
        for worker in (self.convert_worker, self.annotate_worker):
            if worker.isRunning():
                worker.stop()
                stopped_any = True
        if stopped_any:
            # 等待线程退出（最多 3 秒）
            self.convert_worker.wait(3000)
            self.annotate_worker.wait(3000)
        event.accept()

    # -------------------------- 图标 --------------------------
    def set_window_icon(self, icon: QIcon) -> None:
        """设置窗口图标（由 main.py 调用，兼容打包路径）。

        Args:
            icon: 已构造的 QIcon。
        """
        self.setWindowIcon(icon)
