# -*- coding: utf-8 -*-
"""
字段控件 - PathField / LabeledSpin / CustomItemWidget

PathField: 只读路径输入框 + 浏览按钮，发射 path_changed 信号。
LabeledSpin: 标签 + 数值输入框（int/double）组合控件。
CustomItemWidget: 可编辑列表项（类别/关键点编辑器），移植自 utils/qt.py。

作者: BaiBinnan
创建日期: 2026-08-10
"""

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QCheckBox,
    QSpacerItem,
    QSizePolicy,
    QListWidget,
)
from PySide6.QtCore import Signal, Qt, QObject, QEvent

from .buttons import SecondaryButton
from .dialogs import chooseDir, chooseFile


class FocusAwareSpinBox(QSpinBox):
    """焦点感知的整数输入框 - 仅在已获焦时响应鼠标滚轮。

    重写 wheelEvent：未获焦时忽略滚轮事件，防止鼠标悬停滚轮误改值。
    配合 StrongFocus 策略，确保滚轮仅在点击/Tab 获焦后生效。
    """

    def wheelEvent(self, event):
        """仅当控件已获焦时才将滚轮事件传递给父类处理（stepBy）。"""
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class FocusAwareDoubleSpinBox(QDoubleSpinBox):
    """焦点感知的浮点数输入框 - 仅在已获焦时响应鼠标滚轮。

    重写 wheelEvent：未获焦时忽略滚轮事件，防止鼠标悬停滚轮误改值。
    配合 StrongFocus 策略，确保滚轮仅在点击/Tab 获焦后生效。
    """

    def wheelEvent(self, event):
        """仅当控件已获焦时才将滚轮事件传递给父类处理（stepBy）。"""
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class _WheelGuardFilter(QObject):
    """滚轮守卫事件过滤器 - 对未使用 FocusAware 子类的数值控件提供兜底保护。

    拦截 Wheel 事件：仅当目标控件已获焦时放行，否则忽略，防止悬停滚轮误改值。
    作为 apply_click_to_focus 的补充，覆盖非 LabeledSpin 创建的数值控件。
    """

    def eventFilter(self, obj, event):
        """拦截未获焦控件的滚轮事件。

        Args:
            obj: 被监控的控件。
            event: 事件对象。

        Returns:
            True 表示拦截事件（不传递给控件），False 表示放行。
        """
        if event.type() == QEvent.Type.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return False


# 滚轮守卫过滤器单例（避免为每个控件重复创建）
_wheel_guard = _WheelGuardFilter()


class PathField(QWidget):
    """路径字段 - 只读输入框 + 浏览按钮。

    支持目录选择或文件选择模式。路径变化时发射 path_changed 信号。

    Attributes:
        line_edit: 只读路径显示框。
        browse_btn: 浏览按钮。
    """

    path_changed = Signal(str)

    def __init__(
        self,
        browse_type: str = "dir",
        file_filter: str = "",
        placeholder: str = "点击右侧按钮选择路径",
        parent=None,
    ):
        """初始化路径字段。

        Args:
            browse_type: "dir" 选择目录，"file" 选择文件。
            file_filter: 文件过滤器（browse_type="file" 时生效），如 "模型 (*.onnx *.engine)"。
            placeholder: 占位提示文本。
            parent: 父控件。
        """
        super().__init__(parent)
        self._browse_type = browse_type
        self._file_filter = file_filter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.line_edit = QLineEdit()
        self.line_edit.setReadOnly(True)
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        self.browse_btn = SecondaryButton("浏览")
        self.browse_btn.clicked.connect(self._on_browse)

        layout.addWidget(self.line_edit)
        layout.addWidget(self.browse_btn)

    def _on_browse(self) -> None:
        """点击浏览按钮，打开文件/目录对话框。"""
        if self._browse_type == "dir":
            path = chooseDir(self.line_edit.text())
        else:
            path = chooseFile(self._file_filter, self.line_edit.text())
        if path:
            self.line_edit.setText(path)
            self.path_changed.emit(path)

    def path(self) -> str:
        """返回当前路径。"""
        return self.line_edit.text()

    def set_path(self, path: str) -> None:
        """设置路径（不触发信号，用于配置回填）。

        Args:
            path: 路径字符串。
        """
        self.line_edit.setText(path)


