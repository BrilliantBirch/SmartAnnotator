"""
Description：YOLO预测器
Author:BaiBinnan
Date:2025/02/17
LastEdit:2025/09/05
LastEditBy:BaiBinnan
E-mail:baiBinnan@chuanfeng.com
"""

import numpy as np
import ast
import cv2
from pathlib import Path
from ..utils import (
    resize_image,
    get_cpu_info,
    get_gpu_info,
    get_total_memory,
    scale_boxes,
    scale_coords,
    process_mask,
    scale_image,
)
from .onnxbackend import ONNXInfer
from cfg import LOGGER, AnnotateConfig, DEVICE


class BasePredictor:
    def __init__(self, config: AnnotateConfig):
        self.model_path = Path(config.modelPath)
        self.device = config.device
        self.conf = config.bboxConf
        self.iou = config.nms
        self.load_model()

    def load_model(self):
        pass

    def unload_model(self):
        self.is_warmup = False

    def predict(self, input_data):
        pass

    def postprocess(self, predictions, pred_shape, orig_shapes):
        pass

    def preprocess(self, images):
        img_resized = [resize_image(x, self.imgSize) for x in images]
        img = np.stack(img_resized)
        img = img[..., ::-1].transpose((0, 3, 1, 2))
        img = np.ascontiguousarray(img)
        img = img.astype(np.float16) if self.fp16 else img.astype(np.float32)
        img /= 255
        return img

    def warm_up(self):
        """
        模型预热
        Args:
            batch (int, optional): 批次大小. Defaults to 1.
        """
        imgSize = self.imgSize
        img = [np.ones((imgSize[0], imgSize[1], 3))]
        for _ in range(self.batch - 1):
            img.extend(img)
        for _ in range(5):
            self.predict(img)


# region 目标检测
class DetectionPredictor(BasePredictor):
    """目标检测的检测器

    Args:
        BasePredictor (_type_): _description_
    """

    def __init__(self, config: AnnotateConfig):
        super().__init__(config=config)

    def load_model(self):
        if self.device == DEVICE.CPU:
            if get_cpu_info() == -1 or get_total_memory() == -1:
                LOGGER.warning("找不到cpu信息")
            LOGGER.info("加载onnx模型")

            if self.model_path.suffix == ".onnx":
                try:
                    self.model = ONNXInfer(self.model_path, device=self.device)
                except Exception as ex:
                    LOGGER.error(f"onnx模型加载失败{str(ex)}")
                    return False
            else:
                LOGGER.error(
                    f"模型文件类型错误{self.model_path},CPU仅支持用onnx模型推理,请检查"
                )
                return False

        elif self.device == DEVICE.GPU:
            from .tensorrtbackend import TensorRTInfer

            if get_gpu_info() == -1:
                LOGGER.warning("找不到显卡信息,请检查是否安装了显卡驱动")
                return False

            if self.model_path.suffix == ".onnx":
                LOGGER.warning("GPU使用tensorrt推理,尝试寻找engine模型")
                engine_path = self.model_path.with_suffix(".engine")
                if engine_path.exists():
                    try:
                        self.model = TensorRTInfer(engine_path)
                        self.model_path = engine_path
                    except Exception as ex:
                        LOGGER.error(f"engine模型加载失败{str(ex)}")
                        return False
                else:
                    LOGGER.warning("未找到engine模型,尝试转换")
                    try:
                        from .onnx2engine import Onnx2Engine

                        LOGGER.info(
                            f"开始转换{self.model_path},请耐心等待，根据模型大小需要10-30mins,请勿关闭程序"
                        )
                        onnx2engine = Onnx2Engine(onnxfile=self.model_path)
                        engine_path = onnx2engine.run()
                        self.model_path = engine_path
                        self.model = TensorRTInfer(engine_path)
                        LOGGER.info(f"转换完成,模型已保存到{engine_path}")
                    except Exception as ex:
                        LOGGER.error(f"模型转换失败{str(ex)}")
                        return False

            elif self.model_path.suffix == ".engine":

                try:
                    self.model = TensorRTInfer(self.model_path)
                except Exception as ex:
                    LOGGER.error(f"engine模型加载失败{str(ex)}")
                    return False

        # 尝试从模型元数据中获取
        if self.model.metadata:
            self.batch = int(ast.literal_eval(self.model.metadata.get("batch")))
            self.imgSize = tuple(ast.literal_eval(self.model.metadata.get("imgsz")))
            # args = ast.literal_eval(self.model.metadata.get("args", None))
            # self.fp16 = args.get("half", False)
            self.fp16 = self.model.metadata.get("fp16", False)
            class_mapping = self.model.metadata.get("names")
            if isinstance(class_mapping, str):
                class_mapping = ast.literal_eval(class_mapping)
                if isinstance(class_mapping, dict):
                    class_mapping = {
                        int(key): value for key, value in class_mapping.items()
                    }
                else:
                    LOGGER.warning("模型元数据中类别映射格式错误")
                    return False

        self.class_mapping = class_mapping

        return True

    def postprocess(self, predictions, pred_shape, orig_shapes):
        outputs = np.transpose(predictions, (0, 2, 1))
        bboxes, scores = np.split(
            outputs,
            [
                4,
            ],
            2,
        )
        idxs = scores.max(axis=2) > self.conf
        predict_results = []
        for i in range(len(predictions)):
            idx = idxs[i]
            score, bbox = scores[i][idx], bboxes[i][idx]
            j = score.argmax(1)
            confidence = np.max(score, axis=1)
            cxcy, wh = np.split(
                bbox,
                [
                    2,
                ],
                -1,
            )
            cv_box = np.concatenate([cxcy - 0.5 * wh, wh], -1)
            nms_idx = cv2.dnn.NMSBoxesBatched(
                cv_box, confidence, j, self.conf, self.iou
            )
            cv_box, confidence, j = cv_box[nms_idx], confidence[nms_idx], j[nms_idx]
            # xyxy
            cv_box[:, 2:] += cv_box[:, :2]
            cv_box = scale_boxes(pred_shape, cv_box, orig_shapes[i]).round()
            predict_results.append({"bboxs": cv_box, "scores": confidence, "labels": j})
        return predict_results

    def predict(self, input_data):
        # 预处理阶段
        preprocess_input = self.preprocess(input_data)
        predictions = self.model.predict(preprocess_input)[0]
        orig_shapes = [x.shape[:2] for x in input_data]
        results = self.postprocess(predictions, self.model.imgsz, orig_shapes)
        return results


