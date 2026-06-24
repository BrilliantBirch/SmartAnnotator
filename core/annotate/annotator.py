"""
Description：自动标注工具-支持多种模型的目标检测、姿态估计等
Author: BaiBinnan
Date: 2025/06/09
LastEdit: 2026/06/24
LastEditBy: BaiBinnan
E-mail: baibinnan@chuanfeng.com
update：
    1. 2026/06/24: 使用策略模式重构标注格式化逻辑，消除多重if-else
    2. 2026/06/24: 预分配内存复用，减少批处理GC开销
    3. 2026/06/24: 完善类型提示，增强代码可读性
    4. 2026/06/24: 添加模型加载失败检查，避免静默崩溃
"""

import cv2
import numpy as np
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Callable, Generator
from concurrent.futures import ThreadPoolExecutor, as_completed

from cfg import SysConfig, AnnotateConfig, MODE, LOGGER, LABELME_VERSION
from .vision import DetectionPredictor, PoseDetectionPredictor, SegmentationPredictor
from .formatters import FormatterFactory, BaseFormatter
from utils.tool import yolo_to_labelme, generate_labelme_file


def _load_image(image_path: Path) -> np.ndarray:
    """从磁盘加载并解码单张图片（模块级函数，供线程池调用）"""
    image_data = np.fromfile(image_path, dtype=np.uint8)
    return cv2.imdecode(image_data, cv2.IMREAD_COLOR)


class Annotator:
    """自动标注器，负责加载模型、预测结果并输出LabelMe格式标注文件"""

    def __init__(self, config: SysConfig):
        """
        初始化自动标注器

        Args:
            config: 系统配置对象

        Raises:
            ValueError: 当任务类型不支持时抛出
            RuntimeError: 当模型加载失败时抛出
        """
        self.mode = config.currentMode
        self.config = config.annotateConfig

        # 使用策略模式，根据任务类型创建预测器
        model = self._create_predictor()
        if model is None:
            raise RuntimeError(f"模型加载失败: {self.config.modelPath}")

        self.model = model
        self.formatter: BaseFormatter = FormatterFactory.create(self.mode)

        # 模型预热
        self.model.warm_up()

    def _create_predictor(self) -> Optional[Any]:
        """
        根据任务模式创建对应的预测器

        Returns:
            预测器实例，失败时返回None
        """
        predictor_map = {
            MODE.DETECT: DetectionPredictor,
            MODE.POSE: PoseDetectionPredictor,
            MODE.SEGMENT: SegmentationPredictor,
        }

        predictor_cls = predictor_map.get(self.mode)
        if predictor_cls is None:
            LOGGER.warning(f"任务类型:{self.mode.name}暂不支持")
            raise ValueError(f"任务类型:{self.mode.name}暂不支持")

        predictor = predictor_cls(self.config)
        # 检查预测器是否成功初始化（模型是否加载成功）
        if not hasattr(predictor, "model") or predictor.model is None:
            LOGGER.error(f"模型初始化失败: {self.config.modelPath}")
            return None

        return predictor

    def run(self, callback: Callable[[str, float], bool]) -> bool:
        """
        运行自动标注任务

        Args:
            callback: 进度回调函数，接收(描述, 进度百分比)，返回是否继续

        Returns:
            任务是否正常完成
        """

        def annotation_generator(
            img_list: List[Any], batch: int = 1
        ) -> Generator[List[Path], None, None]:
            if batch <= 0:
                raise ValueError("批处理大小无效")
            for i in range(0, len(img_list), batch):
                batch_paths = [Path(img) for img in img_list[i : i + batch]]
                yield batch_paths

        if not isinstance(self.config, AnnotateConfig):
            LOGGER.error("标注配置错误，无法解析图片")
            return False

        annotation_gen = annotation_generator(
            self.config.annotationFiles, self.model.batch
        )

        self.output = Path(self.config.outputDir)
        self.output.mkdir(parents=True, exist_ok=True)
        total = len(self.config.annotationFiles)

        for idx, annotation_pathList in enumerate(annotation_gen):
            try:
                if not callback(
                    "正处理第{}批标注数据".format(idx + 1),
                    (idx + 1) * self.model.batch / total,
                ):
                    return False
                self._label(annotation_pathList)
            except Exception as e:
                LOGGER.error(f"处理第{idx}批标注数据时出错: {e}")

        return True

    def _label(self, image_pathList: List[Path]) -> None:
        """
        对图像列表进行批处理标注

        Args:
            image_pathList: 图像路径列表
        """
        batch_size = len(image_pathList)

        # 使用线程池并行图片解码，I/O密集型任务线程池可提升吞吐量
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
            if pred.get("bboxs") is None:
                continue

            # 使用策略模式格式化，根据任务类型自动选择对应的格式化器
            kpt_shape = (
                self.model.kpt_shape[0] if self.mode == MODE.POSE else None
            )
            lines = self.formatter.format(
                pred,
                kpt_conf=self.config.kptConf,
                class_mapping=self.model.class_mapping,
                kpt_shape=kpt_shape,
            )

            annotations = yolo_to_labelme(
                lines,
                img_w,
                img_h,
                self.model.class_mapping,
                self.mode.value,
                kpt_shape,
            )

            # 生成labelme格式文件
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