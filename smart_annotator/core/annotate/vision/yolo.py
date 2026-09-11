# -*- coding: utf-8 -*-
"""
YOLO 预测器

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-06-25 兼容 YOLOv26 端到端推理，自动检测模型版本并路由
更新: 2026-09-04 GPU 推理由 TensorRT engine 切换为 onnxruntime CUDA EP：
      删除 engine 加载与 onnx→engine 隐式转换逻辑（转换持 GIL 导致 UI
      卡死），后处理移除 .engine 输出顺序分支
更新: 2026-09-11 清理死代码：删除零调用的 BasePredictor.unload_model 方法
"""

import numpy as np
import ast
import cv2
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union

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
from smart_annotator.config import AnnotateConfig, DEVICE
from smart_annotator.utils import LOGGER


class BasePredictor:
    """YOLO 预测器基类，定义通用接口。"""

    model_path: Path
    device: DEVICE
    conf: float
    iou: float
    model: Any
    batch: int
    imgSize: Tuple[int, int]
    fp16: bool
    class_mapping: Dict[int, str]
    is_end2end: bool

    def __init__(self, config: AnnotateConfig):
        """初始化预测器。

        Args:
            config: 标注配置对象。
        """
        self.model_path = Path(config.model_path)
        self.device = config.device
        self.conf = config.conf
        self.iou = config.nms
        self.model = None
        self.class_mapping = {}
        self.is_end2end = False
        self.load_model()

    def _detect_model_format(self) -> None:
        """自动检测模型版本，识别是否为端到端（YOLOv26）模型。

        仅通过模型元数据中的 end2end 标志判断，不依赖输出张量形状。
        """
        if not self.model or not self.model.metadata:
            self.is_end2end = False
            LOGGER.info("模型无元数据，按传统YOLO模型处理")
            return

        metadata = self.model.metadata

        if metadata.get("end2end", "False") == "True":
            self.is_end2end = True
            LOGGER.info("检测到端到端（YOLOv26）模型（元数据标志）")
        else:
            self.is_end2end = False
            LOGGER.info("检测到传统YOLO模型（非端到端）")

    def _get_output_shape(self) -> Optional[Tuple[int, ...]]:
        """获取模型输出张量形状，用于推断模型版本。"""
        try:
            if hasattr(self.model, "output_spec"):
                specs = self.model.output_spec()
                if specs and len(specs) > 0:
                    return tuple(specs[0][0])
            if hasattr(self.model, "output_name") and hasattr(self.model, "session"):
                name = self.model.output_name[0]
                shape = self.model.session.get_outputs()[0].shape
                return tuple(shape)
        except Exception:
            pass
        return None

    def load_model(self) -> bool:
        """加载模型。

        Returns:
            加载成功返回 True，失败返回 False。
        """
        pass

    def predict(self, input_data: List[np.ndarray]) -> Optional[List[Dict[str, Any]]]:
        """对输入图像进行预测。

        Args:
            input_data: 图像列表。

        Returns:
            预测结果列表，失败返回 None。
        """
        pass

    def postprocess(
        self,
        predictions: np.ndarray,
        pred_shape: Tuple[int, int],
        orig_shapes: List[Tuple[int, int]],
    ) -> List[Dict[str, Any]]:
        """后处理预测结果。

        Args:
            predictions: 模型输出预测。
            pred_shape: 输入图像尺寸。
            orig_shapes: 原图尺寸列表。

        Returns:
            后处理后的预测结果列表。
        """
        pass

    def preprocess(self, images: List[np.ndarray]) -> np.ndarray:
        """预处理图像，调整大小并转换为 CHW 格式。

        预分配输出数组，避免多次内存拷贝。

        Args:
            images: 原图列表。

        Returns:
            预处理后的 batch 张量 (N, C, H, W)。
        """
        batch = len(images)
        target_h, target_w = self.imgSize
        dtype = np.float16 if self.fp16 else np.float32

        # 预分配连续内存，避免 stack→transpose→ascontiguousarray→astype 四次拷贝
        output = np.empty((batch, 3, target_h, target_w), dtype=dtype)

        for i, img in enumerate(images):
            resized = resize_image(img, self.imgSize)
            # BGR→RGB 同时 HWC→CHW，直接写入预分配数组
            output[i] = resized[..., ::-1].transpose(2, 0, 1)

        output /= 255
        return output

    def warm_up(self) -> None:
        """模型预热，减少首次推理延迟。

        仅需 2 轮即可达到稳定状态，避免不必要的预热开销。
        使用与模型批次大小一致的数量创建 dummy 图像。
        """
        imgSize = self.imgSize
        # 直接创建 batch 张 dummy 图像，避免 extend 导致列表翻倍
        img = [
            np.ones((imgSize[0], imgSize[1], 3), dtype=np.float32)
            for _ in range(self.batch)
        ]
        for _ in range(2):
            self.predict(img)


