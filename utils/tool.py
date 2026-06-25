from pathlib import Path
import shutil
import yaml
import json
import os
import sys


# region 标注检查
def is_point_in_box(point, box):
    """检查点是否在框内"""
    x, y = point
    x1, y1 = box[0]
    x2, y2 = box[1]
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    return x1 <= x <= x2 and y1 <= y <= y2


def is_rect_inside(box1, box2):
    """检查box1是否在box2内"""
    # box1
    box_x1, box_y1 = box1[0]
    box_x2, box_y2 = box1[1]
    box_x1, box_x2 = min(box_x1, box_x2), max(box_x1, box_x2)
    box_y1, box_y2 = min(box_y1, box_y2), max(box_y1, box_y2)
    # box2
    box2_x1, box2_y1 = box2[0]
    box2_x2, box2_y2 = box2[1]
    box2_x1, box2_x2 = min(box2_x1, box2_x2), max(box2_x1, box2_x2)
    box2_y1, box2_y2 = min(box2_y1, box2_y2), max(box2_y1, box2_y2)
    return (
        box2_x1 <= box_x1 <= box2_x2
        and box2_x1 <= box_x2 <= box2_x2
        and box2_y1 <= box_y1 <= box2_y2
        and box2_y1 <= box_y2 <= box2_y2
    )


def detect_anomalies(annotations, threshold_min_area=1, threshold_max_area=1):
    """
    检查yolo格式标签是否在指定像素面积内

    Args:
        annotations (list[str]): 标注文本
        threshold_min_area (int, optional): 最小面积. Defaults to 1.
        threshold_max_area (int, optional): 最大面积. Defaults to 1.

    Returns:
        _type_: 错误的标注行
    """
    anomalies = []
    for annotation in annotations:
        _, x_center, y_center, w, h = annotation
        if x_center < 0 or x_center > 1 or y_center < 0 or y_center > 1:
            anomalies.append(annotation)
        area = w * h
        if area < threshold_min_area or area > threshold_max_area:
            anomalies.append(annotation)
    return anomalies


# endregion 标注检查


def classMapping(classes):
    """Convert txt files to categorized dictionaries
    Args:
        classes (str): predefine_labels.txt
    Returns:
        dict: categorized dictionaries
    """
    class_dict = dict()
    with open(classes, mode="r") as c:
        for index, line in enumerate(c):
            class_dict[line.strip()] = index
    return class_dict


# endregion 标注检查


# region 数据集分割与yaml文件生成
def split_data(data_dir, split_ratios, callback=None):
    """
    划分YOLO格式的数据集

    Args:
        data_dir: 数据集根目录，包含images和labels文件夹
        split_ratios: 训练集、验证集、测试集的比例
        random_seed: 随机种子，确保结果可重现
    """
    try:
        data_dir = Path(data_dir)
        # 路径设置
        images_dir = Path(data_dir) / "images"
        labels_dir = Path(data_dir) / "labels"

        # 获取所有图片文件
        image_extensions = [".jpg", ".jpeg", ".png", ".bmp"]
        image_files = [
            f for f in images_dir.iterdir() if f.suffix.lower() in image_extensions
        ]
        import random

        random.seed(42)
        # 随机打乱文件列表
        random.shuffle(image_files)

        # 计算各集合的数量
        total_count = len(image_files)
        train_count = int(total_count * split_ratios[0])
        val_count = int(total_count * split_ratios[1])
        test_count = total_count - train_count - val_count

        # 分割文件列表
        train_files = image_files[:train_count]
        val_files = image_files[train_count : train_count + val_count]
        test_files = image_files[train_count + val_count :]

        # 创建输出目录结构
        splits = ["train", "val", "test"]
        for split in splits:
            (data_dir / split).mkdir(parents=True, exist_ok=True)
            (data_dir / split / "images").mkdir(parents=True, exist_ok=True)
            (data_dir / split / "labels").mkdir(parents=True, exist_ok=True)

        # 复制文件到对应目录
        def move_files(files, split_name, callback=None):
            total = len(files)
            for idx, file in enumerate(files):
                if callback:
                    callback(f"正在处理{split_name}数据集", (idx + 1) / total)
                # 图片文件
                img_src = images_dir / file
                img_dst = data_dir / split_name / "images" / file.name
                shutil.move(img_src, img_dst)

                # 对应的标注文件
                label_file = file.with_suffix(".txt")
                label_src = labels_dir / label_file.name
                label_dst = (
                    data_dir / split_name / "labels" / label_file.name
                ).absolute()
                if label_src.exists():
                    shutil.move(label_src, label_dst)

        # 复制各集合文件
        move_files(train_files, "train", callback)
        move_files(val_files, "val", callback)
        move_files(test_files, "test", callback)
        # 删除源
        shutil.rmtree(images_dir)
        shutil.rmtree(labels_dir)

        return True
    except Exception as e:
        return False


