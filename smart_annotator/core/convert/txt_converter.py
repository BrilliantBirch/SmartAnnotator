# -*- coding: utf-8 -*-
"""
labelme 文件转到 txt 格式的标签

功能说明：
1. 支持灵活的关键点匹配策略
2. 处理关键点遮挡和缺失情况
3. 增强可视化标注效果
4. 支持 labelme 的 json 格式转换为 yolo、yolo_pose、ppocr 等模型所需的 txt 格式

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-02 run() 图片匹配改为按文件名主干索引（兼容 label/image/
      dataset 目录层级，原实现要求 JSON 与图片同目录同名）
更新: 2026-09-04 复制图片前校验源与目标是否同一文件（输出目录与输入目录
      一致时 shutil.copy 抛 SameFileError 导致任务中断），复用 _safe_copy
更新: 2026-09-10 PPOCRConverter 重写为 LabelMe→PaddleOCR 标注导出：
      输出 images/ + det_gt.txt + rec_images/ + rec_gt.txt + dict.txt
      （+ visualize/），自带 run 编排（不走基类 YOLO 行语义），裁剪
      复用 core.annotate.vision.ocr.get_rotate_crop_image，可视化改用
      PIL 中文多边形描边与文本绘制
"""

from smart_annotator.config import RANDOM_SEED, ConvertConfig, MODE
from smart_annotator.utils import LOGGER, COLORS, is_point_in_box, export
from smart_annotator.core.convert.json_converter import _safe_copy
from smart_annotator.core.annotate.vision.ocr import (
    get_rotate_crop_image,
    DBPostProcess,
)


from typing import List, Tuple, Set
from pathlib import Path
import random
import json
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# region labelme2txt


class TxtConverter:
    """LabelMe JSON → YOLO TXT 转换器基类。"""

    def __init__(self, config: ConvertConfig):
        """初始化转换器。

        Args:
            config: 转换配置对象。
        """
        self.imageFiles = [Path(imageFile) for imageFile in config.image_files]
        self.annotationFiles = [
            Path(annotationFile) for annotationFile in config.annotation_files
        ]
        self.output = Path(config.output_dir)
        self.classes = config.classes
        self.kpt = config.kpt
        self.splitRatio = (config.train_ratio, config.val_ratio, config.test_ratio)
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
        self.visualized = config.visualize
        self.export = config.export
        random.seed(RANDOM_SEED)
        selected_colors = random.sample(list(COLORS), len(self.classes))
        self.class_color_map = {i: color for i, color in enumerate(selected_colors)}

    def process(self, path: str) -> Tuple[List[str], bool, Set]:
        """处理单个标注文件（子类实现）。"""
        pass

    def visualize(
        self, imgPath: str, outputFileName: str, yololines: List[str], infos: Set[int]
    ):
        """可视化标注结果（子类实现）。"""
        LOGGER.warning(f"当前转换器暂不支持可视化")

    def run(self, progress_callback=None):
        """执行转换任务。

        Args:
            progress_callback: 进度回调函数，签名 callback(desc, progress) -> bool。

        Returns:
            任务是否成功完成。
        """
        try:
            convertImgFolder = self.output / "images"
            convertImgFolder.mkdir(parents=True, exist_ok=True)
            convertLabelFolder = self.output / "labels"
            convertLabelFolder.mkdir(parents=True, exist_ok=True)
            if self.visualized:
                visualizeFolder = self.output / "visualized"
                visualizeFolder.mkdir(parents=True, exist_ok=True)
            empty_files = []
            failed_files = []
            # 图片按文件名主干建索引（兼容不同扩展名与目录层级：
            # labels/images 兄弟目录、dataset 子目录、平铺等）
            image_map = {Path(img).stem: img for img in self.imageFiles}
            # 开始转换
            total = len(self.annotationFiles)
            for id, json_path in enumerate(self.annotationFiles):
                if not progress_callback("标签转换中", (id + 1) / total):
                    return False
                json_path = Path(json_path)
                # 根据标签文件名主干获取图片路径
                img_path = image_map.get(json_path.stem)
                if img_path is not None:
                    # 标记为已处理
                    self.imageFiles.remove(img_path)
                    del image_map[json_path.stem]
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
                        _safe_copy(img_path, destination)
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
                    if not progress_callback(
                        "背景图片转换中", (id + 1) / background_total
                    ):
                        return False
                    _safe_copy(imageFile, backgroundFolder_img / imageFile.name)
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
                    _safe_copy(json_path, failedFolder / json_path.name)
                    _safe_copy(img_path, failedFolder / img_path.name)
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
                    progress_callback(desc, process)

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
    """LabelMe JSON → YOLO-Pose TXT 转换器。"""

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
        """处理单个标注文件。"""
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
        """可视化姿态标注结果。

        Args:
            imgPath: 输入图片路径（支持中文）。
            outputFileName: 输出图片路径（支持中文）。
            annotations: YOLO 格式标注列表（每行：class_id + 框坐标 + 关键点坐标）。
            infos: 错误关键点坐标集合（归一化坐标）。
        """

        if not annotations or len(annotations) == 0:
            if not infos or len(infos) == 0:
                return
        try:
            # 转为 RGB 通道（统一格式，避免 RGBA/灰度图问题）
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

                    # 绘制类别标签（对应 OpenCV cv2.putText）
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

                    # 解析并绘制关键点（每个关键点含 x,y,可见性，共3个值）
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
                                fill=point_color,  # 圆形填充颜色
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

        # 保存可视化结果
        try:
            image.save(outputFileName)
        except Exception as e:
            LOGGER.error(f"保存图片失败：{outputFileName}，错误：{str(e)}")


