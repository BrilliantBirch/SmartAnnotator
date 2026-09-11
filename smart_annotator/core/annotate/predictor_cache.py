# -*- coding: utf-8 -*-
"""
预测器缓存 - 模型仅在首次使用时加载与预热，后续标注任务复用

按 (任务类型, 模型路径, OCR 识别模型路径, 识别字典路径, 设备) 五元组
缓存预测器实例：
    - 首次请求：创建预测器（加载模型）并执行 warm_up，经 progress_cb
      上报"加载 / 预热"阶段进度（供模型预加载进度弹窗显示）
    - 命中缓存：仅刷新推理参数（conf/NMS/OCR 阈值等），不重复加载
      与预热——批量/单张/预加载共享同一模型实例
    - 模型文件、识别模型、字典或设备变化：key 变化自动重建

线程模型： AnnotationWorker / SingleAnnotateWorker / ModelLoadWorker
均在不同 QThread 中调用本模块，全局锁保护缓存的检查与创建（加载期间
并发请求阻塞等待，加载完成后直接复用，避免同 key 重复加载）。

作者: BaiBinnan
创建日期: 2026-09-11
更新: 2026-09-11 首次创建：五元组 key 缓存 + 加载/预热进度回调 +
      命中刷新推理参数（refresh_params）
"""

import threading
from typing import Callable, Dict, Optional, Tuple

from smart_annotator.config import AnnotateConfig, MODE
from smart_annotator.core.annotate.vision import (
    DetectionPredictor,
    PoseDetectionPredictor,
    SegmentationPredictor,
)
from smart_annotator.core.annotate.vision.ocr import OcrPredictor
from smart_annotator.core.annotate.vision.yolo import BasePredictor
from smart_annotator.utils import LOGGER

# 进度回调签名：(阶段描述, 0-1 进度)
ProgressCallback = Callable[[str, float], None]

# 缓存互斥锁（保护检查 + 创建全程：加载期间并发请求排队等待复用）
_predictor_lock = threading.Lock()
# 预测器缓存：key -> 预测器实例
_predictor_cache: Dict[Tuple, BasePredictor] = {}


def _cache_key(config: AnnotateConfig) -> Tuple:
    """构造预测器缓存 key。

    模型文件 / 识别模型 / 字典 / 设备任一变化均产生新 key（自动重建）；
    任务类型决定预测器类（后处理差异），同样纳入 key。

    Args:
        config: 标注配置对象。

    Returns:
        缓存 key 五元组。
    """
    return (
        config.task_type.name if isinstance(config.task_type, MODE) else str(config.task_type),
        str(config.model_path),
        str(config.rec_model_path),
        str(config.rec_dict_path),
        config.device.name,
    )


def _create_predictor(config: AnnotateConfig) -> Optional[BasePredictor]:
    """根据任务类型创建对应预测器（含模型加载）。

    Args:
        config: 标注配置对象。

    Returns:
        预测器实例，失败时返回 None。

    Raises:
        ValueError: 任务类型不支持时抛出。
    """
    predictor_map = {
        MODE.DETECT: DetectionPredictor,
        MODE.POSE: PoseDetectionPredictor,
        MODE.SEGMENT: SegmentationPredictor,
        MODE.OCR: OcrPredictor,
    }
    predictor_cls = predictor_map.get(config.task_type)
    if predictor_cls is None:
        LOGGER.warning(f"任务类型:{config.task_type.name}暂不支持")
        raise ValueError(f"任务类型:{config.task_type.name}暂不支持")

    predictor = predictor_cls(config)
    # 检查预测器是否成功初始化（模型是否加载成功）
    if not hasattr(predictor, "model") or predictor.model is None:
        LOGGER.error(f"模型初始化失败: {config.model_path}")
        return None
    return predictor


def has_predictor(config: AnnotateConfig) -> bool:
    """查询指定配置的预测器是否已在缓存中（模型已加载）。

    Args:
        config: 标注配置对象。

    Returns:
        缓存命中返回 True。
    """
    with _predictor_lock:
        return _cache_key(config) in _predictor_cache


def get_predictor(
    config: AnnotateConfig,
    progress_cb: Optional[ProgressCallback] = None,
) -> Optional[BasePredictor]:
    """获取指定配置的预测器（首次加载+warmup，后续复用）。

    缓存命中时仅刷新推理参数立即返回；未命中时创建预测器（加载模型）
    并执行 warm_up，全程经 progress_cb 上报阶段进度。加载持有全局锁，
    并发请求排队等待后直接复用结果。

    Args:
        config: 标注配置对象。
        progress_cb: 进度回调 (阶段描述, 0-1 进度)，可选。

    Returns:
        预测器实例，模型加载失败返回 None。

    Raises:
        ValueError: 任务类型不支持时抛出。
    """
    key = _cache_key(config)

    def _report(desc: str, progress: float) -> None:
        """安全调用进度回调（未传回调时忽略）。"""
        if progress_cb is not None:
            progress_cb(desc, progress)

    with _predictor_lock:
        # ===== 缓存命中：刷新推理参数直接复用（不重复加载/预热） =====
        cached = _predictor_cache.get(key)
        if cached is not None:
            cached.refresh_params(config)
            _report("模型已就绪", 1.0)
            return cached

        # ===== 缓存未命中：创建预测器（模型加载）+ warmup =====
        _report("正在加载模型...", 0.1)
        predictor = _create_predictor(config)
        if predictor is None:
            return None
        _report("正在预热模型...", 0.4)
        predictor.warm_up(progress_cb=_report)
        _report("模型预热完成", 1.0)
        _predictor_cache[key] = predictor
        return predictor


def clear_cache() -> None:
    """清空预测器缓存（切换模型由 key 变化自动重建，本函数供显式释放）。"""
    with _predictor_lock:
        _predictor_cache.clear()
