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


def process_mask(protos, masks_in, bboxes, shape, upsample=False):
    """_summary_

    Args:
        protos (_type_): _description_
        masks_in (_type_): _description_
        bboxes (_type_): _description_
        shape (_type_): _description_
        upsample (bool, optional): _description_. Defaults to False.

    Returns:
        _type_: _description_
    """
    c, mh, mw = protos.shape  # CHW
    ih, iw = shape
    masks = (masks_in @ protos.astype(np.float32).reshape(c, -1)).reshape(
        -1, mh, mw
    )  # CHW

    width_ratio = mw / iw
    height_ratio = mh / ih

    downsampled_bboxes = bboxes.copy()
    downsampled_bboxes[:, 0] *= width_ratio
    downsampled_bboxes[:, 2] *= width_ratio
    downsampled_bboxes[:, 3] *= height_ratio
    downsampled_bboxes[:, 1] *= height_ratio

    masks = crop_mask(masks, downsampled_bboxes)  # CHW
    if upsample:
        masks = cv2.resize(
            masks.transpose(1, 2, 0), (iw, ih), interpolation=cv2.INTER_LINEAR
        )  # CHW
        # masks = F.interpolate(masks[None], shape, mode="bilinear", align_corners=False)[0]  # CHW
    return masks > 0.0


def crop_mask(masks, boxes):
    """
    Apply boxes to masks, returning cropped masks
    """
    _, h, w = masks.shape
    x1, y1, x2, y2 = np.split(boxes[:, :, None], 4, 1)  # x1 shape(n,1,1)
    r = np.arange(w, dtype=x1.dtype)[None, None, :]  # rows shape(1,1,w)
    c = np.arange(h, dtype=x1.dtype)[None, :, None]  # cols shape(1,h,1)

    return masks * ((r >= x1) * (r < x2) * (c >= y1) * (c < y2))


def scale_image(im1_shape, masks, im0_shape, ratio_pad=None):
    """
    Rescale masks from im1_shape to im0_shape
    """
    if ratio_pad is None:
        gain = min(im1_shape[0] / im0_shape[0], im1_shape[1] / im0_shape[1])
        pad = (im1_shape[1] - im0_shape[1] * gain) / 2, (
            im1_shape[0] - im0_shape[0] * gain
        ) / 2
    else:
        pad = ratio_pad[1]
    top, left = int(pad[1]), int(pad[0])  # y, x
    bottom, right = int(im1_shape[0] - pad[1]), int(im1_shape[1] - pad[0])

    if len(masks.shape) < 2:
        raise ValueError(
            f'"len of masks shape" should be 2 or 3, but got {len(masks.shape)}'
        )
    masks = masks[top:bottom, left:right]
    masks = cv2.resize(
        masks.astype(np.uint8),
        (im0_shape[1], im0_shape[0]),
        interpolation=cv2.INTER_LINEAR,
    )

    if len(masks.shape) == 2:
        masks = masks[:, :, None]
    masks = np.transpose(masks, (2, 0, 1))
    return masks
