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
