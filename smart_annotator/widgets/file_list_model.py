# -*- coding: utf-8 -*-
"""
文件列表模型 - FileListModel

QAbstractListModel 通用文件列表模型（UI 虚拟化）：一次性持有全量文件
路径（路径本身轻量，10 万条字符串仅数 MB），视图（QListView）只为
可见行调用 data() 渲染，不为每个文件创建 QListWidgetItem 常驻控件，
万级目录打开文件列表不再逐项建 item 卡顿。

设计要点：
    - 数据与状态分离：路径列表 + 可选的行状态（如"已标注"复选框）；
      状态经 set_row_state 增量更新（dataChanged 精确刷新单行）
    - 只读复选框：flags 不含 ItemIsUserCheckable，复选框仅作状态
      指示（用户不可点击切换），由宿主程序化维护
    - 选中/当前行操作由 QListView 的 selectionModel 承担
    - 每行可携带标签集合（TagsRole，供检索代理按标签过滤），经
      set_file_tags 增量填充；配套 FileSearchProxyModel 提供文件名/
      标签/标注状态实时过滤与命中行高亮

作者: BaiBinnan
创建日期: 2026-09-04
更新: 2026-09-07 新增 TagsRole（每文件标注标签集合）与 set_file_tags 增量
      填充接口（dataChanged 精确刷新）；新增 FileSearchProxyModel 检索
      代理模型（文件名/标签/已标注状态词过滤 + 命中行高亮底色）
"""

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor

# 过滤激活（检索词非空）时命中行的背景高亮色（淡黄，与 #fafafa 浅色主题协调）
_FILTER_HIGHLIGHT = QColor(255, 243, 205)


class FileListModel(QAbstractListModel):
    """通用文件列表模型（全量路径 + 可选行状态/标签集合，供 QListView 渲染）。"""

    # 自定义角色：每文件标注标签集合（data() 返回 list[str]，UserRole+1）
    TagsRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None):
        """初始化空模型（无文件、无状态、无标签）。"""
        super().__init__(parent)
        self._files: list[str] = []       # 文件路径列表（行序即列表序）
        self._checked: list[bool] = []    # 与 _files 等长的行状态（None 视为未启用）
        self._tags: list[set] = []        # 与 _files 等长的行标签集合（set[str]，默认空）

    # ---------------- QAbstractListModel 必需接口 ----------------
    def rowCount(self, parent=QModelIndex()) -> int:
        """返回文件总数（列表模型无层级，有效父索引返回 0）。

        Args:
            parent: 父索引。
        """
        return 0 if parent.isValid() else len(self._files)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """按角色返回行数据（文件名 / 路径 / 状态复选框 / 标签集合）。

        Args:
            index: 行索引。
            role: 数据角色（DisplayRole / ToolTipRole / UserRole /
                CheckStateRole / TagsRole）。

        Returns:
            对应数据；索引无效或角色不匹配返回 None。
        """
        if not index.isValid() or not (0 <= index.row() < len(self._files)):
            return None
        row = index.row()
        if role == Qt.ItemDataRole.DisplayRole:
            # 文件名（跨平台路径分隔符取最后一段）
            path = self._files[row]
            return path.replace("\\", "/").rsplit("/", 1)[-1]
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._files[row]  # 悬停显示完整路径
        if role == Qt.ItemDataRole.UserRole:
            return self._files[row]
        if role == FileListModel.TagsRole:
            # 标签集合的列表形式（QVariant 不承载 set，列表语义等价）
            return list(self._tags[row])
        if role == Qt.ItemDataRole.CheckStateRole and self._checked:
            # 行状态复选框（未启用时返回 None 不渲染复选框）
            return (
                Qt.CheckState.Checked
                if self._checked[row]
                else Qt.CheckState.Unchecked
            )
        return None

    def flags(self, index):
        """行可选中；不含 ItemIsUserCheckable（复选框只读，仅状态指示）。"""
        return super().flags(index)

    # ---------------- 数据填充与状态维护 ----------------
    def set_files(self, files, checked=None) -> None:
        """整体替换文件列表（模型重置，选中态由视图自动清空）。

        Args:
            files: 文件路径列表（行序即列表序）。
            checked: 与 files 等长的行状态列表（None = 不启用复选框）。
        """
        self.beginResetModel()
        self._files = [str(f) for f in files]
        self._checked = [bool(c) for c in checked] if checked is not None else []
        # 标签集合随列表重建清空（由宿主经 set_file_tags 分批增量填充）
        self._tags = [set() for _ in self._files]
        self.endResetModel()

    def set_row_state(self, row: int, checked: bool) -> None:
        """更新单行状态（精确 dataChanged 刷新，不扰动选中态）。

        Args:
            row: 文件下标（越界或不启用状态时无操作）。
            checked: 新状态。
        """
        if self._checked and 0 <= row < len(self._checked):
            self._checked[row] = checked
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.CheckStateRole])

    def set_file_tags(self, row: int, tags) -> None:
        """更新单行标签集合（增量填充，精确 dataChanged 刷新）。

        供宿主在后台分批读取标注 JSON 后逐行填充标签（万级目录下
        避免一次性同步读盘卡 UI）；检索代理按 TagsRole 过滤。

        Args:
            row: 文件下标（越界时无操作）。
            tags: 该文件的标签集合（任意字符串可迭代对象，存为 set[str]）。
        """
        if 0 <= row < len(self._files):
            self._tags[row] = {str(t) for t in tags}
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [FileListModel.TagsRole])

    def file_at(self, row: int) -> str:
        """返回指定行文件路径。

        Args:
            row: 文件下标。

        Returns:
            路径；越界返回空字符串。
        """
        if 0 <= row < len(self._files):
            return self._files[row]
        return ""

    def count(self) -> int:
        """返回文件总数。"""
        return len(self._files)


