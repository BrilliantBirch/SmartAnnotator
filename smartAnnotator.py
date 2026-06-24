"""
Description：自动标注工具的主程序
Author: Baibinnan
Date: 2025/8/25
LastEdit: 2026/06/24
LastEditBy: Baibinnan
E-mail: baibinnan@chuanfeng.com
update：
    1. 2026/06/24: 加载现代化QSS样式表，优化UI视觉效果

"""

import argparse
import sys

from cfg import __APPNAME__, __VERSION__, LOGGER, ROOT, DEVICE, MODE, SysConfig
from utils import (
    add_text_browser_handler,
    chooseDir,
    chooseFile,
    showMessageBox,
    checkAnnotationFiles,
    getImageFilesInDir,
    resource_path,
    CustomItemWidget,
)

from core import ConvertWorker, AnnotateWorker
from ui import Ui_MainWindow


from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QListWidgetItem
from PyQt5.QtGui import QIcon, QPixmap, QRegExpValidator
from PyQt5.QtCore import Qt, QRegExp
from PyQt5 import QtCore

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
        # 当前模式
        self.sysConfig = SysConfig()
        self.sysConfig.currentMode = MODE(self.mainWindow.taskComBox.currentData())
        # convert 初始化
        self.mainWindow.convertCancelBtn.hide()
        self.initConverter()
        # 初始化转换源
        if self.mainWindow.jsonBtn.isChecked():
            self.sysConfig.convertConfig.setSourceFormat("json")
        elif self.mainWindow.txtBtn.isChecked():
            self.sysConfig.convertConfig.setSourceFormat("txt")
        else:
            self.mainWindow.jsonBtn.setChecked(True)
            self.sysConfig.convertConfig.setSourceFormat("json")
        # 初始化标注
        self.mainWindow.annotateCancelBtn.hide()
        self.initAnnotator()
        if self.mainWindow.gpuBtn.isChecked():
            self.sysConfig.annotateConfig.device = DEVICE.GPU
        elif self.mainWindow.cpuBtn.isChecked():
            self.sysConfig.annotateConfig.device = DEVICE.CPU
        else:
            self.mainWindow.gpuBtn.setChecked(True)
            self.sysConfig.annotateConfig.device = DEVICE.GPU

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
        # 加载现代化样式表
        self._load_stylesheet()

        # 加载并设置图片以及logo
        pixmap = QPixmap(resource_path(r"resources/images/welcome.png"))
        if pixmap.isNull():
            LOGGER.warning(
                f"加载资源图片失败: {resource_path('resources/images/welcome.png')}"
            )
        else:
            scaled_pixmap = pixmap.scaled(
                self.mainWindow.welcomeImageLabel.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.mainWindow.welcomeImageLabel.setPixmap(scaled_pixmap)

        app_icon = QIcon(resource_path("resources/images/welcome.ico"))
        if app_icon.isNull():
            LOGGER.warning(
                f"加载资源图片失败: {resource_path('resources/images/welcome.ico')}"
            )
        else:
            self.setWindowIcon(app_icon)
        # 加载模式类型
        for mode in MODE:
            self.mainWindow.taskComBox.addItem(mode.name, mode.value)
        # 默认为Detect
        self.mainWindow.taskComBox.setCurrentIndex(0)
        # 隐藏关键点配置
        self.showkptConfig(False)
        # 参数验证器
        regex = QRegExp(r"^0(\.\d{1,2})?$|^1(\.0{1,2})?$")
        validator = QRegExpValidator(regex)
        self.mainWindow.trainRatio.setValidator(validator)
        self.mainWindow.valRatio.setValidator(validator)
        self.mainWindow.testRatio.setValidator(validator)
        self.mainWindow.bboxConfEdit.setValidator(validator)
        self.mainWindow.keyConfEdit.setValidator(validator)
        self.mainWindow.nmsEdit.setValidator(validator)
        self.name_index_map = self._build_name_index_map()

        # 切换到欢迎页
        self.changePage("welcomePage")

    def _load_stylesheet(self):
        """
        加载QSS样式表，实现现代化UI外观
        """
        qss_path = resource_path(r"resources/styles/app.qss")
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
            LOGGER.info("样式表加载成功")
        except FileNotFoundError:
            LOGGER.warning(f"样式表文件未找到: {qss_path}，使用默认样式")
        except Exception as e:
            LOGGER.error(f"样式表加载失败: {e}")

    def initConverter(self):
        """
        初始化转换线程
        """
        self.converter = ConvertWorker()
        self.converter.progress_updated.connect(
            lambda x: self.setConvertProcessValue(x)
        )
        self.converter.task_finished.connect(lambda: self.handleConvertFinished())
        self.converter.error_occurred.connect(
            lambda msg: self.handleConverterError(msg)
        )
        self.converter.progress_desc.connect(lambda x: self.setConvertProcessLabel(x))

    def initAnnotator(self):
        """
        初始化标注线程
        """
        self.annotator = AnnotateWorker()
        self.annotator.progress_updated.connect(
            lambda x: self.setAnnotateProcessValue(x)
        )
        self.annotator.task_finished.connect(lambda: self.handleAnnotateFinished())
        self.annotator.error_occurred.connect(lambda: self.handleAnnotateError())
        self.annotator.progress_desc.connect(lambda x: self.setAnnotateProcessLabel(x))

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
                lambda checked: self.setConvertSourceFormat("json") if checked else None
            )
            self.mainWindow.txtBtn.toggled.connect(
                lambda checked: self.setConvertSourceFormat("txt") if checked else None
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
            self.mainWindow.gpuBtn.toggled.connect(
                lambda: self.sysConfig.annotateConfig.setDevice(DEVICE.GPU)
            )
            self.mainWindow.cpuBtn.toggled.connect(
                lambda: self.sysConfig.annotateConfig.setDevice(DEVICE.CPU)
            )
            self.mainWindow.modelInputBtn.clicked.connect(lambda: self.updateModel())
            self.mainWindow.annotateImgInputBtn.clicked.connect(
                lambda: self.updateAnnotateImg()
            )
            self.mainWindow.annotateOutputBtn.clicked.connect(
                lambda: self.updateAnnotateOutputDir()
            )
            self.mainWindow.annotateBtn.clicked.connect(lambda: self.annotate())
            self.mainWindow.annotateCancelBtn.clicked.connect(
                lambda: self.handleAnnotateCancel()
            )
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

    def setConvertProcessLabel(self, text):
        """
        设置进度条的标签
        """
        self.mainWindow.convertStatusLabel.setText(text)

    def setConvertProcessValue(self, value):
        """
        设置进度条的值
        """
        if 0.0 <= value <= 100.0:
            self.mainWindow.convertProgressBar.setValue(
                int(100 * value)
            )  # 进度条用整数近似

    def changePage(self, page_name):
        """
        切换页面
        """
        page_title_map = {
            "welcomePage": "欢迎页",
            "convertPage": "格式转换",
            "annotatePage": "自动标注",
            "modifyPage": "标注修改",
            "exportPage": "数据集导出",
        }
        if page_name in self.name_index_map:
            index = self.name_index_map[page_name]
            if page_name == "welcomePage":
                self.mainWindow.taskComBox.hide()
                self.mainWindow.label_5.hide()
            else:
                self.mainWindow.taskComBox.show()
                self.mainWindow.label_5.show()

            self.mainWindow.stackedWidget.setCurrentIndex(index)
            # 更新页面标题
            self.mainWindow.pageTitleLabel.setText(page_title_map.get(page_name, page_name))

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
            self.mainWindow.label_30.show()
            self.mainWindow.keyConfEdit.show()
        else:
            self.mainWindow.kptListView.hide()
            self.mainWindow.addKptBtn.hide()
            self.mainWindow.clearKptBtn.hide()
            self.mainWindow.label_9.hide()
            self.mainWindow.kptLabel.hide()
            self.mainWindow.label_30.hide()
            self.mainWindow.keyConfEdit.hide()

    # endregion SYS

    # region 转换

    def setConvertSourceFormat(self, format: str):
        """
        设置转换源格式
        """
        self.sysConfig.convertConfig.sourceFormat = format
        if format == "json":
            self.mainWindow.valRatio.setEnabled(True)
            self.mainWindow.testRatio.setEnabled(True)
            self.mainWindow.trainRatio.setEnabled(True)
            self.mainWindow.exportBtn.setEnabled(True)
            self.mainWindow.visualizeBtn.setEnabled(True)
        elif format == "txt":
            self.mainWindow.valRatio.setEnabled(False)
            self.mainWindow.testRatio.setEnabled(False)
            self.mainWindow.trainRatio.setEnabled(False)
            self.mainWindow.exportBtn.setEnabled(False)
            self.mainWindow.visualizeBtn.setEnabled(False)
        self.getConvertSource(self.sysConfig.convertConfig.inputDir, format)

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
        self.setConvertProcessLabel("转换错误")

    def handleConvertFinished(self):
        """
        转换完成
        """
        self.mainWindow.convertCancelBtn.hide()
        self.mainWindow.convertRunBtn.setText("开始")
        self.enabelConvertBtn(True)
        self.setConvertProcessLabel("转换完成")

    def handleConvertPause(self):
        """
        转换暂停
        """
        self.setConvertProcessLabel("已暂停")
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
        if self.sysConfig.convertConfig.sourceFormat == "json":
            self.getConvertSource(dir, "json")
        elif self.sysConfig.convertConfig.sourceFormat == "txt":
            self.getConvertSource(dir, "txt")

    def getConvertSource(self, dirPath: str, type: str):
        """
        获取转换目录下的所有JSON文件
        """
        try:
            anotationFiles, imageFiles, lostAnnoFiles = checkAnnotationFiles(
                dirPath, type
            )
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
                f"获取转换目录下的所有{type}文件失败，错误信息：{e}",
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
            result = showMessageBox(
                QMessageBox.Icon.Question,
                "输出目录为空，不指定则输出到程序执行目录下output目录，是否继续？",
            )
            if result == QMessageBox.Cancel:
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
        if self.sysConfig.convertConfig.export:
            trainRatio = float(self.mainWindow.trainRatio.text())
            valRatio = float(self.mainWindow.valRatio.text())
            testRatio = float(self.mainWindow.testRatio.text())
            if trainRatio + valRatio + testRatio != 1.0:
                showMessageBox(
                    QMessageBox.Icon.Warning, "训练比例、验证比例、测试比例之和必须为1"
                )
                return False
            else:
                self.sysConfig.convertConfig.trainRatio = trainRatio
                self.sysConfig.convertConfig.valRatio = valRatio
                self.sysConfig.convertConfig.testRatio = testRatio

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
            self.converter.start()
            self.setConvertProcessLabel("转换中...")

        except Exception as e:
            LOGGER.error(f"转换失败，错误信息：{e}")
            showMessageBox(QMessageBox.Icon.Critical, f"转换失败，错误信息：{e}")

    # endregion 转换

    # region 标注
    def updateModel(self):
        """
        更新模型
        """
        suffix = "模型文件 (*.engine *.onnx)"
        self.sysConfig.annotateConfig.modelPath = chooseFile(
            suffix, self.sysConfig.annotateConfig.modelPath
        )
        self.mainWindow.modelInput.setText(self.sysConfig.annotateConfig.modelPath)

    def updateAnnotateImg(self):
        """
        更新标注输入图片
        """
        self.sysConfig.annotateConfig.inputDir = chooseDir(
            self.sysConfig.annotateConfig.inputDir
        )
        self.mainWindow.annotateImgInput.setText(self.sysConfig.annotateConfig.inputDir)
        # 获取目录下所有图片文件 并更新预览到前端
        imgFiles = getImageFilesInDir(self.sysConfig.annotateConfig.inputDir)
        dataModel = QtCore.QStringListModel()
        dataModel.setStringList(imgFiles)
        self.mainWindow.annoateImgListView.setModel(dataModel)
        self.sysConfig.annotateConfig.annotationFiles = imgFiles
        self.mainWindow.annotationImgNumLabel.setText(f"共有{len(imgFiles)}张图片")
        LOGGER.info(f"共有{len(imgFiles)}张图片")

    def updateAnnotateOutputDir(self):
        """
        更新标注输出目录
        """

        self.sysConfig.annotateConfig.outputDir = chooseDir(
            self.sysConfig.annotateConfig.outputDir
        )
        self.mainWindow.annotateOutput.setText(self.sysConfig.annotateConfig.outputDir)

    def setAnnotateProcessLabel(self, text):
        """
        设置进度条的标签
        """
        self.mainWindow.annotateStatusLabel.setText(text)

    def setAnnotateProcessValue(self, value):
        """
        设置进度条的值
        """
        if 0.0 <= value <= 100.0:
            self.mainWindow.annotateProgressBar.setValue(
                int(100 * value)
            )  # 进度条用整数近似

    def checkAnnotateParams(self):
        """
        检查标注参数
        """
        if not self.sysConfig.annotateConfig.modelPath:
            showMessageBox(QMessageBox.Icon.Warning, "请选择模型文件")
            return False
        if not self.sysConfig.annotateConfig.inputDir:
            showMessageBox(QMessageBox.Icon.Warning, "请选择标注输入目录")
            return False
        if not self.sysConfig.annotateConfig.annotationFiles:
            showMessageBox(QMessageBox.Icon.Warning, "源目录没有图像文件")
            return False
        if not self.sysConfig.annotateConfig.outputDir:
            result = showMessageBox(
                QMessageBox.Icon.Question, "输出目录为空，将在图像目录生成标注文件"
            )
            if result == QMessageBox.Cancel:
                return False
            else:
                self.sysConfig.annotateConfig.outputDir = (
                    self.sysConfig.annotateConfig.inputDir
                )
                self.mainWindow.annotateOutput.setText(
                    self.sysConfig.annotateConfig.outputDir
                )
        if not self.mainWindow.bboxConfEdit.text():
            showMessageBox(QMessageBox.Icon.Warning, "请输入置信度阈值")
            return False
        else:
            self.sysConfig.annotateConfig.bboxConf = float(
                self.mainWindow.bboxConfEdit.text()
            )
        if not self.mainWindow.nmsEdit.text():
            showMessageBox(QMessageBox.Icon.Warning, "请输入NMS阈值")
            return False
        else:
            self.sysConfig.annotateConfig.nms = float(self.mainWindow.nmsEdit.text())
        if (
            self.sysConfig.currentMode == MODE.POSE
            and not self.mainWindow.keyConfEdit.text()
        ):
            showMessageBox(QMessageBox.Icon.Warning, "请输入关键点置信度阈值")
            return False
        else:
            self.sysConfig.annotateConfig.kptConf = float(
                self.mainWindow.keyConfEdit.text()
            )

        return True

    def handleAnnotateCancel(self):
        """
        标注取消
        """
        self.annotator.stop()

    def handleAnnotateContinue(self):
        """
        标注继续
        """
        self.annotator.resume()
        self.mainWindow.annotateBtn.setText("暂停")

    def handleAnnotatePause(self):
        """
        标注暂停
        """
        self.setAnnotateProcessLabel("标注暂停")
        self.annotator.pause()
        self.mainWindow.annotateBtn.setText("继续")

    def handleAnnotateError(self):
        """
        标注错误
        """
        self.setAnnotateProcessLabel("标注错误")
        showMessageBox(QMessageBox.Icon.Critical, "标注错误")

    def handleAnnotateFinished(self):
        """
        标注完成
        """
        self.setAnnotateProcessLabel("标注完成")
        self.mainWindow.annotateBtn.setText("开始")
        self.mainWindow.annotateCancelBtn.hide()

    def annotate(self):
        """
        标注
        """
        try:
            if not self.checkAnnotateParams():
                return

            if hasattr(self, "annotator") and self.annotator.isRunning():
                if self.mainWindow.annotateBtn.text() == "暂停":
                    self.handleAnnotatePause()
                    return
                elif self.mainWindow.annotateBtn.text() == "继续":
                    self.handleAnnotateContinue()
                    return
            self.annotator.setConfig(self.sysConfig)
            self.annotator.start()
            self.mainWindow.annotateBtn.setText("暂停")
            self.mainWindow.annotateCancelBtn.show()
            self.setAnnotateProcessLabel("标注中...")
        except Exception as e:
            LOGGER.error(f"标注失败，错误信息：{e}")
            showMessageBox(QMessageBox.Icon.Critical, f"标注失败，错误信息：{e}")


# endregion 标注


# region 程序入口
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


# endregion 程序入口