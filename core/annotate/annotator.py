"""
Description：自动标注工具-支持多种模型的目标检测、姿态估计等
Author:BaiBinnan
Date:2025/06/9
LastEdit:2026/2/4
LastEditBy:BaiBinnan
E-mail:baiBinnan@chuanfeng.com
"""

import cv2
import numpy as np
import shutil
from pathlib import Path
from typing import List
from cfg import SysConfig, AnnotateConfig, MODE, LOGGER, LABELME_VERSION
from .vision import DetectionPredictor, PoseDetectionPredictor, SegmentationPredictor
from utils.tool import yolo_to_labelme, generate_labelme_file


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

        def annotation_generator(imgList, batch=1):
            if batch <= 0:
                raise ValueError("批处理大小无效")
            for i in range(0, len(imgList), batch):
                batch_paths = [Path(img) for img in imgList[i : i + batch]]
                yield batch_paths

        if isinstance(self.config, AnnotateConfig):
            annotation_gen = annotation_generator(
                self.config.annotationFiles, self.model.batch
            )
        else:
            LOGGER.error("标注配置错误，无法解析图片")
            return False
        self.output = Path(self.config.outputDir)
        self.output.mkdir(parents=True, exist_ok=True)
        total = len(self.config.annotationFiles)
        for idx, annotation_pathList in enumerate(annotation_gen):
            try:
                if not callback("自动标注中", (idx + 1) * self.model.batch / total):
                    return False
                # 标注
                self._label(annotation_pathList)

            except Exception as e:
                LOGGER.error(f"处理 第{idx}批标注数据时出错: {e}")

    def _label(self, image_pathList: List[Path]):
        """
        用于处理图像列表的标注。

        image : 输入图像。
        """
        imgList = []
        imgInfo = []

        for image_path in image_pathList:
            image_data = np.fromfile(image_path, dtype=np.uint8)
            image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
            img_h, img_w = image.shape[:2]
            imgList.append(image)
            imgInfo.append([image_path, img_h, img_w])

        predections = self.model.predict(imgList)
        if predections:
            for idx, pred in enumerate(predections):
                lines = []
                image_path, img_h, img_w = imgInfo[idx]
                bboxes = pred["bboxs"]
                labels = pred["labels"]
                boundary_points = pred.get("boundary_points")
                kpt_shape = self.model.kpt_shape[0] if self.mode == MODE.POSE else None
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
                annotations = yolo_to_labelme(
                    lines,
                    img_w,
                    img_h,
                    self.model.class_mapping,
                    self.mode.value,
                    kpt_shape,
                )
                # 生成labelme格式文件
                generate_labelme_file(
                    annotations,
                    LABELME_VERSION,
                    image_path.name,
                    img_w,
                    img_h,
                    self.output / f"{image_path.stem}.json",
                )
                if image_path != self.output / image_path.name:
                    shutil.copy(image_path, self.output / image_path.name)
