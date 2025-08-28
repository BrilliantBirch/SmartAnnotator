"""
Description：txt文件转到labelme json格式的标签 ,用于自动标注工具结果转换为Labelme格式便于人工复核
Author: Baibinnan
Date: 2025/3/19
LastEdit: 2025/3/19
E-mail: baibinnan@chuanfeng.com

"""

from cfg import LOGGER
from pathlib import Path
import shutil
from datetime import datetime
import os


# region YOLO系列转换Labelme json
class JsonBaseConverter:
    def __init__(self, *args, **kwargs):
        self.source = kwargs.get("source", None)
        if self.source is None or not Path.exists(Path(self.source)):
            raise ValueError("未指定源")
        class_mapping = kwargs.get("class_mapping", None)
        if class_mapping is None or not isinstance(class_mapping, list):
            raise ValueError(f"需要以列表形式指定检测类型")
        self.class_mapping = {idx: value for idx, value in enumerate(class_mapping)}
        self.ignore = kwargs.get("ignore", [])

    def process(self, path, imagePath):
        pass

    def run(self):
        try:
            LOGGER.info(f"标签开始转换，任务类型：{self.task}")
            source = Path(self.source)
            target = Path(self.target)
            background = target / "background"
            target.mkdir(parents=True, exist_ok=True)
            background.mkdir(parents=True, exist_ok=True)
            image_extensions = ("*.jpg", "*.jpeg", "*.png", "*.gif")
            image_files = []
            for ext in image_extensions:
                found_images = list(source.rglob(ext))
                image_files.extend([str(img) for img in found_images])
            self.image_files_set = set(image_files)
            label_extensions = "*.txt"
            found_labels = list(source.rglob(label_extensions))
            self.label_files_set = set([str(label) for label in found_labels])
            # 构建标注文件名到标注文件路径的哈希索引
            self.label_name2path = {
                os.path.splitext(os.path.basename(path))[0]: path
                for path in self.label_files_set
            }
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task = "yolo2labelme"
        self.target = kwargs.get(
            "target",
            os.path.join(
                ROOT,
                "target",
                f"{self.task}",
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}",
            ),
        )

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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kpt = kwargs.get("kpt", None)
        self.ignore = kwargs.get("ignore", [])
        self.ignore = [k.lower() for k in self.ignore]
        if self.kpt is None:
            raise ValueError(f"关键点--kpt参数缺失")
        self.task = "yolopose2labelme"
        self.target = kwargs.get(
            "target",
            os.path.join(
                ROOT,
                "target",
                f"{self.task}",
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}",
            ),
        )

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
                if self.class_mapping[class_id].lower() not in self.ignore:

                    annotations.append(
                        {
                            "class": self.class_mapping[class_id],
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