# region 目标检测
class DetectionPredictor(BasePredictor):
    """目标检测的检测器。"""

    def load_model(self) -> bool:
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
            if get_gpu_info() == -1:
                LOGGER.warning("找不到显卡信息,请检查是否安装了显卡驱动")
                return False

            # GPU 推理统一走 onnxruntime CUDA EP（无需 TensorRT engine 转换）
            if self.model_path.suffix == ".onnx":
                try:
                    self.model = ONNXInfer(self.model_path, device=self.device)
                except Exception as ex:
                    LOGGER.error(f"onnx模型加载失败{str(ex)}")
                    return False
            else:
                LOGGER.error(
                    f"模型文件类型错误{self.model_path},仅支持onnx模型推理,请检查"
                )
                return False

        # 尝试从模型元数据中获取
        if self.model and self.model.metadata:
            self.batch = int(ast.literal_eval(self.model.metadata.get("batch")))
            self.imgSize = tuple(ast.literal_eval(self.model.metadata.get("imgsz")))
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
        else:
            LOGGER.error("模型元数据无效或模型未加载")
            return False

        # 自动检测模型版本（端到端 vs 传统）
        self._detect_model_format()

        return True

    def postprocess(
        self,
        predictions: np.ndarray,
        pred_shape: Tuple[int, int],
        orig_shapes: List[Tuple[int, int]],
    ) -> List[Dict[str, Any]]:
        if self.is_end2end:
            return self._postprocess_end2end(predictions, pred_shape, orig_shapes)
        return self._postprocess_traditional(predictions, pred_shape, orig_shapes)

    def _postprocess_traditional(
        self,
        predictions: np.ndarray,
        pred_shape: Tuple[int, int],
        orig_shapes: List[Tuple[int, int]],
    ) -> List[Dict[str, Any]]:
        """传统 YOLO 后处理（v8/v11 等），包含 NMS。"""
        outputs = np.transpose(predictions, (0, 2, 1))
        bboxes, scores = np.split(
            outputs,
            [
                4,
            ],
            2,
        )
        idxs = scores.max(axis=2) > self.conf
        predict_results: List[Dict[str, Any]] = []
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

    def _postprocess_end2end(
        self,
        predictions: np.ndarray,
        pred_shape: Tuple[int, int],
        orig_shapes: List[Tuple[int, int]],
    ) -> List[Dict[str, Any]]:
        """端到端 YOLO 后处理（v26），输出已包含筛选后的检测框，无需 NMS。"""
        predict_results: List[Dict[str, Any]] = []
        for i in range(len(predictions)):
            pred = predictions[i]
            # 端到端输出格式: (N, 6) -> [x1, y1, x2, y2, score, class_id]
            if pred.ndim == 2 and pred.shape[1] == 6:
                bboxes = pred[:, :4]
                scores = pred[:, 4]
                labels = pred[:, 5].astype(int)
                # 按置信度过滤
                keep = scores > self.conf
                bboxes, scores, labels = bboxes[keep], scores[keep], labels[keep]
                if len(bboxes) > 0:
                    bboxes = scale_boxes(pred_shape, bboxes, orig_shapes[i]).round()
                predict_results.append(
                    {"bboxs": bboxes, "scores": scores, "labels": labels}
                )
            else:
                # 空预测
                predict_results.append(
                    {"bboxs": np.empty((0, 4)), "scores": np.empty(0), "labels": np.empty(0, dtype=int)}
                )
        return predict_results

    def predict(self, input_data: List[np.ndarray]) -> Optional[List[Dict[str, Any]]]:
        """对输入图像进行预测，自动处理批次不匹配。

        实际批次超过模型批次时分块推理，不足时补零填充。

        Args:
            input_data: 图像列表。

        Returns:
            预测结果列表，失败返回 None。
        """
        try:
            actual_batch = len(input_data)
            model_batch = self.batch

            # 实际批次超过模型批次时，分块推理后合并结果
            if actual_batch > model_batch:
                all_results: List[Dict[str, Any]] = []
                for i in range(0, actual_batch, model_batch):
                    chunk = input_data[i : i + model_batch]
                    chunk_results = self._predict_single_batch(chunk)
                    if chunk_results is None:
                        return None
                    all_results.extend(chunk_results)
                return all_results

            return self._predict_single_batch(input_data)
        except Exception as ex:
            LOGGER.error(f"预测过程出错: {str(ex)}")
            return None

    def _predict_single_batch(
        self, input_data: List[np.ndarray]
    ) -> Optional[List[Dict[str, Any]]]:
        """对单批次图像执行预处理→推理→后处理。

        实际批次不足模型批次时自动补齐零填充，推理后截取有效结果。

        Args:
            input_data: 图像列表（长度 ≤ model.batch）。

        Returns:
            预测结果列表，失败返回 None。
        """
        try:
            actual_batch = len(input_data)
            model_batch = self.batch

            if actual_batch < model_batch:
                pad_img = np.zeros(
                    (self.imgSize[0], self.imgSize[1], 3), dtype=input_data[0].dtype
                )
                padded_data = list(input_data) + [
                    pad_img
                ] * (model_batch - actual_batch)
                preprocess_input = self.preprocess(padded_data)
            else:
                preprocess_input = self.preprocess(input_data)

            predictions = self.model.predict(preprocess_input)[0]
            predictions = predictions[:actual_batch]

            orig_shapes = [x.shape[:2] for x in input_data]
            results = self.postprocess(predictions, self.model.imgsz, orig_shapes)
            return results
        except Exception as ex:
            LOGGER.error(f"预测过程出错: {str(ex)}")
            return None


