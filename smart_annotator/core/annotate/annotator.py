# -*- coding: utf-8 -*-
"""
自动标注工具 - 支持多种模型的目标检测、姿态估计、实例分割

作者: BaiBinnan
创建日期: 2026-08-10
更新:
    1. 2026-06-24 使用策略模式重构标注格式化逻辑，消除多重 if-else
    2. 2026-06-24 预分配内存复用，减少批处理 GC 开销
    3. 2026-06-24 完善类型提示，增强代码可读性
    4. 2026-06-24 添加模型加载失败检查，避免静默崩溃
    5. 2026-07-07 添加视频文件处理支持，实现智能抽帧和冗余帧过滤
    6. 2026-08-26 支持按用户选择的类别过滤推理结果（selected_classes）
    7. 2026-09-03 图片批次进度描述附带文件名；视频分支改为逐帧批次回调
       （帧级进度 + 可中断，中止时已生成帧保留、剩余帧停止处理）
    8. 2026-09-10 注册 OCR 模式（OcrPredictor/OcrFormatter），批量/单张
       输出通道兼容 OCR 直出 labelme 形状；视频标注增加断点续传跳过
"""

import cv2
import numpy as np
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Callable, Generator
from concurrent.futures import ThreadPoolExecutor, as_completed

from smart_annotator.config import SysConfig, AnnotateConfig, MODE, LABELME_VERSION
from smart_annotator.utils import LOGGER
from .vision import DetectionPredictor, PoseDetectionPredictor, SegmentationPredictor
from .vision.ocr import OcrPredictor
from .formatters import FormatterFactory, BaseFormatter
from .video_processor import VideoProcessor
from smart_annotator.utils import yolo_to_labelme, generate_labelme_file
from smart_annotator.core.labelme_io import empty_document, save_document


def _load_image(image_path: Path) -> np.ndarray:
    """从磁盘加载并解码单张图片（模块级函数，供线程池调用）。

    Args:
        image_path: 图片路径。

    Returns:
        解码后的 BGR 图像数组。
    """
    image_data = np.fromfile(image_path, dtype=np.uint8)
    return cv2.imdecode(image_data, cv2.IMREAD_COLOR)


