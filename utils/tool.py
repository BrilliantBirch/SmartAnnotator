from pathlib import Path
import shutil
import yaml


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