# endregion 目标检测


# region 分割检测
class SegmentationPredictor(DetectionPredictor):
    """实例分割预测器。"""

    class_num: int

    def load_model(self) -> bool:
        if not super().load_model():
            return False
        try:
            self.class_num = len(self.class_mapping)
            return True
        except Exception as ex:
            LOGGER.error(f"模型元数据中类别信息获取失败{str(ex)}")
            return False

    def postprocess(
        self,
        predictions: Union[np.ndarray, Tuple[np.ndarray, np.ndarray]],
        pred_shape: Tuple[int, int],
        orig_shapes: List[Tuple[int, int]],
    ) -> List[Dict[str, Any]]:
        if self.is_end2end:
            return self._seg_postprocess_end2end(predictions, pred_shape, orig_shapes)
        return self._seg_postprocess_traditional(predictions, pred_shape, orig_shapes)

    def _seg_postprocess_traditional(
        self,
        predictions: Union[np.ndarray, Tuple[np.ndarray, np.ndarray]],
        pred_shape: Tuple[int, int],
        orig_shapes: List[Tuple[int, int]],
    ) -> List[Dict[str, Any]]:
        """传统分割后处理（v8/v11 等），包含 NMS 和 proto 掩码解码。"""
        if self.model_path.suffix == ".onnx":
            assert isinstance(predictions, (list, tuple))
            proto, outputs = predictions[1], predictions[0]
        else:
            LOGGER.error(f"不支持的模型格式: {self.model_path.suffix}")
            return []

        outputs = np.transpose(outputs, (0, 2, 1))
        bboxes, scores, maskconf = np.split(outputs, [4, 4 + self.class_num], 2)
        idxs = scores.max(axis=2) > self.conf

        predict_results: List[Dict[str, Any]] = []

        for i in range(len(outputs)):
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
            boundary_points = self._contours_to_boundary(masks, orig_shapes[i])
            cv_box = scale_boxes(pred_shape, cv_box, orig_shapes[i])

            predict_results.append(
                {
                    "bboxs": cv_box,
                    "scores": conf,
                    "labels": j,
                    "boundary_points": boundary_points,
                }
            )

        return predict_results

    def _seg_postprocess_end2end(
        self,
        predictions: Union[np.ndarray, Tuple[np.ndarray, np.ndarray]],
        pred_shape: Tuple[int, int],
        orig_shapes: List[Tuple[int, int]],
    ) -> List[Dict[str, Any]]:
        """端到端分割后处理（v26），输出已包含筛选结果，无需 NMS。"""
        if isinstance(predictions, (list, tuple)) and len(predictions) == 2:
            # 端到端分割通常有两个输出: (detections, proto)
            outputs, proto = predictions[0], predictions[1]
        else:
            LOGGER.error("端到端分割模型预期两个输出，实际不匹配")
            return []

        predict_results: List[Dict[str, Any]] = []
        mask_coeff_dim = 32  # 标准掩码系数维度

        for i in range(len(outputs)):
            pred = outputs[i]
            if pred.ndim != 2 or pred.shape[1] < 4 + 1 + 1 + mask_coeff_dim:
                predict_results.append(
                    {"bboxs": None, "scores": None, "labels": None, "masks": None}
                )
                continue

            # 端到端格式: [x1, y1, x2, y2, score, cls, mask_coeff_0, ..., mask_coeff_31]
            bboxes = pred[:, :4]
            scores = pred[:, 4]
            labels = pred[:, 5].astype(int)
            mask_coeffs = pred[:, 6:6 + mask_coeff_dim]

            keep = scores > self.conf
            bboxes, scores, labels, mask_coeffs = (
                bboxes[keep], scores[keep], labels[keep], mask_coeffs[keep]
            )

            if len(bboxes) > 0:
                bboxes = scale_boxes(pred_shape, bboxes, orig_shapes[i])
                masks = process_mask(
                    proto[i], mask_coeffs, bboxes, pred_shape, upsample=True
                )
                masks = scale_image(pred_shape, masks, orig_shapes[i], ratio_pad=None)
                boundary_points = self._contours_to_boundary(masks, orig_shapes[i])
                predict_results.append(
                    {
                        "bboxs": bboxes,
                        "scores": scores,
                        "labels": labels,
                        "boundary_points": boundary_points,
                    }
                )
            else:
                predict_results.append(
                    {"bboxs": None, "scores": None, "labels": None, "masks": None}
                )

        return predict_results

    @staticmethod
    def _contours_to_boundary(
        masks: np.ndarray, orig_shape: Tuple[int, int]
    ) -> List[List[float]]:
        """将掩码转换为归一化边界点列表。"""
        boundary_points: List[List[float]] = []
        for mask in masks:
            contours, _ = cv2.findContours(
                mask.astype(np.uint8),
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )
            if contours:
                max_contour = max(contours, key=cv2.contourArea)
                epsilon = 0.005 * cv2.arcLength(max_contour, closed=True)
                approx_contour = cv2.approxPolyDP(max_contour, epsilon, closed=True)
                h, w = orig_shape[0], orig_shape[1]
                contour_points = approx_contour.squeeze().tolist()
                normalized_points: List[float] = []
                for p in contour_points:
                    if isinstance(p, (list, np.ndarray)) and len(p) == 2:
                        nx = round(float(p[0]) / w, 6)
                        ny = round(float(p[1]) / h, 6)
                        normalized_points.extend([nx, ny])
                boundary_points.append(normalized_points)
            else:
                boundary_points.append([])
        return boundary_points

    def predict(self, input_data: List[np.ndarray]) -> Optional[List[Dict[str, Any]]]:
        """对输入图像进行预测，自动处理批次不匹配。

        实际批次超过模型批次时分块推理，不足时补零填充。

        Args:
            input_data: 图像列表。

        Returns:
            预测结果列表，失败返回 None。
        """
        try:
            actual_batch = len(input_data)
            model_batch = self.batch

            # 实际批次超过模型批次时，分块推理后合并结果
            if actual_batch > model_batch:
                all_results: List[Dict[str, Any]] = []
                for i in range(0, actual_batch, model_batch):
                    chunk = input_data[i : i + model_batch]
                    chunk_results = self._predict_single_batch(chunk)
                    if chunk_results is None:
                        return None
                    all_results.extend(chunk_results)
                return all_results

            return self._predict_single_batch(input_data)
        except Exception as ex:
            LOGGER.error(f"预测过程出错: {str(ex)}")
            return None

    def _predict_single_batch(
        self, input_data: List[np.ndarray]
    ) -> Optional[List[Dict[str, Any]]]:
        """对单批次图像执行预处理→推理→后处理。

        实际批次不足模型批次时自动补齐零填充，推理后截取有效结果。

        Args:
            input_data: 图像列表（长度 ≤ model.batch）。

        Returns:
            预测结果列表，失败返回 None。
        """
        try:
            actual_batch = len(input_data)
            model_batch = self.batch

            if actual_batch < model_batch:
                pad_img = np.zeros(
                    (self.imgSize[0], self.imgSize[1], 3), dtype=input_data[0].dtype
                )
                padded_data = list(input_data) + [
                    pad_img
                ] * (model_batch - actual_batch)
                preprocess_input = self.preprocess(padded_data)
            else:
                preprocess_input = self.preprocess(input_data)

            predictions = self.model.predict(preprocess_input)
            orig_shapes = [x.shape[:2] for x in input_data]
            results = self.postprocess(predictions, self.model.imgsz, orig_shapes)
            # 截取有效结果（补零部分无效）
            return results[:actual_batch]
        except Exception as ex:
            LOGGER.error(f"预测过程出错: {str(ex)}")
            return None