class Annotator:
    """自动标注器，负责加载模型、预测结果并输出 LabelMe 格式标注文件。"""

    def __init__(self, config: SysConfig):
        """初始化自动标注器。

        Args:
            config: 系统配置对象。

        Raises:
            ValueError: 当任务类型不支持时抛出。
            RuntimeError: 当模型加载失败时抛出。
        """
        self.mode = config.task_type
        self.config = config.annotate_config

        # 使用策略模式，根据任务类型创建预测器
        model = self._create_predictor()
        if model is None:
            raise RuntimeError(f"模型加载失败: {self.config.model_path}")

        self.model = model
        self.formatter: BaseFormatter = FormatterFactory.create(self.mode)

        # 用户选择的检测类别（空 = 不过滤，检测所有类别）
        self._selected_classes = set(self.config.selected_classes) if self.config.selected_classes else None
        if self._selected_classes is not None:
            LOGGER.info(
                f"按选定类别过滤检测: {sorted(self._selected_classes)}"
            )

        # 模型预热
        self.model.warm_up()

    def _create_predictor(self) -> Optional[Any]:
        """根据任务模式创建对应的预测器。

        Returns:
            预测器实例，失败时返回 None。

        Raises:
            ValueError: 当任务类型不支持时抛出。
        """
        predictor_map = {
            MODE.DETECT: DetectionPredictor,
            MODE.POSE: PoseDetectionPredictor,
            MODE.SEGMENT: SegmentationPredictor,
            MODE.OCR: OcrPredictor,
        }

        predictor_cls = predictor_map.get(self.mode)
        if predictor_cls is None:
            LOGGER.warning(f"任务类型:{self.mode.name}暂不支持")
            raise ValueError(f"任务类型:{self.mode.name}暂不支持")

        predictor = predictor_cls(self.config)
        # 检查预测器是否成功初始化（模型是否加载成功）
        if not hasattr(predictor, "model") or predictor.model is None:
            LOGGER.error(f"模型初始化失败: {self.config.model_path}")
            return None

        return predictor

    def run(self, callback: Callable[[str, float], bool]) -> bool:
        """运行自动标注任务。

        Args:
            callback: 进度回调函数，接收 (描述, 进度百分比)，返回是否继续。

        Returns:
            任务是否正常完成。
        """

        def annotation_generator(
            img_iter, batch: int = 1
        ) -> Generator[List[Path], None, None]:
            if batch <= 0:
                raise ValueError("批处理大小无效")
            batch_paths = []
            for img in img_iter:
                batch_paths.append(Path(img))
                if len(batch_paths) >= batch:
                    yield batch_paths
                    batch_paths = []
            if batch_paths:
                yield batch_paths

        if not isinstance(self.config, AnnotateConfig):
            LOGGER.error("标注配置错误，无法解析图片")
            return False

        self.output = Path(self.config.dataset_path)
        self.output.mkdir(parents=True, exist_ok=True)

        success = True
        image_files = self.config.annotation_files
        video_files = self.config.video_files
        total_tasks = len(image_files) + len(video_files)
        processed_tasks = 0

        if image_files:
            annotation_gen = annotation_generator(image_files, self.model.batch)
            total_images = len(image_files)

            for idx, annotation_pathList in enumerate(annotation_gen):
                try:
                    progress = processed_tasks / total_tasks if total_tasks > 0 else 0
                    # 进度描述附带本批文件名（供进度窗口日志展示）
                    names = "、".join(Path(p).name for p in annotation_pathList[:2])
                    suffix = f" 等{len(annotation_pathList)}张" if len(annotation_pathList) > 2 else ""
                    if not callback(
                        f"标注图片: {names}{suffix}",
                        progress,
                    ):
                        return False
                    self._label(annotation_pathList)
                    processed_tasks += len(annotation_pathList)
                except Exception as e:
                    LOGGER.error(f"处理第{idx}批图片数据时出错: {e}")
                    success = False

        if video_files:
            video_processor = VideoProcessor(
                frame_interval=self.config.frame_interval,
                diff_threshold=self.config.diff_threshold,
            )
            total_video_frames = 0
            total_skipped_frames = 0

            for video_idx, video_path in enumerate(video_files):
                try:
                    progress = processed_tasks / total_tasks if total_tasks > 0 else 0
                    if not callback(
                        f"开始处理视频 {video_idx+1}/{len(video_files)}: {Path(video_path).name}",
                        progress,
                    ):
                        return False

                    # 预估抽帧总数（帧级进度：按总帧数/间隔估算）
                    info = VideoProcessor.get_video_info(Path(video_path))
                    total_frames = int(info.get("total_frames", 0)) if info else 0
                    est_frames = max(1, total_frames // self.config.frame_interval + 1)

                    frame_iter = video_processor.extract_frames_iter(
                        Path(video_path), self.output
                    )
                    annotation_gen = annotation_generator(
                        frame_iter, self.model.batch
                    )
                    labeled_frames = 0
                    for idx, annotation_pathList in enumerate(annotation_gen):
                        # 帧级进度与中断检查（中止时已生成帧保留）
                        labeled_frames += len(annotation_pathList)
                        inner = min(labeled_frames / est_frames, 1.0)
                        progress = (processed_tasks + inner) / total_tasks if total_tasks > 0 else 0
                        if not callback(
                            f"标注视频帧: {Path(video_path).name} 已抽取 {video_processor.extracted_count} 帧",
                            progress,
                        ):
                            return False
                        # 断点续传：帧图对应标注 JSON 已存在时跳过该帧标注
                        # （对所有任务模式生效），中断重跑只补标缺失帧
                        pending_paths = [
                            p
                            for p in annotation_pathList
                            if not (self.output / f"{p.stem}.json").exists()
                        ]
                        if not pending_paths:
                            continue
                        try:
                            self._label(pending_paths)
                        except Exception as e:
                            LOGGER.error(f"处理视频帧时出错: {e}")

                    total_video_frames += video_processor.extracted_count
                    total_skipped_frames += video_processor.skipped_count
                    processed_tasks += 1
                except Exception as e:
                    LOGGER.error(f"处理视频 {video_path} 时出错: {e}")
                    success = False

            LOGGER.info(
                f"视频标注完成 - 总抽取帧数: {total_video_frames}, 跳过冗余帧数: {total_skipped_frames}"
            )

        return success

    def annotate_image(self, image_path) -> List[Dict[str, Any]]:
        """对单张图片推理并返回 labelme 形状字典列表（不写文件）。

        复用与批量标注完全相同的预测器/格式化器/类别过滤链路，
        仅将结果以 labelme 形状字典形式返回，供标注编辑器直接显示。

        Args:
            image_path: 图片文件路径（字符串或 Path）。

        Returns:
            labelme 形状字典列表；无检测结果或失败时返回空列表。
        """
        path = Path(image_path)
        img = _load_image(path)
        if img is None:
            return []
        img_h, img_w = img.shape[:2]

        predictions = self.model.predict([img])
        if not predictions:
            return []

        pred = predictions[0]
        # OCR 预测结果无 bboxs 键（输出为文本行），仅检测类模式做空结果检查
        if self.mode != MODE.OCR and pred.get("bboxs") is None:
            return []

        # 与批量标注保持一致：按用户选择的类别过滤
        # （OCR 结果无类别标签，跳过过滤）
        if self._selected_classes is not None and self.mode != MODE.OCR:
            pred = self._filter_by_classes(pred, self._selected_classes)

        kpt_shape = self.model.kpt_shape[0] if self.mode == MODE.POSE else None
        lines = self.formatter.format(
            pred,
            kpt_conf=self.config.kpt_conf,
            class_mapping=self.model.class_mapping,
            kpt_shape=kpt_shape,
        )
        if self.mode == MODE.OCR:
            # OCR 格式化器直出 labelme 形状字典列表（含 PPOCRLabel 兼容的
            # score 字段），跳过 YOLO 行转换直接返回
            return lines

        annotations = yolo_to_labelme(
            lines,
            img_w,
            img_h,
            self.model.class_mapping,
            self.mode.value,
            kpt_shape,
        )

        # 转换为 labelme 标准形状字典（与 labelme_io.new_shape 结构一致）
        shapes: List[Dict[str, Any]] = []
        for a in annotations:
            shapes.append(
                {
                    "label": a["class"],
                    "points": a["points"],
                    "group_id": a.get("group_id"),
                    "description": a.get("description", ""),
                    "shape_type": a["shape_type"],
                    "flags": {},
                    "mask": None,
                }
            )
        return shapes

    def _label(self, image_pathList: List[Path]) -> None:
        """对图像列表进行批处理标注。

        Args:
            image_pathList: 图像路径列表。
        """
        batch_size = len(image_pathList)

        # 使用线程池并行图片解码，I/O 密集型任务线程池可提升吞吐量
        images: List[np.ndarray] = []
        imgInfo: List[Tuple[Path, int, int]] = []

        with ThreadPoolExecutor(max_workers=min(batch_size, 8)) as executor:
            # 提交所有解码任务
            futures = {
                executor.submit(_load_image, path): path
                for path in image_pathList
            }
            # 收集结果，保持顺序和路径对应
            result_map = {}
            for future in as_completed(futures):
                path = futures[future]
                img = future.result()
                result_map[path] = img

            # 按原始顺序重构列表
            for path in image_pathList:
                img = result_map[path]
                img_h, img_w = img.shape[:2]
                images.append(img)
                imgInfo.append((path, img_h, img_w))

        predictions = self.model.predict(images)
        if not predictions:
            return

        for idx, pred in enumerate(predictions):
            image_path, img_h, img_w = imgInfo[idx]
            # OCR 预测结果无 bboxs 键（输出为文本行），仅检测类模式做空结果检查
            if self.mode != MODE.OCR and pred.get("bboxs") is None:
                continue

            # 按用户选择的类别过滤（同步过滤所有与检测框对齐的字段；
            # OCR 结果无类别标签，跳过过滤）
            if self._selected_classes is not None and self.mode != MODE.OCR:
                pred = self._filter_by_classes(pred, self._selected_classes)

            # 使用策略模式格式化，根据任务类型自动选择对应的格式化器
            kpt_shape = (
                self.model.kpt_shape[0] if self.mode == MODE.POSE else None
            )
            lines = self.formatter.format(
                pred,
                kpt_conf=self.config.kpt_conf,
                class_mapping=self.model.class_mapping,
                kpt_shape=kpt_shape,
            )

            if self.mode == MODE.OCR:
                # OCR 格式化器直出 labelme 形状字典（含 PPOCRLabel 兼容的
                # score 字段与识别文本 description），无法经 yolo_to_labelme
                # （其输入为 YOLO 文本行），直接经 labelme_io 写 JSON
                # （与 generate_labelme_file 口径一致：空结果不写文件）
                if lines:
                    doc = empty_document(image_path.name, img_w, img_h)
                    doc["shapes"] = lines
                    save_document(
                        doc, self.output / f"{image_path.stem}.json"
                    )
            else:
                annotations = yolo_to_labelme(
                    lines,
                    img_w,
                    img_h,
                    self.model.class_mapping,
                    self.mode.value,
                    kpt_shape,
                )

                # 生成 labelme 格式文件
                generate_labelme_file(
                    annotations,
                    LABELME_VERSION,
                    image_path.name,
                    img_w,
                    img_h,
                    self.output / f"{image_path.stem}.json",
                )

            # 复制原图到输出目录（避免重复复制）
            dest_path = self.output / image_path.name
            if image_path.resolve() != dest_path.resolve():
                shutil.copy(image_path, dest_path)

    @staticmethod
    def _filter_by_classes(pred: Dict[str, Any], allowed: set) -> Dict[str, Any]:
        """按类别 id 集合过滤单张图像的预测结果。

        同步过滤所有第一维与 labels 对齐的字段：
        - ndarray 字段: bboxs / scores / labels / keypoints（掩码索引）
        - list 字段: boundary_points（SEGMENT 变长多边形，逐项筛选）

        Args:
            pred: 单张图像的预测字典（含 bboxs/scores/labels 等）。
            allowed: 允许的类别 id 集合。

        Returns:
            过滤后的预测字典（全保留时原样返回）。
        """
        labels = pred.get("labels")
        if labels is None or len(labels) == 0:
            return pred

        keep = np.isin(np.asarray(labels), list(allowed))
        if keep.all():
            return pred

        keep_idx = np.nonzero(keep)[0]
        filtered: Dict[str, Any] = {}
        for key, value in pred.items():
            if isinstance(value, np.ndarray) and value.shape[:1] == np.asarray(labels).shape[:1]:
                filtered[key] = value[keep]
            elif isinstance(value, list) and len(value) == len(labels):
                filtered[key] = [value[i] for i in keep_idx]
            else:
                filtered[key] = value
        return filtered
