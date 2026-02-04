from cfg import SysConfig, LOGGER
from core.annotate.annotator import Annotator, AnnotateConfig, MODE
from utils.files import getImageFilesInDir

sysConfig = SysConfig()
sysConfig.currentMode = MODE.POSE
sysConfig.annotateConfig = AnnotateConfig()
# sysConfig.annotateConfig.modelPath = r"D:\VSS\05安装\VAI_10\01 运行环境\Equiment Vision AI System\VAI_Crane\Resources\CPS\CPS_11m_736x1280_BS2_FP32_20260113.engine"
sysConfig.annotateConfig.modelPath = (
    r"C:\Users\99056\Desktop\Work\CPS_11m_736x1280_BS1_FP32_20260130.engine"
)
sysConfig.annotateConfig.inputDir = "D:\data\cps\qc106test_method2"
sysConfig.annotateConfig.outputDir = "D:\data\cps\qc106test_method2"
sysConfig.annotateConfig.imgFiles = getImageFilesInDir(
    sysConfig.annotateConfig.inputDir
)


def progress_callback(status: str, progress: float) -> bool:
    print(f"{status}: {progress*100:.2f}%")
    return True


annotator = Annotator(sysConfig)
annotator.run(progress_callback)
