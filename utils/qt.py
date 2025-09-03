"""
Description：QT的控件

Author: Baibinnan
Date: 2025/8/27
LastEdit: 2025/8/27
E-mail: baibinnan@chuanfeng.com
update：

"""

from PyQt5.QtWidgets import (
    QMessageBox,
    QFileDialog,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QWidget,
    QListWidget,
    QCheckBox,
    QSpacerItem,
    QSizePolicy,
)
from PyQt5.QtCore import pyqtSignal


def showMessageBox(messageType: QMessageBox.Icon, message):
    """
    显示消息框
    """
    msg_box = QMessageBox()
    if messageType == QMessageBox.Icon.Information:
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setWindowTitle("信息")
        msg_box.setStandardButtons(QMessageBox.Ok)

    elif messageType == QMessageBox.Icon.Warning:
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("警告")
        msg_box.setStandardButtons(QMessageBox.Ok)
    elif messageType == QMessageBox.Icon.Critical:
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("错误")
        msg_box.setStandardButtons(QMessageBox.Ok)
    elif messageType == QMessageBox.Icon.Question:
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle("问题")
        msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

    msg_box.setText(message)
    msg_box.exec_()
    return msg_box.result()


def chooseDir(dir=None) -> str:
    """
    选择目录
    """
    dialog = QFileDialog(directory=dir)
    dialog.setWindowTitle("选择目录")
    dialog.setFileMode(QFileDialog.Directory)
    dialog.setOption(QFileDialog.ShowDirsOnly, True)
    # dialog.setOption(QFileDialog.DontUseNativeDialog)
    if dialog.exec_() == QFileDialog.Accepted:
        # 获取选中的目录（返回列表，取第一个元素）
        return dialog.selectedFiles()[0]
    return ""


class CustomItemWidget(QWidget):

    def __init__(self, text, list_widget, parent=None, check=False):
        super().__init__(parent)
        self.list_widget = list_widget  # 保存列表引用

        # 控件：可编辑文本框 + 删除按钮
        self.edit = QLineEdit(text)  # 替换QLabel为QLineEdit
        self.edit.setStyleSheet("border: none;")
        self.check = None
        self.checkEdit = None
        if check:
            self.edit.setPlaceholderText("请以_point{idx}结尾")
            self.edit.editingFinished.connect(self.on_edit_finished)
            self.check = QCheckBox("补充框")
            self.checkEdit = QLineEdit("")
            self.checkEdit.setPlaceholderText("大小")
            self.checkEdit.setStyleSheet("border: 1px solid #ddd; border-radius: 3px;")
            self.checkEdit.setMinimumWidth(150)  # 限制最小宽度，避免被压缩
        self.del_btn = QPushButton("×")
        self.del_btn.setStyleSheet(
            """
            QPushButton { border: none; color: red; font-size: 14px; }
            QPushButton:hover { background-color: #f0f0f0; border-radius: 12px; }
        """
        )

        self.del_btn.setFixedSize(24, 24)

        # 布局设置
        layout = QHBoxLayout()
        layout.addWidget(self.edit)
        if check:
            layout.addSpacing(10)  # 与主文本框保持间距
            layout.addWidget(self.check)
            layout.addWidget(self.checkEdit)
        layout.addSpacerItem(
            QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        layout.addWidget(self.del_btn)
        layout.setContentsMargins(2, 5, 2, 5)
        self.setLayout(layout)

        # 连接信号
        self.del_btn.clicked.connect(self.on_delete)

    def on_delete(self):
        # 获取当前项索引并删除
        pos = self.pos()
        if isinstance(self.list_widget, QListWidget):
            index = self.list_widget.indexAt(pos)
            if index.isValid():
                self.list_widget.takeItem(index.row())

    def get_text(self):
        # 获取当前文本
        return self.edit.text()

    def get_check_status(self):
        # 获取当前文本
        return self.check.isChecked()

    def get_check_size(self):
        # 获取当前文本
        return self.checkEdit.text()

    def on_edit_finished(self):
        # 检查输入是否为空
        if len(self.get_text().split("_point")) < 2:
            self.edit.setText("")