# endregion


# region ToYOLO
class YoloConverter(TxtConverter):
    """LabelMe JSON → YOLO DET TXT 转换器。"""

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
        """可视化标注结果。"""
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
    """LabelMe JSON → YOLO-Seg TXT 转换器。"""

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
        """可视化多边形标注结果。"""
        try:
            image = Image.open(imgPath).convert("RGB")
            draw = ImageDraw.Draw(image)
            width, height = image.size  # Pillow 中是宽x高
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
                        # 转换为整数坐标，与 OpenCV 保持一致
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
                    # 手动闭合多边形（添加第一个点到末尾）
                    ordered_points.append(points[0])
                else:
                    ordered_points = points
                # 绘制多边形线条（使用 line 而非 polygon 函数，确保按顺序连接）
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
    """LabelMe JSON → PaddleOCR 标注格式导出（OCR 任务专用）。

    输出目录结构（不走基类 run 的 YOLO 行语义，自带编排）：
        {output}/images/        复制源图（文件名主干匹配基类 run 的 path/imagePath 链路）
        {output}/det_gt.txt     检测标注：每行 {图片相对路径}\t{JSON数组}
        {output}/rec_gt.txt     识别标注：每行 {裁剪图相对路径}\t{transcription}
        {output}/rec_images/    裁剪文本行图（{stem}_{序号}.jpg）
        {output}/dict.txt       字符字典：字符首次出现顺序去重 + use_space_char 尾追加空格行
        {output}/visualize/     可视化结果（config.visualize 时）

    PaddleOCR det 标注规范：
        数组元素 {"transcription": 文本, "points": [[x1,y1],...,[x4,y4]], "difficult": bool}；
        无文本（description 空）的框保留 det（transcription 空串）跳过 rec；
        空标注文件（无有效框）不写该图行（记录日志），与现有链路口径一致。

    Args:
        config: 转换配置对象。
    """

    def __init__(self, config: ConvertConfig):
        """初始化转换器（保存 OCR 专属开关）。

        Args:
            config: 转换配置对象（ocr_gen_rec/ocr_use_space_char 仅 OCR 使用）。
        """
        super().__init__(config)
        self.mode = MODE.OCR
        # OCR 专属开关：是否生成 rec 识别数据集 / 字典尾是否追加空格字符
        self.gen_rec = config.ocr_gen_rec
        self.use_space_char = config.ocr_use_space_char

    def _process_shapes(self, path: Path) -> List[dict]:
        """解析单个 JSON 的 shapes，转 PaddleOCR det 元素列表。

        polygon/quadrilateral 4 点直取（其余点数经最小外接四边形归一）；
        rectangle 两点转四角点（兼容 PPOCRLabel 四角点矩形）。
        兼容老 JSON 无 difficult 字段（取 False）。无文本的框保留 det 但
        transcription 为空串（由 run 决定是否参与 rec/dict）。

        Args:
            path: JSON 文件路径。

        Returns:
            PaddleOCR det 元素列表（每个含 transcription/points/difficult）；
            解析失败返回空列表。
        """
        ppocr_annotations = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as ex:
            LOGGER.error(f"PPOCR 导出解析 JSON 失败 {path}: {ex}")
            return ppocr_annotations
        for shape in data.get("shapes", []):
            points = shape.get("points") or []
            shape_type = shape.get("shape_type", "")
            # 多边形/四边形：4 点直接取；其余点数经最小外接四边形归一为 4 点
            # （PaddleOCR det 格式要求严格四点框）
            if shape_type in ("polygon", "quadrilateral"):
                if len(points) < 3:
                    continue
                if len(points) == 4:
                    ppocr_points = [[round(float(p[0])), round(float(p[1]))] for p in points]
                else:
                    quad = self._min_area_quad(points)
                    if quad is None:
                        LOGGER.warning(
                            f"{path} 多边形点数({len(points)})无法归一为四点框，跳过"
                        )
                        continue
                    ppocr_points = quad
            # 矩形：两点转四角点（轴对齐，取全部顶点包围盒，兼容 PPOCRLabel 四角点矩形）
            elif shape_type == "rectangle":
                if len(points) < 2:
                    continue
                x_coords = [float(p[0]) for p in points]
                y_coords = [float(p[1]) for p in points]
                left = round(min(x_coords))
                right = round(max(x_coords))
                top = round(min(y_coords))
                bottom = round(max(y_coords))
                ppocr_points = [
                    [left, top],
                    [right, top],
                    [right, bottom],
                    [left, bottom],
                ]
            else:
                continue
            # transcription：取 description，缺失/None 视为空串
            text = shape.get("description") or ""
            text = text.strip()
            difficult = bool(shape.get("difficult", False))
            ppocr_annotations.append(
                {
                    "transcription": text,
                    "points": ppocr_points,
                    "difficult": difficult,
                }
            )
        return ppocr_annotations

    @staticmethod
    def _min_area_quad(points) -> List[List[int]]:
        """任意多边形点集归一为 左上/右上/右下/左下 顺序的四点框。

        复用 DBPostProcess._get_mini_boxes（最小外接四边形 + 顶点排序），
        用于把非 4 点的多边形归一为 PaddleOCR det 要求的严格四点框。

        Args:
            points: 点列表 [[x, y], ...]（点数 >= 3）。

        Returns:
            四点整数坐标列表；归一失败（退化/异常）返回 None。
        """
        try:
            contour = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
            box, _ = DBPostProcess._get_mini_boxes(contour)
            return [[int(round(float(p[0]))), int(round(float(p[1])))] for p in box]
        except Exception:
            return None

    def _load_font(self, size: int = 18):
        """加载中文 TrueType 字体，失败回退 PIL 默认字体。

        参考 YoloPoseConverter.visualize 的 PIL 用法；中文字体优先
        simhei.ttf / msyh.ttc，失败时回退 ImageFont.load_default()。

        Args:
            size: 字体字号（磅）。

        Returns:
            PIL ImageFont 实例。
        """
        for name in ("simhei.ttf", "msyh.ttc", "msyhbd.ttc", "simsun.ttc"):
            try:
                return ImageFont.truetype(name, size=size)
            except Exception:
                continue
        LOGGER.warning("未找到中文字体，可视化文本回退默认字体（中文可能乱码）")
        return ImageFont.load_default()

    def _visualize(self, img_path: Path, out_path: Path, items: List[dict]) -> None:
        """可视化 PaddleOCR det 标注（红色 2px 多边形描边 + transcription 文本）。

        Args:
            img_path: 源图路径。
            out_path: 输出图路径。
            items: det 元素列表（含 points/transcription）。
        """
        try:
            image = Image.open(img_path).convert("RGB")
            draw = ImageDraw.Draw(image)
            font = self._load_font(18)
            for it in items:
                pts = [(int(p[0]), int(p[1])) for p in it["points"]]
                if len(pts) < 2:
                    continue
                # 多边形描边（红色 2px）
                if pts[0] != pts[-1]:
                    pts_closed = pts + [pts[0]]
                else:
                    pts_closed = pts
                draw.line(pts_closed, fill=(255, 0, 0), width=2)
                # transcription 文本（框顶部）
                text = it.get("transcription", "")
                if text:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    tx = min(xs)
                    ty = max(0, min(ys) - 20)
                    draw.text((tx, ty), text, font=font, fill=(255, 0, 0))
            image.save(out_path)
        except Exception as ex:
            LOGGER.error(f"PPOCR 可视化失败 {img_path}: {ex}")

    def run(self, progress_callback=None) -> bool:
        """执行 LabelMe→PaddleOCR 标注导出（不走基类 YOLO 行语义）。

        Args:
            progress_callback: 进度回调 callback(desc, progress) -> bool；
                返回 False 时中断返回 False。

        Returns:
            任务是否成功完成。
        """
        try:
            # 输出目录结构创建
            img_folder = self.output / "images"
            img_folder.mkdir(parents=True, exist_ok=True)
            rec_folder = self.output / "rec_images"
            if self.gen_rec:
                rec_folder.mkdir(parents=True, exist_ok=True)
            vis_folder = None
            if self.visualized:
                vis_folder = self.output / "visualize"
                vis_folder.mkdir(parents=True, exist_ok=True)
            # det_gt.txt / rec_gt.txt / dict.txt 累积写入
            det_lines: List[str] = []
            rec_lines: List[str] = []
            dict_chars: List[str] = []  # 字符首次出现顺序（未去重前累积）
            seen_chars: Set[str] = set()
            # 图片按文件名主干建索引（与基类 run 一致）
            image_map = {Path(img).stem: img for img in self.imageFiles}
            total = len(self.annotationFiles)
            for idx, json_path in enumerate(self.annotationFiles):
                if not progress_callback("PPOCR 标注导出中", (idx + 1) / total):
                    return False
                json_path = Path(json_path)
                img_path = image_map.get(json_path.stem)
                if img_path is None:
                    LOGGER.warning(f"{json_path} 未找到对应图片，跳过")
                    continue
                # 解析 shapes
                items = self._process_shapes(json_path)
                if not items:
                    LOGGER.info(f"{json_path} 无有效 OCR 框，跳过 det 行")
                    continue
                # 复制源图到 images/
                dst_img = img_folder / img_path.name
                try:
                    _safe_copy(Path(img_path), dst_img)
                except Exception as e:
                    LOGGER.error(f"复制图片 {img_path} 失败: {e}")
                # det_gt 行：相对路径（正斜杠）+ JSON 数组
                rel_path = f"images/{img_path.name}"
                det_lines.append(f"{rel_path}\t{json.dumps(items, ensure_ascii=False)}")
                # rec 数据集：裁剪文本行图 + rec_gt 行（无文本跳过）
                if self.gen_rec:
                    # 读图（cv2.imdecode 支持中文路径）
                    img_data = np.fromfile(str(img_path), dtype=np.uint8)
                    img = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
                    if img is None:
                        LOGGER.warning(f"读取图片失败 {img_path}，跳过 rec 裁剪")
                    else:
                        for seq, it in enumerate(items):
                            text = it.get("transcription", "")
                            if not text:
                                # 无文本框跳过 rec（保留 det）
                                continue
                            pts = np.array(it["points"], dtype=np.float32)
                            try:
                                crop = get_rotate_crop_image(img, pts)
                            except Exception as ex:
                                LOGGER.warning(
                                    f"裁剪文本行失败 {json_path.name}#{seq}: {ex}"
                                )
                                continue
                            rec_name = f"{json_path.stem}_{seq}.jpg"
                            rec_dst = rec_folder / rec_name
                            # cv2.imwrite 不支持中文路径，用 imencode 写盘
                            ok, buf = cv2.imencode(".jpg", crop)
                            if ok:
                                buf.tofile(str(rec_dst))
                            else:
                                LOGGER.warning(f"保存裁剪图失败 {rec_dst}")
                                continue
                            rec_lines.append(f"rec_images/{rec_name}\t{text}")
                            # 字典字符累积（首次出现顺序去重）
                            for ch in text:
                                if ch not in seen_chars:
                                    seen_chars.add(ch)
                                    dict_chars.append(ch)
                else:
                    # 不生成 rec 时仍按全部 det transcription 累积字典字符
                    for it in items:
                        for ch in it.get("transcription", ""):
                            if ch not in seen_chars:
                                seen_chars.add(ch)
                                dict_chars.append(ch)
                # 可视化
                if self.visualized and vis_folder is not None:
                    self._visualize(
                        Path(img_path), vis_folder / img_path.name, items
                    )
            # 写 det_gt.txt
            with open(self.output / "det_gt.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(det_lines))
            # 写 rec_gt.txt（ocr_gen_rec 时）
            if self.gen_rec:
                with open(self.output / "rec_gt.txt", "w", encoding="utf-8") as f:
                    f.write("\n".join(rec_lines))
            # 写 dict.txt（字符首次出现顺序去重 + use_space_char 尾追加空格行）
            dict_lines = list(dict_chars)
            if self.use_space_char:
                dict_lines.append(" ")
            with open(self.output / "dict.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(dict_lines))
            LOGGER.info(
                f"PPOCR 导出完成: det={len(det_lines)} 行, rec={len(rec_lines)} 行, "
                f"dict={len(dict_chars)} 字符"
            )
            return True
        except Exception as ex:
            LOGGER.error(f"PPOCR 标注导出错误：{str(ex)}")
            return False


# endregion
