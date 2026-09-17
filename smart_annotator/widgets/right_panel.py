# -*- coding: utf-8 -*-
"""
右侧信息栏控件 - 独立分区控件（LabelSection / ObjectSection /
FileSection / RoiSection）

主窗口右侧以独立 QDockWidget 分别承载各分区控件（纵向堆叠）——
    - LabelSection（标签列表）：工作路径下全部标签（单击/双击设为当前
      绘制标签）
    - ObjectSection（对象列表，标题"对象"）：当前图片上的全部标注对象
      （含 point 形状），支持多选、可见性复选框与右键上下文菜单
      （编辑属性/删除/进入编辑模式）
    - FileSection（文件列表）：工作路径下全部图片，顶部检索框
      （FileSearchProxyModel 按文件名/标签/已标注状态实时过滤）与
      "无匹配文件"空态提示
    - RoiSection（感知区列表）：当前图片上的全部感知区（ROI 裁剪框），
      单击选中与画布联动，双击/右键"定位"请求视图缩放定位，右键
      "删除"经主窗口统一确认链路删除（Dock 装配由主窗口完成）

Dock 纵向堆叠时高度由 Dock 间分隔条拖拽调节；挂靠左右边界时宽度由
Dock 与中央控件间分隔条拖拽调节。每个分区构造时强制 96px 最小高度与
180px 最小宽度（拖拽下限，防止分区被拖到不可用）。分区交互经信号对外
发射，由主窗口统一处理，保持列表与画布联动。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-03 对象列表更名"标签"、多选（ExtendedSelection）、右键上下文菜单
更新: 2026-09-03 移除标签列表"+"新增按钮与 add_label_requested 信号（新标签经属性弹窗键入创建）
更新: 2026-09-03 列表高度改为垂直分栏可拖拽调节（sizes_changed 信号 +
      set_section_heights 接口），宽度界限交由主窗口水平分栏控制
更新: 2026-09-03 对象/关键点列表加复选框（可见性控制）与行-形状下标映射，关键点列表重构为 point 形状对象列表（交互与对象列表一致），文件列表加只读已标注复选框；移除 keypoint_selected 标签名交互
更新: 2026-09-04 select_file 滚动到选中行（QListView 重构后快捷键切换
      图片时列表不跟随滚动，补 scrollTo PositionAtCenter）；移除
      selectionModel 信号屏蔽（屏蔽抑制视图重绘导致选中高亮视觉上
      不跟随，回馈由主窗口 _current_index 守卫阻断）
更新: 2026-09-07 移除关键点列表分区与关键点专用信号/右键分支（point 形状
      统一进对象列表）；对象列表圆点颜色改为组色/标签色（条目元组扩展为
      (下标, 文本, 标签, 可见, 颜色)，颜色由调用方计算传入）；分栏高度
      记忆改为三组列表
更新: 2026-09-07 顶层设置 objectName="rightPanel"（供全局 QSS 按作用域
      设置列表字号）；新增 set_section_visible 分区显隐方法（供视图菜单
      控制三组列表整体显隐，隐藏不丢数据）
更新: 2026-09-07 文件分区顶部新增检索框（fileSearchEdit，实时过滤）：
      QListView 改挂 FileSearchProxyModel（按文件名/标签/已标注状态
      过滤，命中行高亮），选中行号经 mapToSource 转换；检索无匹配时
      视图上覆盖"无匹配文件"空态提示；新增 set_file_tags 转发接口；
      select_file 目标被过滤隐藏时清空检索词后再选中
更新: 2026-09-07 三分区独立 Dock 化：删除 RightPanel 聚合类（垂直分栏
      QSplitter、sizes_changed/高度记忆、set_section_visible、宽度上限
      setMaximumWidth 全部随之移除），_Section 演化为三个独立公开控件
      LabelSection / ObjectSection / FileSection（各设 objectName 与
      180px 最小宽度，由主窗口三个 QDockWidget 分别承载，宽度由 Dock
      分隔条调节）
更新: 2026-09-08 三分区再次独立 Dock 化：删除 RightPanel 聚合面板与
      宽度边界常量（主窗口以三个 QDockWidget 分别承载三分区，纵向
      堆叠高度由 Dock 间分隔条拖拽调节、挂靠左右边界时宽度由 Dock
      与中央控件间分隔条拖拽调节，布局状态统一由 dock_state 持久化，
      高度记忆 sizes_changed/宽度上限随之移除）；_Section 统一 96px
      最小高度（Dock 堆叠拖拽下限防折叠）与 180px 最小宽度
更新: 2026-09-08 对象列表交互增强：新增双击条目编辑（复用右键"编辑"
      链路 edit_object_requested：主窗口进入编辑模式 + 属性弹窗，与
      单击选择互不冲突）；新增内部拖拽排序（_ObjectListWidget
      InternalMove + Move 动作，dropEvent 屏蔽中间态噪声信号并延后
      到事件循环下一拍收尾——覆盖"插入落点副本 + startDrag 删源行"
      两步重排）；形状下标改存条目 UserRole 数据（拖放副本经 mime
      编解码保留），收尾按 UserRole 重建行号映射，重排经新增
      objects_reordered 信号通知主窗口同步重排画布形状
更新: 2026-09-17 新增 RoiSection 感知区列表分区（单选 QListWidget，
      行文本 ROI{id} (x1, y1) - (x2, y2) w×h，行号 → ROI id 映射且
      id 存条目 UserRole；roi_selected / roi_locate_requested /
      roi_delete_requested 三个 object 签名信号，程序化选中全程
      blockSignals 静默避免回环）
"""

