# -*- coding: utf-8 -*-
"""
拖拽排序列表控件 - DragDropListWidget

支持条目内部拖拽排序的 QListWidget 子类：
    - 拖拽调整顺序后自动刷新行首索引（顺序经页面 collect_config
      按行号重建，无需额外信号）
    - 行首索引标签自动刷新（行号即转换后的类别索引）

注意：必须重写 dropEvent 手动重排——QListWidget 默认的 InternalMove
实现会删除并重建行项，导致 setItemWidget 关联的自定义控件被销毁。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-11 清理死代码：删除全库零连接的 order_changed 信号
      （类别顺序由页面 collect_config 按行号重建）
"""

from PySide6.QtWidgets import QListWidget


class DragDropListWidget(QListWidget):
    """支持内部拖拽排序的列表控件（保留 itemWidget 关联）。"""

    def __init__(self, parent=None):
        """初始化拖拽模式与行结构变化监听。"""
        super().__init__(parent)
        # 内部移动模式：仅允许本列表内拖拽调整顺序
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        # 行结构变化（手动重排的 take/insert、增删行）时刷新行首索引
        self.model().rowsInserted.connect(self._on_rows_changed)
        self.model().rowsRemoved.connect(self._on_rows_changed)

    def dropEvent(self, event) -> None:
        """手动处理拖拽落点：取出行项并在目标位置重新插入。

        不调用父类默认实现（默认会删除源行项导致 itemWidget 被销毁），
        改用 takeItem/insertItem 保持行项与关联控件的同一性。

        Args:
            event: 拖拽落点事件。
        """
        # 仅接受本列表内部的移动拖拽
        if event.source() is not self or self.count() == 0:
            event.ignore()
            return

        pos = event.position().toPoint()
        dest_item = self.itemAt(pos)
        if dest_item is None:
            # 落在空白区域：追加到末尾
            dest_row = self.count()
        else:
            dest_row = self.row(dest_item)
            # 按落点在目标行上/下半区决定插入到其前/后
            rect = self.visualItemRect(dest_item)
            if pos.y() > rect.center().y():
                dest_row += 1

        source_row = self.currentRow()
        if source_row < 0:
            event.ignore()
            return

        # 取出源行项并插入目标位置。
        # 注意：行项移除时 Qt 会销毁该行关联的 itemWidget，因此先解除关联
        # （removeItemWidget），插入后再重新绑定，保证自定义控件随行项移动。
        item = self.item(source_row)
        widget = self.itemWidget(item)
        if widget is not None:
            self.removeItemWidget(item)
        item = self.takeItem(source_row)
        if source_row < dest_row:
            dest_row -= 1  # 源行移除后的位置偏移修正
        if dest_row > self.count():
            dest_row = self.count()
        self.insertItem(dest_row, item)
        if widget is not None:
            self.setItemWidget(item, widget)
        self.setCurrentRow(dest_row)

        event.accept()  # 标记事件已处理，阻止默认删除逻辑
        self.refresh_indices()

    def refresh_indices(self) -> None:
        """刷新所有行的索引前缀标签。

        行号即转换后的类别索引（class_mapping = {行号: 类别名}），
        排序变化后由本方法保证索引显示实时更新。
        """
        for row in range(self.count()):
            widget = self.itemWidget(self.item(row))
            if widget is not None and hasattr(widget, "set_index"):
                widget.set_index(row)

    def _on_rows_changed(self, *args) -> None:
        """行插入/删除后刷新索引显示。"""
        self.refresh_indices()
