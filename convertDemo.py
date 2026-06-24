from cfg import SysConfig, LOGGER, ConvertConfig
from core.convert.converter import YoloConverter, MODE
from utils.files import checkAnnotationFiles

sysConfig = SysConfig()
sysConfig.currentMode = MODE.DETECT
sysConfig.convertConfig = ConvertConfig()
sysConfig.convertConfig.setSourceFormat("json")
sysConfig.convertConfig.inputDir = r"D:\data\JTSD\20260327_20260328"
sysConfig.convertConfig.outputDir = r"D:\data\JTSD\output"