from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QEvent, QItemSelectionModel, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QFrame,
    QListWidgetItem,
    QListView,
    QMenu,
    QAbstractItemView,
    QLineEdit,
)

from .canvas import color_for_label
from .file_list_model import FileListModel, FileSearchProxyModel


def _color_dot_icon(color: QColor) -> QIcon:
    """生成一个实心圆点图标，用于列表项前的类别颜色标识。

    Args:
        color: 圆点颜色。

    Returns:
        圆点图标。
    """
    pm = QPixmap(12, 12)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#9ca3af"), 1))
    painter.setBrush(color)
    painter.drawEllipse(1, 1, 10, 10)
    painter.end()
    return QIcon(pm)


class _Section(QFrame):
    """信息栏分区基类：QFrame 圆角边框容器 + 标题行 + 内容垂直布局。

    三个具体分区（LabelSection / ObjectSection / FileSection）继承本类，
    复用边框/标题骨架；列表控件由子类自行构建并挂入 self.lay（子类决定
    挂载顺序，如文件分区需在标题与列表之间插入检索框）。

    Args:
        title: 分区标题。
        parent: 父控件。
    """

    def __init__(self, title: str, parent=None):
        """初始化分区容器（边框/最小尺寸/标题行）。"""
        super().__init__(parent)
        self.setStyleSheet("QFrame { border: 1px solid #e4e4e7; border-radius: 8px; }")
        # 最小尺寸：Dock 纵向堆叠时高度下限 96px、宽度下限 180px，
        # 防止分隔条拖拽过度导致分区不可用（不设最大尺寸，堆叠高度与
        # 挂靠宽度均由主窗口 Dock 分隔条拖拽调节）
        self.setMinimumSize(180, 96)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(8, 8, 8, 8)
        self.lay.setSpacing(6)

        # 标题行：弱化色标题 + 右侧伸缩占位
        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #71717a; font-weight: 600; border: 0;")
        header.addWidget(self.title_label)
        header.addStretch()
        self.lay.addLayout(header)


class LabelSection(_Section):
    """标签列表分区：工作路径下全部标签（单击/双击设为当前绘制标签）。

    Signals:
        label_selected(str): 用户单击/双击标签（主窗口设为当前绘制标签）。
    """

    label_selected = Signal(str)

    def __init__(self, parent=None):
        """初始化标签列表分区（objectName 供全局 QSS 按作用域设置字号）。"""
        super().__init__("标签列表", parent)
        self.setObjectName("labelSection")
        # 标签列表：每项前显示与类别框颜色一致的圆点图标
        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget { background-color: #fafafa; border: 0; }"
        )
        self.list.itemDoubleClicked.connect(self._on_label_double)
        # 单击即选中标签作为当前绘制标签（直接选择预设标签进行标注）
        self.list.itemClicked.connect(self._on_label_click)
        self.lay.addWidget(self.list, 1)

    def set_labels(self, labels) -> None:
        """填充标签列表，每项前显示与类别框颜色一致的圆点。

        Args:
            labels: 标签名列表。
        """
        self.list.clear()
        for name in labels:
            item = QListWidgetItem(str(name))
            item.setIcon(_color_dot_icon(color_for_label(str(name))))
            self.list.addItem(item)

    def _on_label_double(self, item: QListWidgetItem) -> None:
        """双击标签：发射设为当前绘制标签信号。

        Args:
            item: 被双击的列表项。
        """
        self.label_selected.emit(item.text())

    def _on_label_click(self, item: QListWidgetItem) -> None:
        """单击标签：同样设为当前绘制标签（直接选择预设标签）。

        Args:
            item: 被单击的列表项。
        """
        self.label_selected.emit(item.text())


