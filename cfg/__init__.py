"""
Description：配置
Author: Baibinnan
Date: 2025/8/25
LastEdit: 2025/8/27
E-mail: baibinnan@chuanfeng.com
update：

"""

from enum import Enum

from utils import LOGGER

__APPNAME__ = "VAI_E_SmartAnnotator"
__VERSION__ = "1.0.0"


class MODE(Enum):
    DETECT = 0
    POSE = 1
    SEGMENT = 2
    OCR = 3


class TASK(Enum):
    MODIFY = 0
    ANNOTATE = 1
    CONVERT = 2
    EXPORT = 3


class ConvertConfig:
    def __init__(self):
        self.sourceFormat = None
        self.classes = []
        self.kpt = []
        self.visualize = False
        self.annotationFiles = []
        self.imageFiles = []
        self.export = False
        self.inputDir = ""
        self.outputDir = ""

    def setSourceFormat(self, format):
        self.sourceFormat = format

    def setInputDir(self, dir):
        self.inputDir = dir

    def setOutputDir(self, dir):
        self.outputDir = dir

    def setVisualize(self, visualize: bool):
        self.visualize = visualize

    def setExport(self, export: bool):
        self.export = export


class AnnotateConfig:
    def __init__(self):
        self.classes = []
        self.kpt = []


class ModifyConfig:
    def __init__(self):
        self.classes = []
        self.kpt = []


class exportConfig:
    def __init__(self):
        self.format = "COCO"
        self.split = 0.8
        self.exportImg = True
        self.exportAnno = True


class SysConfig:
    def __init__(self):
        self.currentMode = None
        self.currentTask = None
        self.convertConfig = ConvertConfig()
        self.annotateConfig = AnnotateConfig()
        self.modifyConfig = ModifyConfig()
        self.exportConfig = exportConfig()
