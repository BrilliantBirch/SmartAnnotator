# -*- coding: utf-8 -*-
"""
快捷操作工具栏组件 - LeftToolbar

菜单栏下方的水平工具栏（QToolBar），两个分组从左到右排列，
分组之间以竖分隔线区隔，全部按钮为图标按钮（QPainter 程序化矢量图标，
语义保留在 tooltip 与 accessibleName）：
    - 文件操作：打开文件夹、打开文件、保存、另存为、删除选中、删除图片文件、适应窗口
    - 标注工具：编辑（V/Ctrl+E）、矩形、点、多边形、感知区（互斥可选，含快捷键提示）

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
更新: 2026-09-07 按钮图标化：新增 QPainter 程序化矢量图标（_build_icon，
      三态配色 Normal 灰 / Active 深 / On 反白，与 QSS checked 深底一致），
      全部按钮以图标替代文字（语义保留在 tooltip 与 accessibleName），
      按钮改为紧凑方形，工具栏高度与溢出折叠行为不变
更新: 2026-09-07 补设 objectName（leftToolBar）：修复 QMainWindow.saveState
      因工具栏缺少 objectName 而告警且布局无法恢复的问题
更新: 2026-09-08 新增"适应窗口"按钮（fit 图标四角括号 + 中心矩形、
      fit_requested 信号，置于文件操作组末尾），并新增
      refresh_shortcut_hints 方法：主窗口快捷键应用/自定义改键后调用，
      同步各按钮 tooltip 的快捷键提示（覆盖 Ctrl+0 等默认占位提示）
更新: 2026-09-11 新增"OCR 仅识别"checkable 开关按钮（rec_only 图标虚线
      框 + A 字，独立于绘制互斥组，默认隐藏由主窗口按任务类型显隐）；
      新增 rec_only_toggled 信号与 set_rec_only_visible/
      set_rec_only_checked 同步方法；tooltip 随快捷键绑定与启用状态刷新
更新: 2026-09-17 新增"感知区"工具按钮（TOOL_ROI，感知区/roi 图标：
      虚线矩形 + 四角实心角标），并入标注工具互斥组（顺序：编辑/矩形/
      点/多边形/感知区，默认仍选中"编辑"）；TOOL_ROI 常量由画布
      widgets/canvas.py 定义（画布是工具语义的归属方），此处相对导入复用
"""

from typing import Dict

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QWidget,
    QToolBar,
    QPushButton,
    QButtonGroup,
    QFrame,
    QSizePolicy,
)

# 感知区工具常量由画布定义（canvas.py：工具语义与交互的归属方，
# 画布不反向引用本模块，故此处相对导入无循环依赖）
from .canvas import TOOL_ROI

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
    TOOL_ROI: "O",
}

# ===== 程序化矢量图标（QPainter 绘制，与全局 QSS 扁平风格同源配色）=====
# 逻辑画布 24x24，2x 超采样输出 48x48（setDevicePixelRatio 保证高清渲染）
_ICON_SIZE = 24
_ICON_SCALE = 2
# 图标配色（与 _ToolBarButton 的 QSS 状态色一致）：
#   Normal(Off) 普通态中性灰；Active(hover) 深墨；On(checked) 反白（深底按钮上可见）
_ICON_COLOR_NORMAL = QColor("#3f3f46")
_ICON_COLOR_ACTIVE = QColor("#18181b")
_ICON_COLOR_ON = QColor("#fafafa")


def _pen(color: QColor, width: float = 2.0) -> QPen:
    """构造统一风格的图标描边画笔（圆头/圆角连接，扁平线性风格）。

    Args:
        color: 描边颜色。
        width: 线宽（逻辑像素）。

    Returns:
        配置好的 QPen。
    """
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _paint_folder(p: QPainter, color: QColor) -> None:
    """绘制"打开文件夹"图标：文件夹主体 + 后置翻盖。"""
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # 后置翻盖（左上斜折）
    p.drawPolyline([QPointF(3, 15), QPointF(3, 6), QPointF(9, 6), QPointF(11, 9)])
    # 主体（带前开口折边）
    p.drawPolygon(
        [
            QPointF(3, 15),
            QPointF(11, 9),
            QPointF(21, 9),
            QPointF(21, 19),
            QPointF(3, 19),
        ]
    )


