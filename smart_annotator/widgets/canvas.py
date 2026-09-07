# -*- coding: utf-8 -*-
"""
标注画布组件 - Canvas(QGraphicsView)

图像显示 + 标注对象的绘制与编辑：
    - 背景图像：QPixmap 1:1 绘制在场景原点，场景坐标即图像像素坐标
    - 标注工具：矩形（rectangle，两点式：两次左键点击定对角）、点（point）、多边形（polygon）
    - 绘制辅助：十字虚线引导线（延伸至图像四边界）+ 已放置顶点显示
    - 编辑模式（工具为"编辑"）：多选（Shift+点击 / Ctrl+框选）、
      批量拖拽移动（边界钳制 + 阻力反馈）、端点拖动缩放（边界钳制）、
      hover 半透明掩码、可编辑端点仅选中形状显示
    - 滚轮缩放（光标锚定，手动调整滚动条）+ Esc 取消当前绘制

形状以 labelme 标准字典为唯一数据源（见 core/labelme_io.py），
绘制结果对外发射 shapes_changed / selection_changed 信号供右侧栏联动。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-03 移除预览模式、右键菜单携带命中形状
更新: 2026-09-03 新增 discard_shape/copy_selected/paste_clipboard/has_clipboard/can_undo/can_redo（空 label 丢弃、内部剪贴板与撤销状态查询）
更新: 2026-09-03 端点仅选中形状显示；新增 set_render_config（线宽/不透明度/字号）与通用文本渲染（标签/组号/描述，替代 OCR 特例）
更新: 2026-09-03 新增 set_shape_visible 形状渲染可见性（运行时键 _visible，纯视图状态不发信号；_render/_render_vertices 跳过隐藏形状）
更新: 2026-09-07 滚轮缩放改为手动锚定缩放（_apply_zoom 统一入口 + 倍率钳制 0.05–40.0）；
      矩形绘制改两点式（两次左键点击定对角，无按键移动实时预览）；形状拖拽/端点
      编辑钳制在图片边界内并新增边界阻力高亮；新增 color_for_group 组关联配色
      （有合法组号优先组色，无组保持标签色）
    更新: 2026-09-07 新建标注坐标钳制：绘制类创建（矩形/点/多边形）的点击与
      预览坐标统一钳制在图片显示区内（_clamp_to_image），禁止在图片外创建标注
"""

import copy
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QPoint, QTimer
from PySide6.QtGui import (
    QColor,
    QPen,
    QBrush,
    QPixmap,
    QPolygonF,
    QCursor,
    QPainter,
    QFont,
)
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsEllipseItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
    QGraphicsLineItem,
    QGraphicsItem,
)

from ..config import RenderConfig
from ..core import labelme_io

# 顶点（点/多边形顶点）绘制半径（像素）
_VERTEX_RADIUS = 4.0
# 编辑模式下可拖动端点的显示半径（像素）
_EDIT_VERTEX_RADIUS = 5.0
# 绘制中多边形预览线样式
_DRAFT_PEN = QPen(QColor("#18181b"), 2, Qt.PenStyle.DashLine)
# 绘制模式十字引导线样式（虚线）
_GUIDE_PEN = QPen(QColor("#52525b"), 1, Qt.PenStyle.DashLine)
# Ctrl 框选矩形样式（虚线）
_RUBBER_PEN = QPen(QColor("#2563eb"), 1, Qt.PenStyle.DashLine)
# 编辑模式 hover 掩码透明度
_MASK_ALPHA = 90
# 边界阻力触发距离（形状包围盒边缘距图片边界小于该值时位移按剩余空间比例衰减）
_EDGE_RESIST_PX = 10.0
# 边界阻力高亮条厚度（场景像素）
_EDGE_HINT_THICKNESS = 3.0

# 每个标签的固定调色板（循环使用，10 色高区分度）
_PALETTE = [
    "#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6",
    "#ec4899", "#14b8a6", "#f97316", "#64748b", "#84cc16",
]

# 标签 -> 颜色 的确定性全局缓存：同一标签在整个标注过程中保持唯一且一致的颜色
_LABEL_COLOR_CACHE: Dict[str, QColor] = {}
# 下一个待分配颜色的下标（跨 Canvas 实例共享计数，避免重建画布时颜色错位）
_COLOR_SEQ = [0]
# 撤销/重做栈的最大深度
_MAX_UNDO = 50
# 粘贴剪贴板形状时的顶点坐标偏移量（像素，避免粘贴件与原形状完全重叠）
_PASTE_OFFSET = 10.0
# 形状描述文本在图像上的显示截断长度（超过则用 .. 截断）
_OCR_TRUNCATE = 32


def color_for_label(label: str) -> QColor:
    """按标签名稳定分配唯一颜色（进程内首次出现的标签固定同色）。

    以模块级全局缓存保证同一标签在整个标注过程中颜色唯一一致，
    并供右侧信息栏（标签/对象列表颜色圆点）复用，确保两侧颜色严格对齐。

    Args:
        label: 标签名。

    Returns:
        对应颜色。
    """
    if label not in _LABEL_COLOR_CACHE:
        idx = _COLOR_SEQ[0] % len(_PALETTE)
        _COLOR_SEQ[0] += 1
        _LABEL_COLOR_CACHE[label] = QColor(_PALETTE[idx])
    return _LABEL_COLOR_CACHE[label]


# 每个组号的固定调色板（独立于标签调色板，10 色循环，用于组关联配色）
_GROUP_PALETTE = [
    "#0ea5e9", "#d946ef", "#eab308", "#10b981", "#6366f1",
    "#f43f5e", "#06b6d4", "#a855f7", "#e11d48", "#65a30d",
]

# 组号 -> 颜色 的确定性缓存：同一组号全程保持唯一且一致的颜色
_GROUP_COLOR_CACHE: Dict[int, QColor] = {}


def color_for_group(gid) -> Optional[QColor]:
    """按组号稳定返回组关联颜色（独立 10 色调色板按 gid 取模循环）。

    与 color_for_label 相互独立：同一组号的全部形状共用组色，
    供画布描边/文本与右侧对象列表圆点对齐展示。

    Args:
        gid: 组号；非 int 或负数视为非法。

    Returns:
        对应组颜色；gid 非法时返回 None（调用方回退标签色）。
    """
    if not isinstance(gid, int) or gid < 0:
        return None
    if gid not in _GROUP_COLOR_CACHE:
        _GROUP_COLOR_CACHE[gid] = QColor(_GROUP_PALETTE[gid % len(_GROUP_PALETTE)])
    return _GROUP_COLOR_CACHE[gid]


