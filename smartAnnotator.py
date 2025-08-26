"""
Description：自动标注工具的主程序
Author: Baibinnan
Date: 2025/8/25
LastEdit: 2025/8/26
E-mail: baibinnan@chuanfeng.com
update：

"""

import argparse
import sys

from cfg import __APPNAME__, __VERSION__, LOGGER
from ui import Ui_MainWindow

from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.mainWindow = Ui_MainWindow()
        self.mainWindow.setupUi(self)
        pixmap = QPixmap("resources/images/welcome.png")
        scaled_pixmap = pixmap.scaled(
            self.mainWindow.welcomeImageLabel.size(),  # 适应QLabel的大小
            Qt.KeepAspectRatio,  # 保持宽高比
            Qt.SmoothTransformation,  # 平滑缩放（抗锯齿）
        )
        self.mainWindow.welcomeImageLabel.setPixmap(scaled_pixmap)
        self.currentWorkingDir = ""

        self.name_index_map = self._build_name_index_map()
        self.bindEvents()

    def bindEvents(self):
        """
        信号槽绑定事件
        """
        # self.mainWindow.actionExit.triggered.connect(self.close)
        self.mainWindow.actionConvert.triggered.connect(
            lambda: self.changePage("convertPage")
        )

        self.mainWindow.actionAnnotate.triggered.connect(
            lambda: self.changePage("annotatePage")
        )
        self.mainWindow.actionModify.triggered.connect(
            lambda: self.changePage("modifyPage")
        )
        self.mainWindow.actionexport.triggered.connect(
            lambda: self.changePage("exportPage")
        )

    def showMessageBox(self, messageType: QMessageBox.Icon, message):
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

    def _build_name_index_map(self):
        """
        构建页面名称与索引的映射关系
        """
        name_map = {}
        for i in range(self.mainWindow.stackedWidget.count()):
            page = self.mainWindow.stackedWidget.widget(i)  # 获取第i个页面
            page_name = page.objectName()  # 获取页面名称
            name_map[page_name] = i  # 存储 名称→索引
        return name_map

    def setProcessLabel(self, text):
        """
        设置进度条的标签
        """
        self.mainWindow.statusLabel.setText(text)

    def setProcessValue(self, value):
        """
        设置进度条的值
        """
        if value <= 100.0 and value >= 0.0:
            self.mainWindow.progressBar.setValue(value)

    def changePage(self, page_name):
        """
        切换页面
        """
        if page_name in self.name_index_map:
            index = self.name_index_map[page_name]
            self.mainWindow.stackedWidget.setCurrentIndex(index)
        else:
            LOGGER.error(f"页面切换失败，未找到页面：{page_name}")
            self.showMessageBox(
                QMessageBox.Icon.Warning, f"页面切换失败，未找到页面：{page_name}"
            )


def get_main_app(argv=[]):
    """
    没有方便通过单线程测试应用的方式，所以这里没有使用app.exec_()
    """
    app = QApplication(argv)
    app.setApplicationName(__APPNAME__)
    # app.setWindowIcon(newIcon("app"))
    arg_parser = argparse.ArgumentParser()
    # arg_parser.add_argument("--lang", type=str, default="ch", nargs="?")

    args = arg_parser.parse_args(argv[1:])
    win = MainWindow()
    win.show()
    return app, win


def main():
    """
    程序进入点
    """
    app, win = get_main_app(sys.argv)
    LOGGER.info(f"{__APPNAME__},版本： {__VERSION__} 启动")
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