class FileSearchProxyModel(QSortFilterProxyModel):
    """文件列表检索代理模型：按文件名 / 标签 / 标注状态实时过滤。

    过滤规则（检索词去空白并转小写，空词全部接受；任一命中即接受）：
        - 文件名（DisplayRole）不区分大小写包含检索词；
        - 文件任一标签（TagsRole）包含检索词；
        - 状态词命中：检索词含"未标注"/"unannotated" → 仅未标注文件；
          含"已标注"/"annotated" → 仅已标注文件（状态词优先判定"未标注"，
          因其包含"已标注"子串）。
    过滤激活（检索词非空）时，命中行 BackgroundRole 返回淡黄高亮底色。

    增量填充联动：内建再过滤仅由 filterRole（DisplayRole）触发，标签
    （TagsRole）/标注状态（CheckStateRole）变化需显式监听源模型
    dataChanged 后重过滤；经 0ms 单发定时器合并（分批填充同批多次
    dataChanged 只触发一次 invalidateFilter，万级目录不卡 UI）。
    """

    def __init__(self, parent=None):
        """初始化代理（空检索词 = 显示全部文件）。"""
        super().__init__(parent)
        self._filter_text = ""  # 当前检索词（去空白并转小写）
        # 延迟再过滤定时器（0ms 单发：合并同一事件循环内的多次源数据变更）
        self._refilter_timer = QTimer(self)
        self._refilter_timer.setSingleShot(True)
        self._refilter_timer.setInterval(0)
        self._refilter_timer.timeout.connect(self._refilter_now)

    # ---------------- 检索入口 ----------------
    def set_filter_text(self, text: str) -> None:
        """设置检索词并立即重过滤（实时检索入口）。

        Args:
            text: 检索框文本（空 = 显示全部文件）。
        """
        normalized = (text or "").strip().lower()
        if normalized == self._filter_text:
            return
        self._filter_text = normalized
        self.invalidateFilter()

    # ---------------- 过滤联动 ----------------
    def setSourceModel(self, source_model) -> None:
        """设置源模型并连接其 dataChanged（标签/状态变化触发再过滤）。

        Args:
            source_model: 源模型（FileListModel）。
        """
        old_model = self.sourceModel()
        if old_model is not None:
            try:
                old_model.dataChanged.disconnect(self._on_source_data_changed)
            except (RuntimeError, TypeError):
                pass  # 连接已断开（重复设置源模型时容错）
        super().setSourceModel(source_model)
        if source_model is not None:
            source_model.dataChanged.connect(self._on_source_data_changed)

    def _on_source_data_changed(self, top_left, bottom_right, roles) -> None:
        """源模型数据变化：检索激活时对标签/标注状态变更安排再过滤。

        Args:
            top_left: 变更区域左上角索引（仅为信号签名，未使用）。
            bottom_right: 变更区域右下角索引（仅为信号签名，未使用）。
            roles: 变更角色列表。
        """
        if not self._filter_text:
            return
        if not roles or FileListModel.TagsRole in roles or Qt.ItemDataRole.CheckStateRole in roles:
            self._refilter_timer.start()  # 合并同批多次变更，事件循环空闲时统一重过滤

    def _refilter_now(self) -> None:
        """定时器回调：执行延迟重过滤（合并分批填充的多次增量写入）。"""
        self.invalidateFilter()

    # ---------------- 过滤与渲染 ----------------
    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        """过滤单行：空词全部接受；否则文件名/任一标签/状态词任一命中即接受。

        Args:
            source_row: 源模型行号。
            source_parent: 源模型父索引（列表模型恒无效）。

        Returns:
            该行是否可见。
        """
        if not self._filter_text:
            return True
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        # 1) 文件名命中（DisplayRole，不区分大小写包含）
        name = str(model.data(index, Qt.ItemDataRole.DisplayRole) or "").lower()
        if self._filter_text in name:
            return True
        # 2) 任一标签包含命中
        for tag in model.data(index, FileListModel.TagsRole) or ():
            if self._filter_text in str(tag).lower():
                return True
        # 3) 状态词命中（先判"未标注"：其包含"已标注"子串）
        is_annotated = (
            model.data(index, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
        )
        if "未标注" in self._filter_text or "unannotated" in self._filter_text:
            return not is_annotated
        if "已标注" in self._filter_text or "annotated" in self._filter_text:
            return is_annotated
        return False

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """过滤激活时为命中行追加淡黄高亮底色（其余角色透传源模型）。

        Args:
            index: 代理索引。
            role: 数据角色。

        Returns:
            角色数据；索引无效或角色不匹配返回 None。
        """
        # 检索词非空：全部可见行即命中行，统一高亮提示过滤生效
        if role == Qt.ItemDataRole.BackgroundRole and self._filter_text and index.isValid():
            return _FILTER_HIGHLIGHT
        return super().data(index, role)