# endregion 目标检测


# region 分割检测
class SegmentationPredictor(DetectionPredictor):
    def __init__(self, config: AnnotateConfig):
        super().__init__(config)

    def load_model(self):
        super().load_model()
        try:
            self.class_num = len(self.class_mapping)
            return True
        except Exception as ex:
            LOGGER.error(f"模型元数据中关键点形状获取失败{str(ex)}")
            return False

    def postprocess(self, predictions, pred_shape, orig_shapes):
        if self.model_path.suffix == ".onnx":
            proto, outputs = predictions[1], predictions[0]
        elif self.model_path.suffix == ".engine":
            proto, outputs = predictions[0], predictions[1]
        outputs = np.transpose(outputs, (0, 2, 1))
        bboxes, scores, maskconf = np.split(outputs, [4, 4 + self.class_num], 2)
        idxs = scores.max(axis=2) > self.conf

        predict_results = []

        for i in range(len(predictions[1])):
            idx = idxs[i]
            score, bbox, mask_conf = scores[i][idx], bboxes[i][idx], maskconf[i][idx]
            if not len(bbox):
                predict_results.append(
                    {"bboxs": None, "scores": None, "labels": None, "masks": None}
                )
                continue
            j = score.argmax(1)
            conf = np.max(score, axis=1)
            cxcy, wh = np.split(
                bbox,
                [
                    2,
                ],
                -1,
            )
            cv_box = np.concatenate([cxcy - 0.5 * wh, wh], -1)
            nms_idx = cv2.dnn.NMSBoxesBatched(cv_box, conf, j, self.conf, self.iou)
            cv_box, conf, j, mask_conf = (
                cv_box[nms_idx],
                conf[nms_idx],
                j[nms_idx],
                mask_conf[nms_idx],
            )
            # xyxy
            cv_box[:, 2:] += cv_box[:, :2]

            masks = process_mask(
                proto[i], mask_conf, cv_box, pred_shape, upsample=True
            )  # HWC

            masks = scale_image(pred_shape, masks, orig_shapes[i], ratio_pad=None)
            boundary_points = []
            for mask in masks:
                # 将掩码转换为uint8类型并寻找轮廓
                contours, _ = cv2.findContours(
                    mask.astype(np.uint8),
                    cv2.RETR_EXTERNAL,  # 只检测外轮廓
                    cv2.CHAIN_APPROX_SIMPLE,  # 压缩冗余线段
                )
                if contours:
                    # 取面积最大的轮廓
                    max_contour = max(contours, key=cv2.contourArea)

                    # ====== 新增：轮廓点精简 ======
                    # 使用Douglas-Peucker算法近似轮廓（保留关键节点）
                    epsilon = 0.005 * cv2.arcLength(
                        max_contour, closed=True
                    )  # 可调整阈值控制点数
                    approx_contour = cv2.approxPolyDP(max_contour, epsilon, closed=True)

                    # ====== 新增：归一化处理 ======
                    # 获取原始图像尺寸 (h, w)
                    h, w = orig_shapes[i][0], orig_shapes[i][1]
                    # 转换为归一化坐标 (x/w, y/h) 并保留6位小数
                    contour_points = approx_contour.squeeze().tolist()
                    normalized_points = []
                    for p in contour_points:
                        if isinstance(p, (list, np.ndarray)) and len(p) == 2:
                            nx = round(p[0] / w, 6)
                            ny = round(p[1] / h, 6)
                            normalized_points.extend(
                                [nx, ny]
                            )  # 展平为 [x1,y1,x2,y2,...]

                    boundary_points.append(normalized_points)
                else:
                    boundary_points.append([])
            cv_box = scale_boxes(pred_shape, cv_box, orig_shapes[i])

            predict_results.append(
                {
                    "bboxs": cv_box,
                    "scores": conf,
                    "labels": j,
                    # "masks": masks,
                    "boundary_points": boundary_points,
                }
            )

        return predict_results

    def predict(self, input_data):
        # 预处理阶段
        preprocess_input = self.preprocess(input_data)
        predictions = self.model.predict(preprocess_input)
        orig_shapes = [x.shape[:2] for x in input_data]
        results = self.postprocess(predictions, self.model.imgsz, orig_shapes)
        return results