class _ObjectListWidget(QListWidget):
    """对象列表控件（QListWidget + 内部拖拽排序支持）。

    InternalMove 拖放的完整重排分两步跨调用栈完成：dropEvent 内插入
    落点副本，源行删除发生在拖放循环返回之后（QAbstractItemView
    startDrag 的 clearOrRemove）。本控件在 dropEvent 期间屏蔽自身
    信号（模型处于"副本+源行"中间态，itemChanged/selectionChanged
    以旧映射解读会误发可见性/选中联动），并延后到事件循环下一拍统一
    收尾，确保列表已是最终视觉顺序后再通知重排。

    Signals:
        order_dropped: 一次内部拖放落点完成（延后收尾由 ObjectSection
            的 _finalize_order_drop 执行）。
    """

    order_dropped = Signal()

    def dropEvent(self, event) -> None:
        """拖放落点：屏蔽信号执行默认移动逻辑，延后到下一拍收尾。

        Args:
            event: 拖放事件。
        """
        self.blockSignals(True)
        try:
            super().dropEvent(event)
        except Exception:  # pragma: no cover - 默认拖放异常时恢复信号防卡死
            self.blockSignals(False)
            raise
        # 信号恢复与映射重建延后到 _finalize_order_drop（覆盖源行删除阶段）
        QTimer.singleShot(0, self._finalize_order_drop)

    def _finalize_order_drop(self) -> None:
        """拖放收尾（事件循环下一拍执行）：恢复信号并通知排序完成。

        此时源行删除（startDrag 的 clearOrRemove）已完成、列表处于
        最终视觉顺序；信号恢复后发射 order_dropped，由 ObjectSection
        重建行号映射并通知主窗口重排画布形状。
        """
        self.blockSignals(False)
        self.order_dropped.emit()


