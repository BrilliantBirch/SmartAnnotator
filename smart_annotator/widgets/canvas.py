# -*- coding: utf-8 -*-
"""
标注画布组件 - Canvas(QGraphicsView)

图像显示 + 标注对象的绘制、编辑与预览：
    - 背景图像：QPixmap 1:1 绘制在场景原点，场景坐标即图像像素坐标
    - 标注工具：矩形（rectangle）、点（point）、多边形（polygon）
    - 编辑能力：选中、拖拽移动、删除（Delete 键）、Esc 取消当前绘制
    - 滚轮缩放 + 双击适配窗口（fit）

形状以 labelme 标准字典为唯一数据源（见 core/labelme_io.py），
绘制结果对外发射 shapes_changed / shape_selected 信号供右侧栏联动。

作者: BaiBinnan
创建日期: 2026-09-02
"""

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QPoint
from PySide6.QtGui import (
    QColor,
    QPen,
    QBrush,
    QPixmap,
    QPolygonF,
    QCursor,
    QPainter,
)
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsEllipseItem,
    QGraphicsPolygonItem,
    QGraphicsItem,
)

from ..core import labelme_io

# 顶点（点/多边形顶点）绘制半径（像素）
_VERTEX_RADIUS = 4.0
# 绘制中多边形预览线样式
_DRAFT_PEN = QPen(QColor("#18181b"), 2, Qt.PenStyle.DashLine)

# 每个标签的固定调色板（循环使用）
_PALETTE = [
    "#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6",
    "#ec4899", "#14b8a6", "#f97316", "#64748b", "#84cc16",
]