def create_yaml(data_dir: Path, classMapping, kpt):
    """
    创建YOLO格式的数据集配置文件

    Args:
        data_dir: 数据集根目录
        class_dict: 类别名称到索引的映射
        split_ratios: 训练集、验证集、测试集的比例
    """
    classMapping = {v: k for k, v in classMapping.items()}
    if kpt:
        yaml_content = {
            "path": data_dir.absolute().as_posix(),  # dataset root dir
            "train": r"train/images",
            "val": r"val/images",
            "test": r"test/images",
            "kpt_shape": [len(kpt), 3],
            "names": classMapping,
        }
    else:
        yaml_content = {
            "path": data_dir.absolute().as_posix(),  # dataset root dir
            "train": r"train/images",
            "val": r"val/images",
            "test": r"test/images",
            "nc": len(classMapping),
            "names": classMapping,
        }
    with open(data_dir / "Dataset.yaml", "w") as file:
        yaml.dump(yaml_content, file, default_flow_style=False, sort_keys=False)


def export(
    data_dir: Path, classMapping, kpt, split_ratios=(0.7, 0.2, 0.1), callback=None
):
    """
    导出YOLO格式的数据集配置文件

    Args:
        data_dir: 数据集根目录
        class_dict: 类别名称到索引的映射
        split_ratios: 训练集、验证集、测试集的比例
    """
    if split_data(data_dir, split_ratios, callback):
        create_yaml(data_dir, classMapping, kpt)
    else:
        raise Exception("数据集分割失败")


# endregion 数据集分割与yaml文件生成


# region yolo文本行转换为labelme格式标签
def detect_to_labelme(lines, img_width, img_height, classMapping, *args):
    """
    将检测结果转换为Labelme格式的标签

    Args:
        line: 检测结果，格式为：class_id x_center y_center width height
        img_width: 图像宽度
        img_height: 图像高度
        classMapping: 类别映射

    Returns:
        dict: Labelme格式的标签，包含类别、框坐标和关键点坐标
    """
    annotations = []
    for line_no, line in enumerate(lines, 1):
        parts = line.strip().split()
        if len(parts) != 5:
            raise ValueError(f"标注文本格式第{line_no}行有误，{line}")
        class_id = int(float(parts[0]))
        x1 = int(float(parts[1]))
        y1 = int(float(parts[2]))
        x2 = int(float(parts[3]))
        y2 = int(float(parts[4]))

        annotations.append(
            {
                "class": classMapping[class_id],
                "points": [[x1, y1], [x2, y2]],
                "shape_type": "rectangle",
                "description": "",
            }
        )
    return annotations


def pose_to_labelme(lines, img_width, img_height, classMapping, *args):
    """
    将姿态检测结果转换为Labelme格式的标签

    Args:
        line: 姿态检测结果，格式为：class_id x_center y_center width height kpt...
        img_width: 图像宽度
        img_height: 图像高度
        classMapping: 类别映射

    Returns:
        dict: Labelme格式的标签，包含类别、框坐标和关键点坐标
    """
    annotations = []
    kpt_nums = args[0]
    kpt_stride = kpt_nums * 3
    expected_parts = 5 + kpt_stride

    for group_id, line in enumerate(lines):
        parts = line.strip().split()
        if len(parts) != expected_parts:
            continue

        class_id = int(float(parts[0]))
        class_name = classMapping[class_id].lower()
        x1 = int(float(parts[1]))
        y1 = int(float(parts[2]))
        x2 = int(float(parts[3]))
        y2 = int(float(parts[4]))

        annotations.append(
            {
                "class": class_name,
                "points": [[x1, y1], [x2, y2]],
                "shape_type": "rectangle",
                "description": "",
                "group_id": group_id,
            }
        )

        kpts = parts[5:]
        point_idx = 1
        for i in range(0, kpt_stride, 3):
            x, y, vis = kpts[i : i + 3]
            if int(vis) != 2:
                continue
            x_val = float(x)
            y_val = float(y)
            if x_val == y_val == 0 or x_val == img_width or y_val == img_height:
                continue
            annotations.append(
                {
                    "class": f"{class_name}_point{point_idx}",
                    "points": [[x_val, y_val]],
                    "shape_type": "point",
                    "description": vis,
                    "group_id": group_id,
                }
            )
            point_idx += 1
    return annotations