class Canvas(QGraphicsView):
    """标注画布 - 图像显示 + 标注绘制/编辑。

    Signals:
        shapes_changed: 形状列表发生增删改时发射（供保存状态联动）。
        selection_changed(list): 选中形状集合变化时发射（参数为形状字典列表，可为空）。
        shape_created(object): 单个对象绘制完成时发射（参数为新建形状字典）。
        context_menu_requested: 选择/编辑模式下右键（空白或对象）请求上下文菜单。
    """

    shapes_changed = Signal()
    # 参数为形状字典列表。必须用 object 签名：list 签名会经 QVariantList
    # 转换复制字典元素导致 id() 身份失效，主窗口无法回联选中下标
    selection_changed = Signal(object)
    # 单个对象绘制完成时发射（参数为新建形状字典，供主窗口弹出属性编辑）
    shape_created = Signal(object)
    # 空闲状态右键（无绘制草稿）：参数为命中形状字典或 None（空白处）
    context_menu_requested = Signal(object)

    # 缩放步进倍率（滚轮/放大/缩小共用）
    _ZOOM_FACTOR = 1.12
    # 缩放倍率钳制区间（以 transform().m11() 判断当前缩放水平）
    _ZOOM_MIN = 0.05
    _ZOOM_MAX = 40.0

    def __init__(self, parent=None):
        """初始化画布：建立场景、图像项与交互状态。"""
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        # 渲染质量（抗锯齿 + 平滑缩放）
        self._set_qhints()
        # 缩放锚定由 _apply_zoom 手动控制（滚轮锚定光标、按钮锚定视图中心），
        # 变换锚点固定为视图中心，不再依赖 AnchorUnderMouse 隐式行为
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMouseTracking(True)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        # 背景色：浅灰（与左右两栏 #fafafa 相近但有区分度，未加载图像时非纯黑）
        self.setBackgroundBrush(QColor("#eef0f2"))

        # 图像
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._image_path: str = ""
        self._image_width: int = 0
        self._image_height: int = 0

        # 标注数据：形状字典列表（labelme 格式）
        self._shapes: List[Dict] = []
        # 渲染关联：形状 id -> QGraphicsItem 列表
        self._shape_items: Dict[int, QGraphicsItem] = {}
        # 反向索引：QGraphicsItem id -> 形状 id
        self._item_shape: Dict[int, int] = {}
        # 形状文本显示项（按渲染配置叠加显示标签/组号/描述）
        self._text_items: List[QGraphicsTextItem] = []

        # 当前标注工具：None/'rectangle'/'point'/'polygon'（None 即编辑模式）
        self._tool: Optional[str] = None
        self._current_label: str = ""

        # 绘制中的临时状态
        self._draft_item: Optional[QGraphicsItem] = None
        self._draft_points: List[QPointF] = []
        self._press_scene: Optional[QPointF] = None

        # 选中形状 id 集合（支持多选：Shift+点击 / Ctrl+框选）
        self._selected_ids: List[int] = []
        # 拖拽移动（编辑模式）
        self._dragging: bool = False
        self._drag_last: Optional[QPointF] = None

        # Ctrl+拖拽框选状态
        self._rubber_item: Optional[QGraphicsRectItem] = None
        self._rubber_start: Optional[QPointF] = None

        # 编辑模式 hover 半透明掩码
        self._hover_id: Optional[int] = None
        self._hover_item: Optional[QGraphicsItem] = None

        # 编辑模式可拖动端点项：形状 id -> [端点 item]
        self._vertex_items: Dict[int, List[QGraphicsItem]] = {}
        # 端点 item id -> (形状 id, 点下标)
        self._vertex_map: Dict[int, Tuple[int, int]] = {}
        # 端点拖动（缩放形状）状态：(形状 id, 点下标)
        self._vertex_drag: Optional[Tuple[int, int]] = None
        # 拖拽移动/端点拖动是否已发生实际位移（懒记录快照，避免误标脏状态）
        self._drag_moved: bool = False
        self._vertex_moved: bool = False

        # 绘制模式十字引导线（虚线延伸至图像四边界）
        self._guide_items: List[QGraphicsLineItem] = []
        # 绘制过程中已放置的顶点显示项
        self._draft_vertex_items: List[QGraphicsItem] = []

        # 撤销/重做栈（存放形状列表的深拷贝快照）
        self._undo_stack: List[List[Dict]] = []
        self._redo_stack: List[List[Dict]] = []
        # 内部剪贴板（存放选中形状的深拷贝，供复制/粘贴）
        self._clipboard: List[Dict] = []

        # 画布渲染配置（线宽/不透明度/字号/文本开关，由主窗口视图菜单设置）
        self._render_config: RenderConfig = RenderConfig()

        # 边界阻力高亮提示项与自动清除定时器（拖动贴边时短暂显示）
        self._edge_hint_items: List[QGraphicsItem] = []
        self._edge_hint_timer = QTimer(self)
        self._edge_hint_timer.setSingleShot(True)
        self._edge_hint_timer.setInterval(400)
        self._edge_hint_timer.timeout.connect(self._clear_edge_hints)

    # -------------------------- 几何换算助手 --------------------------
    def _set_qhints(self) -> None:
        """设置抗锯齿与平滑缩放渲染提示。"""
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    def _scene_pos(self, pos: QPoint) -> QPointF:
        """将视口坐标转换为场景坐标（即图像像素坐标）。

        Args:
            pos: 视口坐标。

        Returns:
            场景坐标点。
        """
        return self.mapToScene(pos)

    # -------------------------- 图像加载 --------------------------
    def load_image(self, path: str) -> bool:
        """加载图像并清空当前形状（原图像上的标注由外部另行 set_shapes）。

        Args:
            path: 图像文件路径。

        Returns:
            加载成功返回 True，否则 False。
        """
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return False
        self._image_path = path
        self._image_width = pixmap.width()
        self._image_height = pixmap.height()

        self._scene.clear()
        self._pixmap_item = QGraphicsPixmapItem(pixmap)
        self._pixmap_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation
        )
        self._scene.addItem(self._pixmap_item)
        self._scene.setSceneRect(QRectF(0, 0, self._image_width, self._image_height))

        # 重置标注与选中状态（scene.clear 已移除全部 item，引用置空防悬空）
        self._shapes = []
        self._shape_items = {}
        self._item_shape = {}
        self._text_items = []
        self._selected_ids = []
        self._hover_id = None
        self._hover_item = None
        self._vertex_items = {}
        self._vertex_map = {}
        self._vertex_drag = None
        self._rubber_item = None
        self._rubber_start = None
        self._guide_items = []
        self._draft_vertex_items = []
        self._edge_hint_items = []
        self._edge_hint_timer.stop()
        self._clear_draft()

        self._fit_to_window()
        return True

    def _fit_to_window(self) -> None:
        """使图像适配当前视口。"""
        if self._pixmap_item is not None:
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # -------------------------- 图像信息访问器 --------------------------
    def image_path(self) -> str:
        """返回当前已加载图像的路径（未加载返回空字符串）。

        Returns:
            图像文件路径。
        """
        return self._image_path

    def image_width(self) -> int:
        """返回当前图像宽度（像素）。"""
        return self._image_width

    def image_height(self) -> int:
        """返回当前图像高度（像素）。"""
        return self._image_height

    # -------------------------- 形状数据接口 --------------------------
    def shapes(self) -> List[Dict]:
        """返回当前全部形状（labelme 字典列表）。

        Returns:
            形状字典列表。
        """
        return list(self._shapes)

    def set_shapes(self, shapes: List[Dict]) -> None:
        """整体替换形状列表并重新渲染。

        Args:
            shapes: 新的形状字典列表。
        """
        self._shapes = [dict(s) for s in shapes]
        self._selected_ids = []
        self._clear_draft()
        # 外部整体替换（加载/自动标注）视为新起点，清空历史
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._render()
        self.shapes_changed.emit()
        self.selection_changed.emit([])

    def clear_shapes(self) -> None:
        """清空当前图像的所有形状。"""
        self.set_shapes([])

    def refresh(self) -> None:
        """重新渲染当前形状（供外部修改形状属性后刷新显示，不清空历史）。"""
        self._render()
        self.shapes_changed.emit()

    def set_shape_visible(self, shape: Dict, visible: bool) -> None:
        """设置单个形状的渲染可见性（纯视图状态，不改变标注数据）。

        以运行时键 "_visible"（"_" 前缀，序列化时由 labelme_io 剥离）记录：
        False = 不渲染（无图形项/文本/编辑端点，不可点击命中）；True/缺省 = 渲染。
        仅重绘不发信号、不进撤销栈、不触发未保存标记；撤销/重做的深拷贝
        快照会保留该字段，故可见性跨撤销/重做保持。

        Args:
            shape: 形状字典。
            visible: 是否渲染。
        """
        if visible:
            # 恢复可见：删除运行时键（缺省即可见，保持字典干净）
            shape.pop("_visible", None)
        else:
            shape["_visible"] = False
        self._render()

    def set_current_label(self, label: str) -> None:
        """设置绘制新形状时使用的默认标签。

        Args:
            label: 标签名。
        """
        self._current_label = label

    def set_render_config(self, cfg: RenderConfig) -> None:
        """应用画布渲染配置并全量重绘（纯显示效果，不改变标注数据与脏状态）。

        Args:
            cfg: 渲染配置。
        """
        self._render_config = cfg
        self._render()

    # -------------------------- 工具切换 --------------------------
    def set_tool(self, tool: Optional[str]) -> None:
        """切换标注工具（tool 为 None 即进入编辑模式）。

        Args:
            tool: 'rectangle' / 'point' / 'polygon' / None（编辑模式）。
        """
        self._tool = tool
        self._clear_draft()
        self._clear_guides()
        self._clear_rubber()
        if tool is not None:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()
        # 重渲染以更新编辑端点的显示/隐藏（仅编辑模式显示端点）
        self._render()

    def tool(self) -> Optional[str]:
        """返回当前标注工具名。"""
        return self._tool

    def current_label(self) -> str:
        """返回当前默认标签名。"""
        return self._current_label

    # -------------------------- 编辑操作 --------------------------
    def delete_selected(self) -> None:
        """删除当前全部选中的形状（支持多选批量删除）。"""
        if not self._selected_ids:
            return
        self._push_undo()
        selected = set(self._selected_ids)
        self._shapes = [s for s in self._shapes if id(s) not in selected]
        self._selected_ids = []
        self._render()
        self.shapes_changed.emit()
        self.selection_changed.emit([])

    def delete_shapes_at(self, indices: List[int]) -> None:
        """按下标批量删除形状（供右侧对象列表右键删除）。

        Args:
            indices: 形状在列表中的下标集合（越界项自动忽略）。
        """
        idx_set = {i for i in indices if 0 <= i < len(self._shapes)}
        if not idx_set:
            return
        self._push_undo()
        self._shapes = [s for i, s in enumerate(self._shapes) if i not in idx_set]
        self._selected_ids = []
        self._render()
        self.shapes_changed.emit()
        self.selection_changed.emit([])

    def discard_shape(self, shape: Dict) -> None:
        """静默丢弃指定形状（用于“空 label 形状不生效”），不记录撤销快照。

        按对象身份（is）从形状列表移除；若撤销栈顶快照与移除后的
        形状列表深度相等，则弹出该栈顶快照（清理“创建后即丢弃”
        产生的无效撤销记录）。

        Args:
            shape: 要丢弃的形状字典。
        """
        # 形状不在列表中：无操作
        if not any(s is shape for s in self._shapes):
            return
        # 按对象身份过滤移除
        self._shapes = [s for s in self._shapes if s is not shape]
        # 清理无效撤销记录：栈顶快照与移除后的形状列表一致时弹出
        if self._undo_stack and self._undo_stack[-1] == self._shapes:
            self._undo_stack.pop()
        # 同步移除选中集合中的该形状 id
        sid = id(shape)
        self._selected_ids = [x for x in self._selected_ids if x != sid]
        # 重渲染并通知外部
        self._render()
        self.shapes_changed.emit()
        self.selection_changed.emit(self.selected_shapes())

    # -------------------------- 撤销 / 重做 --------------------------
    def _snapshot(self) -> List[Dict]:
        """返回当前形状列表的深拷贝快照。"""
        return copy.deepcopy(self._shapes)

    def _push_undo(self) -> None:
        """在形状变更前记录一次撤销快照，并清空重做栈。"""
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > _MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> None:
        """撤销上一步形状变更。"""
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self._shapes = self._undo_stack.pop()
        self._selected_ids = []
        self._render()
        self.shapes_changed.emit()
        self.selection_changed.emit([])

    def redo(self) -> None:
        """重做上一步被撤销的变更。"""
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self._shapes = self._redo_stack.pop()
        self._selected_ids = []
        self._render()
        self.shapes_changed.emit()
        self.selection_changed.emit([])

    def can_undo(self) -> bool:
        """返回撤销栈是否非空（是否存在可撤销的变更）。

        Returns:
            可撤销返回 True，否则 False。
        """
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        """返回重做栈是否非空（是否存在可重做的变更）。

        Returns:
            可重做返回 True，否则 False。
        """
        return bool(self._redo_stack)

    # -------------------------- 剪贴板（复制 / 粘贴） --------------------------
    def copy_selected(self) -> int:
        """深拷贝当前选中形状到内部剪贴板。

        无选中时清空剪贴板。不修改形状数据、不发射信号、不记录撤销。

        Returns:
            复制的形状数量。
        """
        selected = self.selected_shapes()
        if not selected:
            self._clipboard = []
            return 0
        self._clipboard = copy.deepcopy(selected)
        return len(self._clipboard)

    def paste_clipboard(self) -> None:
        """粘贴内部剪贴板形状：深拷贝并整体偏移 _PASTE_OFFSET 后追加。

        粘贴产生的新形状集合成为当前选中；操作记录撤销快照。
        """
        if not self._clipboard:
            return
        # 粘贴属于形状变更：记录撤销快照
        self._push_undo()
        # 逐个深拷贝并整体偏移全部顶点坐标，追加到形状列表
        pasted: List[Dict] = []
        for src in self._clipboard:
            shape = copy.deepcopy(src)
            for p in shape.get("points", []):
                p[0] += _PASTE_OFFSET
                p[1] += _PASTE_OFFSET
            self._shapes.append(shape)
            pasted.append(shape)
        # 新形状集合设为选中
        self._selected_ids = [id(s) for s in pasted]
        # 重渲染并通知外部
        self._render()
        self.shapes_changed.emit()
        self.selection_changed.emit(self.selected_shapes())

    def has_clipboard(self) -> bool:
        """返回内部剪贴板是否非空。

        Returns:
            剪贴板非空返回 True，否则 False。
        """
        return bool(self._clipboard)

    def select_shape(self, shape: Optional[Dict]) -> None:
        """按形状字典选中（None 取消全部选中）。

        Args:
            shape: 形状字典或 None。
        """
        self._selected_ids = [id(shape)] if shape is not None else []
        self._render()
        self.selection_changed.emit([shape] if shape is not None else [])

    def selected_shapes(self) -> List[Dict]:
        """返回当前全部选中的形状字典列表。

        Returns:
            选中形状字典列表（按形状列表顺序）。
        """
        selected = set(self._selected_ids)
        return [s for s in self._shapes if id(s) in selected]

    def select_shape_by_index(self, index: int) -> None:
        """按下标选中形状（供右侧对象列表联动）。

        Args:
            index: 形状在列表中的下标（越界则取消选中）。
        """
        if 0 <= index < len(self._shapes):
            self.select_shape(self._shapes[index])
        else:
            self.select_shape(None)

    def select_shapes_by_indices(self, indices: List[int]) -> None:
        """按下标集合多选形状（供右侧对象列表多选联动）。

        Args:
            indices: 形状下标列表（越界项自动忽略）。
        """
        self._selected_ids = [
            id(self._shapes[i]) for i in indices if 0 <= i < len(self._shapes)
        ]
        self._render()
        self.selection_changed.emit(self.selected_shapes())

    # -------------------------- 缩放 --------------------------
    def zoom_in(self) -> None:
        """放大（以视图中心对应场景点为锚点）。"""
        self._apply_zoom(self._ZOOM_FACTOR)

    def zoom_out(self) -> None:
        """缩小（以视图中心对应场景点为锚点）。"""
        self._apply_zoom(1 / self._ZOOM_FACTOR)

    def _apply_zoom(self, factor: float, anchor_scene_pos: Optional[QPointF] = None) -> None:
        """按倍率缩放并保持锚点场景点在视口中的位置不变（手动锚定缩放）。

        缩放倍率以 transform().m11() 判断当前水平，钳制在
        [_ZOOM_MIN, _ZOOM_MAX] 区间：越界方向按剩余余量收缩步长，
        已达边界则不再缩放。anchor_scene_pos 为空时以视图中心对应
        场景点为锚点（zoom_in/zoom_out 的既有行为）。

        Args:
            factor: 缩放倍率（>1 放大，<1 缩小）。
            anchor_scene_pos: 锚点场景坐标；None 时取视图中心。
        """
        # 倍率钳制：目标水平越界时收缩 factor 至恰好到达边界
        current = self.transform().m11()
        target = current * factor
        if target > self._ZOOM_MAX:
            factor = self._ZOOM_MAX / current
        elif target < self._ZOOM_MIN:
            factor = self._ZOOM_MIN / current
        if abs(factor - 1.0) < 1e-9:
            return
        # 锚点缺省为视图中心对应场景点
        if anchor_scene_pos is None:
            anchor_scene_pos = self.mapToScene(self.viewport().rect().center())
        # 记录锚点当前视口位置，缩放后调整滚动条使其回到原位
        anchor_view_pos = self.mapFromScene(anchor_scene_pos)
        self.scale(factor, factor)
        delta = self.mapFromScene(anchor_scene_pos) - anchor_view_pos
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() + delta.x()
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() + delta.y()
        )

    # -------------------------- 渲染逻辑 --------------------------
    @staticmethod
    def _shape_color(shape: Dict) -> QColor:
        """解析形状显示颜色：有合法 group_id 用组色，否则回退标签色。

        Args:
            shape: 形状字典。

        Returns:
            显示颜色。
        """
        color = color_for_group(shape.get("group_id"))
        if color is None:
            color = color_for_label(str(shape.get("label", "") or ""))
        return color

    def _make_item(self, shape: Dict) -> Optional[QGraphicsItem]:
        """根据形状字典创建对应的 QGraphicsItem。

        Args:
            shape: 形状字典。

        Returns:
            图形项；不支持的形状类型返回 None。
        """
        # 描边颜色：有合法组号用组色，否则用标签色
        color = self._shape_color(shape)
        pen = QPen(color, self._render_config.pen_width)
        pen.setCosmetic(True)
        shape_type = shape.get("shape_type", "")
        points = shape.get("points", [])

        if shape_type == labelme_io.SHAPE_RECTANGLE and len(points) >= 2:
            p1 = QPointF(points[0][0], points[0][1])
            p2 = QPointF(points[1][0], points[1][1])
            item = QGraphicsRectItem(QRectF(p1, p2).normalized())
            item.setPen(pen)
            return item

        if shape_type == labelme_io.SHAPE_POINT and len(points) >= 1:
            x, y = points[0][0], points[0][1]
            r = _VERTEX_RADIUS
            item = QGraphicsEllipseItem(x - r, y - r, r * 2, r * 2)
            item.setPen(QPen(QColor("#ffffff"), 1))
            item.setBrush(QBrush(color))
            return item

        if shape_type == labelme_io.SHAPE_POLYGON and len(points) >= 3:
            poly = QPolygonF([QPointF(p[0], p[1]) for p in points])
            item = QGraphicsPolygonItem(poly)
            item.setPen(pen)
            item.setBrush(QBrush(QColor(color)))
            item.setOpacity(self._render_config.opacity)
            return item

        return None

    def _render(self) -> None:
        """根据当前形状列表重建所有图形项。"""
        # 清除旧图形项（保留背景图片项）与形状文本项
        for item in list(self._shape_items.values()):
            self._scene.removeItem(item)
        self._shape_items = {}
        self._item_shape = {}
        for item in self._text_items:
            self._scene.removeItem(item)
        self._text_items = []
        # 清除 hover 掩码（形状可能已被删除/修改）
        self._remove_hover_mask()

        for shape in self._shapes:
            # 隐藏形状（复选框取消勾选）不创建图形项与文本
            if not shape.get("_visible", True):
                continue
            item = self._make_item(shape)
            if item is None:
                continue
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self._scene.addItem(item)
            self._shape_items[id(shape)] = item
            self._item_shape[id(item)] = id(shape)
            # 文本渲染：按渲染配置显示标签/组号/描述
            self._maybe_add_shape_text(shape)

        # 编辑模式（工具为 None）：渲染可拖动编辑端点
        self._render_vertices()
        self._highlight_selection()

    def _maybe_add_shape_text(self, shape: Dict) -> None:
        """按渲染配置在形状第一个点上方渲染文本（标签/组号/描述，多行）。

        - 标签：show_label 开且 label 非空；label 为 "text"（OCR 形状）时跳过
        - 组号：show_group 开且 group_id 非 None，显示 "G{group_id}"
        - 描述：show_description 开且非空，超过 _OCR_TRUNCATE 字符截断加 ".."
        - 全部关闭或无内容时不渲染；文本颜色与组色/标签色一致（有合法组号
          用组色），字号取配置。
        - 纯显示效果：不改变标注数据。

        Args:
            shape: 形状字典。
        """
        cfg = self._render_config
        label = str(shape.get("label", "") or "")
        parts: List[str] = []
        # 标签部分（OCR 形状 label 恒为 text，无展示意义，跳过）
        if cfg.show_label and label and label != "text":
            parts.append(label)
        # 组号部分
        gid = shape.get("group_id")
        if cfg.show_group and isinstance(gid, int) and gid >= 0:
            parts.append(f"G{gid}")
        # 描述部分（超长截断）
        desc = str(shape.get("description", "") or "")
        if cfg.show_description and desc:
            if len(desc) > _OCR_TRUNCATE:
                desc = desc[:_OCR_TRUNCATE] + ".."
            parts.append(desc)
        if not parts:
            return
        points = shape.get("points") or []
        if not points:
            return
        # 多行文本（HTML 换行），颜色与组色/标签色一致
        html = "<br>".join(p.replace("<", "&lt;").replace(">", "&gt;") for p in parts)
        text_item = QGraphicsTextItem()
        font = QFont()
        font.setPointSizeF(float(cfg.font_size))
        text_item.setFont(font)
        text_item.setHtml(
            f'<span style="color:{self._shape_color(shape).name()};">{html}</span>'
        )
        text_item.setPos(
            float(points[0][0]),
            float(points[0][1]) - (float(cfg.font_size) + 4),
        )
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._scene.addItem(text_item)
        self._text_items.append(text_item)

    def _highlight_selection(self) -> None:
        """高亮当前选中的全部形状（描边加粗），其余恢复默认。"""
        selected = set(self._selected_ids)
        for shape_id, item in self._shape_items.items():
            color = None
            for s in self._shapes:
                if id(s) == shape_id:
                    color = self._shape_color(s)
                    break
            if color is None:
                continue
            if shape_id in selected:
                pen = QPen(color, self._render_config.pen_width + 2)
            else:
                pen = QPen(color, self._render_config.pen_width)
            pen.setCosmetic(True)
            if hasattr(item, "setPen"):
                # 点形状使用白色描边，保持可辨识
                is_point = any(
                    id(s) == shape_id
                    and s.get("shape_type") == labelme_io.SHAPE_POINT
                    for s in self._shapes
                )
                if is_point:
                    pen = QPen(QColor("#ffffff"), 3 if shape_id in selected else 1)
                item.setPen(pen)

    def _render_vertices(self) -> None:
        """编辑模式下渲染**选中**形状的可拖动编辑端点。

        矩形显示左上/右下两个端点；多边形显示全部顶点；点形状即顶点本身
        不额外渲染。非编辑模式（绘制工具激活）或形状未选中时不显示端点。
        """
        # 清理旧端点项
        for items in self._vertex_items.values():
            for it in items:
                if it.scene() is self._scene:
                    self._scene.removeItem(it)
        self._vertex_items = {}
        self._vertex_map = {}

        # 仅编辑模式（工具为 None）时显示
        if self._tool is not None:
            return

        for shape in self._shapes:
            # 隐藏形状不渲染编辑端点
            if not shape.get("_visible", True):
                continue
            # 仅选中形状显示可拖动端点（未选中的形状即使在编辑模式也不显示）
            if id(shape) not in self._selected_ids:
                continue
            shape_type = shape.get("shape_type", "")
            points = shape.get("points", [])
            if shape_type == labelme_io.SHAPE_RECTANGLE:
                point_indices = [0, 1]
            elif shape_type == labelme_io.SHAPE_POLYGON:
                point_indices = list(range(len(points)))
            else:
                # 点形状本身即顶点，无需额外端点
                continue
            color = color_for_label(shape.get("label", ""))
            for pi in point_indices:
                if pi >= len(points):
                    continue
                x, y = points[pi]
                r = _EDIT_VERTEX_RADIUS
                item = QGraphicsEllipseItem(x - r, y - r, r * 2, r * 2)
                item.setPen(QPen(QColor("#ffffff"), 2))
                item.setBrush(QBrush(color))
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                item.setZValue(10)
                self._scene.addItem(item)
                self._vertex_items.setdefault(id(shape), []).append(item)
                self._vertex_map[id(item)] = (id(shape), pi)

    def _remove_hover_mask(self) -> None:
        """移除当前 hover 半透明掩码（若有）。"""
        if self._hover_item is not None:
            if self._hover_item.scene() is self._scene:
                self._scene.removeItem(self._hover_item)
            self._hover_item = None
        self._hover_id = None

    def _update_hover_mask(self, scene: QPointF) -> None:
        """编辑模式下鼠标进入形状范围时显示半透明掩码。

        Args:
            scene: 当前鼠标场景坐标。
        """
        if self._tool is not None:
            return
        hit_id = self._hit_shape_id(scene)
        if hit_id == self._hover_id:
            return
        # 命中变化：移除旧掩码，按新命中的形状重建
        self._remove_hover_mask()
        if hit_id is None:
            return
        shape = self._find_shape_by_id(hit_id)
        if shape is None:
            return
        color = color_for_label(shape.get("label", ""))
        mask_color = QColor(color)
        mask_color.setAlpha(_MASK_ALPHA)
        shape_type = shape.get("shape_type", "")
        points = shape.get("points", [])
        mask: Optional[QGraphicsItem] = None
        if shape_type == labelme_io.SHAPE_RECTANGLE and len(points) >= 2:
            rect = QRectF(
                QPointF(points[0][0], points[0][1]),
                QPointF(points[1][0], points[1][1]),
            ).normalized()
            mask = QGraphicsRectItem(rect)
            mask.setPen(QPen(Qt.PenStyle.NoPen))
            mask.setBrush(QBrush(mask_color))
        elif shape_type == labelme_io.SHAPE_POLYGON and len(points) >= 3:
            poly = QPolygonF([QPointF(p[0], p[1]) for p in points])
            mask = QGraphicsPolygonItem(poly)
            mask.setPen(QPen(Qt.PenStyle.NoPen))
            mask.setBrush(QBrush(mask_color))
        elif shape_type == labelme_io.SHAPE_POINT and len(points) >= 1:
            r = _EDIT_VERTEX_RADIUS * 3
            x, y = points[0][0], points[0][1]
            mask = QGraphicsEllipseItem(x - r, y - r, r * 2, r * 2)
            mask.setPen(QPen(QColor("#ffffff"), 1))
            mask.setBrush(QBrush(mask_color))
        if mask is not None:
            mask.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            mask.setZValue(5)
            self._scene.addItem(mask)
            self._hover_item = mask
            self._hover_id = hit_id

    def _update_guides(self, scene: QPointF) -> None:
        """绘制模式下更新十字虚线引导线与已放置顶点。

        引导线从光标位置延伸至图像四个边界；矩形绘制中显示起点顶点，
        多边形绘制中显示全部已放置顶点。

        Args:
            scene: 当前鼠标场景坐标。
        """
        self._clear_guides()
        if self._image_width <= 0 or self._image_height <= 0:
            return
        # 垂直/水平引导线（贯穿图像全幅）
        for line in (
            QGraphicsLineItem(scene.x(), 0, scene.x(), self._image_height),
            QGraphicsLineItem(0, scene.y(), self._image_width, scene.y()),
        ):
            line.setPen(_GUIDE_PEN)
            line.setZValue(8)
            line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self._scene.addItem(line)
            self._guide_items.append(line)

        # 已放置顶点显示（矩形：起点；多边形：全部顶点）
        anchor_points: List[QPointF] = []
        if self._tool == labelme_io.SHAPE_RECTANGLE and self._press_scene is not None:
            anchor_points = [self._press_scene]
        elif self._tool == labelme_io.SHAPE_POLYGON and self._draft_points:
            anchor_points = list(self._draft_points)
        for pt in anchor_points:
            r = _EDIT_VERTEX_RADIUS
            item = QGraphicsEllipseItem(pt.x() - r, pt.y() - r, r * 2, r * 2)
            item.setPen(QPen(QColor("#ffffff"), 2))
            item.setBrush(QBrush(QColor("#18181b")))
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            item.setZValue(9)
            self._scene.addItem(item)
            self._draft_vertex_items.append(item)

    def _clear_guides(self) -> None:
        """清理绘制模式的引导线与顶点显示项。"""
        for item in self._guide_items + self._draft_vertex_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._guide_items = []
        self._draft_vertex_items = []

    def _clear_rubber(self) -> None:
        """清理 Ctrl 框选矩形（若有）。"""
        if self._rubber_item is not None:
            if self._rubber_item.scene() is self._scene:
                self._scene.removeItem(self._rubber_item)
            self._rubber_item = None
        self._rubber_start = None

    def _hit_shape_id(self, scene: QPointF) -> Optional[int]:
        """返回命中测试所得形状 id（跳过背景/端点/掩码等辅助项）。

        Args:
            scene: 场景坐标点。

        Returns:
            命中的形状 id；未命中返回 None。
        """
        for item in self._scene.items(scene):
            shape_id = self._item_shape.get(id(item))
            if shape_id is not None:
                return shape_id
        return None

    def _hit_vertex(self, scene: QPointF) -> Optional[Tuple[int, int]]:
        """返回命中测试所得可拖动端点 (形状 id, 点下标)。

        Args:
            scene: 场景坐标点。

        Returns:
            (形状 id, 点下标) 元组；未命中返回 None。
        """
        for item in self._scene.items(scene):
            vertex = self._vertex_map.get(id(item))
            if vertex is not None:
                return vertex
        return None

    def _toggle_selected(self, shape: Dict) -> None:
        """Shift+点击：切换某形状的选中态（多选增量）。

        Args:
            shape: 被点击的形状字典。
        """
        sid = id(shape)
        if sid in self._selected_ids:
            self._selected_ids = [x for x in self._selected_ids if x != sid]
        else:
            self._selected_ids.append(sid)
        self._render()
        self.selection_changed.emit(self.selected_shapes())

    def _finish_rubber_select(self, rect: QRectF) -> None:
        """结束 Ctrl 框选：选中与矩形包围盒相交的全部形状（保留已有选中）。

        Args:
            rect: 框选矩形（场景坐标）。
        """
        self._clear_rubber()
        for shape in self._shapes:
            item = self._shape_items.get(id(shape))
            if item is None:
                continue
            # 形状包围盒与框选矩形相交即选中（保留已有选中集合）
            bbox = item.boundingRect().translated(item.pos())
            if rect.intersects(bbox) and id(shape) not in self._selected_ids:
                self._selected_ids.append(id(shape))
        self._render()
        self.selection_changed.emit(self.selected_shapes())

    def _move_vertex(self, scene: QPointF) -> None:
        """端点拖动中：更新对应形状顶点坐标（缩放形状，钳制在图片边界内）。

        Args:
            scene: 当前鼠标场景坐标。
        """
        if self._vertex_drag is None:
            return
        shape_id, point_idx = self._vertex_drag
        shape = self._find_shape_by_id(shape_id)
        if shape is None or point_idx >= len(shape.get("points", [])):
            return
        # 顶点坐标钳制在图片区（sceneRect）内
        x, y = scene.x(), scene.y()
        rect = self._scene.sceneRect()
        if rect.width() > 0 and rect.height() > 0:
            x = min(max(x, rect.left()), rect.right())
            y = min(max(y, rect.top()), rect.bottom())
        new_pt = [x, y]
        # 钳制后与原坐标一致（无实际移动）：不记撤销快照
        if new_pt == shape["points"][point_idx]:
            return
        # 首次实际移动前记录撤销快照
        if not self._vertex_moved:
            self._push_undo()
            self._vertex_moved = True
        shape["points"][point_idx] = new_pt
        self._render()

    # -------------------------- 绘制状态清理 --------------------------
    def _clear_draft(self) -> None:
        """清理绘制中的临时图形与顶点缓存。"""
        if self._draft_item is not None:
            if self._draft_item.scene() is self._scene:
                self._scene.removeItem(self._draft_item)
            self._draft_item = None
        self._draft_points = []
        self._press_scene = None
        self._clear_guides()

    # -------------------------- 鼠标交互 --------------------------
    def mousePressEvent(self, event) -> None:
        """鼠标按下：按当前工具与修饰键分发到绘制/框选/多选/拖拽逻辑。

        矩形工具为两点式：首次左键点击落起点建虚线草稿，第二次左键
        点击完成创建（创建不由按住拖拽/释放触发）。
        """
        pos = event.position().toPoint()
        scene = self._scene_pos(pos)

        # 右键：绘制草稿进行中取消/闭合；空闲时请求上下文菜单（携带命中形状）
        if event.button() == Qt.MouseButton.RightButton:
            if self._tool == labelme_io.SHAPE_POLYGON and self._draft_points:
                # 多边形绘制中：>=3 顶点右键闭合，否则取消
                if len(self._draft_points) >= 3:
                    self._finalize_polygon()
                else:
                    self._clear_draft()
            elif self._draft_item is not None or self._press_scene is not None:
                # 矩形两点式绘制中：取消当前草稿
                self._clear_draft()
            else:
                # 空白或对象上右键（绘制工具空闲或编辑模式）：请求上下文菜单
                hit = self._find_shape_by_id(self._hit_shape_id(scene))
                self.context_menu_requested.emit(hit)
            return

        # ===== 绘制工具激活 =====
        # 绘制类创建的坐标统一钳制在图片显示区内（禁止在图片外创建标注）
        scene = self._clamp_to_image(scene)
        if self._tool == labelme_io.SHAPE_POINT:
            self._add_point_shape(scene)
            return

        if self._tool == labelme_io.SHAPE_RECTANGLE:
            # 两点式绘制：首次点击记录起点并建虚线草稿，第二次点击完成创建
            if self._draft_item is None:
                self._press_scene = scene
                self._start_rect_draft(scene)
            else:
                # 第二次点击：先把草稿对角更新为钳制后的点击点再完成，
                # 保证快速连点（中间无移动事件）时矩形同样不越界
                self._update_rect_draft(scene)
                self._finalize_rect()
            return

        if self._tool == labelme_io.SHAPE_POLYGON:
            self._draft_points.append(scene)
            self._update_polygon_draft(close_on_first=False)
            return

        # ===== 编辑模式（工具为 None）=====
        # 先检测端点命中：进入端点拖动（缩放形状，快照懒记录见 _move_vertex）
        vertex = self._hit_vertex(scene)
        if vertex is not None:
            self._vertex_drag = vertex
            self._vertex_moved = False
            return

        # Ctrl+按下：开始框选（批量多选）
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._rubber_start = scene
            self._rubber_item = QGraphicsRectItem(QRectF(scene, scene))
            self._rubber_item.setPen(_RUBBER_PEN)
            self._rubber_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._rubber_item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False
            )
            self._rubber_item.setZValue(7)
            self._scene.addItem(self._rubber_item)
            return

        # 普通按下：命中形状则选中/多选切换，并进入拖拽（编辑模式允许移动）
        shape = self._find_shape_by_id(self._hit_shape_id(scene))
        if shape is not None:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+点击：切换该形状选中态（增量多选，不进入拖拽）
                self._toggle_selected(shape)
                return
            # 普通点击：命中已选中项则保留多选集合（便于批量拖动），否则单选
            if id(shape) not in self._selected_ids:
                self.select_shape(shape)
            # 进入拖拽（撤销快照在实际移动时才记录，见 _move_selected）
            self._dragging = True
            self._drag_moved = False
            self._drag_last = scene
        else:
            # 未命中任何形状：清空选中
            if self._selected_ids:
                self.select_shape(None)
            self._dragging = False

    def mouseMoveEvent(self, event) -> None:
        """鼠标移动：更新引导线/绘制/框选/端点拖动/批量移动/hover 掩码。"""
        scene = self._scene_pos(event.position().toPoint())

        # 绘制模式：预览/引导线坐标钳制在图片区内（创建不越界的视觉联动）
        if self._tool is not None:
            scene = self._clamp_to_image(scene)

        # 绘制模式：更新十字引导线与已放置顶点
        if self._tool is not None:
            self._update_guides(scene)

        # 矩形两点式：草稿存在时无按键按下也跟随光标更新预览
        if self._tool == labelme_io.SHAPE_RECTANGLE and self._draft_item is not None:
            self._update_rect_draft(scene)
            return

        # 多边形预览线
        if self._tool == labelme_io.SHAPE_POLYGON and self._draft_points:
            self._update_polygon_draft(close_on_first=False, cursor=scene)
            return

        # Ctrl 框选矩形更新
        if self._rubber_item is not None and self._rubber_start is not None:
            self._rubber_item.setRect(QRectF(self._rubber_start, scene).normalized())
            return

        # 端点拖动（缩放形状）
        if self._vertex_drag is not None:
            self._move_vertex(scene)
            return

        # 批量拖拽移动选中集合（编辑模式）
        if self._dragging and self._selected_ids:
            self._move_selected(scene)
            return

        # 编辑模式空闲移动：更新 hover 半透明掩码
        if self._tool is None:
            self._update_hover_mask(scene)

    def mouseReleaseEvent(self, event) -> None:
        """鼠标释放：结束框选/端点拖动/拖拽移动。

        矩形为两点式：按下/释放不改变草稿状态（草稿预览由无按键移动
        驱动），创建仅由第二次左键点击触发，故矩形工具下直接返回。
        """
        # 矩形两点式：无按住拖拽状态，释放无需清理
        if self._tool == labelme_io.SHAPE_RECTANGLE:
            return

        # Ctrl 框选结束：批量选中相交形状
        if self._rubber_item is not None:
            self._finish_rubber_select(self._rubber_item.rect())
            return

        # 端点拖动结束（缩放完成，仅实际移动时通知变更）
        if self._vertex_drag is not None:
            moved = self._vertex_moved
            self._vertex_drag = None
            self._vertex_moved = False
            if moved:
                self.shapes_changed.emit()
            return

        # 拖拽移动结束（仅实际移动时通知变更）
        if self._dragging:
            moved = self._drag_moved
            self._dragging = False
            self._drag_last = None
            self._drag_moved = False
            # 拖动结束清除边界阻力高亮
            self._clear_edge_hints()
            if moved:
                self.shapes_changed.emit()
            return

    def keyPressEvent(self, event) -> None:
        """快捷键：Esc 取消当前绘制/框选/端点拖动。

        Delete 由主窗口按焦点上下文路由处理（对象列表/文件列表/画布选中删除），
        画布不拦截。
        """
        if event.key() == Qt.Key.Key_Escape:
            if self._vertex_drag is not None:
                # 取消端点拖动：有实际移动则撤销到拖动前快照
                moved = self._vertex_moved
                self._vertex_drag = None
                self._vertex_moved = False
                if moved:
                    self.undo()
                return
            self._clear_draft()
            self._clear_rubber()
            return
        super().keyPressEvent(event)

    def leaveEvent(self, event) -> None:
        """鼠标离开画布：清理引导线与 hover 掩码。"""
        self._clear_guides()
        self._remove_hover_mask()
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:
        """滚轮缩放：以光标下场景点为锚点进行手动锚定缩放。"""
        delta = event.angleDelta().y()
        if delta == 0:
            return
        # 光标位置的场景坐标作为缩放锚点（缩放后仍保持在光标下方）
        anchor = self._scene_pos(event.position().toPoint())
        factor = self._ZOOM_FACTOR if delta > 0 else 1 / self._ZOOM_FACTOR
        self._apply_zoom(factor, anchor)

    # -------------------------- 选中与移动 --------------------------
    def _find_shape_by_id(self, shape_id: int) -> Optional[Dict]:
        """按 id 查找形状字典。

        Args:
            shape_id: 形状 id。

        Returns:
            形状字典；未找到返回 None。
        """
        for s in self._shapes:
            if id(s) == shape_id:
                return s
        return None

    @staticmethod
    def _points_bbox(points: List) -> Optional[QRectF]:
        """遍历形状顶点计算包围盒（x/y 的最小/最大值）。

        Args:
            points: 形状顶点列表（[[x, y], ...]）。

        Returns:
            顶点包围盒；顶点为空返回 None。
        """
        if not points:
            return None
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def _selected_bbox(self) -> Optional[QRectF]:
        """计算全部选中形状顶点的联合包围盒。

        Returns:
            联合包围盒；无选中形状或均无顶点时返回 None。
        """
        selected = set(self._selected_ids)
        bbox: Optional[QRectF] = None
        for shape in self._shapes:
            if id(shape) not in selected:
                continue
            sb = self._points_bbox(shape.get("points", []))
            if sb is None:
                continue
            bbox = sb if bbox is None else bbox.united(sb)
        return bbox

    def _clamp_to_image(self, scene: QPointF) -> QPointF:
        """将场景坐标钳制在图片显示区（sceneRect）内，用于绘制类创建交互。

        新建标注（矩形/点/多边形）的点击与预览坐标必须落在图片内，
        防止在图片外创建标注；未加载图片（sceneRect 为空）时原样返回。

        Args:
            scene: 原始场景坐标。

        Returns:
            钳制后的场景坐标（含图片边界）。
        """
        rect = self._scene.sceneRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return scene
        return QPointF(
            min(max(scene.x(), rect.left()), rect.right()),
            min(max(scene.y(), rect.top()), rect.bottom()),
        )

    def _clamp_move_delta(self, dx: float, dy: float) -> Tuple[float, float]:
        """按选中形状包围盒与图片边界钳制位移，并对贴边方向施加阻力衰减。

        包围盒任何部分不得越出图片区（越界方向位移归零）；包围盒边缘
        距边界小于 _EDGE_RESIST_PX 时，该方向位移按剩余空间/10px 比例
        衰减，并短暂高亮对应边界（阻力反馈）。

        Args:
            dx: 原始 X 方向位移。
            dy: 原始 Y 方向位移。

        Returns:
            (钳制后的 dx, 钳制后的 dy)。
        """
        rect = self._scene.sceneRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return dx, dy
        bbox = self._selected_bbox()
        if bbox is None:
            return dx, dy
        edges = set()
        # X 方向：先阻力衰减（距边界不足 _EDGE_RESIST_PX 按剩余空间比例），再钳制不越界
        if dx > 0:
            gap = rect.right() - bbox.right()
            if gap < _EDGE_RESIST_PX:
                edges.add("right")
                dx *= max(gap, 0.0) / _EDGE_RESIST_PX
            dx = min(dx, max(gap, 0.0))
        elif dx < 0:
            gap = bbox.left() - rect.left()
            if gap < _EDGE_RESIST_PX:
                edges.add("left")
                dx *= max(gap, 0.0) / _EDGE_RESIST_PX
            dx = max(dx, -max(gap, 0.0))
        # Y 方向同上
        if dy > 0:
            gap = rect.bottom() - bbox.bottom()
            if gap < _EDGE_RESIST_PX:
                edges.add("bottom")
                dy *= max(gap, 0.0) / _EDGE_RESIST_PX
            dy = min(dy, max(gap, 0.0))
        elif dy < 0:
            gap = bbox.top() - rect.top()
            if gap < _EDGE_RESIST_PX:
                edges.add("top")
                dy *= max(gap, 0.0) / _EDGE_RESIST_PX
            dy = max(dy, -max(gap, 0.0))
        # 阻力触发：短暂高亮对应边界
        if edges:
            self._show_edge_hints(edges)
        return dx, dy

    def _show_edge_hints(self, edges: set) -> None:
        """沿图片边界显示半透明高亮条（边界阻力反馈，定时器自动清除）。

        Args:
            edges: 需要高亮的边界名集合（left/right/top/bottom）。
        """
        self._clear_edge_hints()
        rect = self._scene.sceneRect()
        # 沿四边界构造高亮条
        bands = {
            "left": QRectF(
                rect.left(), rect.top(), _EDGE_HINT_THICKNESS, rect.height()
            ),
            "right": QRectF(
                rect.right() - _EDGE_HINT_THICKNESS,
                rect.top(),
                _EDGE_HINT_THICKNESS,
                rect.height(),
            ),
            "top": QRectF(
                rect.left(), rect.top(), rect.width(), _EDGE_HINT_THICKNESS
            ),
            "bottom": QRectF(
                rect.left(),
                rect.bottom() - _EDGE_HINT_THICKNESS,
                rect.width(),
                _EDGE_HINT_THICKNESS,
            ),
        }
        for name in edges:
            band = bands.get(name)
            if band is None:
                continue
            item = QGraphicsRectItem(band)
            item.setPen(QPen(Qt.PenStyle.NoPen))
            item.setBrush(QBrush(QColor(37, 99, 235, 120)))
            item.setZValue(11)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self._scene.addItem(item)
            self._edge_hint_items.append(item)
        # 单发定时器自动清除（拖动中持续触发则反复重启）
        self._edge_hint_timer.start()

    def _clear_edge_hints(self) -> None:
        """清除边界阻力高亮提示项。"""
        self._edge_hint_timer.stop()
        for item in self._edge_hint_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._edge_hint_items = []

    def _move_selected(self, scene: QPointF) -> None:
        """拖拽移动全部选中形状的顶点（批量移动，钳制在图片边界内）。

        Args:
            scene: 当前场景坐标点。
        """
        if self._drag_last is None:
            self._drag_last = scene
            return
        dx = scene.x() - self._drag_last.x()
        dy = scene.y() - self._drag_last.y()
        self._drag_last = scene
        if dx == 0 and dy == 0:
            return
        # 边界钳制 + 阻力衰减（钳制后位移为零不视为实际移动，不记撤销）
        dx, dy = self._clamp_move_delta(dx, dy)
        if dx == 0 and dy == 0:
            return
        # 首次实际移动前记录撤销快照
        if not self._drag_moved:
            self._push_undo()
            self._drag_moved = True
        selected = set(self._selected_ids)
        moved = False
        for shape in self._shapes:
            if id(shape) not in selected:
                continue
            for p in shape["points"]:
                p[0] += dx
                p[1] += dy
            moved = True
        if moved:
            # 重建渲染
            self._render()

    # -------------------------- 具体绘制实现 --------------------------
    def _add_point_shape(self, scene: QPointF) -> None:
        """按当前标签在点击位置新增一个点形状。"""
        self._push_undo()
        shape = labelme_io.new_shape(
            self._current_label,
            [[scene.x(), scene.y()]],
            labelme_io.SHAPE_POINT,
        )
        self._shapes.append(shape)
        self._render()
        self.shapes_changed.emit()
        self.shape_created.emit(shape)

    def _start_rect_draft(self, scene: QPointF) -> None:
        """开始矩形绘制：以起点创建临时虚线草稿（两点式首次点击调用）。

        Args:
            scene: 起点场景坐标。
        """
        rect = QRectF(scene, scene)
        item = QGraphicsRectItem(rect)
        item.setPen(_DRAFT_PEN)
        self._scene.addItem(item)
        self._draft_item = item

    def _update_rect_draft(self, scene: QPointF) -> None:
        """更新矩形临时图形大小（两点式：无按键移动时跟随光标预览）。

        Args:
            scene: 当前场景坐标点（对角点）。
        """
        if self._draft_item is None or self._press_scene is None:
            return
        rect = QRectF(self._press_scene, scene).normalized()
        self._draft_item.setRect(rect)

    def _finalize_rect(self) -> None:
        """第二次点击完成矩形绘制：写入形状字典（两点式创建入口）。

        零面积矩形（宽与高均不足 1 像素）静默丢弃，不进入撤销栈。
        """
        if self._draft_item is None or self._press_scene is None:
            self._clear_draft()
            return
        rect = self._draft_item.rect()
        tl = rect.topLeft()
        br = rect.bottomRight()
        self._clear_draft()
        # 忽略无效的零面积矩形
        if abs(tl.x() - br.x()) < 1 and abs(tl.y() - br.y()) < 1:
            return
        # 统一取矩形两对角顶点（保存为 [左上/右下] 语义，与 labelme 一致）
        self._push_undo()
        shape = labelme_io.new_shape(
            self._current_label,
            [[tl.x(), tl.y()], [br.x(), br.y()]],
            labelme_io.SHAPE_RECTANGLE,
        )
        self._shapes.append(shape)
        self._render()
        self.shapes_changed.emit()
        self.shape_created.emit(shape)

    def _update_polygon_draft(self, close_on_first: bool, cursor: Optional[QPointF] = None) -> None:
        """更新多边形临时预览线。

        Args:
            close_on_first: 是否高亮首顶点（接近闭合）。
            cursor: 当前光标场景坐标（用于橡皮筋预览）。
        """
        if self._draft_item is not None:
            self._scene.removeItem(self._draft_item)
            self._draft_item = None
        pts = list(self._draft_points)
        if cursor is not None:
            pts = pts + [cursor]
        if len(pts) < 2:
            return
        poly = QPolygonF(pts)
        item = QGraphicsPolygonItem(poly)
        item.setPen(_DRAFT_PEN)
        item.setBrush(QBrush(QColor(24, 24, 27, 20)))
        self._scene.addItem(item)
        self._draft_item = item

    def _finalize_polygon(self) -> None:
        """结束多边形绘制：闭合为多边形形状。"""
        pts = list(self._draft_points)
        self._clear_draft()
        if len(pts) < 3:
            return
        self._push_undo()
        shape = labelme_io.new_shape(
            self._current_label,
            [[p.x(), p.y()] for p in pts],
            labelme_io.SHAPE_POLYGON,
        )
        self._shapes.append(shape)
        self._render()
        self.shapes_changed.emit()
        self.shape_created.emit(shape)