def _paint_file(p: QPainter, color: QColor) -> None:
    """绘制"打开文件"图标：页面 + 右上折角 + 内容行。"""

    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(
        [
            QPointF(6, 3),
            QPointF(15, 3),
            QPointF(19, 7),
            QPointF(19, 21),
            QPointF(6, 21),
        ]
    )
    p.drawPolyline([QPointF(15, 3), QPointF(15, 7), QPointF(19, 7)])
    p.drawPolyline([QPointF(9, 12), QPointF(16, 12)])
    p.drawPolyline([QPointF(9, 16), QPointF(14, 16)])


def _paint_save(p: QPainter, color: QColor) -> None:
    """绘制"保存"图标：软盘（外壳 + 快门 + 标签框）。"""

    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(
        [
            QPointF(4, 4),
            QPointF(17, 4),
            QPointF(20, 7),
            QPointF(20, 20),
            QPointF(4, 20),
        ]
    )
    p.drawPolyline([QPointF(9, 4), QPointF(9, 9), QPointF(15, 9), QPointF(15, 4)])
    p.drawPolyline(
        [QPointF(8, 20), QPointF(8, 14), QPointF(16, 14), QPointF(16, 20)]
    )


def _paint_save_as(p: QPainter, color: QColor) -> None:
    """绘制"另存为"图标：软盘 + 右上加号（与"保存"区分）。"""

    p.setPen(_pen(color, 1.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(
        [
            QPointF(3, 6),
            QPointF(14, 6),
            QPointF(17, 9),
            QPointF(17, 18),
            QPointF(3, 18),
        ]
    )
    p.drawPolyline([QPointF(8, 6), QPointF(8, 10), QPointF(13, 10), QPointF(13, 6)])
    p.drawPolyline([QPointF(7, 18), QPointF(7, 13), QPointF(13, 13), QPointF(13, 18)])
    # 右上加号
    p.setPen(_pen(color, 2.2))
    p.drawPolyline([QPointF(19.5, 11), QPointF(19.5, 19)])
    p.drawPolyline([QPointF(15.5, 15), QPointF(23.5, 15)])


def _paint_erase(p: QPainter, color: QColor) -> None:
    """绘制"删除选中"图标：斜置橡皮擦（擦除选中标注）。"""

    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # 橡皮擦主体（斜 45° 圆角矩形，分两段色块由分割线表达）
    p.drawPolygon(
        [
            QPointF(4, 15),
            QPointF(12, 5),
            QPointF(19, 10),
            QPointF(11, 20),
            QPointF(6, 20),
        ]
    )
    # 分割线（擦除面/持握面）
    p.drawPolyline([QPointF(10, 8), QPointF(16, 13)])
    # 底部残留线
    p.drawPolyline([QPointF(3, 21), QPointF(21, 21)])


def _paint_trash(p: QPainter, color: QColor) -> None:
    """绘制"删除图片文件"图标：垃圾桶（盖 + 提手 + 桶身 + 竖纹）。"""

    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolyline([QPointF(5, 7), QPointF(19, 7)])
    p.drawPolyline([QPointF(10, 7), QPointF(10, 4), QPointF(14, 4), QPointF(14, 7)])
    p.drawPolygon([QPointF(6.5, 7), QPointF(17.5, 7), QPointF(16, 20), QPointF(8, 20)])
    p.drawPolyline([QPointF(10, 11), QPointF(10.5, 16.5)])
    p.drawPolyline([QPointF(14, 11), QPointF(13.5, 16.5)])


def _paint_cursor(p: QPainter, color: QColor) -> None:
    """绘制"编辑"图标：经典选择光标箭头（填充三角簇）。"""

    p.setPen(QPen(color, 1.2))
    p.setBrush(color)
    p.drawPolygon(
        QPolygonF(
            [
                QPointF(6, 3),
                QPointF(6, 18),
                QPointF(10.2, 14.2),
                QPointF(12.6, 19.8),
                QPointF(15.2, 18.6),
                QPointF(12.8, 13.2),
                QPointF(17.5, 13),
            ]
        )
    )


def _paint_rectangle(p: QPainter, color: QColor) -> None:
    """绘制"矩形"图标：圆角矩形描边。"""
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(4, 6, 16, 12), 2.0, 2.0)


def _paint_point(p: QPainter, color: QColor) -> None:
    """绘制"点"图标：外圈 + 实心圆点。"""
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(4, 4, 16, 16))
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(9, 9, 6, 6))


