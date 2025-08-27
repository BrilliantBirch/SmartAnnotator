"""
Description：QT对话框

Author: Baibinnan
Date: 2025/8/27
LastEdit: 2025/8/27
E-mail: baibinnan@chuanfeng.com
update：

"""

from PyQt5.QtWidgets import QMessageBox, QFileDialog


def showMessageBox(messageType: QMessageBox.Icon, message):
    """
    显示消息框
    """
    msg_box = QMessageBox()
    if messageType == QMessageBox.Icon.Information:
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("信息")
        msg_box.setStandardButtons(QMessageBox.Ok)

    elif messageType == QMessageBox.Icon.Warning:
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("警告")
        msg_box.setStandardButtons(QMessageBox.Ok)
    elif messageType == QMessageBox.Icon.Critical:
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("错误")
        msg_box.setStandardButtons(QMessageBox.Ok)
    elif messageType == QMessageBox.Icon.Question:
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("问题")
        msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

    msg_box.setText(message)
    msg_box.exec_()


def chooseDir(parent=None) -> str:
    """
    选择目录
    """
    dialog = QFileDialog(directory=parent)
    dialog.setWindowTitle("选择目录")
    dialog.setFileMode(QFileDialog.Directory)
    dialog.setOption(QFileDialog.ShowDirsOnly, True)
    # dialog.setOption(QFileDialog.DontUseNativeDialog)
    if dialog.exec_() == QFileDialog.Accepted:
        # 获取选中的目录（返回列表，取第一个元素）
        return dialog.selectedFiles()[0]
