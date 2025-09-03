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

from cfg import __APPNAME__, __VERSION__, LOGGER, ROOT, MODE, SysConfig, TASK
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

import os
from datetime import datetime


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
        # convert
        self.mainWindow.convertCancelBtn.hide()
        self.converter = ConvertWorker()
        self.converter.progress_updated.connect(lambda x: self.setProcessValue(x))
        self.converter.task_finished.connect(lambda: self.handleConvertFinished())
        self.converter.error_occurred.connect(
            lambda msg: self.handleConverterError(msg)
        )
        self.converter.convert_progress_desc.connect(lambda x: self.setProcessLabel(x))

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
        self.showkptConfig(False)

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
            self.mainWindow.taskComBox.currentIndexChanged.connect(
                lambda: self.changeMode()
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

            self.mainWindow.addLabelBtn.clicked.connect(lambda: self.addLabel())
            self.mainWindow.clearLabelBtn.clicked.connect(lambda: self.clearLabel())
            self.mainWindow.addKptBtn.clicked.connect(lambda: self.addKpt())
            self.mainWindow.clearKptBtn.clicked.connect(lambda: self.clearkpt())
            self.mainWindow.exportBtn.toggled.connect(
                lambda state: self.sysConfig.convertConfig.setExport(state)
            )
            self.mainWindow.visualizeBtn.toggled.connect(
                lambda state: self.sysConfig.convertConfig.setVisualize(state)
            )
            self.mainWindow.convertRunBtn.clicked.connect(lambda: self.convert())
            self.mainWindow.convertCancelBtn.clicked.connect(
                lambda: self.handleConvertCancel()
            )
            # annotate

            # modify

            # export

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
        self.mainWindow.convertStatusLabel.setText(text)

    def setProcessValue(self, value):
        """
        设置进度条的值
        """
        if 0.0 <= value <= 100.0:
            self.mainWindow.convertProgressBar.setValue(
                int(100 * value)
            )  # 进度条用整数近似
            # self.mainWindow.progressBar.text = f"{value:.2f}%"  # 标签显示精确浮点数

    def changePage(self, page_name):
        """
        切换页面
        """
        if page_name in self.name_index_map:
            index = self.name_index_map[page_name]
            if page_name == "welcomePage":
                self.mainWindow.taskComBox.hide()
            else:
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
                self.showkptConfig(True)
            else:
                self.showkptConfig(False)

            self.sysConfig.currentMode = mode
        except Exception as e:
            LOGGER.error(f"模式切换失败，错误信息：{e}")
            showMessageBox(QMessageBox.Icon.Warning, f"模式切换失败，错误信息：{e}")

    # endregion SYS

    # region 转换
    def showkptConfig(self, show):
        """
        显示关键点配置
        """
        if show:
            self.mainWindow.addKptBtn.show()
            self.mainWindow.clearKptBtn.show()
            self.mainWindow.kptListView.show()
            self.mainWindow.label_9.show()
            self.mainWindow.kptLabel.show()
        else:
            self.mainWindow.kptListView.hide()
            self.mainWindow.addKptBtn.hide()
            self.mainWindow.clearKptBtn.hide()
            self.mainWindow.label_9.hide()
            self.mainWindow.kptLabel.hide()

    def handleConvertCancel(self):
        """
        取消转换
        """
        self.converter.stop()

    def handleConverterError(self, error_msg):
        """
        处理转换线程中的错误
        """
        showMessageBox(QMessageBox.Icon.Critical, f"转换错误：{error_msg}")
        self.setProcessLabel("转换错误")

    def handleConvertFinished(self):
        """
        转换完成
        """
        self.mainWindow.convertCancelBtn.hide()
        self.mainWindow.convertRunBtn.setText("开始")
        self.enabelConvertBtn(True)

    def handleConvertPause(self):
        """
        转换暂停
        """
        self.setProcessLabel("已暂停")
        self.mainWindow.convertRunBtn.setText("继续")
        self.converter.pause()

    def handleConvertContinue(self):
        """
        转换继续
        """
        self.mainWindow.convertRunBtn.setText("暂停")
        self.converter.resume()

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

    def clearLabel(self):
        """
        清空标签
        """
        self.mainWindow.labelListView.clear()

    def addKpt(self):
        """
        添加关键点
        """
        text = f"kpt_point{self.mainWindow.kptListView.count() + 1}"
        item_widget = CustomItemWidget(text, self.mainWindow.kptListView, check=True)
        item = QListWidgetItem()
        self.mainWindow.kptListView.addItem(item)
        self.mainWindow.kptListView.setItemWidget(item, item_widget)
        item.setSizeHint(item_widget.sizeHint())

    def clearkpt(self):
        """清空关键点"""
        self.mainWindow.kptListView.clear()

    def updateConvertOutputDir(self):
        """
        更新转换器的输出目录
        """
        dir = chooseDir(self.sysConfig.convertConfig.outputDir)
        self.mainWindow.convertOutput.setText(dir)
        self.sysConfig.convertConfig.outputDir = dir

    def getconvertLabels(self):
        """
        获取转换器的标签
        """
        items_text = []
        for i in range(self.mainWindow.labelListView.count()):
            item = self.mainWindow.labelListView.item(i)
            widget = self.mainWindow.labelListView.itemWidget(item)
            if isinstance(widget, CustomItemWidget):
                items_text.append(widget.get_text().lower())
        return items_text

    def getconvertKpt(self):
        """
        获取关键点
        """
        items = {}
        for i in range(self.mainWindow.kptListView.count()):
            item = self.mainWindow.kptListView.item(i)
            widget = self.mainWindow.kptListView.itemWidget(item)
            if isinstance(widget, CustomItemWidget):
                kpt = widget.get_text().lower()
                isChecked = widget.get_check_status()
                bbox_size = widget.get_check_size()
                if kpt not in items:
                    items[kpt] = {
                        "isChecked": isChecked,
                        "bbox_size": bbox_size,
                    }
                else:
                    LOGGER.warning(f"{kpt}重复，请检查")
                    showMessageBox(QMessageBox.Icon.Warning, f"{kpt}重复，请检查")
        return items

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
            else:
                self.sysConfig.convertConfig.outputDir = os.path.join(
                    ROOT,
                    "output",
                    self.sysConfig.currentMode.name,
                    datetime.now().strftime("%Y%m%d%H%M%S"),
                )
                self.mainWindow.convertOutput.setText(
                    self.sysConfig.convertConfig.outputDir
                )

        self.sysConfig.convertConfig.classes = self.getconvertLabels()

        if not self.sysConfig.convertConfig.classes:
            showMessageBox(QMessageBox.Icon.Warning, "请添加标签")
            return False
        if self.sysConfig.currentMode == MODE.POSE:
            self.sysConfig.convertConfig.kpt = self.getconvertKpt()
            if not self.sysConfig.convertConfig.kpt:
                showMessageBox(QMessageBox.Icon.Warning, "请添加关键点")
                return False
        if not self.sysConfig.convertConfig.annotationFiles:
            showMessageBox(QMessageBox.Icon.Warning, "源目录下没有找到标注文件")
            return False
        if not self.sysConfig.convertConfig.imageFiles:
            showMessageBox(QMessageBox.Icon.Warning, "源目录下没有找到图像文件")
            return False
        return True

    def enabelConvertBtn(self, enable=True):
        """
        失能转换相关配置按钮
        """
        self.mainWindow.convertInputBtn.setEnabled(enable)
        self.mainWindow.convertOutputBtn.setEnabled(enable)
        self.mainWindow.clearLabelBtn.setEnabled(enable)
        self.mainWindow.addLabelBtn.setEnabled(enable)

    def convert(self):
        """
        转换
        """
        try:
            if not self.checkConvertParams():
                return

            if hasattr(self, "converter") and self.converter.isRunning():
                if self.mainWindow.convertRunBtn.text() == "暂停":
                    self.handleConvertPause()
                    return
                elif self.mainWindow.convertRunBtn.text() == "继续":
                    self.handleConvertContinue()
                    return

            self.mainWindow.convertCancelBtn.show()
            self.mainWindow.convertRunBtn.setText("暂停")
            self.enabelConvertBtn(False)

            LOGGER.info(
                f"开始转换，任务类型：{self.sysConfig.currentMode.name},输出路径：{self.sysConfig.convertConfig.outputDir},标签：{self.sysConfig.convertConfig.classes}"
            )
            self.converter.setConfig(self.sysConfig)
            self.converter.run()
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
