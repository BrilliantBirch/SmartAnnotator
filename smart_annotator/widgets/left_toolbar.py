# -*- coding: utf-8 -*-
"""
左侧快捷操作栏组件 - LeftToolbar

经典三栏布局的左栏（参考 labelme / X-Anylabel 风格），纵向排列功能按钮：
    - 文件操作：打开文件夹、保存、另存为
    - 编辑操作：删除选中
    - 自动标注：加载模型、自动标注单张、自动标注全部
    - 标注工具：选择、矩形、点、多边形（互斥可选，含快捷键提示）

按钮点击通过信号对外发射，由主窗口统一处理业务逻辑，
保证工具栏与菜单栏动作共享同一套处理函数。

作者: BaiBinnan
创建日期: 2026-09-02
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
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
            QPushButton:disabled { color: #d4d4d8; }
            """
        )


class LeftToolbar(QWidget):
    """左侧快捷操作栏。

    Signals:
        open_requested: 请求打开文件夹。
        save_requested: 请求保存当前标注。
        save_as_requested: 请求另存为标注。
        delete_requested: 请求删除选中标注。
        load_model_requested: 请求加载推理模型。
        annotate_single_requested: 请求自动标注当前图片。
        annotate_all_requested: 请求自动标注全部图片。
        tool_selected(str): 请求切换标注工具（select/rectangle/point/polygon）。
    """

    open_requested = Signal()
    save_requested = Signal()
    save_as_requested = Signal()
    delete_requested = Signal()
    load_model_requested = Signal()
    annotate_single_requested = Signal()
    annotate_all_requested = Signal()
    tool_selected = Signal(str)

    def __init__(self, parent=None):
        """初始化工具栏布局与按钮。"""
        super().__init__(parent)
        self.setFixedWidth(150)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 12, 8, 12)
        root.setSpacing(4)

        # ===== 文件操作 =====
        self.btn_open = _ToolBarButton("打开文件夹", "Ctrl+O")
        self.btn_open.clicked.connect(self.open_requested.emit)
        self.btn_save = _ToolBarButton("保存", "Ctrl+S")
        self.btn_save.clicked.connect(self.save_requested.emit)
        self.btn_save_as = _ToolBarButton("另存为", "Ctrl+Shift+S")
        self.btn_save_as.clicked.connect(self.save_as_requested.emit)
        self.btn_delete = _ToolBarButton("删除选中", "Delete")
        self.btn_delete.clicked.connect(self.delete_requested.emit)

        # ===== 自动标注 =====
        self.btn_load_model = _ToolBarButton("加载模型")
        self.btn_load_model.clicked.connect(self.load_model_requested.emit)
        self.btn_annotate_single = _ToolBarButton("自动标注单张")
        self.btn_annotate_single.clicked.connect(self.annotate_single_requested.emit)
        self.btn_annotate_all = _ToolBarButton("自动标注全部")
        self.btn_annotate_all.clicked.connect(self.annotate_all_requested.emit)

        # ===== 标注工具（互斥可选）=====
        self._tool_buttons = {}
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)

        root.addWidget(self.btn_open)
        root.addWidget(self.btn_save)
        root.addWidget(self.btn_save_as)
        root.addWidget(self.btn_delete)
        root.addWidget(self._separator())
        root.addWidget(self.btn_load_model)
        root.addWidget(self.btn_annotate_single)
        root.addWidget(self.btn_annotate_all)
        root.addWidget(self._separator())

        for tool, text in (
            (TOOL_SELECT, "选择"),
            (TOOL_RECTANGLE, "矩形"),
            (TOOL_POINT, "点"),
            (TOOL_POLYGON, "多边形"),
        ):
            btn = _ToolBarButton(text)
            btn.setCheckable(True)
            self._tool_group.addButton(btn)
            self._tool_buttons[tool] = btn
            btn.clicked.connect(lambda checked=False, t=tool: self.tool_selected.emit(t))
            root.addWidget(btn)

        # 默认选中"选择"工具
        self._tool_buttons[TOOL_SELECT].setChecked(True)

        root.addStretch()

    def _separator(self) -> QFrame:
        """构造一条分组分隔线。

        Returns:
            水平分隔线控件。
        """
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("QFrame { color: #e4e4e7; }")
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

    def set_annotate_enabled(self, enabled: bool) -> None:
        """启用/禁用自动标注相关按钮（无模型时禁用）。

        Args:
            enabled: 是否可用。
        """
        self.btn_annotate_single.setEnabled(enabled)
        self.btn_annotate_all.setEnabled(enabled)