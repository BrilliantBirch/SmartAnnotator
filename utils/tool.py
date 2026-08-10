from pathlib import Path
import shutil
import yaml
import json
import os
import sys
import random
from collections import Counter, defaultdict


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


def _read_label_classes(label_path):
    """
    读取YOLO格式标签文件，返回该图片包含的class_id集合（去重）

    Args:
        label_path: 标签文件路径

    Returns:
        set: 该图片包含的类别ID集合
    """
    classes = set()
    try:
        with open(label_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if parts:
                    classes.add(int(float(parts[0])))
    except Exception as e:
        print(f"  [警告] 读取标注失败 {label_path}: {e}")
    return classes


def _collect_class_ids(samples):
    """
    收集全数据集中出现的所有class_id，返回连续索引列表

    Args:
        samples: 样本列表，每个元素为(image_path, label_path)

    Returns:
        list: 从0到最大ID的连续索引列表
    """
    ids = set()
    for img, lab in samples:
        ids.update(_read_label_classes(lab))
    if not ids:
        return []
    max_id = max(ids)
    return list(range(0, max_id + 1))


def _count_instances(samples, class_ids):
    """
    统计每个类别的实例总数和包含该类的图片数

    Args:
        samples: 样本列表
        class_ids: 类别ID列表

    Returns:
        tuple: (实例计数器, 图片计数器, 多类别图片数)
    """
    inst_counter = Counter()
    img_counter = Counter()
    multi_label = 0

    for img, lab in samples:
        classes = _read_label_classes(lab)
        if len(classes) > 1:
            multi_label += 1
        for c in classes:
            inst_counter[c] += 1
            img_counter[c] += 1

    return inst_counter, img_counter, multi_label


def _stratified_split(samples, ratio, seed):
    """
    图片级分层采样，保证train/val/test各类别分布与原数据一致

    Args:
        samples: 样本列表，每个元素为(image_path, label_path)
        ratio: (train_ratio, val_ratio, test_ratio) 比例元组
        seed: 随机种子

    Returns:
        tuple: (train_samples, val_samples, test_samples)
    """
    rng = random.Random(seed)
    r0, r1, r2 = ratio

    # 按图片包含的类别组合分组（stratum）
    strata = defaultdict(list)
    for img, lab in samples:
        classes = tuple(sorted(_read_label_classes(lab)))
        strata[classes].append((img, lab))

    train, val, test = [], [], []

    for classes, group in strata.items():
        rng.shuffle(group)
        n = len(group)
        n_train = max(1, int(round(n * r0)))
        n_val = max(1, int(round(n * r1)))

        # 确保val/test至少可保留样本
        n_val = min(n_val, n - n_train)
        n_test = n - n_train - n_val
        if n_test < 0:
            n_test = 0
            n_val = n - n_train

        train.extend(group[:n_train])
        val.extend(group[n_train:n_train + n_val])
        test.extend(group[n_train + n_val:])

    return train, val, test


def _generate_split_report(train, val, test, class_ids, class_names=None, callback=None):
    """
    生成数据集划分的统计报告

    Args:
        train: 训练集样本列表
        val: 验证集样本列表
        test: 测试集样本列表
        class_ids: 类别ID列表
        class_names: 类别名称映射 {class_id: class_name}，用于报告显示；为None时使用class_{id}占位
        callback: 回调函数，用于输出报告

    Returns:
        tuple: (report_dict, report_text) 统计报告字典与格式化文本
    """
    report = {
        "total": len(train) + len(val) + len(test),
        "train": len(train),
        "val": len(val),
        "test": len(test),
        "class_stats": {}
    }

    # 统计各子集的类别分布
    for split_name, split_data in [("train", train), ("val", val), ("test", test)]:
        inst_counter, img_counter, multi_label = _count_instances(split_data, class_ids)
        report["class_stats"][split_name] = {
            "instances": dict(inst_counter),
            "images": dict(img_counter),
            "multi_label": multi_label
        }

    # 生成格式化报告文本
    lines = []
    lines.append("=== 数据集划分统计报告 ===")
    lines.append(f"总样本数: {report['total']}")
    lines.append(f"训练集: {report['train']} | 验证集: {report['val']} | 测试集: {report['test']}")
    lines.append(f"{'类别':<20}{'训练实例':>10}{'验证实例':>10}{'测试实例':>10}")

    for cid in class_ids:
        cname = class_names.get(cid, f"class_{cid}") if class_names else f"class_{cid}"
        train_inst = report["class_stats"]["train"]["instances"].get(cid, 0)
        val_inst = report["class_stats"]["val"]["instances"].get(cid, 0)
        test_inst = report["class_stats"]["test"]["instances"].get(cid, 0)
        lines.append(f"{cname:<20}{train_inst:>10}{val_inst:>10}{test_inst:>10}")

    report_text = "\n".join(lines)

    # 通过回调函数输出报告
    if callback:
        callback(report_text, 1.0)

    return report, report_text


def split_data(data_dir, split_ratios, random_seed=42, class_names=None, callback=None):
    """
    划分YOLO格式的数据集（采用分层抽样策略）

    Args:
        data_dir: 数据集根目录，包含images和labels文件夹
        split_ratios: 训练集、验证集、测试集的比例，如(0.7, 0.2, 0.1)
        random_seed: 随机种子，确保结果可重现，默认42
        class_names: 类别名称映射 {class_id: class_name}，用于报告显示；为None时使用class_{id}占位
        callback: 回调函数，签名callback(message, progress)，用于进度和报告输出

    Returns:
        dict: 包含划分统计信息的字典，失败时返回None
    """
    try:
        data_dir = Path(data_dir)
        images_dir = data_dir / "images"
        labels_dir = data_dir / "labels"

        # 验证目录存在
        if not images_dir.exists() or not labels_dir.exists():
            raise FileNotFoundError(f"数据集目录结构不完整，需要images和labels子目录")

        # 获取所有图片文件
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        image_files = {
            f.stem: f for f in images_dir.iterdir()
            if f.suffix.lower() in image_extensions
        }

        # 配对图片和标注文件
        samples = []
        for stem, img_path in image_files.items():
            label_path = labels_dir / f"{stem}.txt"
            if label_path.exists():
                samples.append((img_path, label_path))

        if not samples:
            raise ValueError("未找到有效的图片-标注配对，请检查目录结构")

        if callback:
            callback(f"发现 {len(samples)} 个有效样本", 0.1)

        # 收集类别信息
        class_ids = _collect_class_ids(samples)
        if not class_ids:
            raise ValueError("未在标注中找到任何有效类别")

        if callback:
            callback(f"检测到 {len(class_ids)} 个类别", 0.2)

        # 全数据集统计
        inst_counter, img_counter, multi_label = _count_instances(samples, class_ids)
        if callback:
            lines = [f"\n=== 全数据集统计（共 {sum(inst_counter.values())} 实例） ==="]
            lines.append(f"含多类别标注的图片数: {multi_label}")
            lines.append(f"{'类别':<20}{'实例数':>10}{'含该类图片':>12}")
            for cid in class_ids:
                cname = class_names.get(cid, f"class_{cid}") if class_names else f"class_{cid}"
                lines.append(f"{cname:<20}{inst_counter[cid]:>10}{img_counter[cid]:>12}")
            callback("\n".join(lines), 0.3)

        # 分层抽样划分
        if callback:
            callback("正在进行分层抽样划分...", 0.4)

        train_samples, val_samples, test_samples = _stratified_split(
            samples, split_ratios, random_seed
        )

        if callback:
            callback(f"划分完成: train={len(train_samples)}, val={len(val_samples)}, test={len(test_samples)}", 0.5)

        # 生成统计报告（必须在文件移动之前，此时标签文件仍在原位可读取）
        report, report_text = _generate_split_report(
            train_samples, val_samples, test_samples, class_ids,
            class_names=class_names, callback=callback
        )

        # 将报告写入输出目录（数据集根目录）
        report_path = data_dir / "split_report.txt"
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_text)
        except Exception as e:
            print(f"  [警告] 写入报告文件失败 {report_path}: {e}")

        # 将报告输出到日志（延迟导入 LOGGER，避免循环导入）
        try:
            from utils import LOGGER
            for line in report_text.splitlines():
                LOGGER.info(f"[数据集划分] {line}")
            LOGGER.info(f"[数据集划分] 报告文件已保存至: {report_path}")
        except Exception as e:
            print(f"  [警告] 日志输出失败: {e}")

        # 创建输出目录结构
        for split in ["train", "val", "test"]:
            (data_dir / split / "images").mkdir(parents=True, exist_ok=True)
            (data_dir / split / "labels").mkdir(parents=True, exist_ok=True)

        # 移动文件到对应目录
        def move_files(samples_list, split_name, start_progress, end_progress):
            total = len(samples_list)
            for idx, (img_path, lab_path) in enumerate(samples_list):
                if callback and idx % max(1, total // 10) == 0:
                    progress = start_progress + (end_progress - start_progress) * (idx / total)
                    callback(f"正在处理{split_name}数据集", progress)

                # 移动图片
                shutil.move(img_path, data_dir / split_name / "images" / img_path.name)
                # 移动标注文件
                shutil.move(lab_path, data_dir / split_name / "labels" / lab_path.name)

        move_files(train_samples, "train", 0.5, 0.7)
        move_files(val_samples, "val", 0.7, 0.85)
        move_files(test_samples, "test", 0.85, 0.95)

        # 删除源目录
        shutil.rmtree(images_dir)
        shutil.rmtree(labels_dir)

        if callback:
            callback(f"报告已保存至: {report_path}", 1.0)
            callback("数据集划分完成！", 1.0)

        return report

    except Exception as e:
        if callback:
            callback(f"数据集划分失败: {str(e)}", 0.0)
        return None


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
    data_dir: Path, classMapping, kpt, split_ratios=(0.7, 0.2, 0.1), random_seed=42, callback=None
):
    """
    导出YOLO格式的数据集配置文件

    Args:
        data_dir: 数据集根目录
        classMapping: 类别名称到索引的映射 {class_name: class_id}
        kpt: 关键点信息（可选）
        split_ratios: 训练集、验证集、测试集的比例，默认(0.7, 0.2, 0.1)
        random_seed: 随机种子，确保结果可重现，默认42
        callback: 回调函数，签名callback(message, progress)，用于进度和报告输出
    """
    # 翻转为 {class_id: class_name}，供报告显示真实类别名
    class_names = {v: k for k, v in classMapping.items()}
    report = split_data(
        data_dir, split_ratios,
        random_seed=random_seed,
        class_names=class_names,
        callback=callback,
    )
    if report is not None:
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