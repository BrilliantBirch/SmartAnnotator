"""
Description：YOLO预测器
Author:BaiBinnan
Date:2025/02/17
LastEdit:2025/02/17
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
)
from .onnxbackend import ONNXInfer
from .tensorrtbackend import TensorRTInfer
from cfg import LOGGER, AnnotateConfig, DEVICE


class BasePredictor:
    def __init__(self, config: AnnotateConfig):
        self.model_path = Path(config.modelPath)
        self.device = config.device
        self.conf = config.bboxConf
        self.iou = config.nms

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
        for _ in range(self.warmupcount):
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
            if get_gpu_info() == -1:
                LOGGER.warning("找不到显卡信息")
            if self.model_path.suffix == ".onnx":
                LOGGER.warning("GPU使用tensorrt推理,尝试寻找engine模型")
                engine_path = self.model_path.with_suffix(".engine")
                if engine_path.exists():

                    try:
                        self.model = TensorRTInfer(engine_path)
                    except Exception as ex:
                        LOGGER.error(f"engine模型加载失败{str(ex)}")
                        return False
                else:
                    LOGGER.warning("未找到engine模型,尝试转换")
                    try:
                        from .onnx2engine import Onnx2Engine

                        onnx2engine = Onnx2Engine(onnxfile=self.model_path)
                        engine_path = onnx2engine.run()
                        self.model = TensorRTInfer(engine_path)

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


# endregion


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
        outputs = np.transpose(predictions, (0, 2, 1))
        bboxes, scores, kpts = np.split(outputs, [4, 4 + self.class_num], 2)
        idxs = scores.max(axis=2) > self.conf
        predict_results = []
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
            cxcy, wh, conf, j, kpt = (
                cxcy[nms_idx],
                wh[nms_idx],
                conf[nms_idx],
                j[nms_idx],
                kpt[nms_idx],
            )
            cv_box = np.concatenate([cxcy, wh], -1)
            cv_box = scale_boxes(pred_shape, cv_box, orig_shapes[i], xywh=True)
            # 关键点还原
            kpt = kpt.reshape(len(kpt), *self.kpt_shape)
            kpt = scale_coords(pred_shape, kpt, orig_shapes[i], normalize=True)

            predict_results.append(
                {"bboxs": cv_box, "scores": conf, "labels": j, "keypoints": kpt}
            )

        return predict_results


# endregion
