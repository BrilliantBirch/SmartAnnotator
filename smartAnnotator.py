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
from utils import (
    add_text_browser_handler,
    chooseDir,
    showMessageBox,
    checkAnnotationFiles,
    CustomItemWidget,
)

from core import ConvertWorker
from ui import Ui_MainWindow


from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QListWidgetItem
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5 import QtCore, QtWidgets


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
        self.converter = ConvertWorker()

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

    def initConverter(self):
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

    # region SYS
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

            self.mainWindow.jsonBtn.toggled.connect(
                lambda: self.sysConfig.convertConfig.setSourceFormat("JSON")
            )
            self.mainWindow.txtBtn.toggled.connect(
                lambda: self.sysConfig.convertConfig.setSourceFormat("TXT")
            )
            self.mainWindow.taskComBox.currentIndexChanged.connect(
                lambda: self.changeMode()
            )
            self.mainWindow.addLabelBtn.clicked.connect(lambda: self.addLabel())
            self.mainWindow.exportBtn.toggled.connect(
                lambda state: self.sysConfig.convertConfig.setExport(state)
            )
            self.mainWindow.visualizeBtn.toggled.connect(
                lambda state: self.sysConfig.convertConfig.setVisualize(state)
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
            if page_name == "welcomePage":
                self.mainWindow.label_5.hide()
                self.mainWindow.label_6.hide()
                self.mainWindow.taskComBox.hide()
                self.mainWindow.runBtn.hide()
            else:
                self.mainWindow.runBtn.show()
                self.mainWindow.label_5.show()
                self.mainWindow.label_6.show()
                self.mainWindow.taskComBox.show()
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

    def changeMode(self):
        """
        切换模式
        """
        try:
            mode = MODE(self.mainWindow.taskComBox.currentData())
            if mode == MODE.POSE:
                pass
            else:
                pass
            self.sysConfig.currentMode = mode
        except Exception as e:
            LOGGER.error(f"模式切换失败，错误信息：{e}")
            showMessageBox(QMessageBox.Icon.Warning, f"模式切换失败，错误信息：{e}")

    def run(self):
        """
        运行
        """
        try:
            if self.sysConfig.currentTask == TASK.CONVERT:
                self.convert()
            # elif self.sysConfig.currentTask == TASK.ANNOTATE:
            #     self.annotate()
            # elif self.sysConfig.currentTask == TASK.MODIFY:
            #     self.modify()
            # elif self.sysConfig.currentTask == TASK.EXPORT:
            #     self.export()

        except Exception as e:
            LOGGER.error(f"运行失败，错误信息：{e}")
            showMessageBox(QMessageBox.Icon.Critical, f"运行失败，错误信息：{e}")

    # endregion SYS

    # region 转换
    def updateConvertInputDir(self):
        """
        更新转换器的标注目录
        """
        dir = chooseDir(self.sysConfig.convertConfig.inputDir)
        # if dir == self.sysConfig.convertConfig.inputDir:
        #     return
        self.mainWindow.convertInput.setText(dir)
        self.sysConfig.convertConfig.inputDir = dir
        # 获取当前工作目录下的所有标注文件与图像文件
        if self.sysConfig.convertConfig.sourceFormat == "JSON":
            self.getConvertSource_Json(dir)
        elif self.sysConfig.convertConfig.sourceFormat == "TXT":
            showMessageBox(
                QMessageBox.Icon.Warning,
                f"暂未实现源未TXT格式！",
            )

    def getConvertSource_Json(self, dirPath: str):
        """
        获取转换目录下的所有JSON文件
        """
        try:
            anotationFiles, imageFiles, lostAnnoFiles = checkAnnotationFiles(dirPath)
            self.sysConfig.convertConfig.annotationFiles = anotationFiles
            self.sysConfig.convertConfig.imageFiles = imageFiles
            LOGGER.info(
                f"在目录 {dirPath} 下发现 {len(anotationFiles)} 个标注文件，{len(imageFiles)} 个图像文件"
            )
            if len(lostAnnoFiles) > 0:
                showMessageBox(
                    QMessageBox.Icon.Warning,
                    f"在目录 {dirPath} 下发现 {len(lostAnnoFiles)} 个标注文件缺少对应的图像文件，请检查！",
                )
                LOGGER.warning(
                    f"在目录 {dirPath} 下发现 {len(lostAnnoFiles)} 个缺少图片的标注文件:\n"
                    f"{lostAnnoFiles}"
                )
            self.mainWindow.annotationFilesNumLabel.setText(
                f"共{len(anotationFiles)}个标注文件"
            )
            dataModel = QtCore.QStringListModel()
            dataModel.setStringList(anotationFiles)
            self.mainWindow.annotationFilesView.setModel(dataModel)

        except Exception as e:
            LOGGER.error(f"获取转换目录下的标注文件失败，错误信息：{e}")
            showMessageBox(
                QMessageBox.Icon.Critical,
                f"获取转换目录下的所有JSON文件失败，错误信息：{e}",
            )

    def addLabel(self):
        """
        添加标签
        """
        text = f"label{self.mainWindow.labelListView.count() + 1}"
        item_widget = CustomItemWidget(text, self.mainWindow.labelListView)
        item = QListWidgetItem()
        self.mainWindow.labelListView.addItem(item)
        self.mainWindow.labelListView.setItemWidget(item, item_widget)
        item.setSizeHint(item_widget.sizeHint())

    def updateConvertOutputDir(self):
        """
        更新转换器的输出目录
        """
        dir = chooseDir(self.sysConfig.convertConfig.outputDir)
        self.mainWindow.convertOutput.setText(dir)
        self.sysConfig.convertConfig.outputDir = dir

    def checkConvertParams(self):
        """
        检查转换参数
        """
        if self.sysConfig.convertConfig.inputDir == "":
            showMessageBox(QMessageBox.Icon.Warning, "请选择标注目录")
            return False
        if self.sysConfig.convertConfig.outputDir == "":
            reslut = showMessageBox(
                QMessageBox.Icon.Question,
                "输出目录为空，不指定则输出到程序执行目录下output目录，是否继续？",
            )
            if reslut == QMessageBox.Cancel:
                return False
        if not self.sysConfig.convertConfig.classes:
            showMessageBox(QMessageBox.Icon.Warning, "请添加标签")
            return False
        if not self.sysConfig.convertConfig.annotationFiles:
            showMessageBox(QMessageBox.Icon.Warning, "源目录下没有找到标注文件")
            return False
        if not self.sysConfig.convertConfig.imageFiles:
            showMessageBox(QMessageBox.Icon.Warning, "源目录下没有找到图像文件")
            return False
        return True

    def convert(self):
        """
        转换
        """
        try:
            if not self.checkConvertParams():
                return

            if hasattr(self, "converter") and self.converter.isRunning():
                showMessageBox(QMessageBox.Icon.Information, "转换任务已在运行中")
                return

            self.converter.progress_updated.connect(self.setProcessValue)
            self.converter.task_finished.connect(lambda: self.setProcessLabel("未作业"))
            self.converter.start()
            self.setProcessLabel("转换中...")

        except Exception as e:
            LOGGER.error(f"转换失败，错误信息：{e}")
            showMessageBox(QMessageBox.Icon.Critical, f"转换失败，错误信息：{e}")


# endregion 转换


def get_main_app(argv=[]):
    """
    没有方便通过单线程测试应用的方式，所以这里没有使用app.exec_()
    """
    app = QApplication(argv)
    app.setApplicationName(__APPNAME__)
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
