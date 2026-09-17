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
    9. 2026-09-11 注释修正：视频断点续传注释补充局限说明（空推理结果帧
       不写 JSON，重跑会重复推理该帧，结果一致仅性能损耗）
    10. 2026-09-11 修复视频中止标注 GeneratorExit：批量/视频两分支的标注
        生成器改经 contextlib.closing 显式确定性关闭（中止 return 时受控
        抛出而非依赖 GC 随机触发；关闭链传播至帧迭代器 finally 释放
        VideoCapture），视频中止补记"已抽取帧数（保留）"日志
    11. 2026-09-11 模型缓存接入：预测器创建与 warmup 移交
        predictor_cache（首次加载预热、后续任务复用，模型/设备/字典
        变化自动重建），构造函数新增 progress_cb 透传加载进度
    12. 2026-09-11 OCR 仅识别模式：批量读输出目录已有 JSON 标注回写
        识别文本（_label_rec_only），单张回填画布现有标注文本
        （annotate_image 分支），跳过 det 检测阶段
    13. 2026-09-11 修复单张仅识别与画布状态脱节：annotate_image 改参数
        驱动（rec_only + existing_shapes 由调用方传入画布实时形状深拷贝，
        不再读磁盘 JSON——未保存的删除/新增不再被磁盘旧状态覆盖）；
        无可识别形状返回 None 哨兵（调用侧不回填画布，防止清空标注）
    14. 2026-09-17 覆盖写盘保留感知区（ROI）：_label_rec_only、OCR 分支与
        普通分支写 JSON 前读取磁盘既有 ROI 并回写（读取失败静默跳过），
        重新标注不再丢失感知区；refresh 相关行为与跳过判断不变
