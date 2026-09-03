# -*- coding: utf-8 -*-
"""
全局样式表 - GLOBAL_QSS

按 UI 设计文档 §7 设计系统约束：黑白灰主色、12px 圆角、统一边框。
采用全局样式表 + 局部覆盖策略，控件局部样式仅用于按钮/卡片等语义化组件。

设计变量（对应 colors_and_type.css）:
    --background        #fafafa   窗口背景
    --foreground        #18181b   主文字
    --muted-foreground  #71717a   弱化文字
    --border            #e4e4e7   边框
    --radius-md         12px      圆角

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-03 新增 QComboBox 下拉箭头、禁用态与 QMenu 样式（修复下拉按钮不可见、禁用无视觉反馈）
更新: 2026-09-03 新增 QSplitter 分栏拖拽手柄样式（默认透明，悬停高亮）
"""

GLOBAL_QSS = """
/* ===== 基础控件 ===== */
QWidget {
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    color: #18181b;
    font-size: 13px;
}
QMainWindow {
    background-color: #fafafa;
}

/* ===== 输入控件（统一边框 + 圆角 + 聚焦高亮）===== */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    border: 1px solid #e4e4e7;
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 28px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 2px solid #18181b;
}
QComboBox::drop-down {
    border: 0;
    width: 24px;
    border-radius: 6px;
}
QComboBox::drop-down:hover {
    background-color: #f4f4f5;
}
/* 纯 QSS border 三角形绘制下拉箭头（drop-down 去边框后默认箭头消失，需自绘替代）*/
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #71717a;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #e4e4e7;
    border-radius: 8px;
    selection-background-color: #f4f4f5;
    selection-color: #18181b;
    outline: 0;
}

/* ===== 禁用态（灰字 + 浅灰底，明确视觉反馈）===== */
QPushButton:disabled,
QLineEdit:disabled,
QComboBox:disabled,
QSpinBox:disabled,
QDoubleSpinBox:disabled {
    color: #a1a1aa;
    background-color: #f4f4f5;
    border-color: #e4e4e7;
}
QComboBox:disabled::down-arrow {
    border-top-color: #d4d4d8;
}

/* ===== 滚动区域 ===== */
QScrollArea {
    background-color: transparent;
    border: 0;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #d4d4d8;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #a1a1aa;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #d4d4d8;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background: #a1a1aa;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ===== 进度条（药丸形）===== */
/* 读条用中灰色：黑色文字在轨道（#f4f4f5）与读条上均保持可读 */
QProgressBar {
    border: 0;
    border-radius: 999px;
    background-color: #f4f4f5;
    text-align: center;
    min-height: 18px;
    color: #18181b;
    font-size: 12px;
}
QProgressBar::chunk {
    border-radius: 999px;
    background-color: #a1a1aa;
}

/* ===== 日志面板（等宽字体）===== */
QPlainTextEdit {
    background-color: #fafafa;
    border: 1px solid #e4e4e7;
    border-radius: 12px;
    padding: 8px;
}

/* ===== 单选 / 复选 ===== */
QRadioButton, QCheckBox {
    spacing: 6px;
}
QRadioButton::indicator, QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #d4d4d8;
    border-radius: 4px;
    background: #ffffff;
}
QRadioButton::indicator {
    border-radius: 8px;
}
QRadioButton::indicator:checked, QCheckBox::indicator:checked {
    background: #18181b;
    border: 1px solid #18181b;
}

/* ===== 列表 ===== */
QListWidget {
    background-color: #fafafa;
    border: 1px solid #e4e4e7;
    border-radius: 8px;
    padding: 4px;
    outline: 0;
}
QListWidget::item {
    border-radius: 6px;
    padding: 2px 4px;
}
QListWidget::item:selected {
    background-color: #f4f4f5;
    color: #18181b;
}

/* ===== 标签（弱化文字）===== */
QLabel {
    background-color: transparent;
}

/* ===== 分栏拖拽手柄（默认透明，悬停高亮提示可拖）===== */
QSplitter::handle {
    background-color: transparent;
}
QSplitter::handle:hover {
    background-color: #d4d4d8;
    border-radius: 2px;
}
QSplitter::handle:horizontal {
    width: 3px;
}
QSplitter::handle:vertical {
    height: 3px;
}

/* ===== 菜单（白底圆角，禁用项置灰）===== */
QMenu {
    background-color: #ffffff;
    border: 1px solid #e4e4e7;
    border-radius: 8px;
    padding: 4px;
}
/* item 不写 color：继承 QWidget 的 #18181b，避免覆盖下方禁用置灰规则 */
QMenu::item {
    padding: 6px 24px;
    border-radius: 6px;
}
QMenu::item:selected {
    background-color: #f4f4f5;
}
QMenu::item:disabled {
    color: #a1a1aa;
}
QMenu::separator {
    height: 1px;
    background-color: #e4e4e7;
    margin: 4px 8px;
}

/* ===== 工具提示 ===== */
QToolTip {
    background-color: #18181b;
    color: #fafafa;
    border: 0;
    border-radius: 6px;
    padding: 4px 8px;
}
"""