class LabeledSpin(QWidget):
    """标签 + 数值输入框组合控件。

    用于推理参数（置信度、NMS、抽帧间隔等）。

    Attributes:
        spin: 数值输入框（QSpinBox 或 QDoubleSpinBox）。
    """

    def __init__(
        self,
        label: str,
        spin_type: str = "double",
        minimum=0,
        maximum=9999,
        step=0.01,
        value=0.0,
        parent=None,
    ):
        """初始化带标签的数值输入框。

        Args:
            label: 标签文本。
            spin_type: "double" 或 "int"。
            minimum: 最小值。
            maximum: 最大值。
            step: 步长。
            value: 默认值。
            parent: 父控件。
        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.label = QLabel(label)
        self.label.setMinimumWidth(80)
        layout.addWidget(self.label)

        if spin_type == "double":
            self.spin = FocusAwareDoubleSpinBox()
            self.spin.setDecimals(2)
            self.spin.setRange(float(minimum), float(maximum))
            self.spin.setSingleStep(float(step))
            self.spin.setValue(float(value))
        else:
            self.spin = FocusAwareSpinBox()
            self.spin.setRange(int(minimum), int(maximum))
            self.spin.setSingleStep(int(step))
            self.spin.setValue(int(value))
        # 焦点策略：StrongFocus（点击/Tab 获焦），禁用 WheelFocus
        # 配合 FocusAware 子类的 wheelEvent 重写，确保滚轮仅在获焦后生效
        self.spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.spin.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self.spin)

    def value(self):
        """返回当前值。"""
        return self.spin.value()

    def set_value(self, value) -> None:
        """设置当前值。

        Args:
            value: 数值。
        """
        self.spin.setValue(value)


class CustomItemWidget(QWidget):
    """可编辑列表项 - 用于类别/关键点编辑器。

    含可编辑文本框 + 可选复选框（关键点补充框）+ 可选大小输入框 + 删除按钮。
    移植自 utils/qt.py，改 PyQt5 → PySide6。

    Attributes:
        edit: 文本输入框。
        check: 复选框（关键点模式）。
        checkEdit: 大小输入框（关键点模式）。
        del_btn: 删除按钮。
    """

    def __init__(
        self,
        text: str,
        list_widget,
        parent=None,
        check: bool = False,
        checkDesc: str = "补充框",
        hideCheckEdit: bool = False,
        placeholder: str = "大小",
        checked: bool = False,
        bbox_size: int = 10,
    ):
        """初始化可编辑列表项。

        Args:
            text: 初始文本。
            list_widget: 所属 QListWidget 引用（用于删除定位）。
            parent: 父控件。
            check: 是否启用复选框（关键点模式）。
            checkDesc: 复选框描述。
            hideCheckEdit: 是否隐藏大小输入框。
            placeholder: 大小输入框占位文本。
            checked: 复选框初始状态。
            bbox_size: 大小输入框初始值。
        """
        super().__init__(parent)
        self.list_widget = list_widget  # 保存列表引用

        # 控件：可编辑文本框 + 删除按钮
        self.edit = QLineEdit(text)
        self.edit.setStyleSheet("border: none;")
        self.check = None
        self.checkEdit = None
        if check:
            self.edit.setPlaceholderText("请以_point{idx}结尾")
            self.edit.editingFinished.connect(self.on_edit_finished)
            self.check = QCheckBox(checkDesc)
            self.check.setChecked(checked)
            if not hideCheckEdit:
                self.checkEdit = QLineEdit(str(bbox_size))
                self.checkEdit.setPlaceholderText(placeholder)
                self.checkEdit.setStyleSheet(
                    "border: 1px solid #e4e4e7; border-radius: 6px; padding: 2px 6px;"
                )
                self.checkEdit.setMinimumWidth(120)
        self.del_btn = QPushButton("×")
        self.del_btn.setStyleSheet(
            """
            QPushButton { border: none; color: #ef4444; font-size: 16px; font-weight: 700; }
            QPushButton:hover { background-color: #fee2e2; border-radius: 12px; }
        """
        )
        self.del_btn.setFixedSize(24, 24)

        # 布局设置
        layout = QHBoxLayout()
        layout.addWidget(self.edit)
        if check:
            layout.addSpacing(10)
            layout.addWidget(self.check)
            if self.checkEdit is not None:
                layout.addWidget(self.checkEdit)
        layout.addSpacerItem(
            QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        layout.addWidget(self.del_btn)
        layout.setContentsMargins(2, 5, 2, 5)
        self.setLayout(layout)

        # 连接信号
        self.del_btn.clicked.connect(self.on_delete)

    def on_delete(self) -> None:
        """删除当前列表项。"""
        pos = self.pos()
        if isinstance(self.list_widget, QListWidget):
            index = self.list_widget.indexAt(pos)
            if index.isValid():
                self.list_widget.takeItem(index.row())

    def get_text(self) -> str:
        """返回文本框内容。"""
        return self.edit.text()

    def get_check_status(self) -> bool:
        """返回复选框状态。"""
        return self.check.isChecked()

    def get_check_size(self) -> str:
        """返回大小输入框内容。"""
        return self.checkEdit.text()

    def on_edit_finished(self) -> None:
        """文本编辑完成校验（关键点命名须以 _point 结尾）。"""
        if len(self.get_text().split("_point")) < 2:
            self.edit.setText("")


def apply_click_to_focus(root: QWidget) -> int:
    """递归将 root 下所有数值输入控件设为点击获焦 + 滚轮守卫。

    对每个 QSpinBox/QDoubleSpinBox：
        1. 设置 StrongFocus 策略（点击/Tab 获焦，禁用滚轮悬停获焦）
        2. 若非 FocusAware 子类，安装 _WheelGuardFilter 拦截未获焦时的滚轮事件

    确保所有数值控件遵循"点击获焦后滚轮方可调值"的交互规则。

    Args:
        root: 待处理的根控件（通常为页面或对话框）。

    Returns:
        已处理的控件数量。
    """
    from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox

    count = 0
    for spin in root.findChildren(QSpinBox):
        spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # 非 FocusAware 子类需安装滚轮守卫过滤器兜底
        if not isinstance(spin, FocusAwareSpinBox):
            spin.installEventFilter(_wheel_guard)
        count += 1
    for spin in root.findChildren(QDoubleSpinBox):
        spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if not isinstance(spin, FocusAwareDoubleSpinBox):
            spin.installEventFilter(_wheel_guard)
        count += 1
    return count
