# -*- coding: utf-8 -*-
"""
快捷操作工具栏组件 - LeftToolbar

菜单栏下方的水平工具栏（QToolBar），两个分组从左到右排列，
分组之间以竖分隔线区隔：
    - 文件操作：打开文件夹、打开文件、保存、另存为、删除选中、删除图片文件
    - 标注工具：编辑（V/Ctrl+E）、矩形、点、多边形（互斥可选，含快捷键提示）

自动标注入口（加载模型/标注当前图片/标注所有图片/标注视频）统一收敛到
主窗口"工具"菜单，不再提供工具栏按钮（入口唯一）。

容器为 QToolBar（不可拖动/浮动）：高度固定、宽度随按钮内容自适应，
窗口过窄时自带"»"溢出折叠（放不下的按钮收进弹出菜单，文字不丢失）。

按钮点击通过信号对外发射，由主窗口统一处理业务逻辑，
保证工具栏与菜单栏动作共享同一套处理函数。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-03 "选择"工具更名为"编辑"，移除预览模式按钮
更新: 2026-09-03 移除"删除标注文件"按钮与 delete_file_requested 信号（Delete 改由主窗口按焦点路由）
更新: 2026-09-03 按钮禁用态增强（灰字 + 浅灰底，明确视觉反馈）
更新: 2026-09-03 标注按钮重命名（标注当前图片/标注所有图片）并新增
      "标注视频"按钮（annotate_video_requested 信号）
更新: 2026-09-07 布局水平化：基类 QWidget→QToolBar（关闭拖动/浮动），固定宽 150
      改为固定高 52px、宽度自适应；分组标题改为竖分隔线（含工具提示/无障碍名称），
      按钮横向排列并以末端弹性占位收尾，利用 QToolBar 自带"»"溢出折叠；对外信号与方法不变
更新: 2026-09-07 入口唯一化：移除"自动标注"分组（btn_load_model/
      btn_annotate_single/btn_annotate_all/btn_annotate_video 四个按钮、
      对应 4 个信号与 set_annotate_enabled 方法），自动标注入口统一收敛
      到主窗口"工具"菜单
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QToolBar,
    QPushButton,
    QButtonGroup,
    QFrame,
    QSizePolicy,
)

# 标注工具名常量（与 Canvas.set_tool 的参数一致）
TOOL_SELECT = "select"
TOOL_RECTANGLE = "rectangle"
TOOL_POINT = "point"
TOOL_POLYGON = "polygon"

# 工具按钮的快捷键提示（显示在 tooltip 中）
_TOOL_SHORTCUT_HINTS = {
    TOOL_SELECT: "V / Ctrl+E",
    TOOL_RECTANGLE: "R",
    TOOL_POINT: "P",
    TOOL_POLYGON: "G",
}


class _ToolBarButton(QPushButton):
    """工具栏按钮 - 统一紧凑样式（黑白灰、左对齐）。"""

    def __init__(self, text: str, shortcut: str = "", parent=None):
        """初始化工具栏按钮。

        Args:
            text: 按钮文字（含快捷键提示后缀）。
            shortcut: 快捷键说明（显示在 tooltip 中）。
            parent: 父控件。
        """
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if shortcut:
            self.setToolTip(f"{text}（{shortcut}）")
        self.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: 0;
                border-radius: 8px;
                padding: 10px 14px;
                text-align: left;
                font-weight: 500;
                color: #3f3f46;
            }
            QPushButton:hover { background-color: #f4f4f5; color: #18181b; }
            QPushButton:pressed { background-color: #e4e4e7; }
            QPushButton:checked {
                background-color: #18181b;
                color: #fafafa;
            }
            QPushButton:disabled {
                background-color: #f4f4f5;
                color: #a1a1aa;
            }
            """
        )


