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

作者: BaiBinnan
创建日期: 2026-09-04
"""

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class FileListModel(QAbstractListModel):
    """通用文件列表模型（全量路径 + 可选行状态，供 QListView 渲染）。"""

    def __init__(self, parent=None):
        """初始化空模型（无文件、无状态）。"""
        super().__init__(parent)
        self._files: list[str] = []       # 文件路径列表（行序即列表序）
        self._checked: list[bool] = []    # 与 _files 等长的行状态（None 视为未启用）

    # ---------------- QAbstractListModel 必需接口 ----------------
    def rowCount(self, parent=QModelIndex()) -> int:
        """返回文件总数（列表模型无层级，有效父索引返回 0）。

        Args:
            parent: 父索引。
        """
        return 0 if parent.isValid() else len(self._files)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """按角色返回行数据（文件名 / 路径 / 状态复选框）。

        Args:
            index: 行索引。
            role: 数据角色（DisplayRole / ToolTipRole / UserRole /
                CheckStateRole）。

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