"""

import cv2
import numpy as np
import shutil
from contextlib import closing
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Callable, Generator
from concurrent.futures import ThreadPoolExecutor, as_completed

from smart_annotator.config import SysConfig, AnnotateConfig, MODE, LABELME_VERSION
from smart_annotator.utils import LOGGER
from smart_annotator.core.labelme_io import (
    empty_document,
    save_document,
    load_document,
    document_shapes,
    document_rois,
    set_document_rois,
)
from .predictor_cache import get_predictor
from .formatters import FormatterFactory, BaseFormatter
from .video_processor import VideoProcessor
from smart_annotator.utils import yolo_to_labelme, generate_labelme_file


def _load_image(image_path: Path) -> np.ndarray:
    """从磁盘加载并解码单张图片（模块级函数，供线程池调用）。

    Args:
        image_path: 图片路径。

    Returns:
        解码后的 BGR 图像数组；解码失败（损坏/非图片文件）返回 None。
    """
    image_data = np.fromfile(image_path, dtype=np.uint8)
    return cv2.imdecode(image_data, cv2.IMREAD_COLOR)


def _restore_rois(doc: Dict[str, Any], json_path: Path) -> None:
    """覆盖写盘前把磁盘既有感知区（ROI）回写到待写文档。

    自动标注为覆盖式写盘（重建 shapes 后整篇写出），若不在写盘前回写
    ROI，磁盘上既有的感知区会丢失。读取失败（文件不存在/JSON 损坏）
    静默跳过，不影响既有标注行为。

    Args:
        doc: 待写入的 labelme 文档字典（就地更新）。
        json_path: 目标 labelme JSON 路径（即被覆盖的同名旧文件）。
    """
    try:
        set_document_rois(doc, document_rois(load_document(json_path)))
    except Exception:
        pass


class Annotator:
    """自动标注器，负责加载模型、预测结果并输出 LabelMe 格式标注文件。"""

    def __init__(
        self,
        config: SysConfig,
        progress_cb: Optional[Callable[[str, float], None]] = None,
    ):
        """初始化自动标注器。

        预测器经 predictor_cache 获取：首次使用该模型时执行加载与
        warmup（进度经 progress_cb 上报），后续任务复用缓存实例
        （仅刷新推理参数），不再重复加载。

        Args:
            config: 系统配置对象。
            progress_cb: 模型加载/预热进度回调 (描述, 0-1 进度)，可选。

        Raises:
            ValueError: 当任务类型不支持时抛出。
            RuntimeError: 当模型加载失败时抛出。
        """
        self.mode = config.task_type
        self.config = config.annotate_config

        # 经缓存获取预测器（首次创建+warmup，命中复用并刷新参数）
        model = get_predictor(self.config, progress_cb)
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
            total_images = len(image_files)
            # closing 确保中止（return False）时生成器在受控点确定性关闭：
            # 否则依赖 GC 随机触发 GeneratorExit，调试器会捕获为未处理异常
            with closing(annotation_generator(image_files, self.model.batch)) as annotation_gen:
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
                    labeled_frames = 0
                    # closing 链式确定性关闭：annotation_gen 关闭时
                    # GeneratorExit 传播至 frame_iter 的 finally
                    # （cap.release()），视频句柄不再依赖 GC 释放
                    with closing(annotation_generator(
                        frame_iter, self.model.batch
                    )) as annotation_gen:
                        for idx, annotation_pathList in enumerate(annotation_gen):
                            # 帧级进度与中断检查（中止时已生成帧保留）
                            labeled_frames += len(annotation_pathList)
                            inner = min(labeled_frames / est_frames, 1.0)
                            progress = (processed_tasks + inner) / total_tasks if total_tasks > 0 else 0
                            if not callback(
                                f"标注视频帧: {Path(video_path).name} 已抽取 {video_processor.extracted_count} 帧",
                                progress,
                            ):
                                LOGGER.info(
                                    f"视频标注中止: {Path(video_path).name}，"
                                    f"已抽取 {video_processor.extracted_count} 帧（保留）"
                                )
                                return False
                            # 断点续传：帧图对应标注 JSON 已存在时跳过该帧标注
                            # （对所有任务模式生效），中断重跑只补标缺失帧。
                            # 局限：空推理结果帧不写 JSON，重跑时会重复推理
                            # 该帧（结果一致，仅性能损耗）
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

    def annotate_image(
        self,
        image_path,
        rec_only: bool = False,
        existing_shapes: Optional[List[Dict[str, Any]]] = None,
    ):
        """对单张图片推理并返回 labelme 形状字典列表（不写文件）。

        复用与批量标注完全相同的预测器/格式化器/类别过滤链路，
        仅将结果以 labelme 形状字典形式返回，供标注编辑器直接显示。

        Args:
            image_path: 图片文件路径（字符串或 Path）。
            rec_only: OCR 仅识别模式（跳过检测，对 existing_shapes 区域
                识别回写文本）。调用方传入画布实时形状，与磁盘 JSON
                无关——避免未保存的删除/新增被磁盘旧状态覆盖。
            existing_shapes: 仅识别的输入形状列表（画布实时状态深拷贝）。

        Returns:
            普通模式：labelme 形状字典列表（无检测结果为空列表）；
            仅识别模式：更新识别文本后的形状列表；无可识别内容
            （existing_shapes 为空）时返回 None（调用侧不回填画布）。
        """
        path = Path(image_path)
        img = _load_image(path)
        if img is None:
            return []

        # ===== OCR 仅识别：对画布实时形状区域识别回写（不读磁盘 JSON）=====
        if rec_only:
            if not existing_shapes:
                LOGGER.warning("仅识别：当前图片无已标注 shape，跳过识别")
                return None
            return self.model.recognize_shapes(img, existing_shapes)

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

    def _label_rec_only(self, image_pathList: List[Path]) -> None:
        """OCR 仅识别批量标注：读输出目录已有 JSON，识别文本就地回写。

        跳过 det 检测与原图复制；未标注图片跳过（记日志），标注文件
        读取失败不拖垮整批。

        Args:
            image_pathList: 图像路径列表（JSON 取输出目录同名 .json）。
        """
        for path in image_pathList:
            json_path = self.output / f"{path.stem}.json"
            if not json_path.exists():
                LOGGER.warning(f"仅识别跳过未标注图片: {path.name}")
                continue
            try:
                doc = load_document(json_path)
                shapes = document_shapes(doc)
                if not shapes:
                    LOGGER.warning(f"仅识别跳过无标注图片: {path.name}")
                    continue
                img = _load_image(path)
                if img is None:
                    LOGGER.warning(f"图片解码失败，已跳过: {path}")
                    continue
                # rec 会话识别并回写 description/score（label/points 不变）
                doc["shapes"] = self.model.recognize_shapes(img, shapes)
                # 覆盖写盘前回写磁盘既有感知区（ROI），防止重新识别丢失感知区
                _restore_rois(doc, json_path)
                save_document(doc, json_path)
            except Exception as e:
                LOGGER.error(f"仅识别处理失败: {path.name}，{e}")

    def _label(self, image_pathList: List[Path]) -> None:
        """对图像列表进行批处理标注。

        Args:
            image_pathList: 图像路径列表。
        """
        # OCR 仅识别模式：跳过检测，对已有标注区域回写识别文本
        if self.mode == MODE.OCR and self.config.ocr_rec_only:
            self._label_rec_only(image_pathList)
            return

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

            # 按原始顺序重构列表（解码失败的坏图跳过：不入推理批也不入
            # imgInfo，保证 predictions 与 imgInfo 枚举对齐，单图失败不
            # 再拖垮整批）
            for path in image_pathList:
                img = result_map[path]
                if img is None:
                    LOGGER.warning(f"图片解码失败，已跳过: {path}")
                    continue
                img_h, img_w = img.shape[:2]
                images.append(img)
                imgInfo.append((path, img_h, img_w))

        # 整批解码失败时直接返回（空批次不送推理）
        if not images:
            LOGGER.warning(f"本批图片全部解码失败，已跳过: {[p.name for p in image_pathList]}")
            return

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
                    json_path = self.output / f"{image_path.stem}.json"
                    # 覆盖写盘前回写磁盘既有感知区（ROI）：空文档不含 ROI
                    _restore_rois(doc, json_path)
                    save_document(doc, json_path)
            else:
                annotations = yolo_to_labelme(
                    lines,
                    img_w,
                    img_h,
                    self.model.class_mapping,
                    self.mode.value,
                    kpt_shape,
                )

                json_path = self.output / f"{image_path.stem}.json"
                # 覆盖写盘前取出磁盘既有感知区（ROI）：generate_labelme_file
                # 重建整篇文档（不含 ROI），需在写盘后回写，否则重新标注丢失
                # 感知区。空结果时 generate_labelme_file 不写文件，无需回写
                old_rois: List[Dict[str, Any]] = []
                if annotations:
                    try:
                        old_rois = document_rois(load_document(json_path))
                    except Exception:
                        old_rois = []

                # 生成 labelme 格式文件
                generate_labelme_file(
                    annotations,
                    LABELME_VERSION,
                    image_path.name,
                    img_w,
                    img_h,
                    json_path,
                )

                # 回写感知区（写盘后读取刚生成的文档再补 ROI 字段）
                if old_rois:
                    try:
                        doc = load_document(json_path)
                        set_document_rois(doc, old_rois)
                        save_document(doc, json_path)
                    except Exception:
                        pass

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
