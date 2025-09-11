"""
Description：txt文件转到labelme json格式的标签 ,用于自动标注工具结果转换为Labelme格式便于人工复核
Author: Baibinnan
Date: 2025/3/19
LastEdit: 2025/3/19
E-mail: baibinnan@chuanfeng.com

"""

from cfg import LOGGER, LABELME_VERSION, ConvertConfig, MODE
from pathlib import Path
import shutil
import os
import cv2
import numpy as np


# region YOLO系列转换Labelme json
class JsonBaseConverter:
    def __init__(self, config: ConvertConfig):
        self.config = config
        self.imageFiles = [Path(imageFile) for imageFile in config.imageFiles]
        self.annotationFiles = [
            Path(annotationFile) for annotationFile in config.annotationFiles
        ]
        self.output = Path(self.config.outputDir)
        kpt_type = []
        for k in config.kpt:
            kpt_type.append(k)
        self.kpt = kpt_type
        self.classes = config.classes
        # 对类别去重
        seen = set()
        unique_classes = []
        for value in self.classes:
            lower_val = value.lower()
            if lower_val not in seen:
                seen.add(lower_val)
                unique_classes.append(lower_val)
            else:
                LOGGER.warning(f"类别{value}重复，已去重")
        self.class_mapping = {i: v for i, v in enumerate(unique_classes)}

    def process(self, path, imagePath):
        pass

    def run(self, callback):
        try:
            self.output.mkdir(parents=True, exist_ok=True)
            total = len(self.annotationFiles)
            empty_files = []
            # 获取图片路径及其后缀字典
            imageFiles_dir = {
                str(Path(imageFile).stem): Path(imageFile).suffix
                for imageFile in self.imageFiles
            }
            # 遍历图片转换标签
            for idx, file in enumerate(self.annotationFiles):
                if not callback(f"标签转换中", (idx + 1) / total):
                    return False
                imagePath = file.parent.parent / "images" / file.name
                imagePath = imagePath.with_suffix(
                    imageFiles_dir.get(imagePath.stem, "")
                )
                if imagePath in self.imageFiles:
                    self.imageFiles.remove(imagePath)
                    annotations, image_height, image_width = self.process(
                        file, imagePath
                    )
                    if not annotations:
                        empty_files.append(imagePath)
                        continue
                    from utils import generate_labelme_file

                    generate_labelme_file(
                        annotations,
                        LABELME_VERSION,
                        imagePath.name,
                        image_height,
                        image_width,
                        self.output / (file.stem + ".json"),
                    )
                    shutil.copy(imagePath, self.output / imagePath.name)
                else:
                    LOGGER.warning(f"当前标签{file.name}无图片")
            if self.imageFiles or empty_files:
                background_total = len(self.imageFiles) + len(empty_files)
                LOGGER.info(
                    f"开始处理背景图片，共{background_total}张，复制到{self.output / 'background'}"
                )
                backgroundFolder_img = self.output / "background" / "images"
                backgroundFolder_img.mkdir(parents=True, exist_ok=True)
                background_imgFiles = self.imageFiles + empty_files
                for id, imageFile in enumerate(background_imgFiles):
                    if not callback("背景图片转换中", (id + 1) / background_total):
                        return False
                    shutil.copy(imageFile, backgroundFolder_img / imageFile.name)
            return True
        except Exception as ex:
            LOGGER.error(f"标签转换失败：{str(ex)}")
            return False


# region 目标检测结果转换为Labelme Json
class Yolo2JsonConverter(JsonBaseConverter):
    def __init__(self, config: ConvertConfig):
        super().__init__(config)
        self.mode = MODE.DETECT

    def process(self, path, imagePath):
        annotations = []
        image_data = np.fromfile(imagePath, dtype=np.uint8)
        image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        image_height, image_width = image.shape[:2]
        with open(path, "r", encoding="utf-8") as l:
            lineNo = 0
            for line in l:
                lineNo += 1
                parts = line.strip().split()
                if len(parts) != 5:
                    LOGGER.warning(f"{path}标注文本格式第{lineNo}行有误，{line}")
                    continue
                class_id = int(parts[0])
                x_center = float(parts[1])
                y_center = float(parts[2])
                width = float(parts[3])
                height = float(parts[4])

                # 计算点坐标 (左上角和右下角)
                x_center *= image_width  # 假设图像宽度是 1.0 的归一化值
                y_center *= image_height  # 假设图像高度是 1.0 的归一化值
                width *= image_width
                height *= image_height

                x_min = x_center - width / 2
                x_max = x_center + width / 2
                y_min = y_center - height / 2
                y_max = y_center + height / 2

                points = [
                    [x_min, y_min],
                    [x_max, y_max],
                ]

                annotations.append(
                    {
                        "class": self.class_mapping[class_id],
                        "points": points,
                        "shape_type": "rectangle",
                        "description": "",
                    }
                )
        return annotations, image_height, image_width


