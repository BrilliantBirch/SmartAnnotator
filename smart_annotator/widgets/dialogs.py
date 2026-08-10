# -*- coding: utf-8 -*-
"""
对话框工具 - chooseDir / chooseFile / showMessageBox

移植自旧版 utils/qt.py，改 PyQt5 → PySide6（exec_ → exec）。

作者: BaiBinnan
创建日期: 2026-08-10
"""

from PySide6.QtWidgets import QMessageBox, QFileDialog


def showMessageBox(messageType: QMessageBox.Icon, message: str) -> int:
    """显示消息框。

    Args:
        messageType: 消息类型（Information/Warning/Critical/Question）。
        message: 消息文本。

    Returns:
        点击的标准按钮值（QMessageBox.StandardButton）。
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
    msg_box.exec()
    return msg_box.result()


def chooseDir(dir: str = "") -> str:
    """选择目录。

    Args:
        dir: 默认起始目录。

    Returns:
        选中的目录路径，取消时返回空字符串。
    """
    dialog = QFileDialog(directory=dir if dir else None)
    dialog.setWindowTitle("选择目录")
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    if dialog.exec() == QFileDialog.DialogCode.Accepted:
        return dialog.selectedFiles()[0]
    return ""


def chooseFile(suffix: str, dir: str = "") -> str:
    """选择文件。

    Args:
        suffix: 文件过滤器，如 "模型 (*.onnx *.engine)"。
        dir: 默认起始目录。

    Returns:
        选中的文件路径，取消时返回空字符串。
    """
    dialog = QFileDialog(directory=dir if dir else None)
    dialog.setWindowTitle("选择文件")
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setNameFilter(suffix)
    if dialog.exec() == QFileDialog.DialogCode.Accepted:
        return dialog.selectedFiles()[0]
    return ""
