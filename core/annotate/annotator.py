"""
Description：自动标注工具-支持多种模型的目标检测、姿态估计等
Author:BaiBinnan
Date:2025/06/9
LastEdit:2025/6/11
LastEditBy:BaiBinnan
E-mail:baiBinnan@chuanfeng.com
"""

import cv2
import numpy as np
import shutil
from pathlib import Path
from cfg import SysConfig, AnnotateConfig, MODE, LOGGER
from ..convert import Yolo2JsonConverter, YoloPose2JsonConverter
from .vision import DetectionPredictor, PoseDetectionPredictor


class Annotator:
    def __init__(self, config: SysConfig):
        """
        初始化自动标注工具


        """
        self.mode = config.currentMode
        self.config = config.annotateConfig

        if self.mode == MODE.DETECT:
            self.model = DetectionPredictor(self.config)
            self.converter = Yolo2JsonConverter(self.config)
        elif self.mode == MODE.POSE:
            self.model = PoseDetectionPredictor(self.config)
            self.converter = YoloPose2JsonConverter(self.config)
        else:
            raise ValueError(f"任务类型:{self.mode.name}暂不支持")

        # 模型预热
        self.model.warm_up()

    def run(self, callback):
        """
        运行自动标注工具
        """

        def image_generator(imgList):
            for image in imgList:
                yield Path(image)

        if isinstance(self.config, AnnotateConfig):
            image_gen = image_generator(self.config.imgFiles)
        else:
            LOGGER.error("标注配置错误，无法解析图片")
            return False
        self.output = Path(self.config.outputDir)
        self.output.mkdir(parents=True, exist_ok=True)
        total = len(self.config.imgFiles)
        for idx, image_path in enumerate(image_gen):
            try:
                if not callback("自动标注中", (idx + 1) / total):
                    return False
                lines = self._label(image_path)
                annotations, h, w = self.converter.process(lines, image_path)
            except Exception as e:
                print(f"处理 {image_path} 时出错: {e}")

    def _label(self, image_path: Path):
        """
        用于处理单个图像的标注。

        image : 输入图像。
        """
        filename = image_path.name
        image_data = np.fromfile(image_path, dtype=np.uint8)
        image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        predections = self.model.predict([image])
        lines = []
        if predections:
            for pred in predections:
                bboxes = pred["bboxs"]
                labels = pred["labels"]
                scores = pred["scores"]
                if self.mode == MODE.POSE:
                    kpt = pred["keypoints"]
                    for det in zip(bboxes, labels, kpt):
                        bbox, label, kpt = det
                        x, y, w, h = bbox
                        cls = label
                        kpt_str = " ".join(
                            [
                                (
                                    f"{k[0]} {k[1]} 2"
                                    if k[2] > self.config.kptConf
                                    else "0 0 0"
                                )
                                for k in kpt
                            ]
                        )
                        lines.append(f"{cls} {x} {y} {w} {h} {kpt_str}\n")
                elif self.mode == MODE.DETECT:
                    for det in zip(bboxes, labels):
                        bbox, label = det
                        x, y, w, h = bbox
                        cls = label
                        lines.append(f"{cls} {x} {y} {w} {h}\n")
        return lines
