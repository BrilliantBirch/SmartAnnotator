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
    # 定义一个信号，用于通知文本变化
    textFinishedEdit = pyqtSignal(int, str)  # 参数：索引，新文本

    def __init__(self, text, list_widget, parent=None):
        super().__init__(parent)
        self.list_widget = list_widget  # 保存列表引用

        # 控件：可编辑文本框 + 删除按钮
        self.edit = QLineEdit(text)  # 替换QLabel为QLineEdit
        self.edit.setStyleSheet("border: none;")  # 去除边框，模拟标签外观
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
        layout.addStretch()
        layout.addWidget(self.del_btn)
        layout.setContentsMargins(2, 0, 0, 5)
        self.setLayout(layout)

        # 连接信号
        self.del_btn.clicked.connect(self.on_delete)
        self.edit.editingFinished.connect(self.on_text_editingFinished)  # 文本变化信号

    def on_delete(self):
        # 获取当前项索引并删除
        pos = self.pos()
        if isinstance(self.list_widget, QListWidget):
            index = self.list_widget.indexAt(pos)
            if index.isValid():
                self.list_widget.takeItem(index.row())

    def on_text_editingFinished(self):
        # 发送文本变化信号
        new_text = self.edit.text()
        pos = self.pos()
        if isinstance(self.list_widget, QListWidget):
            index = self.list_widget.indexAt(pos)
            if index.isValid():
                self.textFinishedEdit.emit(index.row(), new_text)

    def get_text(self):
        # 获取当前文本
        return self.edit.text()
