# -*- coding: utf-8 -*-
"""
txt 文件转到 labelme json 格式的标签

用于自动标注工具结果转换为 Labelme 格式便于人工复核。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-02 图片与标注按文件名主干匹配（兼容 label/image/dataset 目录层级）；
      类别未配置时回退使用类别索引作为标签名；修复 generate_labelme_file
      宽高传参顺序颠倒问题
更新: 2026-09-02 修复 YoloSeg2JsonConverter 行校验条件（合法行为奇数字段数
      且 >= 7，原条件误拒 7 字段合法行、误放行偶数字段数行）
更新: 2026-09-04 复制图片/背景图前校验源与目标是否同一文件（输出目录与
      输入目录一致时 shutil.copy 抛 SameFileError 导致任务中断）
"""

from smart_annotator.config import LABELME_VERSION, ConvertConfig, MODE
from smart_annotator.utils import LOGGER
from pathlib import Path
import shutil
import cv2
import numpy as np


def _safe_copy(src: Path, dst: Path) -> None:
    """复制文件，源与目标为同一文件时跳过（输出目录=输入目录场景）。

    Args:
        src: 源文件路径。
        dst: 目标文件路径。
    """
    try:
        if src.resolve() == dst.resolve():
            return  # 同一文件（用户输出路径与输入路径一致），无需复制
    except OSError:
        pass  # 路径解析失败（如网络盘/已删除文件）交由 copy 抛错统一记录
    shutil.copy(src, dst)


# region YOLO系列转换Labelme json
class JsonBaseConverter:
    """YOLO TXT → LabelMe JSON 转换器基类。"""

    def __init__(self, config: ConvertConfig):
        """初始化转换器。

        Args:
            config: 转换配置对象。
        """
        self.config = config
        self.imageFiles = [Path(imageFile) for imageFile in config.image_files]
        self.annotationFiles = [
            Path(annotationFile) for annotationFile in config.annotation_files
        ]
        self.output = Path(self.config.output_dir)
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
        """处理单个标注文件（子类实现）。"""
        pass

    def run(self, callback):
        """执行转换任务。

        图片与标注按文件名主干（不含扩展名）匹配，兼容任意目录结构
        （label/image 兄弟目录、dataset 子目录、平铺等，目录层级由
        页面扫描阶段经 scan_dataset_files 解析后写入配置）。

        Args:
            callback: 进度回调函数，签名 callback(desc, progress) -> bool。

        Returns:
            任务是否成功完成。
        """
        try:
            self.output.mkdir(parents=True, exist_ok=True)
            total = len(self.annotationFiles)
            empty_files = []
            # 图片按主干名建索引（兼容不同扩展名与目录层级）
            image_map = {img.stem: img for img in self.imageFiles}
            # 遍历标注文件转换
            for idx, file in enumerate(self.annotationFiles):
                if not callback(f"标签转换中", (idx + 1) / total):
                    return False
                imagePath = image_map.get(file.stem)
                if imagePath is not None:
                    del image_map[file.stem]
                    self.imageFiles.remove(imagePath)
                    annotations, image_height, image_width = self.process(
                        file, imagePath
                    )
                    if not annotations:
                        empty_files.append(imagePath)
                        continue
                    from smart_annotator.utils import generate_labelme_file

                    generate_labelme_file(
                        annotations,
                        LABELME_VERSION,
                        imagePath.name,
                        image_width,
                        image_height,
                        self.output / (file.stem + ".json"),
                    )
                    _safe_copy(imagePath, self.output / imagePath.name)
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
                    _safe_copy(imageFile, backgroundFolder_img / imageFile.name)
            return True
        except Exception as ex:
            LOGGER.error(f"标签转换失败：{str(ex)}")
            return False


# region 目标检测结果转换为Labelme Json
class Yolo2JsonConverter(JsonBaseConverter):
    """YOLO DET TXT → LabelMe JSON 转换器。"""

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
                        # 类别未配置时回退使用类别索引作为标签名
                        "class": self.class_mapping.get(class_id, str(class_id)),
                        "points": points,
                        "shape_type": "rectangle",
                        "description": "",
                    }
                )
        return annotations, image_height, image_width


# endregion


# region 分割结果转换为Labelme Json
class YoloSeg2JsonConverter(JsonBaseConverter):
    """YOLO SEG TXT → LabelMe JSON 转换器。"""

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
                # 分割标准格式: classid + N 对坐标（N>=3），字段数须为奇数且 >= 7
                if len(parts) < 7 or len(parts) % 2 == 0:
                    LOGGER.warning(
                        f"{path}标注文本格式第{lineNo}行有误，{line},分割标注至少需三个坐标点"
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
                        # 类别未配置时回退使用类别索引作为标签名
                        "class": self.class_mapping.get(class_id, str(class_id)),
                        "points": points,
                        "shape_type": "polygon",
                        "description": "",
                    }
                )
        return annotations, image_height, image_width


# endregion  分割结果转换为Labelme Json


# region 姿态检测结果转换为Labelme Json
class YoloPose2JsonConverter(JsonBaseConverter):
    """YOLO POSE TXT → LabelMe JSON 转换器。"""

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
            for idx, line in enumerate(l):
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
                        # 类别未配置时回退使用类别索引作为标签名
                        "class": self.class_mapping.get(class_id, str(class_id)).lower(),
                        "points": points,
                        "shape_type": "rectangle",
                        "description": "",
                        "group_id": idx,
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
                            "group_id": idx,
                        }
                    )
        return annotations, image_height, image_width


# endregion

# endregion
