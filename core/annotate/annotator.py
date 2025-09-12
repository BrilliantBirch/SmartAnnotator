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
from cfg import SysConfig, AnnotateConfig, MODE, LOGGER, LABELME_VERSION
from .vision import DetectionPredictor, PoseDetectionPredictor, SegmentationPredictor


class Annotator:
    def __init__(self, config: SysConfig):
        """
        初始化自动标注工具


        """
        self.mode = config.currentMode
        self.config = config.annotateConfig

        if self.mode == MODE.DETECT:
            self.model = DetectionPredictor(self.config)
        elif self.mode == MODE.POSE:
            self.model = PoseDetectionPredictor(self.config)
        elif self.mode == MODE.SEGMENT:
            self.model = SegmentationPredictor(self.config)
        else:

            LOGGER.warning(f"任务类型:{self.mode.name}暂不支持")
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
                # 标注
                lines, h, w = self._label(image_path)
                from utils.tool import yolo_to_labelme, generate_labelme_file

                if self.mode == MODE.POSE:
                    kpt_shape = self.model.kpt_shape[0]
                else:
                    kpt_shape = None
                # 转换为labelme格式
                annotations = yolo_to_labelme(
                    lines,
                    w,
                    h,
                    self.model.class_mapping,
                    self.mode.value,
                    kpt_shape,
                )
                # 生成labelme格式文件
                generate_labelme_file(
                    annotations,
                    LABELME_VERSION,
                    image_path.name,
                    h,
                    w,
                    self.output / f"{image_path.stem}.json",
                )
                if image_path != self.output / image_path.name:
                    shutil.copy(image_path, self.output / image_path.name)
            except Exception as e:
                LOGGER.error(f"处理 {image_path} 时出错: {e}")

    def _label(self, image_path: Path):
        """
        用于处理单个图像的标注。

        image : 输入图像。
        """
        image_data = np.fromfile(image_path, dtype=np.uint8)
        image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        img_h, img_w = image.shape[:2]
        predections = self.model.predict([image])
        lines = []
        if predections:
            for pred in predections:
                bboxes = pred["bboxs"]
                labels = pred["labels"]
                boundary_points = pred["boundary_points"]
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
                elif self.mode == MODE.SEGMENT:
                    for classid, points in zip(labels, boundary_points):
                        line = f"{classid} {' '.join(map(str, points))}"
                        lines.append(line)
        return lines, img_h, img_w