class Canvas(QGraphicsView):
    """标注画布 - 图像显示 + 标注绘制/编辑。

    Signals:
        shapes_changed: 形状列表发生增删改时发射（供保存状态联动）。
        shape_selected: 选中形状变化时发射（参数为形状字典或 None）。
    """

    shapes_changed = Signal()
    shape_selected = Signal(object)

    def __init__(self, parent=None):
        """初始化画布：建立场景、图像项与交互状态。"""
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        # 渲染质量（抗锯齿 + 平滑缩放）
        self._set_qhints()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMouseTracking(True)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setBackgroundBrush(QColor("#18181b"))

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

        # 当前标注工具：None/'rectangle'/'point'/'polygon'
        self._tool: Optional[str] = None
        self._current_label: str = ""

        # 绘制中的临时状态
        self._draft_item: Optional[QGraphicsItem] = None
        self._draft_points: List[QPointF] = []
        self._press_scene: Optional[QPointF] = None

        # 选中形状
        self._selected_id: Optional[int] = None
        # 拖拽移动
        self._dragging = False
        self._drag_last: Optional[QPointF] = None

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

        # 重置标注与选中状态
        self._shapes = []
        self._shape_items = {}
        self._item_shape = {}
        self._selected_id = None
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
        self._selected_id = None
        self._clear_draft()
        self._render()
        self.shapes_changed.emit()

    def clear_shapes(self) -> None:
        """清空当前图像的所有形状。"""
        self.set_shapes([])

    def set_current_label(self, label: str) -> None:
        """设置绘制新形状时使用的默认标签。

        Args:
            label: 标签名。
        """
        self._current_label = label

    # -------------------------- 工具切换 --------------------------
    def set_tool(self, tool: Optional[str]) -> None:
        """切换标注工具。

        Args:
            tool: 'rectangle' / 'point' / 'polygon' / None（选择模式）。
        """
        self._tool = tool
        self._clear_draft()
        if tool is not None:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()

    def tool(self) -> Optional[str]:
        """返回当前标注工具名。"""
        return self._tool

    def current_label(self) -> str:
        """返回当前默认标签名。"""
        return self._current_label

    # -------------------------- 编辑操作 --------------------------
    def delete_selected(self) -> None:
        """删除当前选中的形状。"""
        if self._selected_id is None:
            return
        self._shapes = [s for s in self._shapes if id(s) != self._selected_id]
        self._selected_id = None
        self._render()
        self.shapes_changed.emit()
        self.shape_selected.emit(None)

    def select_shape(self, shape: Optional[Dict]) -> None:
        """按形状字典选中（None 取消选中）。

        Args:
            shape: 形状字典或 None。
        """
        self._selected_id = id(shape) if shape is not None else None
        self._highlight_selection()
        self.shape_selected.emit(shape)

    def selected_shape(self) -> Optional[Dict]:
        """返回当前选中的形状字典（无选中返回 None）。

        Returns:
            形状字典或 None。
        """
        return self._find_shape_by_id(self._selected_id) if self._selected_id is not None else None

    def select_shape_by_index(self, index: int) -> None:
        """按下标选中形状（供右侧对象列表联动）。

        Args:
            index: 形状在列表中的下标（越界则取消选中）。
        """
        if 0 <= index < len(self._shapes):
            self.select_shape(self._shapes[index])
        else:
            self.select_shape(None)

    # -------------------------- 缩放 --------------------------
    def zoom_in(self) -> None:
        """放大。"""
        self.scale(1.2, 1.2)

    def zoom_out(self) -> None:
        """缩小。"""
        self.scale(1 / 1.2, 1 / 1.2)

    # -------------------------- 渲染逻辑 --------------------------
    def _color_for_label(self, label: str) -> QColor:
        """按标签名稳定分配颜色。

        Args:
            label: 标签名。

        Returns:
            对应颜色。
        """
        base = _PALETTE[hash(label) % len(_PALETTE)]
        return QColor(base)

    def _make_item(self, shape: Dict) -> Optional[QGraphicsItem]:
        """根据形状字典创建对应的 QGraphicsItem。

        Args:
            shape: 形状字典。

        Returns:
            图形项；不支持的形状类型返回 None。
        """
        color = self._color_for_label(shape.get("label", ""))
        pen = QPen(color, 2)
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
            item.setOpacity(0.3)
            return item

        return None

    def _render(self) -> None:
        """根据当前形状列表重建所有图形项。"""
        # 清除旧图形项（保留背景图片项）
        for item in list(self._shape_items.values()):
            self._scene.removeItem(item)
        self._shape_items = {}
        self._item_shape = {}

        for shape in self._shapes:
            item = self._make_item(shape)
            if item is None:
                continue
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self._scene.addItem(item)
            self._shape_items[id(shape)] = item
            self._item_shape[id(item)] = id(shape)

        self._highlight_selection()

    def _highlight_selection(self) -> None:
        """高亮当前选中的形状（描边加粗），其余恢复默认。"""
        for shape_id, item in self._shape_items.items():
            color = None
            for s in self._shapes:
                if id(s) == shape_id:
                    color = self._color_for_label(s.get("label", ""))
                    break
            if color is None:
                continue
            if shape_id == self._selected_id:
                pen = QPen(color, 4)
            else:
                pen = QPen(color, 2)
            pen.setCosmetic(True)
            if hasattr(item, "setPen"):
                # 点形状使用白色描边，保持可辨识
                is_point = any(
                    id(s) == shape_id
                    and s.get("shape_type") == labelme_io.SHAPE_POINT
                    for s in self._shapes
                )
                if is_point:
                    pen = QPen(QColor("#ffffff"), 3 if shape_id == self._selected_id else 1)
                item.setPen(pen)

    # -------------------------- 绘制状态清理 --------------------------
    def _clear_draft(self) -> None:
        """清理绘制中的临时图形与顶点缓存。"""
        if self._draft_item is not None:
            self._scene.removeItem(self._draft_item)
            self._draft_item = None
        self._draft_points = []
        self._press_scene = None

    # -------------------------- 鼠标交互 --------------------------
    def mousePressEvent(self, event) -> None:
        """鼠标按下：按当前工具分发到绘制或选中/移动逻辑。"""
        pos = event.position().toPoint()
        scene = self._scene_pos(pos)

        # 右键在 polygon 绘制中闭合多边形
        if event.button() == Qt.MouseButton.RightButton:
            if self._tool == labelme_io.SHAPE_POLYGON and len(self._draft_points) >= 3:
                self._finalize_polygon()
            else:
                self._clear_draft()
            return

        if self._tool is None:
            self._on_press_select(scene)
            return

        if self._tool == labelme_io.SHAPE_POINT:
            self._add_point_shape(scene)
            return

        if self._tool == labelme_io.SHAPE_RECTANGLE:
            self._press_scene = scene
            self._start_rect_draft(scene)
            return

        if self._tool == labelme_io.SHAPE_POLYGON:
            self._draft_points.append(scene)
            self._update_polygon_draft(close_on_first=False)
            return

    def mouseMoveEvent(self, event) -> None:
        """鼠标移动：更新矩形拉伸、多边形预览或拖拽移动选中形状。"""
        scene = self._scene_pos(event.position().toPoint())

        if self._tool == labelme_io.SHAPE_RECTANGLE and self._press_scene is not None:
            self._update_rect_draft(scene)
            return

        if self._tool == labelme_io.SHAPE_POLYGON and self._draft_points:
            self._update_polygon_draft(close_on_first=False, cursor=scene)
            return

        if self._dragging and self._selected_id is not None:
            self._move_selected(scene)

    def mouseReleaseEvent(self, event) -> None:
        """鼠标释放：结束矩形绘制或拖拽移动。"""
        if self._tool == labelme_io.SHAPE_RECTANGLE and self._press_scene is not None:
            scene = self._scene_pos(event.position().toPoint())
            self._update_rect_draft(scene)
            self._finalize_rect()
            return
        if self._dragging:
            self._dragging = False
            self._drag_last = None
            self.shapes_changed.emit()
            return

    def keyPressEvent(self, event) -> None:
        """快捷键：Delete 删除选中，Esc 取消绘制。"""
        if event.key() == Qt.Key.Key_Delete:
            self.delete_selected()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._clear_draft()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        """滚轮缩放。"""
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    # -------------------------- 选中与移动 --------------------------
    def _on_press_select(self, scene: QPointF) -> None:
        """选择模式下按下：命中形状则选中并进入拖拽，否则取消选中。"""
        # 自顶向下命中检测：跳过背景图片项，只匹配形状图形项
        for item in self._scene.items(scene):
            shape_id = self._item_shape.get(id(item))
            if shape_id is not None:
                shape = self._find_shape_by_id(shape_id)
                self.select_shape(shape)
                self._dragging = True
                self._drag_last = scene
                return
        # 未命中任何形状：取消选中
        self.select_shape(None)
        self._dragging = False

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

    def _move_selected(self, scene: QPointF) -> None:
        """拖拽移动选中形状的所有顶点。

        Args:
            scene: 当前场景坐标点。
        """
        if self._drag_last is None:
            self._drag_last = scene
            return
        dx = scene.x() - self._drag_last.x()
        dy = scene.y() - self._drag_last.y()
        self._drag_last = scene
        shape = self._find_shape_by_id(self._selected_id)
        if shape is None:
            return
        for p in shape["points"]:
            p[0] += dx
            p[1] += dy
        # 重建渲染
        self._render()

    # -------------------------- 具体绘制实现 --------------------------
    def _add_point_shape(self, scene: QPointF) -> None:
        """按当前标签在点击位置新增一个点形状。"""
        shape = labelme_io.new_shape(
            self._current_label,
            [[scene.x(), scene.y()]],
            labelme_io.SHAPE_POINT,
        )
        self._shapes.append(shape)
        self._render()
        self.shapes_changed.emit()

    def _start_rect_draft(self, scene: QPointF) -> None:
        """开始矩形绘制：记录起点并创建临时图形。"""
        rect = QRectF(scene, scene)
        item = QGraphicsRectItem(rect)
        item.setPen(_DRAFT_PEN)
        self._scene.addItem(item)
        self._draft_item = item

    def _update_rect_draft(self, scene: QPointF) -> None:
        """更新矩形临时图形大小。

        Args:
            scene: 当前场景坐标点。
        """
        if self._draft_item is None or self._press_scene is None:
            return
        rect = QRectF(self._press_scene, scene).normalized()
        self._draft_item.setRect(rect)

    def _finalize_rect(self) -> None:
        """结束矩形绘制：写入形状字典。"""
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
        shape = labelme_io.new_shape(
            self._current_label,
            [[tl.x(), tl.y()], [br.x(), br.y()]],
            labelme_io.SHAPE_RECTANGLE,
        )
        self._shapes.append(shape)
        self._render()
        self.shapes_changed.emit()

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
        shape = labelme_io.new_shape(
            self._current_label,
            [[p.x(), p.y()] for p in pts],
            labelme_io.SHAPE_POLYGON,
        )
        self._shapes.append(shape)
        self._render()
        self.shapes_changed.emit()