"""
Description：图像的采集、缩放还原操作
Author:LiFei
Date:2025/02/24
LastEdit:2025/03/24
LastEditBy:BaiBinnan
E-mail:baiBinnan@chuanfeng.com

update:
"""

import cv2
import numpy as np
from typing import Tuple


def resize_image(image: np.ndarray, target_shape=(640, 640)):
    """
        图像的裁剪、填充
    Args:
        image (np.ndarray): 原图
        target_shape (tuple, int):目标形状

    Returns:
        img (np.ndarray): 裁剪填充后的图像
    """
    origin_shape = image.shape[:2]
    scale = min(target_shape[0] / origin_shape[0], target_shape[1] / origin_shape[1])
    scale_shape = int(round(origin_shape[1] * scale)), int(
        round(origin_shape[0] * scale)
    )

    pad_w, pad_h = target_shape[1] - scale_shape[0], target_shape[0] - scale_shape[1]
    pad_w /= 2
    pad_h /= 2

    if origin_shape[::-1] != scale_shape:  # resize
        image = cv2.resize(image, scale_shape, interpolation=cv2.INTER_LINEAR)

    top, bottom = int(round(pad_h - 0.1)), int(round(pad_h + 0.1))
    left, right = int(round(pad_w - 0.1)), int(round(pad_w + 0.1))
    image = cv2.copyMakeBorder(
        image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )
    return image


def scale_boxes(
    img1_shape: Tuple[int],
    boxes: np.ndarray,
    img0_shape: Tuple[int],
    ratio_pad=None,
    padding=True,
    xywh=False,
):
    """
       检测框坐标还原到原图
    Args:
        img1_shape (tuple[int]): 检测图形状
        boxes (np.ndarray): 检测框
        img0_shape (tuple[int]): 原图形状
        ratio_pad (_type_, optional): 缩放比例
        padding (bool, optional): 填充. Defaults to True.
        xywh (bool, optional): 检测框是否是xywh格式. Defaults to False.

    Returns:
        _type_: _description_
    """
    if ratio_pad is None:  # calculate from img0_shape
        gain = min(
            img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1]
        )  # gain  = old / new
        pad = (
            round((img1_shape[1] - img0_shape[1] * gain) / 2 - 0.1),
            round((img1_shape[0] - img0_shape[0] * gain) / 2 - 0.1),
        )  # wh padding
    else:
        gain = ratio_pad[0][0]
        pad = ratio_pad[1]

    if padding:
        boxes[..., 0] -= pad[0]  # x padding
        boxes[..., 1] -= pad[1]  # y padding
        if not xywh:
            boxes[..., 2] -= pad[0]  # x padding
            boxes[..., 3] -= pad[1]  # y padding
    boxes[..., :4] /= gain
    return clip_boxes(boxes, img0_shape)


def clip_boxes(boxes: np.ndarray, shape: Tuple[int]):
    """
        检测框原图坐标裁剪，还原后的检测框大小不应超出原图并且归一化
    Args:
        boxes (np.ndarray): _de检测框scription_
        shape (tuple[int]): 原图形状

    Returns:
        np.ndarray: 还原后的检测框
    """
    boxes[..., [0, 2]] = boxes[..., [0, 2]].clip(0, shape[1]) / shape[1]  # x1, x2
    boxes[..., [1, 3]] = boxes[..., [1, 3]].clip(0, shape[0]) / shape[0]  # y1, y2
    return boxes


def scale_coords(
    img1_shape, coords, img0_shape, ratio_pad=None, normalize=False, padding=True
):
    if ratio_pad is None:  # calculate from img0_shape
        gain = min(
            img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1]
        )  # gain  = old / new
        pad = (img1_shape[1] - img0_shape[1] * gain) / 2, (
            img1_shape[0] - img0_shape[0] * gain
        ) / 2  # wh padding
    else:
        gain = ratio_pad[0][0]
        pad = ratio_pad[1]

    if padding:
        coords[..., 0] -= pad[0]  # x padding
        coords[..., 1] -= pad[1]  # y padding

    coords[..., 0] /= gain
    coords[..., 1] /= gain
    coords = clip_coords(coords, img0_shape)
    if normalize:
        coords[..., 0] /= img0_shape[1]  # width
        coords[..., 1] /= img0_shape[0]  # height
    coords[..., :2] = coords[..., :2]
    return coords


def clip_coords(coords, shape):
    coords[..., 0] = coords[..., 0].clip(0, shape[1])  # x
    coords[..., 1] = coords[..., 1].clip(0, shape[0])  # y
    return coords
