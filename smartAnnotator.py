"""
Description：自动标注工具的主程序
Author: Baibinnan
Date: 2025/8/25
LastEdit: 2025/8/27
E-mail: baibinnan@chuanfeng.com
update：

"""

import argparse
import sys

from cfg import __APPNAME__, __VERSION__, LOGGER, MODE, SysConfig, TASK
from utils import add_text_browser_handler, chooseDir, showMessageBox

from ui import Ui_MainWindow


from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.mainWindow = Ui_MainWindow()
        self.mainWindow.setupUi(self)

        self.initUI()
        self.initSys()
        self.initLogger()
        self.bindEvents()

    def initSys(self):
        """
        初始化系统相关设置
        """
        self.currentWorkingDir = ""
        # 当前模式
        self.sysConfig = SysConfig()

    def initLogger(self):
        init = add_text_browser_handler(LOGGER.name, self.mainWindow.logBrowser, 500)
        if init:
            LOGGER.info("前端日志记录器初始化完成")
        else:
            LOGGER.error("前端日志记录器初始化失败")

    def initUI(self):
        """
        初始化UI
        """
        # 加载并设置图片以及logo
        pixmap = QPixmap("resources/images/welcome.png")
        scaled_pixmap = pixmap.scaled(
            self.mainWindow.welcomeImageLabel.size(),  # 适应QLabel的大小
            Qt.KeepAspectRatio,  # 保持宽高比
            Qt.SmoothTransformation,  # 平滑缩放（抗锯齿）
        )
        self.mainWindow.welcomeImageLabel.setPixmap(scaled_pixmap)
        self.setWindowIcon(QIcon("resources/images/welcome.ico"))
        # 加载模式类型
        for mode in MODE:
            self.mainWindow.taskComBox.addItem(mode.name, mode.value)
        self.name_index_map = self._build_name_index_map()
        self.changePage("welcomePage")

    def initConveter(self):
        """
        初始化转换器
        """
        pass

    def initAnnotator(self):
        """
        初始化标注器
        """
        pass

    def initModifier(self):
        """
        初始化修改器
        """
        pass

    def initExporter(self):
        """
        初始化导出器
        """
        pass

    def bindEvents(self):
        """
        信号槽绑定事件
        """
        try:
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
            # converter
            self.mainWindow.convertInputBtn.clicked.connect(
                lambda: self.updateConvertInputDir()
            )
            self.mainWindow.convertOutputBtn.clicked.connect(
                lambda: self.updateConvertOutputDir()
            )
            # self.mainWindow.convertInput.textChanged.connect(
            #     lambda: LOGGER.info(
            #         f"转换器输入目录更新为：{self.mainWindow.convertInput.text()}"
            #     )
            # )
            # self.mainWindow.convertOutput.textChanged.connect(
            #     lambda: LOGGER.info(
            #         f"转换器输出目录更新为：{self.mainWindow.convertOutput.text()}"
            #     )
            # )

            self.mainWindow.jsonBtn.toggled.connect(
                lambda: self.sysConfig.convertConfig.setSourceFormat("JSON")
            )
            self.mainWindow.txtBtn.toggled.connect(
                lambda: self.sysConfig.convertConfig.setSourceFormat("TXT")
            )

            # run
            self.mainWindow.runBtn.clicked.connect(lambda: self.run())

        except Exception as e:
            LOGGER.error(f"事件绑定失败，错误信息：{e}")
            showMessageBox(QMessageBox.Icon.Critical, f"事件绑定失败，错误信息：{e}")

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
            if page_name == "annotatePage":
                self.sysConfig.currentTask = TASK.ANNOTATE

            # 切换到转换页面时，设置当前模式和格式
            elif page_name == "convertPage":
                self.sysConfig.currentTask = TASK.CONVERT
                self.sysConfig.currentMode = MODE(
                    self.mainWindow.taskComBox.currentData()
                )
                if self.mainWindow.jsonBtn.isChecked():
                    self.sysConfig.convertConfig.setSourceFormat("JSON")
                elif self.mainWindow.txtBtn.isChecked():
                    self.sysConfig.convertConfig.setSourceFormat("TXT")
                else:
                    self.mainWindow.jsonBtn.setChecked(True)
                    self.sysConfig.convertConfig.setSourceFormat("JSON")

            elif page_name == "modifyPage":
                self.sysConfig.currentTask = TASK.MODIFY
            elif page_name == "exportPage":
                self.sysConfig.currentTask = TASK.EXPORT

            self.mainWindow.stackedWidget.setCurrentIndex(index)

        else:
            LOGGER.error(f"页面切换失败，未找到页面：{page_name}")
            showMessageBox(
                QMessageBox.Icon.Warning, f"页面切换失败，未找到页面：{page_name}"
            )

    def run(self):
        """
        运行
        """
        try:
            pass
        except Exception as e:
            LOGGER.error(f"运行失败，错误信息：{e}")
            showMessageBox(QMessageBox.Icon.Critical, f"运行失败，错误信息：{e}")

    # region 转换
    def updateConvertInputDir(self):
        """
        更新转换器的标注目录
        """
        dir = chooseDir(self.sysConfig.convertConfig.inputDir)
        self.mainWindow.convertInput.setText(dir)
        self.sysConfig.convertConfig.inputDir = dir

    def updateConvertOutputDir(self):
        """
        更新转换器的输出目录
        """
        dir = chooseDir(self.sysConfig.convertConfig.outputDir)
        self.mainWindow.convertOutput.setText(dir)
        self.sysConfig.convertConfig.outputDir = dir

    def convert(self):
        """
        转换
        """
        try:
            pass

        except Exception as e:
            LOGGER.error(f"转换失败，错误信息：{e}")
            showMessageBox(QMessageBox.Icon.Critical, f"转换失败，错误信息：{e}")


# endregion


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