class ObjectSection(_Section):
    """对象列表分区：当前图片上的全部标注对象（含 point 形状）。

    每项带可见性复选框与颜色圆点；支持多选（ExtendedSelection）、右键
    上下文菜单（编辑属性/删除/进入编辑模式）、双击条目进入编辑模式
    （复用右键"编辑"链路，与单击选择互不冲突）与内部拖拽排序（落点
    经 _finalize_order_drop 重建映射后经 objects_reordered 通知主窗口
    同步重排画布形状）。列表行号经 _object_indices 映射到
    canvas.shapes() 的真实形状下标；形状下标同时存于条目 UserRole
    数据（拖放副本经 mime 编解码保留，供重排后重建映射）。

    Signals:
        objects_selected(list): 用户选中对象集合变化（参数为形状下标列表）。
        shape_visibility_requested(int, bool): 用户切换对象列表项复选框
            （参数为形状下标与是否可见）。
        edit_object_requested(int): 右键"编辑"或双击条目请求编辑指定对象
            （参数为形状下标；主窗口进入编辑模式并弹出属性编辑窗）。
        delete_objects_requested(list): 右键请求删除选中对象
            （参数为形状下标列表）。
        enter_edit_mode_requested: 右键请求进入编辑模式。
        objects_reordered(list): 拖拽排序完成（参数为新视觉顺序的形状
            下标列表，new_order[i] = 重排后第 i 行对应的原形状下标）。
    """

    # 参数为对象下标列表（object 签名避免 QVariantList 转换）
    objects_selected = Signal(object)
    # 参数为形状下标 + 是否可见（对象列表复选框切换）
    shape_visibility_requested = Signal(int, bool)
    edit_object_requested = Signal(int)
    delete_objects_requested = Signal(object)
    enter_edit_mode_requested = Signal()
    # 参数为新顺序形状下标列表（object 签名避免 QVariantList 转换）
    objects_reordered = Signal(object)

    def __init__(self, parent=None):
        """初始化对象列表分区（多选 + 可见性复选框 + 右键菜单 + 双击编辑 + 拖拽排序）。"""
        super().__init__("对象", parent)
        self.setObjectName("objectSection")
        # 行号 → 形状下标映射（所有选中/编辑/删除交互均经此映射到
        # canvas.shapes() 的真实下标）
        self._object_indices: List[int] = []

        # _ObjectListWidget：支持 InternalMove 内部拖拽排序（dropEvent
        # 屏蔽中间态噪声信号并延后收尾，见类注释）
        self.list = _ObjectListWidget()
        self.list.setStyleSheet(
            "QListWidget { background-color: #fafafa; border: 0; }"
        )
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        # 拖拽排序：仅允许列表内部移动（不与外部部件交换数据），
        # 强制 Move 动作保证拖放语义为"移动"而非"复制"
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        # 拖放落点收尾：重建行号 → 形状下标映射并通知主窗口重排画布
        self.list.order_dropped.connect(self._on_order_dropped)
        # 双击条目：进入该对象编辑模式（复用右键"编辑"链路）
        self.list.itemDoubleClicked.connect(self._on_object_double_clicked)
        self.list.itemSelectionChanged.connect(
            self._on_object_selection_changed
        )
        # 复选框切换：发射形状可见性变化信号
        self.list.itemChanged.connect(self._on_object_item_changed)
        # 右键上下文菜单：编辑（仅单选）/删除（多选可用）/进入编辑模式
        self.list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.list.customContextMenuRequested.connect(
            self._on_object_context_menu
        )
        self.lay.addWidget(self.list, 1)

    def set_objects(self, items) -> None:
        """填充当前图片对象列表（全部形状），带可见性复选框与下标映射。

        清空与重建全程屏蔽信号：否则 clear() 会触发 itemSelectionChanged
        → objects_selected([]) → 反向清空画布选中集合（多选丢失），
        且设置复选框状态会触发 itemChanged → 误发射可见性信号。

        Args:
            items: (形状下标, 描述文本, 标签名, 是否可见, 圆点颜色) 五元组列表，
                形状下标为在 canvas.shapes() 中的真实下标；圆点颜色由调用方
                按"有合法组号用组色、否则用标签色"计算传入（与画布描边一致）。
        """
        lst = self.list
        lst.blockSignals(True)
        # 清空列表并同步重置行号 → 形状下标映射
        lst.clear()
        self._object_indices = []
        for shape_index, desc, _label, visible, color in items:
            item = QListWidgetItem(str(desc))
            item.setIcon(_color_dot_icon(color))
            # 复选框控制形状可见性（可由用户点击切换）
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
            )
            # 形状下标存入 UserRole：拖放副本经 mime 编解码保留该数据，
            # 重排完成后按条目 UserRole 重建行号 → 形状下标映射
            item.setData(Qt.ItemDataRole.UserRole, int(shape_index))
            lst.addItem(item)
            self._object_indices.append(int(shape_index))
        lst.blockSignals(False)

    def _on_object_double_clicked(self, item: QListWidgetItem) -> None:
        """双击条目：进入该对象编辑模式并弹出属性编辑窗。

        复用右键"编辑"链路（edit_object_requested → 主窗口先切编辑
        模式再弹属性窗）；双击的第一击已先行选中该行并同步画布选中，
        单击选择功能不受影响。双击落点为条目文本区（复选框区双击
        属快速连续切换可见性的边缘场景，不做特判）。

        Args:
            item: 被双击的列表项。
        """
        row = self.list.row(item)
        if 0 <= row < len(self._object_indices):
            self.edit_object_requested.emit(self._object_indices[row])

    def _on_order_dropped(self) -> None:
        """拖拽排序落点收尾：按最终视觉顺序重建映射并发射重排信号。

        触发时列表已完成 InternalMove 的两步重排（落点副本插入 + 源
        行删除），行序即用户期望的新顺序。按条目 UserRole 数据重建
        行号 → 形状下标映射；重建结果须为画布形状下标的合法排列
        （无重复缺失），且与收尾前的映射不一致（顺序确有变化）时才
        发射——拖放到无效位置或拖放被视图忽略时列表顺序不变，跳过
        以避免误发重排信号导致无意义置脏。
        """
        # 按最终视觉顺序从条目 UserRole 收集形状下标
        rebuilt = []
        for row in range(self.list.count()):
            data = self.list.item(row).data(Qt.ItemDataRole.UserRole)
            if data is None:
                return  # 条目缺少下标数据（异常状态）：放弃本次重排
            rebuilt.append(int(data))
        # 合法性校验：须为 0..n-1 的完整排列
        if sorted(rebuilt) != list(range(len(rebuilt))):
            return
        # 顺序未变化（无效拖放/拖放被忽略）：跳过，避免无意义置脏
        if rebuilt == self._object_indices:
            return
        self._object_indices = rebuilt
        # 拖放只改变顺序、不改变选中集合：画布选中按对象身份存储，
        # 重排天然保持；源行删除阶段被屏蔽的列表选中变化有意丢弃，
        # 后续 shapes_changed → _refresh_objects 会按画布选中恢复列表
        # 选中态（拖动项保持选中）。
        self.objects_reordered.emit(list(rebuilt))

    def _on_object_selection_changed(self) -> None:
        """对象列表选中集合变化：行号经映射转形状下标后发射。"""
        rows = sorted({idx.row() for idx in self.list.selectedIndexes()})
        self.objects_selected.emit([self._object_indices[r] for r in rows])

    def _on_object_item_changed(self, item: QListWidgetItem, *args) -> None:
        """对象列表项数据变化：复选框切换时发射形状可见性信号。

        PySide6 6.11.1 的 itemChanged 仅携带 item 参数（无 role），
        保留可选 role 参数以兼容带 role 的 Qt 版本（仅处理复选框角色）。

        Args:
            item: 数据变化的列表项。
            *args: 兼容携带 role 参数的 Qt 版本（当前版本不传，跳过检查）。
        """
        # role 检查不可用时跳过（当前 Qt 版本的 itemChanged 不携带 role）
        if args and args[0] != Qt.ItemDataRole.CheckStateRole:
            return
        row = self.list.row(item)
        if 0 <= row < len(self._object_indices):
            self.shape_visibility_requested.emit(
                self._object_indices[row],
                item.checkState() == Qt.CheckState.Checked,
            )

    def _on_object_context_menu(self, pos) -> None:
        """对象列表右键菜单：编辑（仅单选）/删除/进入编辑模式。

        右键未选中的项时先将其设为唯一选中（符合常规交互习惯）；
        多选时仅启用删除；单选时启用编辑与删除。编辑/删除发射的均为
        经行号 → 形状下标映射后的真实下标。

        Args:
            pos: 右键位置（列表部件局部坐标）。
        """
        lst = self.list
        # 右键命中的项若不在当前选中集合中，改为单选该项
        item = lst.itemAt(pos)
        if item is not None and not item.isSelected():
            lst.clearSelection()
            item.setSelected(True)
            lst.setCurrentRow(lst.row(item))
        rows = sorted({idx.row() for idx in lst.selectedIndexes()})
        indices = [self._object_indices[r] for r in rows]
        menu = QMenu(self)
        act_edit = menu.addAction("编辑")
        act_delete = menu.addAction("删除")
        menu.addSeparator()
        act_enter = menu.addAction("进入编辑模式")
        # 多选仅启用删除；单选启用编辑与删除；无选中全部禁用
        act_edit.setEnabled(len(rows) == 1)
        act_delete.setEnabled(bool(rows))
        chosen = menu.exec(lst.mapToGlobal(pos))
        if chosen is act_edit:
            self.edit_object_requested.emit(indices[0])
        elif chosen is act_delete:
            self.delete_objects_requested.emit(indices)
        elif chosen is act_enter:
            self.enter_edit_mode_requested.emit()

    def select_objects(self, indices) -> None:
        """程序化选中指定形状集合（画布多选联动，不发射信号）。

        按行号 → 形状下标映射选中对象列表对应行；未命中映射的下标
        自动忽略；indices 为空时列表全清。

        注意：不得调用 setCurrentRow 设置当前项——其内部选择命令会
        清除已设置的选中集合（ExtendedSelection 下实测破坏多选），
        必须以 NoUpdate 命令仅移动当前项。

        Args:
            indices: 形状下标列表（未出现在映射中的下标自动忽略）。
        """
        wanted = set(indices)
        lst = self.list
        lst.blockSignals(True)
        lst.clearSelection()
        # 选中形状下标命中映射的行，并记录最小命中行作为当前项
        first_row = -1
        for row, shape_index in enumerate(self._object_indices):
            if shape_index in wanted:
                lst.item(row).setSelected(True)
                if first_row < 0:
                    first_row = row
        # 仅移动当前项（NoUpdate：不改变选中集合）
        if first_row >= 0:
            lst.selectionModel().setCurrentIndex(
                lst.model().index(first_row, 0),
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )
        else:
            lst.setCurrentRow(-1)
        lst.blockSignals(False)

    def clear_object_selection(self) -> None:
        """清除对象列表选中态（不发射信号）。"""
        lst = self.list
        lst.blockSignals(True)
        lst.clearSelection()
        lst.setCurrentRow(-1)
        lst.blockSignals(False)

    def selected_object_indices(self) -> List[int]:
        """返回对象列表当前选中行经映射的形状下标列表。

        Returns:
            形状下标列表（按行序升序）。
        """
        rows = sorted({idx.row() for idx in self.list.selectedIndexes()})
        return [self._object_indices[r] for r in rows]