def _paint_polygon(p: QPainter, color: QColor) -> None:
    """绘制"多边形"图标：五边形描边。"""

    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(
        [
            QPointF(12, 3),
            QPointF(20.5, 9.5),
            QPointF(17.2, 19.5),
            QPointF(6.8, 19.5),
            QPointF(3.5, 9.5),
        ]
    )


def _paint_fit(p: QPainter, color: QColor) -> None:
    """绘制"适应窗口"图标：四角 L 形括号 + 中心矩形（示意视图内适配）。"""

    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # 左上/右上/右下/左下四组 L 形括号（视窗四角）
    p.drawPolyline([QPointF(3, 9), QPointF(3, 3), QPointF(9, 3)])
    p.drawPolyline([QPointF(15, 3), QPointF(21, 3), QPointF(21, 9)])
    p.drawPolyline([QPointF(21, 15), QPointF(21, 21), QPointF(15, 21)])
    p.drawPolyline([QPointF(9, 21), QPointF(3, 21), QPointF(3, 15)])
    # 中心小矩形（示意图像在视窗内完整适配）
    p.drawRect(QRectF(9, 9, 6, 6))


def _paint_rec_only(p: QPainter, color: QColor) -> None:
    """绘制"OCR 仅识别"图标：文本框 + "A" 字（示意对标注区域文本识别）。"""

    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # 虚线文本框（示意已有标注区域）
    pen = _pen(color, 1.6)
    pen.setDashPattern([3, 2])
    p.setPen(pen)
    p.drawRect(QRectF(3, 4, 18, 16))
    # 框内 "A" 字（示意识别出的文本）
    p.setPen(_pen(color, 2.0))
    f = p.font()
    f.setPixelSize(11)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(3, 4, 18, 16), Qt.AlignmentFlag.AlignCenter, "A")


def _paint_roi(p: QPainter, color: QColor) -> None:
    """绘制"感知区"图标：虚线矩形 + 四角实心角标（示意区域框定/选择）。"""

    # 虚线矩形主体（与画布感知区未选中态的虚线样式呼应）
    pen = _pen(color, 1.6)
    pen.setDashPattern([2.5, 2.0])
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(4.5, 6.5, 15.0, 11.0))
    # 四角实心角标（骑跨矩形四角，强调"区域选择"语义）
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    for cx, cy in ((2.5, 4.5), (17.5, 4.5), (2.5, 15.5), (17.5, 15.5)):
        p.drawRect(QRectF(cx, cy, 4.0, 4.0))


# 图标名 -> 绘制函数（按钮构造处按名取用）
_ICON_PAINTERS = {
    "folder": _paint_folder,
    "file": _paint_file,
    "save": _paint_save,
    "save_as": _paint_save_as,
    "erase": _paint_erase,
    "trash": _paint_trash,
    "cursor": _paint_cursor,
    "rectangle": _paint_rectangle,
    "point": _paint_point,
    "polygon": _paint_polygon,
    "roi": _paint_roi,
    "fit": _paint_fit,
    "rec_only": _paint_rec_only,
}


def _render_icon_pixmap(painter_fn, color: QColor) -> QPixmap:
    """以指定颜色渲染单个图标位图（2x 超采样，透明底）。

    Args:
        painter_fn: 图标绘制函数（接收 QPainter 与颜色）。
        color: 图标颜色。

    Returns:
        48x48 像素、devicePixelRatio=2 的透明底位图。
    """
    pm = QPixmap(_ICON_SIZE * _ICON_SCALE, _ICON_SIZE * _ICON_SCALE)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(float(_ICON_SCALE))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter_fn(p, color)
    p.end()
    return pm