# endregion 分割检测


# region 关键点检测
class PoseDetectionPredictor(DetectionPredictor):
    """姿态估计预测器。"""

    class_num: int
    kpt_shape: Tuple[int, int]

    def load_model(self) -> bool:
        if not super().load_model():
            return False
        try:
            self.class_num = len(self.class_mapping)
            self.kpt_shape = tuple(
                ast.literal_eval(self.model.metadata.get("kpt_shape"))
            )
            return True
        except Exception as ex:
            LOGGER.error(f"模型元数据中关键点形状获取失败{str(ex)}")
            return False

    def postprocess(
        self,
        predictions: np.ndarray,
        pred_shape: Tuple[int, int],
        orig_shapes: List[Tuple[int, int]],
    ) -> List[Dict[str, Any]]:
        predict_results: List[Dict[str, Any]] = []

        if self.is_end2end:
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

    def predict(self, input_data: List[np.ndarray]) -> Optional[List[Dict[str, Any]]]:
        """对输入图像进行预测，自动处理批次不匹配。

        实际批次超过模型批次时分块推理，不足时补零填充。
        复用 DetectionPredictor._predict_single_batch 避免重复逻辑。

        Args:
            input_data: 图像列表。

        Returns:
            预测结果列表，失败返回 None。
        """
        try:
            actual_batch = len(input_data)
            model_batch = self.batch

            if actual_batch > model_batch:
                all_results: List[Dict[str, Any]] = []
                for i in range(0, actual_batch, model_batch):
                    chunk = input_data[i : i + model_batch]
                    chunk_results = self._predict_single_batch(chunk)
                    if chunk_results is None:
                        return None
                    all_results.extend(chunk_results)
                return all_results

            return self._predict_single_batch(input_data)
        except Exception as ex:
            LOGGER.error(f"预测过程出错: {str(ex)}")
            return None


# endregion
