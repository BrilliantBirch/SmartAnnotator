"""
Description：labelme文件转到txt格式的标签
Author: Baibinnan
Date: 2025/3/14
LastEdit: 2025/9/2
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

from cfg import LOGGER, RANDOM_SEED, ConvertConfig, MODE
from utils import COLORS, is_point_in_box, export


from typing import List, Tuple, Set
from pathlib import Path
import random
import shutil
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# region labelme2txt


class TxtConverter:
    def __init__(self, config: ConvertConfig):
        self.imageFiles = [Path(imageFile) for imageFile in config.imageFiles]
        self.annotationFiles = [
            Path(annotationFile) for annotationFile in config.annotationFiles
        ]
        self.output = Path(config.outputDir)
        self.classes = config.classes
        self.kpt = config.kpt
        self.splitRatio = (config.trainRatio, config.valRatio, config.testRatio)
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
        self.class_mapping = {v: i for i, v in enumerate(unique_classes)}
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
                if not prograss_callback("标签转换中", (id + 1) / total):
                    return False
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
                        failed_files.append((json_path, img_path, failInfos))
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

            # 处理背景图片，有两种 一种是空标注 一种是无标注图片(图片列表剩余中未处理的)
            if self.imageFiles or empty_files:
                background_total = len(self.imageFiles) + len(empty_files)
                LOGGER.info(
                    f"开始处理背景图片，共{background_total}张，复制到{self.output / 'background'}"
                )
                backgroundFolder_img = self.output / "background" / "images"
                backgroundFolder_img.mkdir(parents=True, exist_ok=True)
                backgroundFolder_label = self.output / "background" / "labels"
                backgroundFolder_label.mkdir(parents=True, exist_ok=True)
                background_imgFiles = self.imageFiles + empty_files
                for id, imageFile in enumerate(background_imgFiles):
                    if not prograss_callback(
                        "背景图片转换中", (id + 1) / background_total
                    ):
                        return False
                    shutil.copy(imageFile, backgroundFolder_img / imageFile.name)
                    # 生成空的txt文件
                    with open(
                        backgroundFolder_label / f"{imageFile.stem}.txt", "w"
                    ) as f:
                        f.write("")

            # 处理失败转换
            if failed_files:
                failedFolder = self.output / "failed"
                failedFolder.mkdir(parents=True, exist_ok=True)
                for json_path, img_path, infos in failed_files:
                    shutil.copy(json_path, failedFolder / json_path.name)
                    shutil.copy(img_path, failedFolder / img_path.name)
                    self.visualize(
                        str(img_path),
                        str(failedFolder / img_path.stem) + "_failed.jpg",
                        [],
                        infos=infos,
                    )
                LOGGER.info(
                    f"发现 {len(failed_files)} 个转换失败文件，输出到{failedFolder}"
                )

            if self.export:
                LOGGER.info(f"开始导出数据集")

                def exportcallback(desc, process):
                    prograss_callback(desc, process)

                export(
                    self.output,
                    self.class_mapping,
                    self.kpt,
                    self.splitRatio,
                    callback=exportcallback,
                )
                LOGGER.info(f"导出数据集完成")

            return True
        except Exception as ex:
            LOGGER.error(f"标签转换中错误：{str(ex)}")
            return False


# region ToYOLOPose
class YoloPoseConverter(TxtConverter):
    def __init__(self, config: ConvertConfig):
        super().__init__(config)
        self.mode = MODE.POSE
        # 获取要补充框的点
        kpt_withoutBBox = []
        kpt_type = []
        for k in config.kpt:
            if k.split("_point")[0] not in self.class_mapping:
                LOGGER.warning(f"关键点{k}未找到对应的类别")
                raise ValueError(f"关键点{k}未找到对应的类别")
            if config.kpt[k].get("isChecked"):
                kpt_withoutBBox.append(k)
            kpt_type.append(k)
        self.kpt = config.kpt
        self.kpt_type = kpt_type
        self.classnum = len(self.class_mapping)
        self.kpt_num = len(self.kpt)
        selected_colors = random.sample(list(COLORS), self.classnum + self.kpt_num)
        self.class_color_map = {i: color for i, color in enumerate(selected_colors)}
        self.kpt_withoutBBox = kpt_withoutBBox

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

            boxes = []
            kpt_dict = dict()
            kpt_withoutBBox_dict = dict()
            grouped = []

            for shape in data["shapes"]:
                label = shape["label"].lower()
                if label not in self.class_mapping and label not in self.kpt:
                    continue
                if shape.get("group_id", None) is not None:
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

            grouped_dict = {}
            for shape in grouped:
                group_id = shape["group_id"]
                group_id = group_id if group_id is not None else "none"
                if group_id not in grouped_dict:
                    grouped_dict[group_id] = []
                grouped_dict[group_id].append(shape)

            if self.kpt_withoutBBox and kpt_withoutBBox_dict:
                for kpt_type, points_set in kpt_withoutBBox_dict.items():
                    label = kpt_type.split("_point")[0]
                    if label not in self.class_mapping:
                        LOGGER.warning(
                            f"标注文件{path}中存在未定义的类别{label}，请检查"
                        )
                        continue
                    for points, visible in points_set:
                        bboxSize = int(self.kpt[kpt_type].get("bbox_size", 10))
                        x, y = points
                        x1 = max(0, x - bboxSize)
                        y1 = max(0, y - bboxSize)
                        x2 = min(image_width - 1, x + bboxSize)
                        y2 = min(image_height - 1, y + bboxSize)
                        box_points = [(x1, y1), (x2, y2)]
                        boxes.append({"label": label, "points": box_points})

            for group_id, shapes in grouped_dict.items():
                group_boxes = []
                group_kpts = dict()

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

                    for point_category in self.kpt:
                        if not point_category.split("_point")[0] == box_label:
                            line.extend(["0", "0", "0"])
                            continue
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
                                if point_category in kpt_dict:
                                    for point_info in list(kpt_dict[point_category]):
                                        point, visible = point_info
                                        if is_point_in_box(point, box_points):
                                            x, y = point
                                            norm_x = x / image_width
                                            norm_y = y / image_height
                                            line.extend([str(norm_x), str(norm_y), visible])
                                            kpt_dict[point_category].remove(point_info)
                                            matched = True
                                            break
                                if not matched:
                                    line.extend(["0", "0", "0"])
                        else:
                            if point_category in kpt_dict:
                                matched = False
                                for point_info in list(kpt_dict[point_category]):
                                    point, visible = point_info
                                    if is_point_in_box(point, box_points):
                                        x, y = point
                                        norm_x = x / image_width
                                        norm_y = y / image_height
                                        line.extend([str(norm_x), str(norm_y), visible])
                                        kpt_dict[point_category].remove(point_info)
                                        matched = True
                                        break
                                if not matched:
                                    line.extend(["0", "0", "0"])
                            else:
                                line.extend(["0", "0", "0"])
                    yolo_lines.append(" ".join(line))

                for label, points_set in group_kpts.items():
                    if points_set:
                        has_problem = True
                        for (x, y), _ in points_set:
                            infos.add((x / image_width, y / image_height))

            for box in boxes:
                box_label = box["label"].lower()
                box_points = box["points"]
                class_id = self.class_mapping[box_label]

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

                for point_category in self.kpt:
                    if box_label == point_category.split("_point")[0]:
                        if point_category in kpt_dict:
                            for point_info in kpt_dict[point_category]:
                                point, visible = point_info
                                if is_point_in_box(point, box_points):
                                    x, y = point
                                    norm_x = x / image_width
                                    norm_y = y / image_height
                                    line.extend(
                                        [str(norm_x), str(norm_y), visible]
                                    )
                                    kpt_dict[point_category].remove(point_info)
                                    break
                            else:
                                line.extend(["0", "0", "0"])
                        else:
                            line.extend(["0", "0", "0"])
                    else:
                        line.extend(["0", "0", "0"])
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
            LOGGER.error(f"处理标注文件时出错：{str(ex)},记录到errorConvert.txt中")
            with open(self.output / "errorConvert.txt", "a") as f:
                f.write(f"{path}错误原因:{str(ex)}\n")
            return [], True, set()

    def visualize(
        self,
        imgPath: str,
        outputFileName: str,
        annotations: List[str],
        infos: Set[Tuple[float, float]] = set(),
    ):
        """
        :param imgPath: 输入图片路径（支持中文）
        :param outputFileName: 输出图片路径（支持中文）
        :param annotations: YOLO格式标注列表（每行：class_id + 框坐标 + 关键点坐标）
        :param infos: 错误关键点坐标集合（格式：{(x1,y1), (x2,y2), ...}，归一化坐标）
        """

        if not annotations or len(annotations) == 0:
            if not infos or len(infos) == 0:
                return
        try:
            # 转为RGB通道（统一格式，避免RGBA/灰度图问题）
            image = Image.open(imgPath).convert("RGB")
        except Exception as e:
            LOGGER.error(f"读取图片失败：{imgPath}，错误：{str(e)}")
            return
        draw = ImageDraw.Draw(image)  # 初始化绘图对象
        width, height = image.size

        font = ImageFont.load_default()
        errorFont = ImageFont.load_default().font_variant(size=20)
        if annotations:
            # 遍历标注，绘制每一个目标
            for line in annotations:
                parts = line.strip().split()
                # 校验标注格式：至少包含 class_id + 4个框坐标（共5个元素）
                if len(parts) < 5:
                    continue
                try:
                    class_id = int(parts[0])
                    # 归一化坐标 → 实际像素坐标（center_x, center_y, box_w, box_h）
                    center_x = float(parts[1]) * width
                    center_y = float(parts[2]) * height
                    box_w = float(parts[3]) * width
                    box_h = float(parts[4]) * height
                    # 计算边界框对角坐标（左上角x1,y1，右下角x2,y2）
                    x1 = int(center_x - box_w / 2)
                    y1 = int(center_y - box_h / 2)
                    x2 = int(center_x + box_w / 2)
                    y2 = int(center_y + box_h / 2)

                    box_color = tuple(
                        int(c * 255) for c in self.class_color_map[class_id]
                    )
                    draw.rectangle(
                        xy=[x1, y1, x2, y2],  # 矩形对角坐标
                        outline=box_color,  # 边框颜色
                        width=2,
                    )

                    # 绘制类别标签（对应OpenCV cv2.putText）
                    label = f"{list(self.class_mapping.keys())[class_id]}"
                    # 标签位置：边界框左上角上方10像素（避免超出图片顶部）
                    label_x = x1
                    label_y = max(y1 - 10, 10)  # 防止标签超出图片顶部
                    # 绘制标签文字
                    draw.text(
                        xy=(label_x, label_y),
                        text=label,
                        font=font,
                        fill=box_color,  # 文字颜色与边框一致
                    )

                    # 解析并绘制关键点（每个关键点含x,y,可见性，共3个值）
                    if len(parts) >= 8:  # 至少1个关键点（3个值）+ 5个基础参数
                        keypoints = np.array([float(x) for x in parts[5:]]).reshape(
                            -1, 3
                        )
                        for idx, kp in enumerate(keypoints):
                            kp_x = int(kp[0] * width)  # 关键点x坐标
                            kp_y = int(kp[1] * height)  # 关键点y坐标
                            point_color = tuple(
                                int(c * 255)
                                for c in self.class_color_map[self.classnum + idx]
                            )

                            # 绘制关键点
                            circle_radius = 1
                            draw.ellipse(
                                xy=[
                                    kp_x - circle_radius,
                                    kp_y - circle_radius,
                                    kp_x + circle_radius,
                                    kp_y + circle_radius,
                                ],
                                fill=point_color,  # 圆形填充颜色（-1表示填充）
                            )

                            # 绘制关键点标签
                            kp_label = self.kpt_type[idx]
                            # 标签位置：关键点右侧10像素、上方5像素
                            kp_label_x = kp_x + 10
                            kp_label_y = kp_y - 5
                            draw.text(
                                xy=(kp_label_x, kp_label_y),
                                text=kp_label,
                                font=font,
                                fill=point_color,
                            )

                except Exception as e:
                    LOGGER.error(f"解析标注失败：{line}，错误：{str(e)}")
                    continue

        # 绘制错误关键点（infos中的坐标）
        if infos:
            wrong_color = (255, 0, 0)
            for point in infos:
                try:
                    # 错误关键点：归一化坐标 → 实际像素坐标
                    kp_x = int(point[0] * width)
                    kp_y = int(point[1] * height)

                    # 绘制错误关键点（圆形，直径6，红色填充）
                    circle_radius = 1
                    draw.ellipse(
                        xy=[
                            kp_x - circle_radius,
                            kp_y - circle_radius,
                            kp_x + circle_radius,
                            kp_y + circle_radius,
                        ],
                        fill=wrong_color,
                    )
                    wrong_label = "wrong_point"
                    wrong_label_x = kp_x + 20
                    wrong_label_y = kp_y - 20
                    draw.text(
                        xy=(wrong_label_x, wrong_label_y),
                        text=wrong_label,
                        font=errorFont,
                        fill=wrong_color,
                        stroke_width=2,
                    )
                except Exception as e:
                    LOGGER.error(f"绘制错误关键点失败：{point}，错误：{str(e)}")
                    continue

        # 保存可视化结果（
        try:
            image.save(outputFileName)
        except Exception as e:
            LOGGER.error(f"保存图片失败：{outputFileName}，错误：{str(e)}")


# endregion


# region ToYOLO
class YoloConverter(TxtConverter):
    def __init__(self, config: ConvertConfig):
        super().__init__(config)
        self.mode = MODE.DETECT

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
                draw.rectangle(xy=[x1, y1, x2, y2], outline=box_color, width=2)
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
    def __init__(self, config: ConvertConfig):
        super().__init__(config)
        self.mode = MODE.SEGMENT

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
        try:
            image = Image.open(imgPath).convert("RGB")
            draw = ImageDraw.Draw(image)
            width, height = image.size  # Pillow中是宽x高
            font = ImageFont.load_default()

            for line in yololines:
                parts = line.strip().split()
                if len(parts) < 7:
                    continue
                # 解析类别ID
                try:
                    class_id = int(parts[0])
                except ValueError:
                    continue
                # 解析多边形顶点 - 确保按顺序解析并转换为整数坐标
                points = []
                valid_points = True
                for i in range(1, len(parts), 2):
                    if i + 1 >= len(parts):
                        break
                    try:
                        x = float(parts[i]) * width
                        y = float(parts[i + 1]) * height
                        # 转换为整数坐标，与OpenCV保持一致
                        points.append((int(round(x)), int(round(y))))
                    except ValueError:
                        valid_points = False
                        break

                if not valid_points or len(points) < 3:
                    continue

                # 获取颜色
                if class_id in self.class_color_map:
                    box_color = tuple(
                        int(c * 255) for c in self.class_color_map[class_id]
                    )
                else:
                    box_color = (255, 0, 0)

                if points[0] != points[-1]:
                    # 确保按顺序连接并闭合
                    ordered_points = points.copy()
                    # 3. 手动闭合多边形（添加第一个点到末尾）
                    ordered_points.append(points[0])
                else:
                    ordered_points = points
                # 绘制多边形线条（使用line而非polygon函数，确保按顺序连接）
                draw.line(ordered_points, fill=box_color, width=2)
                # 绘制类别标签
                label = f"{list(self.class_mapping.keys())[class_id]}"
                # 标签位置
                label_pos = (points[0][0], points[0][1] - 10)

                # 获取文本尺寸
                text_bbox = draw.textbbox(label_pos, label, font=font)
                text_w = text_bbox[2] - text_bbox[0]
                text_h = text_bbox[3] - text_bbox[1]

                # 调整标签位置，确保不超出图像边界
                label_x, label_y = label_pos
                if label_y < 0:
                    label_y = points[0][1] + 10

                # 绘制标签背景
                draw.rectangle(
                    [
                        (label_x - 2, label_y - text_h - 2),
                        (label_x + text_w + 2, label_y + 2),
                    ],
                    fill=(255, 255, 255),
                    width=2,
                )

                # 绘制标签文字
                draw.text((label_x, label_y - text_h), label, font=font, fill=box_color)
            image.save(outputFileName)

        except Exception as ex:
            LOGGER.error(f"Yolo—Seg标签可视化失败：{ex}")
            return


# endregion


# region ToPPOCR
class PPOCRConverter(TxtConverter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = MODE.OCR

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


# endregion

# endregion