def _build_icon(name: str) -> QIcon:
    """按名称构建三态图标（普通/悬停/选中，与按钮 QSS 状态色联动）。

    Args:
        name: 图标名（见 _ICON_PAINTERS）。

    Returns:
        配置好各状态位图的 QIcon。
    """
    painter_fn = _ICON_PAINTERS.get(name)
    icon = QIcon()
    if painter_fn is None:
        return icon
    normal = _render_icon_pixmap(painter_fn, _ICON_COLOR_NORMAL)
    icon.addPixmap(normal, QIcon.Mode.Normal, QIcon.State.Off)
    # 悬停态：深墨色（对应按钮 hover 时文字加深）
    icon.addPixmap(
        _render_icon_pixmap(painter_fn, _ICON_COLOR_ACTIVE),
        QIcon.Mode.Active,
        QIcon.State.Off,
    )
    # 选中态（工具互斥按钮 checked）：反白，对应 QSS 深底
    icon.addPixmap(
        _render_icon_pixmap(painter_fn, _ICON_COLOR_ON),
        QIcon.Mode.Normal,
        QIcon.State.On,
    )
    icon.addPixmap(
        _render_icon_pixmap(painter_fn, _ICON_COLOR_ON),
        QIcon.Mode.Active,
        QIcon.State.On,
    )
    return icon


