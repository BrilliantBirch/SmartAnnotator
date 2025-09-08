"""
Description：txt文件转到labelme json格式的标签 ,用于自动标注工具结果转换为Labelme格式便于人工复核
Author: Baibinnan
Date: 2025/3/19
LastEdit: 2025/3/19
E-mail: baibinnan@chuanfeng.com

"""

from cfg import LOGGER, ConvertConfig, MODE
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
        self.kpt = config.kpt
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

    def run(self):
        try:
            self.output.mkdir(parents=True, exist_ok=True)
            # 遍历图片转换标签
            for image in tqdm(self.image_files_set, desc="标签转换中", unit="files"):
                image_name = os.path.splitext(os.path.basename(image))[0]
                if image_name in self.label_name2path:
                    label = self.label_name2path[image_name]
                    # #标签不存在 作为背景
                    # if label not in self.label_files_set:
                    #     shutil.copy(image,background)
                    #     continue
                    annotations, image_height, image_width = self.process(label, image)
                    if not annotations:
                        # LOGGER.warning(f'当前标签{label}为空，图片拷贝到背景文件夹')
                        shutil.copy(image, background)
                        self.label_files_set.remove(label)
                        continue
                    writetoLabelme(
                        annotations,
                        image_height,
                        image_width,
                        os.path.basename(image),
                        str(target),
                    )
                    shutil.copy(image, target)
                    # 该标签已被处理 从集合中排除
                    self.label_files_set.remove(label)
                else:
                    # LOGGER.warning(f'当前图像无标签，拷贝到背景文件夹')
                    shutil.copy(image, background)
            if self.label_files_set:
                LOGGER.warning(f"剩余{len(self.label_files_set)}标签未处理")
                for l in self.label_files_set:
                    LOGGER.warning(f"{l}未找到对应的图片，请检查")
            LOGGER.info(f"转换完毕，目标文件夹：{str(target)}")
        except Exception as ex:
            LOGGER.error(f"标签转换失败：{str(ex)}")


# region 目标检测结果转换为Labelme Json
class Yolo2JsonConverter(JsonBaseConverter):
    def __init__(self, config: ConvertConfig):
        super().__init__(config)
        self.mode = MODE.DET

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


# region 姿态检测结果转换为Labelme Json
class YoloPose2JsonConverter(JsonBaseConverter):
    def __init__(self, config: ConvertConfig):
        super().__init__(config)
        self.kpt = config.kpt
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
                    if kpt_name.lower() not in self.ignore:
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