class LeftToolbar(QToolBar):
    """快捷操作工具栏（水平排列，供主窗口放置于菜单栏下方）。

    Signals:
        open_requested: 请求打开文件夹。
        open_file_requested: 请求打开单个图片/标注文件。
        save_requested: 请求保存当前标注。
        save_as_requested: 请求另存为标注。
        delete_requested: 请求删除选中标注（形状）。
        delete_image_requested: 请求删除当前图片及其标注文件（Shift+Delete）。
        tool_selected(str): 请求切换标注工具（select/rectangle/point/polygon）。
    """

    open_requested = Signal()
    open_file_requested = Signal()
    save_requested = Signal()
    save_as_requested = Signal()
    delete_requested = Signal()
    delete_image_requested = Signal()
    tool_selected = Signal(str)

    def __init__(self, parent=None):
        """初始化水平工具栏布局与按钮。"""
        super().__init__(parent)
        # ===== 工具栏形态：不可拖动/浮动，固定高度、宽度随内容自适应 =====
        self.setMovable(False)
        self.setFloatable(False)
        self.setFixedHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # 扁平外观 + 紧凑间距（不绘制原生工具栏边框/渐变，与原透明 QWidget 底色一致）
        self.setStyleSheet(
            "QToolBar { spacing: 2px; padding: 4px 8px; "
            "background: transparent; border: 0; }"
        )

        # ===== 文件操作 =====
        self.btn_open = _ToolBarButton("打开文件夹", "Ctrl+O")
        self.btn_open.clicked.connect(self.open_requested.emit)
        self.btn_open_file = _ToolBarButton("打开文件", "Ctrl+Shift+O")
        self.btn_open_file.clicked.connect(self.open_file_requested.emit)
        self.btn_save = _ToolBarButton("保存", "Ctrl+S")
        self.btn_save.clicked.connect(self.save_requested.emit)
        self.btn_save_as = _ToolBarButton("另存为", "Ctrl+Shift+S")
        self.btn_save_as.clicked.connect(self.save_as_requested.emit)
        self.btn_delete = _ToolBarButton("删除选中")
        self.btn_delete.clicked.connect(self.delete_requested.emit)
        self.btn_delete_image = _ToolBarButton("删除图片文件", "Shift+Delete")
        self.btn_delete_image.clicked.connect(self.delete_image_requested.emit)

        # ===== 标注工具（互斥可选）=====
        self._tool_buttons = {}
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)

        # ===== 横向加入工具栏：文件操作分组 =====
        for btn in (
            self.btn_open,
            self.btn_open_file,
            self.btn_save,
            self.btn_save_as,
            self.btn_delete,
            self.btn_delete_image,
        ):
            self.addWidget(btn)

        # 分组分隔：文件操作 | 标注工具
        self.addWidget(self._separator("文件操作 | 标注工具"))

        # ===== 横向加入工具栏：标注工具分组 =====
        for tool, text in (
            (TOOL_SELECT, "编辑"),
            (TOOL_RECTANGLE, "矩形"),
            (TOOL_POINT, "点"),
            (TOOL_POLYGON, "多边形"),
        ):
            btn = _ToolBarButton(text, _TOOL_SHORTCUT_HINTS.get(tool, ""))
            btn.setCheckable(True)
            self._tool_group.addButton(btn)
            self._tool_buttons[tool] = btn
            btn.clicked.connect(lambda checked=False, t=tool: self.tool_selected.emit(t))
            self.addWidget(btn)

        # 默认选中"编辑"工具（编辑模式：拖拽/端点缩放/多选）
        self._tool_buttons[TOOL_SELECT].setChecked(True)

        # ===== 末端水平弹性留白：按钮整体靠左，多余空间由占位控件吸收 =====
        # （窗口过窄时占位先收缩为 0，仍不足则触发 QToolBar 自带"»"溢出折叠）
        self._tail_stretch = QWidget()
        self._tail_stretch.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.addWidget(self._tail_stretch)

    def _separator(self, group_tip: str = "") -> QFrame:
        """构造一条分组竖分隔线（横向排列时替代原纵向分组标题/横线）。

        Args:
            group_tip: 相邻分组说明，作为分隔线的工具提示与无障碍名称。

        Returns:
            竖直分隔线控件。
        """
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet("QFrame { color: #e4e4e7; }")
        line.setFixedSize(2, 26)
        if group_tip:
            line.setToolTip(group_tip)
            line.setAccessibleName(f"分组分隔线：{group_tip}")
        return line

    def current_tool(self) -> str:
        """返回当前选中的标注工具名。"""
        for tool, btn in self._tool_buttons.items():
            if btn.isChecked():
                return tool
        return TOOL_SELECT

    def set_tool(self, tool: str) -> None:
        """程序化选中指定工具按钮（供菜单栏动作联动）。

        Args:
            tool: 工具名（select/rectangle/point/polygon）。
        """
        btn = self._tool_buttons.get(tool)
        if btn is not None:
            btn.setChecked(True)

    def set_edit_enabled(self, enabled: bool) -> None:
        """统一启用/禁用所有编辑功能（保存/删除/标注工具）。

        主窗口在校验工作目录（未打开文件夹或目录下无图像）后调用，禁用
        或恢复与标注编辑相关的全部按钮，避免对空画布执行无效编辑。

        Args:
            enabled: 是否可用。
        """
        self.btn_save.setEnabled(enabled)
        self.btn_save_as.setEnabled(enabled)
        self.btn_delete.setEnabled(enabled)
        for btn in self._tool_buttons.values():
            btn.setEnabled(enabled)

    def set_file_ops_enabled(self, enabled: bool) -> None:
        """启用/禁用文件删除相关按钮（有工作文件时可用）。

        Args:
            enabled: 是否可用。
        """
        self.btn_delete_image.setEnabled(enabled)