class _ToolBarButton(QPushButton):
    """工具栏按钮 - 图标化紧凑样式（黑白灰扁平风，语义由 tooltip 承载）。

    图标由 _build_icon 程序化绘制（三态配色与 QSS 状态联动：
    普通灰 / 悬停深 / 选中反白），文字不再显示。
    """

    def __init__(
        self,
        text: str,
        shortcut: str = "",
        icon_name: str = "",
        parent=None,
    ):
        """初始化工具栏按钮。

        Args:
            text: 按钮语义文本（作为 tooltip 主体与无障碍名称，不显示）。
            shortcut: 快捷键说明（显示在 tooltip 中）。
            icon_name: 图标名（见 _ICON_PAINTERS；空则退化为纯文字按钮）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(text)
        if shortcut:
            self.setToolTip(f"{text}（{shortcut}）")
        else:
            self.setToolTip(text)
        if icon_name:
            # 图标替代文字：语义保留在 tooltip / accessibleName
            self.setIcon(_build_icon(icon_name))
            self.setIconSize(QSize(24, 24))
            self.setText("")
        else:
            self.setText(text)
        self.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: 0;
                border-radius: 8px;
                padding: 6px 10px;
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
        fit_requested: 请求适应窗口（缩放视图以完整显示当前图片）。
        tool_selected(str): 请求切换标注工具（select/rectangle/point/polygon/roi）。
        rec_only_toggled(bool): OCR 仅识别开关切换（True=启用仅识别模式）。
    """

    open_requested = Signal()
    open_file_requested = Signal()
    save_requested = Signal()
    save_as_requested = Signal()
    delete_requested = Signal()
    delete_image_requested = Signal()
    fit_requested = Signal()
    tool_selected = Signal(str)
    rec_only_toggled = Signal(bool)

    def __init__(self, parent=None):
        """初始化水平工具栏布局与按钮。"""
        super().__init__(parent)
        # objectName 为 QMainWindow.saveState/restoreState 序列化布局的唯一标识
        self.setObjectName("leftToolBar")
        # ===== 工具栏形态：不可拖动/浮动，固定高度、宽度随内容自适应 =====
        self.setMovable(False)
        self.setFloatable(False)
        self.setFixedHeight(52)
        self.setIconSize(QSize(24, 24))  # 图标按钮统一 24px（位图 2x 超采样）
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # 扁平外观 + 紧凑间距（不绘制原生工具栏边框/渐变，与原透明 QWidget 底色一致）
        self.setStyleSheet(
            "QToolBar { spacing: 2px; padding: 4px 8px; "
            "background: transparent; border: 0; }"
        )

        # ===== 文件操作 =====
        self.btn_open = _ToolBarButton("打开文件夹", "Ctrl+O", "folder")
        self.btn_open.clicked.connect(self.open_requested.emit)
        self.btn_open_file = _ToolBarButton("打开文件", "Ctrl+Shift+O", "file")
        self.btn_open_file.clicked.connect(self.open_file_requested.emit)
        self.btn_save = _ToolBarButton("保存", "Ctrl+S", "save")
        self.btn_save.clicked.connect(self.save_requested.emit)
        self.btn_save_as = _ToolBarButton("另存为", "Ctrl+Shift+S", "save_as")
        self.btn_save_as.clicked.connect(self.save_as_requested.emit)
        self.btn_delete = _ToolBarButton("删除选中", icon_name="erase")
        self.btn_delete.clicked.connect(self.delete_requested.emit)
        self.btn_delete_image = _ToolBarButton("删除图片文件", "Shift+Delete", "trash")
        self.btn_delete_image.clicked.connect(self.delete_image_requested.emit)
        # "Ctrl+0" 仅为默认占位提示，主窗口 refresh_shortcut_hints 后会按实际绑定覆盖
        self.btn_fit = _ToolBarButton("适应窗口", "Ctrl+0", "fit")
        self.btn_fit.clicked.connect(self.fit_requested.emit)

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
            self.btn_fit,
        ):
            self.addWidget(btn)

        # 分组分隔：文件操作 | 标注工具
        self.addWidget(self._separator("文件操作 | 标注工具"))

        # ===== 横向加入工具栏：标注工具分组 =====
        tool_icons = {
            TOOL_SELECT: "cursor",
            TOOL_RECTANGLE: "rectangle",
            TOOL_POINT: "point",
            TOOL_POLYGON: "polygon",
            TOOL_ROI: "roi",
        }
        for tool, text in (
            (TOOL_SELECT, "编辑"),
            (TOOL_RECTANGLE, "矩形"),
            (TOOL_POINT, "点"),
            (TOOL_POLYGON, "多边形"),
            (TOOL_ROI, "感知区"),
        ):
            btn = _ToolBarButton(
                text, _TOOL_SHORTCUT_HINTS.get(tool, ""), tool_icons[tool]
            )
            btn.setCheckable(True)
            self._tool_group.addButton(btn)
            self._tool_buttons[tool] = btn
            btn.clicked.connect(lambda checked=False, t=tool: self.tool_selected.emit(t))
            self.addWidget(btn)

        # 默认选中"编辑"工具（编辑模式：拖拽/端点缩放/多选）
        self._tool_buttons[TOOL_SELECT].setChecked(True)

        # ===== OCR 仅识别开关（独立 checkable 按钮，非绘制互斥组）=====
        # 仅加载 OCR 模型时由主窗口显示（set_rec_only_visible）；
        # checked 状态与模型设置对话框的"仅识别"复选框双向同步
        self.btn_rec_only = _ToolBarButton("OCR 仅识别", "", "rec_only")
        self.btn_rec_only.setCheckable(True)
        self.btn_rec_only.setVisible(False)  # 默认隐藏（未加载模型）
        self.btn_rec_only.clicked.connect(self.rec_only_toggled.emit)
        self.addWidget(self._separator("标注工具 | OCR 仅识别"))
        self.addWidget(self.btn_rec_only)

        # 记录各按钮原始语义文本（refresh_shortcut_hints 刷新 tooltip 的描述基准）
        self._button_texts: Dict[QPushButton, str] = {
            self.btn_open: self.btn_open.accessibleName(),
            self.btn_open_file: self.btn_open_file.accessibleName(),
            self.btn_save: self.btn_save.accessibleName(),
            self.btn_save_as: self.btn_save_as.accessibleName(),
            self.btn_delete: self.btn_delete.accessibleName(),
            self.btn_delete_image: self.btn_delete_image.accessibleName(),
            self.btn_fit: self.btn_fit.accessibleName(),
            self.btn_rec_only: self.btn_rec_only.accessibleName(),
        }
        for btn in self._tool_buttons.values():
            self._button_texts[btn] = btn.accessibleName()

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
            tool: 工具名（select/rectangle/point/polygon/roi）。
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

    def set_rec_only_visible(self, visible: bool) -> None:
        """显示/隐藏"OCR 仅识别"按钮（加载 OCR 模型时显示）。

        隐藏时同步取消选中状态，避免下次显示时残留旧开关状态。

        Args:
            visible: 是否显示。
        """
        self.btn_rec_only.setVisible(visible)
        if not visible:
            self.set_rec_only_checked(False)

    def set_rec_only_checked(self, checked: bool) -> None:
        """程序化设置"仅识别"按钮选中状态（与配置复选框同步）。

        阻塞 clicked 信号（setChecked 不触发 clicked，但显式阻断以防
        未来改为 QActions 等 toggle 型信号引入循环触发）。

        Args:
            checked: 是否选中（启用仅识别模式）。
        """
        self.btn_rec_only.blockSignals(True)
        self.btn_rec_only.setChecked(checked)
        self.btn_rec_only.blockSignals(False)

    def refresh_shortcut_hints(
        self, bindings: Dict[str, str], action_defs: Dict[str, str]
    ) -> None:
        """刷新各按钮 tooltip 的快捷键提示（主窗口快捷键应用流程调用）。

        主窗口在应用/自定义快捷键（_apply_shortcuts，含配置导入与用户改键）后
        调用本方法，将按钮 tooltip 的快捷键提示与实际绑定同步——构造时的
        "Ctrl+0" 等默认占位提示会被实际绑定覆盖。

        Args:
            bindings: action_id -> 快捷键序列文本（如 "Ctrl+S"）；
                缺失或空串表示该动作未绑定（对应提示回退为仅描述文本）。
            action_defs: action_id -> 动作中文描述，作为描述文本的回退来源
                （正常情况下以构造时记录的 _button_texts 为准）。
        """
        # ===== 文件操作按钮：tooltip = "描述（快捷键）"，未绑定则仅描述 =====
        file_button_ids = {
            self.btn_open: "open",
            self.btn_open_file: "open_file",
            self.btn_save: "save",
            self.btn_save_as: "save_as",
            self.btn_fit: "fit_window",
        }
        for btn, action_id in file_button_ids.items():
            text = self._button_texts.get(btn) or action_defs.get(action_id, "")
            seq = bindings.get(action_id, "")
            # 有绑定显示"描述（快捷键）"，否则仅显示描述
            btn.setToolTip(f"{text}（{seq}）" if seq else text)
        # ===== OCR 仅识别按钮：tooltip 同步绑定与开关状态 =====
        rec_text = self._button_texts.get(self.btn_rec_only) or action_defs.get(
            "ocr_rec_only", "OCR 仅识别"
        )
        rec_seq = bindings.get("ocr_rec_only", "")
        state_tip = "已启用" if self.btn_rec_only.isChecked() else "未启用"
        rec_tip = f"{rec_text}（{rec_seq}，{state_tip}）" if rec_seq else (
            f"{rec_text}（{state_tip}）"
        )
        self.btn_rec_only.setToolTip(rec_tip)
        # ===== 工具按钮：双提示"工具快捷键 / 编辑模式快捷键" =====
        for tool, btn in self._tool_buttons.items():
            text = self._button_texts.get(btn) or btn.accessibleName()
            seq = bindings.get(f"tool_{tool}", "")
            edit_seq = bindings.get("edit_mode", "")
            # 两项均绑定 → "描述（A / B）"；仅一项 → "描述（A）"；均无 → 仅描述
            if seq and edit_seq:
                btn.setToolTip(f"{text}（{seq} / {edit_seq}）")
            elif seq or edit_seq:
                btn.setToolTip(f"{text}（{seq or edit_seq}）")
            else:
                btn.setToolTip(text)
