from cfg import SysConfig, LOGGER, DEVICE
from core.annotate.annotator import Annotator, AnnotateConfig, MODE
from utils.files import getVideoFilesInDir, getImageFilesInDir

sysConfig = SysConfig()
sysConfig.currentMode = MODE.DETECT
sysConfig.annotateConfig = AnnotateConfig()
sysConfig.annotateConfig.device = DEVICE.GPU
# sysConfig.annotateConfig.modelPath = r"D:\VSS\05安装\VAI_10\01 运行环境\Equiment Vision AI System\VAI_Crane\Resources\CPS\CPS_11m_736x1280_BS2_FP32_20260113.engine"
sysConfig.annotateConfig.modelPath = r"D:\VSS\05安装\VAI_10\01 运行环境\Equiment Vision AI System\VAI_Crane\Resources\JSD\NBBY_JSD_IntrusionDetection_11m_736x1280_BS2_FP32_20260626.engine"
sysConfig.annotateConfig.inputDir = "D:\data\JSD\temp"
sysConfig.annotateConfig.outputDir = "D:\data\JSD\temp\output"
sysConfig.annotateConfig.annotationFiles = getImageFilesInDir(
    sysConfig.annotateConfig.inputDir
)
sysConfig.annotateConfig.videoFiles = getVideoFilesInDir(
    sysConfig.annotateConfig.inputDir)


def progress_callback(status: str, progress: float) -> bool:
    print(f"{status}: {progress*100:.2f}%")
    return True


annotator = Annotator(sysConfig)
annotator.run(progress_callback)