# endregion 分割检测


# region 关键点检测
class PoseDetectionPredictor(DetectionPredictor):
    def __init__(self, config: AnnotateConfig):
        super().__init__(config)

    def load_model(self):
        super().load_model()
        try:
            self.class_num = len(self.class_mapping)
            self.kpt_shape = tuple(
                ast.literal_eval(self.model.metadata.get("kpt_shape"))
            )
            return True
        except Exception as ex:
            LOGGER.error(f"模型元数据中关键点形状获取失败{str(ex)}")
            return False

    def postprocess(self, predictions, pred_shape, orig_shapes):
        # 检查模型是否有end2end属性且为True
        predict_results = []

        if self.model.metadata.get("end2end", False) == "True":
            bboxes, scores, clses, kpts = np.split(predictions, [4, 5, 6], 2)
            idxs = scores.max(axis=2) > self.conf
            for i in range(len(predictions)):
                idx = idxs[i]
                cls, score, bbox, kpt = (
                    clses[i][idx],
                    scores[i][idx],
                    bboxes[i][idx],
                    kpts[i][idx],
                )
                cls = cls.flatten().astype(int).tolist()
                cv_box = scale_boxes(pred_shape, bbox, orig_shapes[i])
                kpt = kpt.reshape(len(kpt), *self.kpt_shape)
                kpt = scale_coords(pred_shape, kpt, orig_shapes[i])
                predict_results.append(
                    {"bboxs": cv_box, "scores": score, "labels": cls, "keypoints": kpt}
                )
        else:
            outputs = np.transpose(predictions, (0, 2, 1))
            bboxes, scores, kpts = np.split(outputs, [4, 4 + self.class_num], 2)
            idxs = scores.max(axis=2) > self.conf
            for i in range(len(predictions)):
                idx = idxs[i]
                score, bbox, kpt = scores[i][idx], bboxes[i][idx], kpts[i][idx]
                j = score.argmax(1)
                conf = np.max(score, axis=1)
                cxcy, wh = np.split(
                    bbox,
                    [
                        2,
                    ],
                    -1,
                )
                cv_box = np.concatenate([cxcy - 0.5 * wh, wh], -1)
                nms_idx = cv2.dnn.NMSBoxesBatched(cv_box, conf, j, self.conf, self.iou)
                cv_box, conf, j, kpt = (
                    cv_box[nms_idx],
                    conf[nms_idx],
                    j[nms_idx],
                    kpt[nms_idx],
                )
                # xyxy
                cv_box[:, 2:] += cv_box[:, :2]
                cv_box = scale_boxes(pred_shape, cv_box, orig_shapes[i])
                # 关键点还原
                kpt = kpt.reshape(len(kpt), *self.kpt_shape)
                kpt = scale_coords(pred_shape, kpt, orig_shapes[i])

                predict_results.append(
                    {"bboxs": cv_box, "scores": conf, "labels": j, "keypoints": kpt}
                )

        return predict_results


# endregion