# endreigon


# region 分割结果转换为Labelme Json
class YoloSeg2JsonConverter(JsonBaseConverter):
    def __init__(self, config: ConvertConfig):
        super().__init__(config)
        self.mode = MODE.SEGMENT

    def process(self, path, imagePath):
        annotations = []
        image_data = np.fromfile(imagePath, dtype=np.uint8)
        image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        image_height, image_width = image.shape[:2]
        with open(path, "r", encoding="utf-8") as l:
            lineNo = 0
            for line in l:
                lineNo += 1
                parts = line.strip().split()
                if len(parts) <= 7 and len(parts) % 2 != 0:
                    LOGGER.warning(
                        f"{path}标注文本格式第{lineNo}行有误，{line},分割模型至少有三个关键点"
                    )
                    continue
                class_id = int(parts[0])
                points = parts[1:]
                # 将点两两配对
                points = [
                    [
                        float(points[i]) * image_width,
                        float(points[i + 1]) * image_height,
                    ]
                    for i in range(0, len(points), 2)
                ]

                annotations.append(
                    {
                        "class": self.class_mapping[class_id],
                        "points": points,
                        "shape_type": "polygon",
                        "description": "",
                    }
                )
        return annotations, image_height, image_width


# endregion  分割结果转换为Labelme Json


# region 姿态检测结果转换为Labelme Json
class YoloPose2JsonConverter(JsonBaseConverter):
    def __init__(self, config: ConvertConfig):
        super().__init__(config)
        self.mode = MODE.POSE

    def process(self, path, imagePath):
        kpt_nums = len(self.kpt)
        annotations = []
        image_data = np.fromfile(imagePath, dtype=np.uint8)
        image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        image_height, image_width = image.shape[:2]
        with open(path, "r", encoding="utf-8") as l:
            lineNo = 0
            for line in l:
                lineNo += 1
                parts = line.strip().split()
                if len(parts) != 5 + (kpt_nums * 3):
                    LOGGER.warning(f"{path}标注文本格式第{lineNo}行有误，{line}")
                    continue
                # 获取框
                class_id = int(parts[0])
                x_center = float(parts[1])
                y_center = float(parts[2])
                width = float(parts[3])
                height = float(parts[4])
                # 计算点坐标 (左上角和右下角)
                x_center *= image_width  # 假设图像宽度是 1.0 的归一化值
                y_center *= image_height  # 假设图像高度是 1.0 的归一化值
                width *= image_width
                height *= image_height
                x_min = x_center - width / 2
                x_max = x_center + width / 2
                y_min = y_center - height / 2
                y_max = y_center + height / 2
                points = [
                    [x_min, y_min],
                    [x_max, y_max],
                ]
                annotations.append(
                    {
                        "class": self.class_mapping[class_id].lower(),
                        "points": points,
                        "shape_type": "rectangle",
                        "description": "",
                    }
                )
                # 获取关键点
                kpts = parts[5:]
                step = 0
                for i in range(0, len(kpts), 3):
                    kpt_name = self.kpt[step]
                    step += 1
                    x, y, vis = kpts[i : i + 3]
                    x = float(x) * image_width
                    y = float(y) * image_height
                    points = [[x, y]]
                    if x == y == 0 or x == image_width or y == image_height:
                        continue
                    annotations.append(
                        {
                            "class": kpt_name,
                            "points": points,
                            "shape_type": "point",
                            "description": vis,
                        }
                    )
        return annotations, image_height, image_width


# endregion

# endregion
