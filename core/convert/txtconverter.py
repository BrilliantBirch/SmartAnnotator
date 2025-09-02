"""
Description：labelme文件转到txt格式的标签
Author: Baibinnan
Date: 2025/3/14
LastEdit: 2025/3/24
E-mail: baibinnan@chuanfeng.com

功能说明：
1. 支持灵活的关键点匹配策略
2. 处理关键点遮挡和缺失情况
3. 增强可视化标注效果
4. 支持labelme的json格式转换为yolo、yolo_pose、ppocr等模型所需的txt格式

update:
1.2025/3/19:结构整理
2.2025/3/24:适配多种图片格式
3.2025/5/08:新增补充单点标注的标注框
"""

from cfg import LOGGER, LABELME_VERSION, ROOT, RANDOM_SEED, ConvertConfig
from utils import COLORS, is_rect_inside, is_point_in_box


from typing import List, Tuple, Set
from pathlib import Path
import random
import shutil
import json
from datetime import datetime
import yaml
from PIL import Image, ImageDraw, ImageFont
import numpy as np


# region labelme2txt


class TxtConverter:
    def __init__(self, config: ConvertConfig):
        self.imageFiles = [Path(imageFile) for imageFile in config.imageFiles]
        self.annotationFiles = [
            Path(annotationFile) for annotationFile in config.annotationFiles
        ]
        self.output = Path(config.outputDir)
        self.classes = config.classes
        # 类别字典续按类别的索引从小到大排序，否则会导致绘图时类别不对应
        self.class_mapping = [value.lower() for value in self.classes]
        self.class_mapping = {
            value: index for index, value in enumerate(self.class_mapping)
        }
        self.visualized = config.visualized
        self.export = config.export
        # 默认分割比例训练集：验证集：测试集 8：1：1
        # self.splitRatio = kwargs.get(
        #     "splitRatio", {"train": 0.8, "val": 0.1, "test": 0.1}
        # )
        random.seed(RANDOM_SEED)
        selected_colors = random.sample(list(COLORS), len(self.classes))
        self.class_color_map = {i: color for i, color in enumerate(selected_colors)}

    def process(self, path: str) -> Tuple[List[str], bool, Set]:
        pass

    def visualize(
        self, imgPath: str, outputFileName: str, yololines: List[str], infos: Set[int]
    ):
        LOGGER.warning(f"当前转换器暂不支持可视化")

    def genDataYaml(self):
        """
        生成数据集yaml文件
        """
        yaml_content = {
            "path": self.output.absolute().as_posix(),  # dataset root dir
            "train": r"train/images",
            "val": r"val/images",
            "test": r"test/images",
            "nc": len(self.classes),
            "names": self.class_mapping,
        }
        if self.yamlName is None or self.yamlName == "":
            self.yamlName = self.output.name
        with open(self.output / self.yamlName / "Dataset.yaml", "w") as file:
            yaml.dump(yaml_content, file, default_flow_style=False, sort_keys=False)
        LOGGER.info(f"数据集生成完毕：{self.output / self.yamlName / 'Dataset.yaml'}")

    def run(self, prograss_callback=None):
        try:
            convertImgFolder = self.output / "images"
            convertImgFolder.mkdir(parents=True, exist_ok=True)
            convertLabelFolder = self.output / "labels"
            convertLabelFolder.mkdir(parents=True, exist_ok=True)
            if self.visualized:
                visualizeFolder = self.output / "visualized"
                visualizeFolder.mkdir(parents=True, exist_ok=True)
            # 获取图片路径及其后缀字典
            imageFiles_dir = {
                str(Path(imageFile)).split(".")[0]: Path(imageFile).suffix
                for imageFile in self.imageFiles
            }
            empty_files = []
            failed_files = []
            # 开始转换
            total = len(self.annotationFiles)
            for id, json_path in enumerate(self.annotationFiles):
                json_path = Path(json_path)
                # 根据标签获取图片路径
                img_path = json_path.with_suffix(
                    imageFiles_dir.get(str(json_path).split(".")[0], "")
                )
                if img_path in self.imageFiles:
                    # 标记为已处理
                    self.imageFiles.remove(img_path)
                    # 转换标注
                    yolo_lines, failed, failInfos = self.process(json_path)
                    # 转换失败
                    if failed:
                        failed_files.append(str(json_path))
                        continue
                    # 空标注文件
                    if not yolo_lines:
                        empty_files.append(img_path)
                        continue
                    # 复制图片
                    destination = convertImgFolder / img_path.name
                    try:
                        shutil.copy(img_path, destination)
                    except Exception as e:
                        LOGGER.error(f"复制 {img_path} 时出错: {e}")
                    txt_path = convertLabelFolder / f"{json_path.stem}.txt"
                    # 写入成功转换后的标注
                    with open(txt_path, "w") as f:
                        f.write("\n".join(yolo_lines))
                    # 可视化转换后的标注文件
                    if self.visualized:
                        vis_path = visualizeFolder / img_path.name
                        self.visualize(
                            str(img_path), str(vis_path), yolo_lines, failInfos
                        )
                else:
                    LOGGER.warning(f"{json_path}未找到对应的图片文件")
                prograss_callback("标签转换中", (id + 1) / total)

            # 处理背景图片，有两种 一种是空标注 一种是无标注图片(图片列表剩余中未处理的)
            if self.imageFiles or empty_files:
                background_total = len(self.imageFiles) + len(empty_files)
                LOGGER.info(f"开始处理背景图片，共{background_total}张")
                backgroundFolder_img = self.output / "background" / "images"
                backgroundFolder_img.mkdir(parents=True, exist_ok=True)
                backgroundFolder_label = self.output / "background" / "labels"
                backgroundFolder_label.mkdir(parents=True, exist_ok=True)
                background_imgFiles = self.imageFiles + empty_files
                for id, imageFile in enumerate(background_imgFiles):
                    prograss_callback("背景图片转换中", (id + 1) / background_total)
                    shutil.copy(imageFile, backgroundFolder_img / imageFile.name)
                    # 生成空的txt文件
                    with open(
                        backgroundFolder_label / f"{imageFile.stem}.txt", "w"
                    ) as f:
                        f.write("")

            # 处理失败转换
            if failed_files:
                pass
                # with open(outputdir / "problematic_files.txt", "w") as f:
                #     f.write("\n".join(problematic_files))
                # print(
                #     f"发现 {len(problematic_files)} 个问题文件，详见 problematic_files.txt"
                # )

            # if self.splitDataSet:
            #     self.splitData()
            # if self.is_genyaml:
            #     if not self.splitDataSet:
            #         if (
            #             input(f"还未执行数据集分割，是否先进行分割(y/n)?").lower()
            #             == "y"
            #         ):
            #             self.splitData()
            #             self.genDataYaml()
            #     else:
            #         self.genDataYaml()
        except Exception as ex:
            LOGGER.error(f"标签转换中错误：{str(ex)}")
            prograss_callback("标签转换异常终止", 1.0)


