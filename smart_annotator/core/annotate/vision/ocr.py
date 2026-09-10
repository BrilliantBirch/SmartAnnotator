# -*- coding: utf-8 -*-
"""
OCR 自动标注预测器 - PP-OCR 文本检测(det) + 文本识别(rec) 端到端链路

移植自 E:\\code\\PaddleOCR\\vai_inference 成熟实现：
    逐图 det 推理（短边限边放大 + 上限钳制 + 32 对齐 + ImageNet 归一化）
    → DB 后处理出四点框（二值化→轮廓→最小四边形→框得分过滤→unclip 外扩
    →短边过滤→坐标还原原图）→ 透视裁剪文本行 → 全部文本行合并后按 batch
    分块批量 rec（高 48 动态宽 + (x/255-0.5)/0.5 归一化）→ CTC greedy 解码
    → 按图聚合。

与 YOLO 预测器的接口差异：
    - det/rec 各建一个 ONNXInfer 会话（det 用 model_path，rec 用
      rec_model_path，字符表来自 rec_dict_path）
    - 预测结果无 bboxs/labels 键，输出 {"texts", "scores", "points",
      "det_scores"}，由 OcrFormatter 直出 labelme 形状
    - unclip 用纯 numpy 手写实现（凸四边形边偏移 + 直线求交），
      不依赖 pyclipper/shapely

作者: BaiBinnan
创建日期: 2026-09-10
更新: 2026-09-10 首次创建：OcrPredictor 端到端推理与 DB 后处理、
      手写 unclip、CTC 解码
更新: 2026-09-10 兼容 static 固定尺寸模型：加载期解析 det/rec 会话输入
      NCHW 签名，det 固定尺寸走 letterbox（贴左上零填充）且固定批 >1 时
      复制补批，rec 固定宽/固定批按会话签名对齐（补零行后截断）；padding
      区预填 -1 修正为与官方"零像素填充后归一化"语义一致；DB 后处理
      阈值改为从配置读取（ocr_thresh/ocr_box_thresh/ocr_unclip_ratio）
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from smart_annotator.config import AnnotateConfig, DEVICE
from smart_annotator.utils import LOGGER
from .onnxbackend import ONNXInfer
from .yolo import BasePredictor

# ===== det 预处理常量（与官方 PP-OCR 推理配置一致）=====
# 短边下限：短边小于该值时按比例放大（DetResizeForTest limit_type="min"）
_DET_LIMIT_SIDE = 736
# ImageNet 归一化参数（与官方 NormalizeImage 一致）
_DET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_DET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# ===== rec 预处理常量 =====
# 输入固定高度（PP-OCR rec 模型规格）
_REC_IMG_H = 48
# 动态宽下限/上限（与官方推理配置一致）
_REC_MIN_W = 80
_REC_MAX_W = 640


def get_rotate_crop_image(img: np.ndarray, points: np.ndarray) -> np.ndarray:
    """透视裁剪：四点框拉平为水平文本行图（移植自官方 tools/infer/utility.py）。

    Args:
        img: 原图 (H, W, 3) BGR。
        points: 四点框 (4, 2)（左上/右上/右下/左下顺序）。

    Returns:
        裁剪后的文本行图像；高宽比 >= 1.5（近竖排）时旋转 90 度转横向，
        匹配 rec 的横向输入；退化框（目标宽或高 < 1 像素）兜底为
        最小外接矩形的轴对齐裁剪。
    """
    points = np.float32(points)
    # 目标尺寸取对边长度的最大值（容忍透视形变）
    img_crop_width = int(
        max(np.linalg.norm(points[0] - points[1]), np.linalg.norm(points[2] - points[3]))
    )
    img_crop_height = int(
        max(np.linalg.norm(points[0] - points[3]), np.linalg.norm(points[1] - points[2]))
    )
    if img_crop_width <= 0 or img_crop_height <= 0:
        # 退化框兜底：按最小外接矩形（轴对齐）直接裁剪
        x, y, w, h = cv2.boundingRect(points.astype(np.int32))
        return img[y : y + h, x : x + w].copy()
    # 透视变换：四点框 -> 水平矩形（边缘复制填充 + 三次插值）
    pts_std = np.float32(
        [
            [0, 0],
            [img_crop_width, 0],
            [img_crop_width, img_crop_height],
            [0, img_crop_height],
        ]
    )
    m = cv2.getPerspectiveTransform(points, pts_std)
    dst_img = cv2.warpPerspective(
        img,
        m,
        (img_crop_width, img_crop_height),
        borderMode=cv2.BORDER_REPLICATE,
        flags=cv2.INTER_CUBIC,
    )
    # 近竖排文本行（高宽比 >= 1.5）旋转 90 度转横向
    dst_img_height, dst_img_width = dst_img.shape[0:2]
    if dst_img_height * 1.0 / dst_img_width >= 1.5:
        dst_img = np.rot90(dst_img)
    return dst_img


class DBPostProcess:
    """DB 后处理器（移植自 ppocr db_postprocess，quad 模式，纯 numpy/cv2 实现）。

    流程：概率图二值化 -> findContours -> 最小外接四边形（左上/右上/右下/左下
    排序）-> 框内平均分过滤 -> unclip 外扩 -> 二次最小四边形与短边过滤 ->
    坐标还原原图尺度。

    Attributes:
        thresh: 概率图二值化阈值。
        box_thresh: 框内平均分过滤阈值。
        max_candidates: 轮廓候选上限。
        unclip_ratio: 框外扩比例。
        min_size: 输出框最短边过滤阈值（像素）。
    """

    def __init__(
        self,
        thresh: float = 0.2,
        box_thresh: float = 0.45,
        unclip_ratio: float = 1.4,
        min_size: int = 3,
        max_candidates: int = 3000,
    ):
        """初始化后处理器。

        Args:
            thresh: 概率图二值化阈值（默认 0.2，与官方推理配置一致）。
            box_thresh: 框内平均分阈值（默认 0.45，与官方推理配置一致）。
            unclip_ratio: unclip 外扩比例（默认 1.4）。
            min_size: 最短边过滤阈值（默认 3 像素）。
            max_candidates: 轮廓候选上限（默认 3000）。
        """
        self.thresh = thresh
        self.box_thresh = box_thresh
        self.unclip_ratio = unclip_ratio
        self.min_size = min_size
        self.max_candidates = max_candidates

    @staticmethod
    def _get_mini_boxes(contour) -> Tuple[List[np.ndarray], float]:
        """轮廓的最小外接四边形（顶点按左上/右上/右下/左下排序）。

        Args:
            contour: cv2 轮廓 (N, 1, 2) 或四点数组。

        Returns:
            (四点坐标列表, 最短边长度)。
        """
        bounding_box = cv2.minAreaRect(contour)
        points = sorted(list(cv2.boxPoints(bounding_box)), key=lambda x: x[0])

        # 按 x 排序后，左右两列各按 y 分出上下顶点，重排为 左上/右上/右下/左下
        index_1, index_2, index_3, index_4 = 0, 1, 2, 3
        if points[1][1] > points[0][1]:
            index_1, index_4 = 0, 1
        else:
            index_1, index_4 = 1, 0
        if points[3][1] > points[2][1]:
            index_2, index_3 = 2, 3
        else:
            index_2, index_3 = 3, 2

        box = [points[index_1], points[index_2], points[index_3], points[index_4]]
        return box, min(bounding_box[1])

    @staticmethod
    def _box_score_fast(bitmap: np.ndarray, _box: np.ndarray) -> float:
        """框内平均分：外接矩形区域内多边形掩码的概率均值。

        Args:
            bitmap: 概率图 (H', W')。
            _box: 四点框 (4, 2)。

        Returns:
            框内平均概率（float）。
        """
        h, w = bitmap.shape[:2]
        box = _box.copy()
        # 框外接矩形钳制在概率图范围内
        xmin = np.clip(np.floor(box[:, 0].min()).astype("int32"), 0, w - 1)
        xmax = np.clip(np.ceil(box[:, 0].max()).astype("int32"), 0, w - 1)
        ymin = np.clip(np.floor(box[:, 1].min()).astype("int32"), 0, h - 1)
        ymax = np.clip(np.ceil(box[:, 1].max()).astype("int32"), 0, h - 1)

        # 多边形掩码 + 均值统计
        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
        box[:, 0] = box[:, 0] - xmin
        box[:, 1] = box[:, 1] - ymin
        cv2.fillPoly(mask, box.reshape(1, -1, 2).astype("int32"), 1)
        return cv2.mean(bitmap[ymin : ymax + 1, xmin : xmax + 1], mask)[0]

    @staticmethod
    def _unclip(box: np.ndarray, unclip_ratio: float) -> Optional[np.ndarray]:
        """凸四边形按面积/周长比例外扩（手写实现，替代 pyclipper + shapely）。

        与 pyclipper JT_ROUND 的等价性说明：
            pyclipper JT_ROUND 在顶点处以圆弧过渡外扩；本流程的输入必为
            cv2.minAreaRect 输出的凸（矩形）四边形，其 JT_ROUND 外扩结果
            等于"各边沿外法线平移 distance 后的圆角矩形"（原矩形与半径
            distance 圆盘的闵可夫斯基和），它与"边外移 + 相邻外移直线求交"
            的尖角外扩四边形具有完全相同的支撑线，二者最小外接矩形一致；
            而 DB 后处理在 unclip 之后必经 _get_mini_boxes（minAreaRect）
            取最小四边形，故手写边偏移实现与 pyclipper JT_ROUND 的最终
            结果等价，且对一般凸四边形同样成立（凸多边形统一外移不会
            自交）。

        实现：shoelace 公式计算面积 area 与周长 length，
        distance = area * unclip_ratio / length；每条边沿其外法线平移
        distance（法线 = 边方向单位向量旋转 90 度，朝向由多边形 shoelace
        有符号面积的符号判定），相邻平移直线求交点得到新四边形。

        Args:
            box: 凸四边形顶点 (4, 2)（顶点按边界顺序排列）。
            unclip_ratio: 外扩比例。

        Returns:
            外扩后的四点坐标 (4, 2) float32；面积/周长退化时返回 None。
        """
        pts = np.asarray(box, dtype=np.float64).reshape(-1, 2)
        x, y = pts[:, 0], pts[:, 1]
        # np.roll(-1)：下一顶点（末点回绕到首点），构成闭合边界
        roll_x, roll_y = np.roll(x, -1), np.roll(y, -1)
        # shoelace 有符号面积（图像坐标系 y 向下，左上/右上/右下/左下顺序为正）
        signed_area = float(np.sum(x * roll_y - roll_x * y) / 2.0)
        area = abs(signed_area)
        if area <= 1e-6:
            # 退化（零面积）：无法外扩
            return None
        # 边向量与周长
        seg = np.stack([roll_x - x, roll_y - y], axis=1)
        seg_len = np.linalg.norm(seg, axis=1)
        length = float(seg_len.sum())
        if length <= 1e-6:
            return None
        # 与官方一致的外扩距离：area * unclip_ratio / length
        distance = area * unclip_ratio / length

        # 外法线朝向由 shoelace 符号判定：符号为正时边 (dx, dy) 的外侧法线
        # 为 (dy, -dx)；符号为负时取反（图像坐标系 y 向下）
        sign = 1.0 if signed_area > 0 else -1.0
        normals = np.stack([sign * seg[:, 1], -sign * seg[:, 0]], axis=1)
        # 单位化法线后平移边：直线过 平移后边起点，方向为原边方向
        normals = normals / np.maximum(seg_len, 1e-12)[:, None]
        line_pts = pts + normals * distance

        # 相邻平移直线求交点：新顶点 j = 直线(j-1) 与 直线(j) 的交点
        new_pts = np.empty_like(pts)
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            a, u = line_pts[i], seg[i]  # 边 i 的平移直线：点 a，方向 u
            b, v = line_pts[j], seg[j]  # 边 j 的平移直线：点 b，方向 v
            denom = u[0] * v[1] - u[1] * v[0]
            if abs(denom) < 1e-12:
                # 相邻边平行（凸四边形不会出现）：取两平移点中点兜底
                new_pts[j] = (a + b) / 2.0
                continue
            # 直线交点：a + t * u = b + s * v，解 t
            t = ((b[0] - a[0]) * v[1] - (b[1] - a[1]) * v[0]) / denom
            new_pts[j] = a + t * u
        return new_pts.astype(np.float32)

    def __call__(
        self,
        pred: np.ndarray,
        src_h: int,
        src_w: int,
        resize_ratio: Optional[float] = None,
    ) -> Tuple[List[np.ndarray], List[float]]:
        """对单张概率图执行 DB 后处理。

        Args:
            pred: 概率图 (H', W')，取值 [0, 1]。
            src_h: 原图高。
            src_w: 原图宽。
            resize_ratio: 预处理实际缩放比（letterbox 模式必传：等比缩放
                且含填充，坐标须按 1/ratio 还原）；None 时按
                概率图/原图 尺寸比例还原（动态 32 对齐模式的等价比例）。

        Returns:
            (boxes, scores)：四点框列表（原图像素坐标 float32, (4, 2)）
            与对应的框内平均分列表。
        """
        # 概率图二值化
        bitmap = pred > self.thresh
        height, width = pred.shape[:2]

        # 轮廓提取（cv2 版本兼容：返回值可能为二元或三元组）
        outs = cv2.findContours(
            (bitmap * 255).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = outs[0] if len(outs) == 2 else outs[1]
        num_contours = min(len(contours), self.max_candidates)

        boxes: List[np.ndarray] = []
        scores: List[float] = []
        for index in range(num_contours):
            contour = contours[index]
            # 最小外接四边形（左上/右上/右下/左下排序）+ 短边预过滤
            points, sside = self._get_mini_boxes(contour)
            if sside < self.min_size:
                continue
            points = np.array(points)
            # 框内平均分过滤
            score = self._box_score_fast(pred, points.reshape(-1, 2))
            if self.box_thresh > score:
                continue
            # unclip 外扩（凸四边形边偏移，等价 pyclipper JT_ROUND + minAreaRect）
            expanded = self._unclip(points, self.unclip_ratio)
            if expanded is None:
                continue
            # 外扩后重取最小四边形 + 二次短边过滤（阈值 +2 与官方一致）
            box, sside = self._get_mini_boxes(expanded)
            if sside < self.min_size + 2:
                continue
            box = np.array(box)
            # 坐标还原原图尺度并钳制在原图范围内：letterbox 按实际缩放比
            # （填充区无响应，不参与还原），动态对齐按概率图/原图尺寸比例
            if resize_ratio is not None:
                sx = sy = 1.0 / resize_ratio
            else:
                sx, sy = src_w / width, src_h / height
            box[:, 0] = np.clip(np.round(box[:, 0] * sx), 0, src_w)
            box[:, 1] = np.clip(np.round(box[:, 1] * sy), 0, src_h)
            boxes.append(box.astype("float32"))
            scores.append(float(score))
        return boxes, scores


class OcrPredictor(BasePredictor):
    """OCR 自动标注预测器（det 文本检测 + rec 文本识别 端到端）。

    预测结果结构（每张图一个字典，字段与文本框一一对应）：
        {"texts": List[str],                 # 识别文本
         "scores": List[float],              # 识别置信度
         "points": List[List[List[float]]],  # 每框 4 点原图像素坐标
         "det_scores": List[float]}          # 检测框得分

    Attributes:
        batch: rec 分块批量推理大小（同时作为图像批处理大小）。
        class_mapping: 兼容基类/Annotator 接口（OCR 无类别，恒为空字典）。
        kpt_shape: 兼容基类/Annotator 接口（OCR 无关键点，恒为 None）。
        det: det 推理会话（ONNXInfer）。
        rec: rec 推理会话（ONNXInfer）。
        postprocess: DB 后处理器。
        character: CTC 字符表 = [blank] + 字典行 + [space]。
    """

    def __init__(self, config: AnnotateConfig):
        """初始化 OCR 预测器并加载模型。

        Args:
            config: 标注配置对象（device/conf/model_path/rec_model_path/
                rec_dict_path）。
        """
        # 先保存配置（基类 __init__ 会回调 load_model，需提前可用）
        self.config = config
        # rec 分块批量大小（默认 8，长文本行整批送入会推高内存峰值）
        self.batch = 8
        # 兼容基类/Annotator 接口：OCR 无类别映射与关键点
        self.class_mapping: Dict[int, str] = {}
        self.kpt_shape = None
        self.det: Optional[ONNXInfer] = None
        self.rec: Optional[ONNXInfer] = None
        self.character: List[str] = []
        # DB 后处理器：阈值从用户 OCR 专属配置读取（默认与官方推理配置
        # 一致：thresh=0.2 / box_thresh=0.45 / unclip_ratio=1.4）
        self.postprocess = DBPostProcess(
            thresh=float(config.ocr_thresh),
            box_thresh=float(config.ocr_box_thresh),
            unclip_ratio=float(config.ocr_unclip_ratio),
            min_size=3,
            max_candidates=3000,
        )
        # static 固定尺寸模型签名：(N, H, W) 或 None（动态尺寸）——
        # 加载期从会话输入解析，预处理按签名对齐（det letterbox / rec 固定宽）
        self._det_fixed: Optional[Tuple[int, int, int]] = None
        self._rec_fixed: Optional[Tuple[int, int, int]] = None
        super().__init__(config)

    def load_model(self) -> bool:
        """加载 det/rec 两个 ONNX 会话与识别字典。

        det 会话使用 config.model_path，rec 会话使用 config.rec_model_path
        （均仅支持 .onnx，GPU 推理走 onnxruntime CUDA EP，与 YOLO 链路
        一致）；字符表来自 config.rec_dict_path（逐行 UTF-8 读取，字符表
        = [blank] + 字典行 + [space]，CTC 约定 blank 固定为索引 0）。

        Returns:
            全部加载成功返回 True，任一失败返回 False。

        Raises:
            ValueError: rec 模型输出类别维 C 与字符表长度不一致
                （换错字典/与训练配置不符时，在加载期响亮失败）。
        """
        # det/rec 模型路径检查（仅支持 onnx）
        det_path = Path(self.config.model_path)
        if det_path.suffix != ".onnx":
            LOGGER.error(f"det 模型文件类型错误: {det_path}，OCR 仅支持 onnx 模型")
            return False
        rec_path = Path(self.config.rec_model_path)
        if rec_path.suffix != ".onnx":
            LOGGER.error(f"rec 模型文件类型错误: {rec_path}，OCR 仅支持 onnx 模型")
            return False
        dict_path = Path(self.config.rec_dict_path)
        if not dict_path.exists():
            LOGGER.error(f"识别字典文件不存在: {dict_path}")
            return False

        # det 会话（device 传入 ONNXInfer，CPU/GPU 由其内部处理）
        try:
            self.det = ONNXInfer(str(det_path), device=self.device)
        except Exception as ex:
            LOGGER.error(f"det 模型加载失败: {ex}")
            return False
        # rec 会话
        try:
            self.rec = ONNXInfer(str(rec_path), device=self.device)
        except Exception as ex:
            LOGGER.error(f"rec 模型加载失败: {ex}")
            return False

        # 字典逐行 UTF-8 读入，字符表 = [blank] + 字典行 + [space]
        self.character = ["blank"]
        with open(dict_path, "r", encoding="utf-8") as f:
            for line in f:
                self.character.append(line.rstrip("\r\n"))
        self.character.append(" ")

        # rec 输出类别维 C 与字符表长度校验（防静默错译）
        self._check_dict_classes()

        # 解析 det/rec 会话输入固定 NCHW 签名（static 模型预处理对齐依据）
        self._det_fixed = self._fixed_nchw(self.det.session)
        self._rec_fixed = self._fixed_nchw(self.rec.session)
        if self._det_fixed is not None:
            n, h, w = self._det_fixed
            LOGGER.info(f"det 为 static 固定尺寸模型: 输入 [{n},3,{h},{w}]")
        if self._rec_fixed is not None:
            n, h, w = self._rec_fixed
            LOGGER.info(f"rec 为 static 固定尺寸模型: 输入 [{n},3,{h},{w}]")

        # 暴露 model 属性，供 Annotator 的加载成功检查使用
        self.model = self.det
        LOGGER.info(
            f"OCR 模型加载完成: det={det_path.name}, rec={rec_path.name}, "
            f"字符表长度={len(self.character)}"
        )
        return True

    @staticmethod
    def _fixed_nchw(infer_session) -> Optional[Tuple[int, int, int]]:
        """从 onnxruntime InferenceSession 提取首输入的固定 NCHW 签名。

        Args:
            infer_session: onnxruntime InferenceSession 对象。

        Returns:
            (N, H, W) 元组（全部为正 int 固定维时）；含动态维（字符串）
            或 rank != 4 时返回 None（动态尺寸模型）。
        """
        shape = infer_session.get_inputs()[0].shape
        if len(shape) != 4:
            return None
        if not all(isinstance(v, int) and v > 0 for v in shape):
            return None
        return (int(shape[0]), int(shape[2]), int(shape[3]))

    def _check_dict_classes(self) -> None:
        """校验 rec 模型输出类别维 C 与字符表长度一致。

        rec 输出 shape 为 (N, T, C)，最后一维 C 由训练字典唯一决定；
        推理字典与训练字典不一致时索引错位，模型会输出"自信的错误文字"
        （静默失败），故在加载期显式报错。C 维为动态（无法确定）时
        告警跳过。

        Raises:
            ValueError: 输出 C 维可确定且与字符表长度不一致。
        """
        out_shape = self.rec.session.get_outputs()[0].shape
        out_c = (
            out_shape[-1]
            if isinstance(out_shape, (list, tuple))
            and len(out_shape) >= 1
            and isinstance(out_shape[-1], int)
            and out_shape[-1] > 0
            else None
        )
        if out_c is None:
            LOGGER.warning(
                "无法从 rec 模型获取输出类别维 C（动态维），跳过字典校验；"
                "若识别结果异常请优先排查字典绑定"
            )
            return
        if int(out_c) != len(self.character):
            raise ValueError(
                f"rec 模型输出类别数({out_c})与字符表长度({len(self.character)})不一致: "
                f"字符表 = blank(1) + 字典行数({len(self.character) - 2}) + space(1)。"
                f"请确认 rec_dict_path 与训练字典逐行一致"
            )
        LOGGER.info(
            f"字典 C 维校验通过: 模型输出类别数 {out_c} == 字符表长度 "
            f"{len(self.character)}"
        )

    def warm_up(self) -> None:
        """模型预热：det/rec 各用小尺寸零数组推理一次，消除首次推理初始化开销。"""
        # det 预热：小图预处理后直接送 det 会话
        dummy_img = np.zeros((320, 320, 3), dtype=np.uint8)
        det_tensor = self._preprocess_det(dummy_img)
        self.det.predict(det_tensor)
        # rec 预热：单行文本图预处理后直接送 rec 会话
        dummy_line = np.zeros((_REC_IMG_H, 320, 3), dtype=np.uint8)
        rec_tensor = self._preprocess_rec([dummy_line])
        self.rec.predict(rec_tensor)
        LOGGER.info("OCR 模型预热完成")

    def predict(self, input_data: List[np.ndarray]) -> Optional[List[Dict[str, Any]]]:
        """对图像列表执行 OCR 端到端推理（det -> 裁剪 -> rec -> 按图聚合）。

        Args:
            input_data: 解码后的 BGR 图像列表 (H, W, 3)。

        Returns:
            每图一个结果字典 {"texts", "scores", "points", "det_scores"}
            （无文本行时各字段为空列表）；失败返回 None。
        """
        try:
            imgs = list(input_data)
            if not imgs:
                return []

            # ===== 阶段 1：逐图 det 推理 + DB 后处理 =====
            all_boxes: List[List[np.ndarray]] = []
            all_det_scores: List[List[float]] = []
            for img in imgs:
                boxes, det_scores = self._detect_one(img)
                all_boxes.append(boxes)
                all_det_scores.append(det_scores)

            # ===== 阶段 2：透视裁剪文本行，记录归属图索引 =====
            crops: List[np.ndarray] = []
            for i, boxes in enumerate(all_boxes):
                for box in boxes:
                    crops.append(get_rotate_crop_image(imgs[i], box))

            # ===== 阶段 3：全部文本行合并后按 batch 分块批量识别（防 OOM）=====
            rec_results: List[Dict[str, Any]] = []
            for start in range(0, len(crops), self.batch):
                chunk = crops[start : start + self.batch]
                rec_results.extend(self._recognize_chunk(chunk))

            # ===== 阶段 4：按图聚合输出（与 Annotator 的 imgInfo 对齐）=====
            results: List[Dict[str, Any]] = [
                {"texts": [], "scores": [], "points": [], "det_scores": []}
                for _ in imgs
            ]
            cursor = 0
            for i, boxes in enumerate(all_boxes):
                entry = results[i]
                for j, box in enumerate(boxes):
                    rec = rec_results[cursor]
                    cursor += 1
                    entry["texts"].append(rec["text"])
                    entry["scores"].append(rec["score"])
                    entry["points"].append([[float(p[0]), float(p[1])] for p in box])
                    entry["det_scores"].append(float(all_det_scores[i][j]))
            return results
        except Exception as ex:
            LOGGER.error(f"OCR 预测过程出错: {ex}")
            return None

    def _detect_one(self, img: np.ndarray) -> Tuple[List[np.ndarray], List[float]]:
        """对单张图执行文本检测（预处理 -> det 推理 -> DB 后处理）。

        Args:
            img: 原图 (H, W, 3) BGR。

        Returns:
            (四点框列表（原图像素坐标 float32, (4, 2)）, 对应 det 得分列表)。
        """
        tensor = self._preprocess_det(img)
        out = self.det.predict(tensor)[0]
        # 概率图取首样本首通道：固定批补批（如 b4）输出为 (N,1,H',W')，
        # 仅取 [0,0]；不能用 np.squeeze（N>1 时会残留批次维导致后处理错乱）
        prob_map = np.asarray(out)[0, 0]
        src_h, src_w = img.shape[:2]
        # static letterbox 模式：按实际缩放比还原坐标（概率图含右侧/下方
        # 填充区，若按 概率图/原图 尺寸比例还原会错位）
        resize_ratio = None
        if self._det_fixed is not None:
            _, fh, fw = self._det_fixed
            resize_ratio = min(fh / src_h, fw / src_w)
        return self.postprocess(prob_map, src_h, src_w, resize_ratio)

    def _preprocess_det(self, img: np.ndarray) -> np.ndarray:
        """det 预处理：static 模型 letterbox 对齐；动态模型限边放大 + 32 对齐。

        static 固定尺寸模型（如 PP-OCRv6 det static960x960）：等比缩放至
        完全放入 (H, W) 后贴左上，右侧/下方零像素填充（与官方 _letterbox
        一致）；固定批 N > 1 时（如 b4 版本）复制单图补批，输出取第 0 份。
        动态尺寸模型：与官方 DetResizeForTest(limit_type="min",
        limit_side_len=736) 一致——短边小于 736 时按比例放大；边长钳制到
        上限（CPU 4000 / GPU 2048）内的最大 32 倍数；四舍五入 32 对齐。
        归一化统一为 BGR 输入直接 x/255 + ImageNet mean/std（无 RGB 转换）。

        Args:
            img: 原图 (H, W, 3) BGR uint8。

        Returns:
            (N, 3, H', W') float 张量（fp16 模型自动降精度）。
        """
        src_h, src_w = img.shape[:2]
        if self._det_fixed is not None:
            # ===== static 固定尺寸：letterbox 贴左上零填充 =====
            n, fh, fw = self._det_fixed
            ratio = min(fh / src_h, fw / src_w)
            rh = min(max(int(round(src_h * ratio)), 1), fh)
            rw = min(max(int(round(src_w * ratio)), 1), fw)
            resized = cv2.resize(img, (rw, rh))
            # 零像素画布贴左上（填充区归一化后非有效区域，DB 后处理天然忽略）
            canvas = np.zeros((fh, fw, 3), dtype=np.uint8)
            canvas[:rh, :rw] = resized
            x = canvas.astype(np.float32) / 255.0
            x = (x - _DET_MEAN) / _DET_STD
            tensor = x.transpose(2, 0, 1)[np.newaxis, ...]
            # 固定批 > 1（如 b4 模型）：复制单图补批，推理结果取第 0 份
            if n > 1:
                tensor = np.repeat(tensor, n, axis=0)
            return self._cast_det(tensor)

        # ===== 动态尺寸：短边限边放大 =====
        # 短边 < 736 时放大（limit_type="min"，与官方推理一致）
        if min(src_h, src_w) < _DET_LIMIT_SIDE:
            ratio = float(_DET_LIMIT_SIDE) / min(src_h, src_w)
        else:
            ratio = 1.0
        resize_h, resize_w = int(src_h * ratio), int(src_w * ratio)
        # 超大图保护：钳制到上限内的最大 32 倍数（GPU 2048 / CPU 4000）
        max_side = 2048 if self.device != DEVICE.CPU else 4000
        aligned = int(max_side // 32) * 32
        if max(resize_h, resize_w) > aligned:
            ratio = float(aligned) / max(resize_h, resize_w)
            resize_h, resize_w = int(resize_h * ratio), int(resize_w * ratio)
        # 四舍五入 32 对齐（下限 32 防退化）
        resize_h = max(int(round(resize_h / 32) * 32), 32)
        resize_w = max(int(round(resize_w / 32) * 32), 32)

        resized = cv2.resize(img, (resize_w, resize_h))
        # 归一化：x/255 -> ImageNet mean/std -> HWC 转 CHW -> 加 batch 维
        x = resized.astype(np.float32) / 255.0
        x = (x - _DET_MEAN) / _DET_STD
        tensor = x.transpose(2, 0, 1)[np.newaxis, ...]
        return self._cast_det(tensor)

    def _cast_det(self, tensor: np.ndarray) -> np.ndarray:
        """det 张量精度处理（fp16 模型自动降精度）并保证内存连续。"""
        if self.det.metadata.get("fp16"):
            tensor = tensor.astype(np.float16)
        return np.ascontiguousarray(tensor)

    def _recognize_chunk(self, lines: List[np.ndarray]) -> List[Dict[str, Any]]:
        """对一批文本行图像执行识别（预处理 -> rec 推理 -> CTC 解码）。

        static 固定批模型（如 rec static48x640 的 N=8）预处理时补零行
        对齐到固定批，解码结果在此截断回实际行数。

        Args:
            lines: 文本行图像列表 (H, W, 3) BGR。

        Returns:
            [{"text": str, "score": float}, ...]（与输入顺序一致）。
        """
        if not lines:
            return []
        tensor = self._preprocess_rec(lines)
        preds = self.rec.predict(tensor)[0]
        results = self._ctc_decode(preds)
        # static 补批（补零行）产生的多余解码结果截断到实际行数
        if self._rec_fixed is not None and len(results) > len(lines):
            results = results[: len(lines)]
        return results

    def _preprocess_rec(self, lines: List[np.ndarray]) -> np.ndarray:
        """rec 预处理：按批统一目标宽 + 右侧零像素填充（static 模型对齐签名）。

        高度固定 48；动态模型目标宽按批内最大宽高比计算并钳制 [80, 640]；
        static 固定尺寸模型（如 rec static48x640）目标宽/批数直接取会话
        输入签名（N, H, W）。单行等比缩放（宽超限则压到目标宽）后右侧
        零像素填充至目标宽（张量预填 -1.0，即零像素经 (x/255-0.5)/0.5
        归一化后的值，与官方 resize_norm_img 语义一致）；static 固定批
        不足时补全填充行对齐。BGR 输入 HWC 转 CHW。

        Args:
            lines: 文本行图像列表 (H, W, 3) BGR。

        Returns:
            (N, 3, 48, W) float 张量（fp16 模型自动降精度），N 为行数或
            static 固定批。
        """
        # 批内目标宽：static 取签名固定宽，动态按最大宽高比钳制
        if self._rec_fixed is not None:
            _, _, fixed_w = self._rec_fixed
            target_w = fixed_w
        else:
            # 批内最大宽高比（钳制到动态宽上限对应的宽高比）
            ratios = [im.shape[1] / im.shape[0] for im in lines]
            max_ratio = min(max(ratios), _REC_MAX_W / _REC_IMG_H)
            # 统一目标宽（下限保证短文本行最小输入宽，上限防止内存/显存超限）
            target_w = int(_REC_IMG_H * max_ratio)
            target_w = max(target_w, _REC_MIN_W)
            target_w = min(target_w, _REC_MAX_W)

        # 批数：static 对齐固定批（不足补全填充行），动态即实际行数
        n = self._rec_fixed[0] if self._rec_fixed is not None else len(lines)
        # 预分配 -1.0 画布（等价右侧零像素填充归一化），有效区域写入左侧
        dtype = np.float16 if self.rec.metadata.get("fp16") else np.float32
        batch = np.full((n, 3, _REC_IMG_H, target_w), -1.0, dtype=dtype)
        for i, img in enumerate(lines):
            # 单行等比缩放：高至 48，宽超目标宽时压缩到目标宽
            h, w = img.shape[:2]
            resized_w = min(int(np.ceil(_REC_IMG_H * (w / h))), target_w)
            resized = cv2.resize(img, (resized_w, _REC_IMG_H))
            # 归一化 (x/255 - 0.5) / 0.5，有效区域写入左侧
            x = (resized.astype(np.float32) / 255.0 - 0.5) / 0.5
            batch[i, :, :, :resized_w] = x.transpose(2, 0, 1)
        if dtype == np.float16:
            return batch
        return np.ascontiguousarray(batch)

    def _ctc_decode(self, preds: np.ndarray) -> List[Dict[str, Any]]:
        """CTC greedy 解码（移植自官方 CTCLabelDecode）。

        Args:
            preds: rec 输出 (N, T, C) logits。

        Returns:
            [{"text": str, "score": float}, ...]（按 batch 顺序）；
            解码规则：argmax 取索引后跳过 blank（索引 0）与相邻时间步
            重复，再映射字符表；置信度为有效字符位置概率均值，
            空文本记 1.0。
        """
        preds_idx = preds.argmax(axis=2)
        preds_prob = preds.max(axis=2)
        results: List[Dict[str, Any]] = []
        for b in range(preds_idx.shape[0]):
            char_list: List[str] = []
            conf_list: List[float] = []
            for t in range(preds_idx.shape[1]):
                idx = int(preds_idx[b, t])
                if idx == 0:
                    # blank（CTC 空白符）
                    continue
                if t > 0 and int(preds_idx[b, t - 1]) == idx:
                    # 相邻时间步重复：CTC 折叠
                    continue
                if idx >= len(self.character):
                    # 越界索引（理论不可达，防御性跳过）
                    continue
                char_list.append(self.character[idx])
                conf_list.append(float(preds_prob[b, t]))
            # 空文本置信度记 1.0，避免空序列均值
            score = float(np.mean(conf_list)) if conf_list else 1.0
            results.append({"text": "".join(char_list), "score": score})
        return results
