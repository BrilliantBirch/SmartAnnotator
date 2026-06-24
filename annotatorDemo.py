from cfg import SysConfig, LOGGER, DEVICE
from core.annotate.annotator import Annotator, AnnotateConfig, MODE
from utils.files import getVideoFilesInDir, getImageFilesInDir

sysConfig = SysConfig()
sysConfig.currentMode = MODE.DETECT
sysConfig.annotateConfig = AnnotateConfig()
sysConfig.annotateConfig.device = DEVICE.GPU
# sysConfig.annotateConfig.modelPath = r"D:\VSS\05安装\VAI_10\01 运行环境\Equiment Vision AI System\VAI_Crane\Resources\CPS\CPS_11m_736x1280_BS2_FP32_20260113.engine"
sysConfig.annotateConfig.modelPath = r"C:\Users\99056\Desktop\LianYunGang_person_yolov8s_640x640_bs1_fp32_Datasets0530.onnx"
sysConfig.annotateConfig.inputDir = "D:\data\JSD\SpreaderDetect"
sysConfig.annotateConfig.outputDir = "D:\data\JSD\SpreaderDetect"
sysConfig.annotateConfig.annotationFiles = getImageFilesInDir(
    sysConfig.annotateConfig.inputDir
)


def progress_callback(status: str, progress: float) -> bool:
    print(f"{status}: {progress*100:.2f}%")
    return True


annotator = Annotator(sysConfig)
annotator.run(progress_callback)