# region ToYOLOPose
class YoloPoseConverter(TxtConverter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task = "ToYOLO_Pose"
        self.kpt = kwargs.get("kpt", [])
        self.kpt = [kpt.lower() for kpt in self.kpt]
        if self.kpt is None:
            raise ValueError(
                "缺少关键点信息，使用--kpt参数，如['Guide_plate_0_Point1','Guide_plate_0_Point2','Guide_plate_1_Point1','Guide_plate_1_Point2']"
            )
        self.kpt = [
            kpt for kpt in self.kpt if kpt.split("_point")[0] in self.class_mapping
        ]
        self.kpt_num = len(self.kpt)
        # 获取要补充框的点
        self.kpt_withoutBBox = kwargs.get("kpt_withoutBBox", [])
        # 需要补充框的大小
        self.BBoxSize = kwargs.get("BBoxSize", 6)
        # 转换为set 去重
        self.kpt_withoutBBox = set((kpt.lower() for kpt in self.kpt_withoutBBox))
        self.target = os.path.join(
            self.target,
            self.task,
            f"{datetime.now().strftime('%Y%m%d%H%M%S')}",
        )
        selected_colors = random.sample(list(COLORS), self.classNum + self.kpt_num)
        self.class_color_map = {i: color for i, color in enumerate(selected_colors)}

    def process(self, path):
        """处理单个标注文件"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            image_width = data["imageWidth"]
            image_height = data["imageHeight"]

            yolo_lines = []
            has_problem = False
            infos = set()
            # 分离框和关键点
            boxes = []
            kpt_dict = dict()
            kpt_withoutBBox_dict = dict()
            grouped = []
            for shape in data["shapes"]:
                label = shape["label"].lower()
                if label not in self.class_mapping and label not in self.kpt:
                    continue
                if shape["group_id"]:
                    grouped.append(shape)
                    continue
                if shape["shape_type"] == "rectangle":
                    boxes.append(shape)
                elif shape["shape_type"] == "point" or shape["shape_type"] == "points":
                    points = shape["points"]
                    description = (
                        shape["description"].lower().split("=")
                        if shape["description"]
                        else ""
                    )
                    visible = description[1] if len(description) > 1 else "2"
                    points = tuple(points[0])
                    if label in self.kpt_withoutBBox:
                        if label not in kpt_withoutBBox_dict:
                            kpt_withoutBBox_dict[label] = set()
                        kpt_withoutBBox_dict[label].add((points, visible))
                    if label not in kpt_dict:
                        kpt_dict[label] = set()
                    kpt_dict[label].add((points, visible))
            # 处理分组
            grouped_dict = {}
            for shape in grouped:
                group_id = shape["group_id"]
                # 确保group_id可哈希（避免None）
                group_id = group_id if group_id is not None else "none"
                if group_id not in grouped_dict:
                    grouped_dict[group_id] = []
                grouped_dict[group_id].append(shape)

            # 在这一步将框补充

            if self.kpt_withoutBBox and kpt_withoutBBox_dict:
                for kpt_type, points_set in kpt_withoutBBox_dict.items():
                    label = kpt_type.split("_point")[0]
                    if label not in self.class_mapping:
                        LOGGER.warning(
                            f"标注文件{path}中存在未定义的类别{label}，请检查"
                        )
                        continue
                    for points, visible in points_set:
                        # 补充框
                        x, y = points
                        x1 = max(0, x - self.BBoxSize)
                        y1 = max(0, y - self.BBoxSize)
                        x2 = min(image_width - 1, x + self.BBoxSize)
                        y2 = min(image_height - 1, y + self.BBoxSize)
                        box_points = [(x1, y1), (x2, y2)]
                        boxes.append({"label": label, "points": box_points})

            for group_id, shapes in grouped_dict.items():
                # 分离组内的框和点
                group_boxes = []
                group_kpts = dict()  # 组内关键点：{label: {(x,y), visible}, ...}

                for shape in shapes:
                    label = shape["label"].lower()
                    if shape["shape_type"] == "rectangle":
                        group_boxes.append(shape)

                    elif shape["shape_type"] in ["point", "points"]:
                        points = shape["points"]
                        description = (
                            shape["description"].lower().split("=")
                            if shape["description"]
                            else ""
                        )
                        visible = description[1] if len(description) > 1 else "2"
                        point = tuple(points[0]) if points else (0, 0)
                        if label not in group_kpts:
                            group_kpts[label] = set()
                        group_kpts[label].add((point, visible))

                # 处理组内的框，只匹配组内的点
                for box in group_boxes:
                    box_label = box["label"].lower()
                    if box_label not in self.class_mapping:
                        continue
                    class_id = self.class_mapping[box_label]
                    box_points = box["points"]
                    x1, y1 = box_points[0]
                    x2, y2 = box_points[1]
                    x1, x2 = min(x1, x2), max(x1, x2)
                    y1, y2 = min(y1, y2), max(y1, y2)

                    # 计算YOLO格式的框坐标
                    center_x = (x1 + x2) / (2 * image_width)
                    center_y = (y1 + y2) / (2 * image_height)
                    box_w = (x2 - x1) / image_width
                    box_h = (y2 - y1) / image_height
                    line = [
                        str(class_id),
                        str(center_x),
                        str(center_y),
                        str(box_w),
                        str(box_h),
                    ]

                    # 匹配组内的关键点
                    for point_category in self.kpt:
                        if not point_category.startswith(box_label):
                            line.extend(["0", "0", "0"])
                            continue
                        # 只查找组内的点
                        if point_category in group_kpts:
                            matched = False
                            for point_info in list(group_kpts[point_category]):
                                point, visible = point_info
                                if is_point_in_box(point, box_points):
                                    x, y = point
                                    norm_x = x / image_width
                                    norm_y = y / image_height
                                    line.extend([str(norm_x), str(norm_y), visible])
                                    group_kpts[point_category].remove(point_info)
                                    matched = True
                                    break
                            if not matched:
                                line.extend(["0", "0", "0"])  # 组内该点不存在于框内
                        else:
                            line.extend(["0", "0", "0"])  # 组内无此类型点
                    yolo_lines.append(" ".join(line))

                # 检查组内是否有未匹配的点（异常情况）
                for label, points_set in group_kpts.items():
                    if points_set:
                        has_problem = True
                        for (x, y), _ in points_set:
                            infos.add((x / image_width, y / image_height))

            for box in boxes:
                box_label = box["label"].lower()
                box_points = box["points"]
                class_id = self.class_mapping[box_label]

                # 计算框的中心点和宽高
                x1, y1 = box_points[0]
                x2, y2 = box_points[1]

                x1, x2 = min(x1, x2), max(x1, x2)
                y1, y2 = min(y1, y2), max(y1, y2)
                center_x = (x1 + x2) / (2 * image_width)
                center_y = (y1 + y2) / (2 * image_height)
                box_w = (x2 - x1) / image_width
                box_h = (y2 - y1) / image_height
                line = [
                    str(class_id),
                    str(center_x),
                    str(center_y),
                    str(box_w),
                    str(box_h),
                ]
                # 处理关键点
                for point_category in self.kpt:
                    point_category = point_category
                    box_label = box_label
                    if point_category.startswith(box_label):
                        if point_category in kpt_dict:
                            for point_info in kpt_dict[point_category]:
                                point, visible = point_info
                                if is_point_in_box(point, box_points):
                                    x, y = point
                                    norm_x = x / image_width
                                    norm_y = y / image_height
                                    line.extend(
                                        [str(norm_x), str(norm_y), visible]
                                    )  # 可见
                                    kpt_dict[point_category].remove(point_info)
                                    break
                            else:
                                # 该框内该点被遮挡了
                                line.extend(["0", "0", "0"])  # 框内不存在点
                        else:
                            line.extend(["0", "0", "0"])  # 该点不存在
                    else:
                        line.extend(["0", "0", "0"])  # 不属于该类别
                yolo_lines.append(" ".join(line))
            for _, kpt_set in kpt_dict.items():
                if kpt_set:
                    has_problem = True
                    for points, _ in kpt_set:
                        x, y = points
                        normalized_x = x / image_width
                        normalized_y = y / image_height
                        infos.add((normalized_x, normalized_y))
            return yolo_lines, has_problem, infos
        except Exception as ex:
            LOGGER.error(f"处理标注文件时出错：{str(ex)}")
            with open(os.path.join(self.target, "problematic_files.txt"), "a") as f:
                f.write(f"{path}错误原因:{str(ex)}\n")
            return [], True, set

    def visualize(
        self,
        imgPath: str,
        outputFileName: str,
        annotations: List[str],
        infos: Set[int] = set(),
    ):
        """可视化标注结果"""
        if annotations is None or len(annotations) == 0:
            return
        image_data = np.fromfile(imgPath, dtype=np.uint8)
        image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        if image is None:
            return
        height, width = image.shape[:2]
        for line in annotations:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            # 解析基础信息
            class_id = int(parts[0])
            center_x = float(parts[1]) * width
            center_y = float(parts[2]) * height
            box_w = float(parts[3]) * width
            box_h = float(parts[4]) * height

            # 计算边界框坐标
            x1 = int(center_x - box_w / 2)
            y1 = int(center_y - box_h / 2)
            x2 = int(center_x + box_w / 2)
            y2 = int(center_y + box_h / 2)

            # 绘制边界框
            box_color = tuple(int(c * 255) for c in self.class_color_map[class_id])
            cv2.rectangle(image, (x1, y1), (x2, y2), box_color, 2)

            # 添加类别标签
            label = f"{list(self.class_mapping.keys())[class_id]}"

            cv2.putText(
                image, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2
            )

            # 解析关键点
            keypoints = np.array([float(x) for x in parts[5:]]).reshape(-1, 3)

            # 绘制关键点
            for idx, kp in enumerate(keypoints):
                kp_x = int(kp[0] * width)
                kp_y = int(kp[1] * height)
                point_color = tuple(
                    int(c * 255) for c in self.class_color_map[self.classNum + idx]
                )
                label = self.kpt[idx]
                # 绘制关键点
                cv2.circle(image, (kp_x, kp_y), 6, point_color, -1)
                # 添加关键点标签
                cv2.putText(
                    image,
                    label,
                    (kp_x + 10, kp_y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    point_color,
                    1,
                )

            if infos:
                # 有错的
                color = (0, 0, 255)
                for points in infos:
                    kp_x = int(points[0] * width)
                    kp_y = int(points[1] * height)
                    # 绘制关键点
                    cv2.circle(image, (kp_x, kp_y), 6, color, -1)
                    # 添加关键点标签
                    cv2.putText(
                        image,
                        "wrong_point",
                        (kp_x + 10, kp_y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        2.0,
                        color,
                        2,
                    )
        cv2.imwrite(outputFileName, image)

    def genDataYaml(self):
        """
        生成Pose数据集yaml文件
        """
        yaml_content = {
            "path": os.path.abspath(str(self.target)),  # dataset root dir
            "train": r"train/images",
            "val": r"val/images",
            "test": r"test/images",
            "kpt_shape": [self.kpt_num, 3],
            "flip_idx": [i for i in range(self.kpt_num)],
            "names": {self.class_mapping[k]: k for k in self.class_mapping},
        }
        if self.yamlName is None or self.yamlName == "":
            self.yamlName = os.path.basename(self.target)
        with open(
            os.path.join(str(self.target), self.yamlName + "Dataset.yaml"),
            "w",
            encoding="utf-8",
        ) as file:
            yaml.dump(
                yaml_content,
                file,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
        LOGGER.info(
            f"数据集生成完毕：{os.path.join(str(self.target),self.yamlName+'Dataset.yaml')}"
        )


# endregion


# region ToYOLO
class YoloConverter(TxtConverter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def process(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            yolo_annotations = []
            image_height = data["imageHeight"]
            image_width = data["imageWidth"]
            for shape in data["shapes"]:
                label = shape["label"].lower()
                if label not in self.class_mapping:
                    continue
                if shape["shape_type"] == "rectangle":
                    points = shape["points"]
                    # convert to YOLO format
                    (xmin, ymin), (xmax, ymax) = points
                    x_center = (xmin + xmax) / 2.0 / image_width
                    y_center = (ymin + ymax) / 2.0 / image_height
                    width = abs((xmax - xmin) / image_width)
                    height = abs((ymax - ymin) / image_height)
                    class_id = self.class_mapping[label]
                    yolo_annotations.append(
                        f"{class_id} {x_center} {y_center} {width} {height}"
                    )
            return yolo_annotations, False, set()
        except Exception as ex:
            LOGGER.error(f"{path}标签转换失败：{ex}")
            return None, True, set()

    def visualize(self, imgPath, outputFileName, yololines, infos=None):
        """可视化标注结果"""
        try:
            image = Image.open(imgPath).convert("RGB")

            draw = ImageDraw.Draw(image)
            width, height = image.size
            font = ImageFont.load_default()
            # 画每一个标签
            for line in yololines:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                # 解析基础信息
                class_id = int(parts[0])
                center_x = float(parts[1]) * width
                center_y = float(parts[2]) * height
                box_w = float(parts[3]) * width
                box_h = float(parts[4]) * height
                # 计算边界框坐标
                x1 = int(center_x - box_w / 2)
                y1 = int(center_y - box_h / 2)
                x2 = int(center_x + box_w / 2)
                y2 = int(center_y + box_h / 2)
                # 绘制边界框
                box_color = tuple(int(c * 255) for c in self.class_color_map[class_id])
                # 绘制矩形框
                draw.rectangle([(x1, y1), (x2, y2)], outline=box_color, width=2)
                # 添加类别标签
                label = f"{list(self.class_mapping.keys())[class_id]}"
                # 计算文本位置，确保文本在图像范围内
                text_x = x1
                text_y = max(0, y1 - 15)  # 稍微向上偏移

                # 先绘制一个背景矩形，使文本更清晰
                text_bbox = draw.textbbox((text_x, text_y), label, font=font)
                draw.rectangle(text_bbox, fill=box_color)
                # 绘制文本（使用白色文字以对比）
                draw.text((text_x, text_y), label, font=font, fill=(255, 255, 255))

            image.save(outputFileName)
        except Exception as ex:
            LOGGER.error(f"Yolo—Det标签可视化失败：{ex}")
            return


# endregion

# region ToYOLOSeg


class YoloSegConverter(TxtConverter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task = "ToYOLOSeg"
        self.target = os.path.join(
            self.target,
            self.task,
            f"{datetime.now().strftime('%Y%m%d%H%M%S')}",
        )

    def process(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        yolo_annotations = []
        image_height = data["imageHeight"]
        image_width = data["imageWidth"]
        for shape in data["shapes"]:
            label = shape["label"].lower()
            if label not in self.class_mapping:
                continue
            if shape["shape_type"] == "polygon":
                points = shape["points"]
                if len(points) < 3:
                    raise ValueError(
                        f"{path}标注文件：类别{label}有误,多边形标注框必须至少有3个点,"
                    )
                # convert to YOLO format
                points_txt = []
                class_id = self.class_mapping[label]
                for point in points:
                    x = point[0] / image_width
                    y = point[1] / image_height
                    points_txt.append(f"{x} {y}")

                yolo_annotations.append(f"{class_id} {' '.join(points_txt)}")

        return yolo_annotations, False, set()

    def visualize(self, imgPath, outputFileName, yololines, infos):
        """可视化多边形标注结果"""
        # 读取含中文路径的图片
        image_data = np.fromfile(imgPath, dtype=np.uint8)
        image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
        if image is None:
            return
        height, width = image.shape[:2]  # 获取图像实际高和宽

        for line in yololines:
            parts = line.strip().split()
            if (
                len(parts) < 7
            ):  # 多边形至少需要3个点（每个点2个坐标）+ 1个class_id，共1+3*2=7个元素
                continue  # 过滤无效标注

            # 解析类别ID
            class_id = int(parts[0])
            # 解析多边形顶点（后续元素为成对的x、y坐标，归一化值）
            points = []
            for i in range(1, len(parts), 2):
                if i + 1 >= len(parts):
                    break  # 避免索引越界
                # 归一化坐标转实际像素坐标
                x = float(parts[i]) * width
                y = float(parts[i + 1]) * height
                points.append((int(x), int(y)))  # 转为整数像素坐标

            # 绘制多边形轮廓
            box_color = tuple(int(c * 255) for c in self.class_color_map[class_id])
            # 转换为numpy数组用于cv2.polylines
            points_np = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
            # 绘制多边形（闭合轮廓，线条粗细2）
            cv2.polylines(
                image, [points_np], isClosed=True, color=box_color, thickness=1
            )

            # 绘制类别标签（放在多边形第一个顶点附近）
            label = f"{list(self.class_mapping.keys())[class_id]}"
            # 标签位置：第一个点的左上方10像素处
            label_pos = (points[0][0], points[0][1] - 10)
            # 绘制标签背景（避免文字与图像重叠）
            (text_w, text_h), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
            )
            cv2.rectangle(
                image,
                (label_pos[0], label_pos[1] - text_h - 5),
                (label_pos[0] + text_w + 5, label_pos[1] + 5),
                (255, 255, 255),  # 白色背景
                -1,  # 填充背景
            )
            # 绘制标签文字
            cv2.putText(
                image, label, label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2
            )

        cv2.imwrite(outputFileName, image)


# endregion


# region ToPPOCR
class PPOCRConverter(TxtConverter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target = kwargs.get(
            "target",
            os.path.join(
                ROOT,
                "target",
                "labelme2ppocr",
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}",
            ),
        )
        self.task = "ToPPOCR"

    def process(self, path):
        ppocr_annotations = []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for shape in data["shapes"]:
            label = shape["label"].lower()
            if label not in self.class_mapping:
                continue
            points = shape["points"]
            # 多边形标注框
            if shape["shape_type"] == "polygon":
                ppocrPoints = [(round(x), round(y)) for x, y in points]
            # 矩形标注框
            elif shape["shape_type"] == "rectangle":
                x_coords = [p[0] for p in points]
                y_coords = [p[1] for p in points]
                left = round(min(x_coords))
                right = round(max(x_coords))
                top = round(min(y_coords))
                bottom = round(max(y_coords))
                p1 = [left, top]
                p2 = [right, top]
                p3 = [right, bottom]
                p4 = [left, bottom]
                ppocrPoints = [p1, p2, p3, p4]
            else:
                continue
            text = shape["description"]
            if text is None:
                continue
            text = text.strip()
            ppocr_data = {
                "transcription": text,
                "points": ppocrPoints,
                "difficult": False,
            }
            ppocr_annotations.append(ppocr_data)
        return ppocr_annotations, False, set()

    def run(self):
        try:
            LOGGER.info(f"标签开始转换，任务类型：{self.task}")
            LOGGER.warning(
                f"ppocr标注格式不统一，目前暂未确定将要使用的版本，此功能未来再做开发"
            )

            # target=Path(self.target)
            # target.mkdir(parents=True, exist_ok=True)
        except Exception as ex:
            LOGGER.error(f"标签转换中错误：{str(ex)}")

    def visualize(self, imgPath, outputFileName, yololines, infos):
        LOGGER.info(f"此任务:{self.task}暂不支持可视化，可使用PPOCRLabel查看转换结果")

    def genDataYaml(self):
        LOGGER.info(f"此任务:{self.task}不支持生成yaml数据集配置")


# endregion

# endregion