class FileSection(_Section):
    """文件列表分区：工作路径下全部图片（QListView + 检索代理模型）。

    顶部检索框（fileSearchEdit）经 FileSearchProxyModel 按文件名/标签/
    已标注状态实时过滤；检索无匹配时视图上覆盖"无匹配文件"空态提示。
    每项带只读"已标注"复选框（勾选状态由主窗口在保存后经
    set_file_annotated 维护）。

    Signals:
        file_selected(int): 用户选中文件（参数为文件在源模型中的下标，
            代理行号已经 mapToSource 转换）。
        file_edit_requested(int): 用户双击文件条目：请求加载该图片并
            进入编辑模式（参数为文件在源模型中的下标，代理行号已经
            mapToSource 转换）。
    """

    file_selected = Signal(int)
    # 双击条目：请求加载该图片并进入编辑模式（参数为源模型文件下标）
    file_edit_requested = Signal(int)

    def __init__(self, parent=None):
        """初始化文件列表分区（QListView 虚拟化 + 检索框 + 空态提示）。"""
        super().__init__("文件列表", parent)
        self.setObjectName("fileSection")
        # 源模型 + 检索代理：视图挂代理模型，按文件名/标签/已标注状态过滤
        self.file_model = FileListModel(self)
        self.file_proxy = FileSearchProxyModel(self)
        self.file_proxy.setSourceModel(self.file_model)
        # QListView（大目录不逐项建 item，UI 虚拟化）
        self.list = QListView()
        self.list.setModel(self.file_proxy)
        self.list.setStyleSheet(
            "QListView { background-color: #fafafa; border: 0; }"
        )
        # 检索框（标题与列表之间，实时过滤文件名/标签/标注状态）
        self.file_search_edit = QLineEdit()
        self.file_search_edit.setObjectName("fileSearchEdit")
        self.file_search_edit.setPlaceholderText("检索文件名/标签…")
        self.file_search_edit.setClearButtonEnabled(True)
        self.file_search_edit.textChanged.connect(self._on_file_search_changed)
        self.lay.addWidget(self.file_search_edit)
        self.lay.addWidget(self.list, 1)
        # 空态提示：覆盖在列表视图上，仅检索词非空且无匹配时显示
        self._file_empty_label = QLabel("无匹配文件", self.list)
        self._file_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._file_empty_label.setStyleSheet(
            "color: #a1a1aa; background-color: #fafafa; border: 0;"
        )
        self._file_empty_label.hide()
        # 视图尺寸变化时空态提示保持覆盖整个视图
        self.list.installEventFilter(self)
        # 当前行变化经 selectionModel 转发（视图挂代理模型，行号需
        # mapToSource 转回源模型行号）
        self.list.selectionModel().currentRowChanged.connect(
            lambda cur, _: self.file_selected.emit(
                self.file_proxy.mapToSource(cur).row() if cur.isValid() else -1
            )
        )
        # 双击条目：请求加载该图片并进入编辑模式（行号经 mapToSource 转换）
        self.list.doubleClicked.connect(self._on_file_double_clicked)
        # 代理行数变化（过滤生效/模型重置）与布局变化时同步空态提示显隐
        self.file_proxy.modelReset.connect(self._update_file_empty_state)
        self.file_proxy.layoutChanged.connect(self._update_file_empty_state)
        self.file_proxy.rowsInserted.connect(self._update_file_empty_state)
        self.file_proxy.rowsRemoved.connect(self._update_file_empty_state)

    def set_files(self, files, annotated=None) -> None:
        """填充文件列表（每项带只读"已标注"复选框）。

        复选框仅指示该文件是否已标注（勾选状态由主窗口在保存后经
        set_file_annotated 维护）；模型 flags 不含 ItemIsUserCheckable，
        用户不可点击切换。模型重置会自动清空选中态，无需屏蔽信号。
        重建后检索代理自动重过滤，检索框中的既有检索词保持生效。

        Args:
            files: 图片绝对路径列表（显示为文件名）。
            annotated: 与 files 等长的已标注布尔列表（None 时全部 False）。
        """
        if annotated is None:
            annotated = [False] * len(files)
        self.file_model.set_files(files, annotated)

    def set_file_tags(self, index: int, tags) -> None:
        """更新指定文件的标签集合（转发模型，供检索按标签过滤）。

        Args:
            index: 文件下标（越界时不操作）。
            tags: 该文件的标签集合（任意字符串可迭代对象）。
        """
        self.file_model.set_file_tags(index, tags)

    def set_file_annotated(self, index: int, checked: bool) -> None:
        """更新指定文件的已标注勾选状态（不发射信号）。

        Args:
            index: 文件下标（越界时不操作）。
            checked: 是否已标注（True 勾选 / False 取消勾选）。
        """
        self.file_model.set_row_state(index, checked)

    def _on_file_search_changed(self, text: str) -> None:
        """检索框文本变化：更新代理过滤词并同步空态提示。

        Args:
            text: 检索框文本。
        """
        self.file_proxy.set_filter_text(text)
        self._update_file_empty_state()

    def _update_file_empty_state(self) -> None:
        """同步文件列表空态提示：仅检索词非空且无匹配行时显示。"""
        has_text = bool(self.file_search_edit.text().strip())
        self._file_empty_label.setVisible(has_text and self.file_proxy.rowCount() == 0)

    def _on_file_double_clicked(self, proxy_index) -> None:
        """双击条目：请求加载该图片并进入编辑模式。

        Args:
            proxy_index: 双击命中的代理模型下标。
        """
        # 代理行号经 mapToSource 转回源模型行号（与 file_selected 一致）
        self.file_edit_requested.emit(
            self.file_proxy.mapToSource(proxy_index).row()
        )

    def eventFilter(self, obj, event) -> bool:
        """文件列表视图事件过滤：视图尺寸变化时保持空态提示覆盖全视图。

        Args:
            obj: 被观察对象。
            event: 事件。

        Returns:
            是否拦截事件（此处不拦截，交还原处理链）。
        """
        if obj is self.list and event.type() == QEvent.Type.Resize:
            self._file_empty_label.setGeometry(self.list.rect())
        return super().eventFilter(obj, event)

    def select_file(self, index: int) -> None:
        """程序化选中指定文件并滚动到可视区（行号经检索代理转换）。

        快捷键切换图片时同步文件列表选中行。不得屏蔽 selectionModel
        信号：视图依赖其 selectionChanged/currentRowChanged 驱动选中行
        重绘，屏蔽后选中状态虽正确但视觉不刷新（旧高亮残留，直至滚动
        触发整体重绘才"追上"）。回馈环路由主窗口 _on_file_selected 的
        index != _current_index 守卫阻断（_current_index 在本调用前已赋值）。
        目标文件正被检索过滤隐藏时不改动视图（保持检索词与过滤态，
        画布切换不受影响）；用户修改检索词后列表恢复过滤视野。

        Args:
            index: 文件下标（越界时不操作）。
        """
        view = self.list
        if 0 <= index < self.file_model.count():
            proxy_index = self.file_proxy.mapFromSource(self.file_model.index(index))
            if not proxy_index.isValid():
                return  # 目标被过滤隐藏：保持检索态与当前选中（不强行清过滤）
            view.setCurrentIndex(proxy_index)
            # 滚动到选中行（PositionAtCenter 保持行在视野中央附近）
            view.scrollTo(
                proxy_index,
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )


class RoiSection(_Section):
    """感知区列表分区：当前图片上的全部感知区（ROI 裁剪框）。

    每行文本形如 `ROI1  (120, 80) - (640, 480)  520×400`（坐标为四舍五入
    后的整数像素，宽高为 x2-x1 / y2-y1）；列表为单选，行号经 _roi_ids
    映射到 ROI 的 id，id 同时存于条目 UserRole 数据（不依赖条目文本解析）。
    单击/切换选中行与画布联动；双击或右键"定位"请求主窗口将视图缩放定位
    到该感知区；右键"删除"请求主窗口走统一确认链路删除。

    Signals:
        roi_selected(object): 用户单击/切换选中行（参数为 ROI 的 id，
            无选中时发射 None）。
        roi_locate_requested(object): 双击条目或右键"定位"（参数为 ROI
            的 id；主窗口将视图缩放定位到该感知区）。
        roi_delete_requested(object): 右键"删除"（参数为 ROI 的 id；
            主窗口走统一确认链路删除）。
    """

    # 参数为 ROI 的 id（object 签名避免 QVariant 转换；无选中为 None）
    roi_selected = Signal(object)
    # 参数为 ROI 的 id（双击/右键"定位"请求视图缩放定位）
    roi_locate_requested = Signal(object)
    # 参数为 ROI 的 id（右键"删除"请求，由主窗口统一确认后删除）
    roi_delete_requested = Signal(object)

    def __init__(self, parent=None):
        """初始化感知区列表分区（单选 + 双击定位 + 右键定位/删除）。"""
        super().__init__("感知区", parent)
        self.setObjectName("roiSection")
        # 行号 → ROI id 映射（选中/定位/删除交互均经此映射到真实 id，
        # 避免依赖条目文本解析）
        self._roi_ids: List[int] = []

        # 感知区列表：单选即可（同一图片的感知区定位/删除均为单目标操作）
        self.list = QListWidget()
        self.list.setStyleSheet(
            "QListWidget { background-color: #fafafa; border: 0; }"
        )
        # 双击条目：请求视图缩放定位到该感知区
        self.list.itemDoubleClicked.connect(self._on_roi_double_clicked)
        # 选中行变化：发射当前选中 ROI id（无选中发射 None）
        self.list.itemSelectionChanged.connect(
            self._on_roi_selection_changed
        )
        # 右键上下文菜单：定位 / 删除
        self.list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.list.customContextMenuRequested.connect(
            self._on_roi_context_menu
        )
        self.lay.addWidget(self.list, 1)

    def set_rois(self, rois) -> None:
        """填充感知区列表（清空并重建），每行显示 id 与归一化后的坐标。

        重建全程屏蔽信号：clear() 与逐行插入会触发 itemSelectionChanged
        → 误发 roi_selected（反向清空画布中已选中的感知区）。重建后清空
        选中，当前选中感知区仍存在时由主窗口随后调用 select_roi 恢复。
        非法条目（缺 id、box 长度不足 4、坐标非数值）跳过而不抛异常。

        Args:
            rois: ROI 字典列表，形如 {"id": int, "box": [x1, y1, x2, y2]}
                （图像像素坐标，已归一为左上/右下）。
        """
        lst = self.list
        lst.blockSignals(True)
        # 清空列表并同步重置行号 → ROI id 映射
        lst.clear()
        self._roi_ids = []
        for roi in rois or []:
            parsed = self._parse_roi(roi)
            if parsed is None:
                continue  # 非法条目：跳过（不中断整个列表重建）
            roi_id, x1, y1, x2, y2 = parsed
            item = QListWidgetItem(
                f"ROI{roi_id}  ({x1}, {y1}) - ({x2}, {y2})  "
                f"{x2 - x1}×{y2 - y1}"
            )
            # ROI id 存入 UserRole：供调试定位与后续扩展读取（行号映射
            # 与之保持一致，文本解析不作为数据来源）
            item.setData(Qt.ItemDataRole.UserRole, roi_id)
            lst.addItem(item)
            self._roi_ids.append(roi_id)
        # 重建后清空选中（当前选中 ROI 仍存在时由主窗口随后 select_roi 恢复）
        lst.clearSelection()
        lst.setCurrentRow(-1)
        lst.blockSignals(False)

    @staticmethod
    def _parse_roi(roi):
        """解析单条 ROI 数据（非法条目返回 None，由调用方跳过）。

        Args:
            roi: 待解析的 ROI 数据（期望 {"id": int, "box": [x1, y1, x2, y2]}）。

        Returns:
            (id, x1, y1, x2, y2) 五元组（坐标为四舍五入后的整数）；
            非字典、缺 id/box、box 长度不足 4 或坐标非数值时返回 None。
        """
        if not isinstance(roi, dict):
            return None
        roi_id = roi.get("id")
        box = roi.get("box")
        if roi_id is None or not isinstance(box, (list, tuple)) or len(box) < 4:
            return None
        try:
            roi_id = int(roi_id)
            # 坐标四舍五入为整数像素（宽高由整数坐标相减得到）
            x1, y1, x2, y2 = (int(round(float(box[i]))) for i in range(4))
        except (TypeError, ValueError):
            return None
        return roi_id, x1, y1, x2, y2

    def select_roi(self, roi_id) -> None:
        """程序化选中指定感知区行（不发射信号）。

        全程 blockSignals 静默设置：避免与主窗口形成"列表选中 → 画布
        联动 → 回填列表选中"的回环。roi_id 为 None 或未命中当前列表时
        清空选中。

        Args:
            roi_id: 目标 ROI 的 id（None 或未命中时清空选中）。
        """
        lst = self.list
        # 行号 → ROI id 映射中查找目标行（未命中为 -1）
        row = -1
        if roi_id is not None:
            for index, current_id in enumerate(self._roi_ids):
                if current_id == roi_id:
                    row = index
                    break
        lst.blockSignals(True)
        if row < 0:
            # 无选中行：清空选中并重置当前项
            lst.clearSelection()
            lst.setCurrentRow(-1)
        else:
            # 单选列表：设置当前行即完成选中
            lst.setCurrentRow(row)
        lst.blockSignals(False)

    def selected_roi_id(self) -> Optional[int]:
        """返回当前选中行对应的 ROI id（无选中返回 None）。

        Returns:
            选中 ROI 的 id；列表为空、无选中或行号越界时为 None。
        """
        rows = [idx.row() for idx in self.list.selectedIndexes()]
        if not rows:
            return None
        row = rows[0]
        if 0 <= row < len(self._roi_ids):
            return self._roi_ids[row]
        return None

    def roi_count(self) -> int:
        """返回当前感知区列表行数（供主窗口状态提示）。

        Returns:
            列表行数（ROI 数量）。
        """
        return self.list.count()

    def _on_roi_selection_changed(self) -> None:
        """感知区列表选中行变化：发射当前选中 ROI id（无选中发 None）。"""
        self.roi_selected.emit(self.selected_roi_id())

    def _on_roi_double_clicked(self, item: QListWidgetItem) -> None:
        """双击条目：请求主窗口将视图缩放定位到该感知区。

        Args:
            item: 被双击的列表项。
        """
        row = self.list.row(item)
        if 0 <= row < len(self._roi_ids):
            self.roi_locate_requested.emit(self._roi_ids[row])

    def _on_roi_context_menu(self, pos) -> None:
        """感知区列表右键菜单：定位（双击链路复用）/ 删除（统一确认链路）。

        右键未选中的项时先将其设为唯一选中（与对象列表交互一致）；右键
        空白处无命中项时两个动作均不可用，弹出菜单不产生任何操作。

        Args:
            pos: 右键位置（列表部件局部坐标）。
        """
        lst = self.list
        # 右键命中的项若不在当前选中集合中，改为单选该项
        item = lst.itemAt(pos)
        if item is not None and not item.isSelected():
            lst.clearSelection()
            item.setSelected(True)
            lst.setCurrentRow(lst.row(item))
        # 仅右键命中条目时才有可操作目标（空白处为 None）
        row = lst.row(item) if item is not None else -1
        roi_id = self._roi_ids[row] if 0 <= row < len(self._roi_ids) else None

        menu = QMenu(self)
        act_locate = menu.addAction("定位")
        act_delete = menu.addAction("删除")
        # 无命中项时两个动作均禁用（菜单仍弹出，符合常规交互）
        act_locate.setEnabled(roi_id is not None)
        act_delete.setEnabled(roi_id is not None)
        chosen = menu.exec(lst.mapToGlobal(pos))
        if roi_id is None:
            return  # 右键空白处：无操作
        if chosen is act_locate:
            self.roi_locate_requested.emit(roi_id)
        elif chosen is act_delete:
            self.roi_delete_requested.emit(roi_id)