def segment_to_labelme(lines, img_width, img_height, classMapping, *args):
    """
    将分割检测结果转换为Labelme格式的标签

    Args:
        line: 分割检测结果，格式为：class_id x_center y_center width height ...
        img_width: 图像宽度
        img_height: 图像高度
        classMapping: 类别映射

    Returns:
        dict: Labelme格式的标签，包含类别、框坐标和关键点坐标
    """
    annotations = []
    mul_w = img_width
    mul_h = img_height

    for line_no, line in enumerate(lines, 1):
        parts = line.strip().split()
        if len(parts) <= 7:
            raise ValueError(f"标注文本格式第{line_no}行有误，多边形至少需要3个点{line}")

        class_id = int(parts[0])
        polygons = parts[1:]
        points = []

        for i in range(0, len(polygons), 2):
            x, y = polygons[i : i + 2]
            x = float(x) * mul_w
            y = float(y) * mul_h
            if not (x == y == 0 or x == mul_w or y == mul_h):
                points.append([x, y])

        if points:
            annotations.append(
                {
                    "class": classMapping[class_id].lower(),
                    "points": points,
                    "shape_type": "polygon",
                    "description": "",
                }
            )
    return annotations


# 模块级转换器映射，避免每次调用时重复创建字典
_CONVERTER_MAP = {
    0: detect_to_labelme,
    1: pose_to_labelme,
    2: segment_to_labelme,
}


def yolo_to_labelme(lines, img_width, img_height, classMapping, type, *args):
    """
    将YOLO格式的文本行转换为Labelme格式的标签

    Args:
        yolo_line: YOLO格式的文本行，格式为：class_id x_center y_center width height
        img_width: 图像宽度
        img_height: 图像高度
        classMapping: 类别映射
        type: 标注类型，bbox或kpt

    Returns:
        dict: Labelme格式的标签，包含类别、框坐标和关键点坐标
    """
    converter = _CONVERTER_MAP.get(type)
    if converter is None:
        raise ValueError(f"标注类型:{type}暂不支持")
    return converter(lines, img_width, img_height, classMapping, *args)


# endregion yolo文本行转换为labelme格式标签


# region 生成labelme格式文件
def generate_labelme_file(
    annotations, labelme_version, image_path, image_width, image_height, output_path
):
    """
    生成Labelme格式的文件
    Args:
        annotations: Labelme格式的标签
        labelme_version: labelme版本
        image_path: 图像路径
        output_path: 输出路径
        image_height: 图像高度
        image_width: 图像宽度
    """
    if not annotations:
        return
    data = {
        "version": labelme_version,
        "flags": {},
        "shapes": [
            {
                "label": a["class"],
                "points": a["points"],
                "group_id": a.get("group_id", None),
                "description": a["description"],
                "shape_type": a["shape_type"],
                "flags": {},
                "mask": None,
            }
            for a in annotations
        ],
        "imagePath": image_path,
        "imageData": None,
        "imageHeight": image_height,
        "imageWidth": image_width,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# endregion 生成labelme格式文件


def resource_path(relative_path):
    """获取打包后资源的绝对路径。
    参数:
        relative_path (str): 资源相对于项目根目录的路径，或直接在资源目录下的文件名。
    返回:
        str: 资源的绝对路径。
    """
    try:
        # 当程序被打包后，sys._MEIPASS 属性会被定义，指向临时解压目录
        base_path = sys._MEIPASS
    except AttributeError:
        # 如果没有定义（即在开发模式下），则使用当前文件的目录作为基础路径
        base_path = os.path.abspath(".")
    # 将基础路径与相对路径结合，创建完整的路径
    full_path = os.path.join(base_path, relative_path)
    return full_path


# region 图片处理
from PIL import Image


def rotate_90_image(imagePath: str, clockwise=True):
    """
    旋转图像
    Args:
        image: 图像
        angle: 旋转角度
    Returns:
        旋转后的图像
    """
    img = Image.open(imagePath)
    # 2. 旋转90°（用transpose实现，自动交换宽高）
    if clockwise:
        # 顺时针旋转90°（等价于transpose(Image.ROTATE_270)）
        rotated_img = img.transpose(Image.ROTATE_270)
    else:
        # 逆时针旋转90°（transpose(Image.ROTATE_90)）
        rotated_img = img.transpose(Image.ROTATE_90)
    return rotated_img


# endregion 图片处理