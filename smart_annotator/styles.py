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
更新: 2026-09-07 新增主窗口分隔样式（顶部工具栏与画布贴合无空隙；右侧
      Dock 分隔条 6px 透明可拖拽、悬停高亮）；新增右栏列表（旧聚合面板
      objectName 作用域）字号 11px 规则（不影响全局 13px）
更新: 2026-09-07 列表选中色加深（#d4d4d8）并补 QListView 规则；条目 padding 收紧（2px→1px）
更新: 2026-09-07 三分区独立 Dock 化：列表字号 11px 规则的作用域由旧聚合
      面板 objectName 改为三个分区控件（#labelSection/#objectSection
      QListWidget 与 #fileSection QListWidget/QListView），生效面不变
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
/* 条目 padding 收紧：11px 字号下行高约 16px，无跨行重叠 */
QListWidget::item {
    border-radius: 6px;
    padding: 1px 4px;
}
/* 选中态加深（zinc 层次链：#f4f4f5 hover → #e4e4e7 边框 → #d4d4d8 选中）；
   QListView 规则覆盖文件列表（QListView 不匹配 QListWidget 选择器） */
QListWidget::item:selected,
QListView::item:selected {
    background-color: #d4d4d8;
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

/* ===== 主窗口分隔条 ===== */
/* 顶部工具栏（不可拖动）与中央画布之间不留空隙 */
QMainWindow::separator:vertical {
    height: 0;
}
/* 右侧对象面板（Dock）与画布之间的分隔条：透明可拖拽，悬停高亮 */
QMainWindow::separator:horizontal {
    width: 6px;
    background-color: transparent;
}
QMainWindow::separator:horizontal:hover {
    background-color: #d4d4d8;
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

/* ===== 右栏三个列表 Dock（标签/对象/文件分区）列表字号 ===== */
/* 右栏三组列表使用更紧凑的 11px 字号（不影响全局 13px） */
#labelSection QListWidget, #objectSection QListWidget, #fileSection QListWidget, #fileSection QListView {
    font-size: 11px;
}

/* ===== 右栏文件检索框 ===== */
/* 与右栏列表协调的紧凑样式（11px 字号、收窄内边距与高度）；
   边框/聚焦态沿用全局 QLineEdit 规则 */
#fileSearchEdit {
    min-height: 24px;
    padding: 2px 8px;
    font-size: 11px;
}
"""
