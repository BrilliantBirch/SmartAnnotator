"""
Description：通用的转换器
Author: Baibinnan
Date: 2025/3/14
LastEdit: 2025/3/20
E-mail: baibinnan@chuanfeng.com

"""

from cfg import MODE, SysConfig
from .txtconverter import (
    YoloConverter,
    YoloPoseConverter,
    PPOCRConverter,
    YoloSegConverter,
)

from .jsonconverter import (
    Yolo2JsonConverter,
    YoloPose2JsonConverter,
    YoloSeg2JsonConverter,
)


# region 通用转换器
class Converter:
    def __init__(self, config: SysConfig):

        self.sourceFormat = config.convertConfig.sourceFormat
        self.mode = config.currentMode

        # LabelmeJson to txt
        if self.sourceFormat == "json":
            if self.mode == MODE.POSE:
                self.converter = YoloPoseConverter(config.convertConfig)

            elif self.mode == MODE.DETECT:
                self.converter = YoloConverter(config.convertConfig)

            elif self.mode == MODE.OCR:
                self.converter = PPOCRConverter(config.convertConfig)

            elif self.mode == MODE.SEGMENT:
                self.converter = YoloSegConverter(config.convertConfig)

            else:
                raise ValueError(
                    f"当源类型为{self.sourceFormat}转换类型不支持{self.mode}"
                )
        # txt to labelmeJson
        elif self.sourceFormat == "txt":
            if self.mode == MODE.DETECT:
                self.converter = Yolo2JsonConverter(config.convertConfig)
            elif self.mode == MODE.POSE:
                self.converter = YoloPose2JsonConverter(config.convertConfig)
            elif self.mode == MODE.SEGMENT:
                self.converter = YoloSeg2JsonConverter(config.convertConfig)
            else:
                raise ValueError(
                    f"当源类型为{self.sourceFormat}转换类型不支持{self.mode}"
                )

    def run(self, run_callback):
        return self.converter.run(run_callback)


# endregion
