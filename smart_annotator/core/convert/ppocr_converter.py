# -*- coding: utf-8 -*-
"""
PaddleOCR det 标注转 LabelMe JSON 格式的标签（OCR 导入链路）

解析 PaddleOCR det 标注文件（det_gt.txt，每行 {图片相对路径}\t{JSON数组}），
为每张图生成 LabelMe JSON（每框一个 polygon 形状：label="text"、
description=transcription、difficult 原值保留），并将图片复制到输出目录，
与现有 YOLO→LabelMe 导入链路的输出约定一致。

输出目录结构（保留 det 行图片相对路径的父目录层级）：
    {output}/{rel_dir}/{图片主干}.json   LabelMe JSON（imagePath=图片文件名）
    {output}/{rel_dir}/{图片文件名}      复制的源图
    {output}/{rel_dir}/background/images 无有效框图片
其中 rel_dir 为 det 行图片相对路径的父目录（如 "images"），平铺输入
（图片与 det txt 同层）时 rel_dir 为空，输出直接落在 {output} 根目录。

容错约定：
    - 行分隔符不足（无 "\\t"）或 JSON 数组解析失败的行记日志跳过并计数汇总；
    - points 兼容 4 点（直接用）与 2 点（转轴对齐四角点），其余点数或
      坐标非法的框单元素容错跳过（记日志计数），不影响其余框与整任务；
    - 图片按行内相对路径于输入目录下定位，找不到时跳过该行并记日志。

作者: BaiBinnan
创建日期: 2026-09-10
更新: 2026-09-10 首次创建：PPOCR2JsonConverter det 标注解析与 LabelMe 导出
更新: 2026-09-11 输出保留 det 行相对目录层级（防不同子目录同主干文件互相
      覆盖，background/images 同步按 rel_dir 归档）；_build_shapes 单框
      坐标解析增加容错（非法 points 跳过该框并告警计数，不再整任务失败）
"""

from smart_annotator.config import ConvertConfig
from smart_annotator.utils import LOGGER
from smart_annotator.core.labelme_io import new_shape, empty_document, save_document
from smart_annotator.core.convert.json_converter import _safe_copy


from typing import List, Optional
from pathlib import Path
import json
import cv2
import numpy as np


class PPOCR2JsonConverter:
    """PaddleOCR det 标注 → LabelMe JSON 转换器（OCR 导入）。

    Attributes:
        config: 转换配置对象。
        input_dir: 输入目录（含 det 标注 txt 与图片）。
        output: 输出目录（LabelMe JSON 与图片）。
    """

    def __init__(self, config: ConvertConfig):
        """初始化转换器。

        Args:
            config: 转换配置对象（使用 input_dir/output_dir 运行期字段）。
        """
        self.config = config
        # 空字符串输入目录置 None（Path("") 会退化为当前目录，静默扫描
        # 工作目录属隐患；run 入口对 None 显式报错）
        raw_input = str(config.input_dir or "").strip()
        self.input_dir = Path(raw_input) if raw_input else None
        self.output = Path(config.output_dir)

    def _locate_image(self, rel_path: str):
        """按行内相对路径在输入目录下定位图片文件。

        Args:
            rel_path: det 行中的图片相对路径（如 "images/xxx.jpg"）。

        Returns:
            图片 Path（存在且为文件时），否则 None。
        """
        if not rel_path:
            return None
        # 统一正斜杠/反斜杠后拼接（Path 在 Windows 下自动处理正斜杠）
        img_path = self.input_dir / rel_path.strip().replace("\\", "/")
        if img_path.is_file():
            return img_path
        return None

    def _read_image(self, img_path: Path):
        """读取图片（np.fromfile + cv2.imdecode，支持中文路径）。

        Args:
            img_path: 图片路径。

        Returns:
            BGR 图像数组；读取失败返回 None。
        """
        try:
            img_data = np.fromfile(str(img_path), dtype=np.uint8)
            return cv2.imdecode(img_data, cv2.IMREAD_COLOR)
        except Exception as ex:
            LOGGER.error(f"读取图片失败 {img_path}: {ex}")
            return None

    def _build_shapes(self, items: List[dict], src: str) -> List[dict]:
        """将 det 数组元素列表转为 LabelMe 形状列表。

        points 兼容 4 点（直接用）与 2 点（转轴对齐四角点）；点数非法或
        坐标解析失败的框单元素容错跳过（告警并计数，不影响其余框）。
        每框 new_shape(label="text", shape_type="polygon",
        description=transcription) 后追加 difficult 键（缺失取 False）。

        Args:
            items: det 数组元素列表（dict，含 points/transcription/difficult）。
            src: 来源描述（日志定位用，如 "det_gt.txt 第 n 行"）。

        Returns:
            LabelMe 形状字典列表。
        """
        shapes = []
        skipped = 0  # 解析失败被跳过的框计数
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                LOGGER.warning(f"{src} 第 {idx} 个元素非对象，跳过")
                skipped += 1
                continue
            points = item.get("points") or []
            # 4 点直接用；2 点转轴对齐四角点；其余点数/坐标非法跳过该框
            # （单元素容错：float() 对非数值坐标抛 TypeError/ValueError，
            # 缺失维度抛 IndexError，均不中断整任务）
            try:
                if len(points) == 4:
                    quad = [[float(p[0]), float(p[1])] for p in points]
                elif len(points) == 2:
                    xs = [float(points[0][0]), float(points[1][0])]
                    ys = [float(points[0][1]), float(points[1][1])]
                    left, right = min(xs), max(xs)
                    top, bottom = min(ys), max(ys)
                    quad = [
                        [left, top],
                        [right, top],
                        [right, bottom],
                        [left, bottom],
                    ]
                else:
                    raise ValueError(f"点数({len(points)})非法")
            except (TypeError, ValueError, IndexError) as ex:
                LOGGER.warning(f"{src} 第 {idx} 个元素点坐标解析失败，跳过: {ex}")
                skipped += 1
                continue
            # transcription 强制转字符串（缺失/None 视为空串）
            text = item.get("transcription")
            text = "" if text is None else str(text)
            difficult = bool(item.get("difficult", False))
            shape = new_shape(
                label="text",
                points=quad,
                shape_type="polygon",
                description=text,
            )
            shape["difficult"] = difficult
            shapes.append(shape)
        # 跳过框计数汇总（便于用户核查数据质量）
        if skipped:
            LOGGER.warning(f"{src} 共 {skipped} 个框解析失败已跳过")
        return shapes

    def run(self, run_callback) -> bool:
        """执行 PaddleOCR det 标注 → LabelMe JSON 转换。

        解析输入目录下全部 *.txt（det 标注文件，多个逐个处理），每行
        生成一个 LabelMe JSON 并复制对应图片到输出目录；无有效框的行
        图片复制到 background/images（与现有导入链路一致）。输出保留
        det 行图片相对路径的父目录层级（{output}/{rel_dir}/），防止
        不同子目录同主干文件互相覆盖；平铺输入时 rel_dir 为空，输出
        直接落在 {output} 根目录（与旧版行为一致）。

        Args:
            run_callback: 进度回调 callback(desc, progress) -> bool；
                返回 False 时中断返回 False。

        Returns:
            任务是否成功完成。
        """
        try:
            # 输入目录防护：未设置/不存在时显式失败
            if self.input_dir is None or not self.input_dir.is_dir():
                LOGGER.error(f"输入目录未设置或不存在: {self.input_dir!r}")
                return False
            self.output.mkdir(parents=True, exist_ok=True)
            # 扫描输入目录下 det 标注 txt（非递归）。排除 PaddleOCR 官方
            # 命名中的识别标注与字典文件（rec_gt*.txt / dict.txt，大小写
            # 不敏感）——它们常与 det 标注共存于同一目录，逐行解析只会
            # 产生无意义告警；其余任意命名的 txt（train/val/det_gt 等）
            # 均按 det 标注解析，行级容错兜底
            _EXCLUDED = ("rec_gt", "dict")
            txt_files = sorted(
                t
                for t in self.input_dir.glob("*.txt")
                if not t.stem.lower().startswith(_EXCLUDED)
            )
            if not txt_files:
                LOGGER.error(f"输入目录未找到 det 标注 txt 文件：{self.input_dir}")
                return False
            # 预统计总行数（进度分母）
            total_lines = 0
            for txt in txt_files:
                with open(txt, "r", encoding="utf-8") as f:
                    total_lines += sum(1 for _ in f)
            if total_lines == 0:
                LOGGER.warning(f"det 标注文件为空：{txt_files}")
                return True
            # 逐行解析转换
            done = 0
            empty_images: List[tuple] = []  # (无有效框图片, 输出子目录)，转 background
            bad_lines = 0  # 分隔符/JSON 解析失败行数
            missing_images = 0  # 图片未找到行数
            json_count = 0  # 成功生成的 JSON 数
            for txt in txt_files:
                with open(txt, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, 1):
                        done += 1
                        if not run_callback("det 标注转换中", done / total_lines):
                            return False
                        line = line.strip()
                        if not line:
                            continue
                        # 行格式：{图片相对路径}\t{JSON数组}
                        parts = line.split("\t", 1)
                        if len(parts) < 2:
                            bad_lines += 1
                            LOGGER.warning(f"{txt.name} 第 {line_no} 行缺少分隔符，跳过")
                            continue
                        rel_path, json_str = parts[0].strip(), parts[1].strip()
                        try:
                            items = json.loads(json_str)
                        except Exception:
                            bad_lines += 1
                            LOGGER.warning(
                                f"{txt.name} 第 {line_no} 行 JSON 解析失败，跳过"
                            )
                            continue
                        # det 行的 JSON 部分必须为数组（rec_gt 的纯文本行在此被过滤）
                        if not isinstance(items, list):
                            bad_lines += 1
                            LOGGER.warning(
                                f"{txt.name} 第 {line_no} 行标注部分非数组，跳过"
                            )
                            continue
                        # 图片定位（按相对路径于输入目录下查找）
                        img_path = self._locate_image(rel_path)
                        if img_path is None:
                            missing_images += 1
                            LOGGER.warning(
                                f"{txt.name} 第 {line_no} 行图片未找到：{rel_path}，跳过"
                            )
                            continue
                        img = self._read_image(img_path)
                        if img is None:
                            missing_images += 1
                            continue
                        image_height, image_width = img.shape[:2]
                        # 输出子目录：保留 det 行图片相对路径的父目录层级
                        # （如 "images"），防不同子目录同主干文件互相覆盖；
                        # 平铺输入（父目录为 "."）时 parts 为空，直接落
                        # {output} 根目录，行为与旧版一致
                        rel_parts = Path(
                            rel_path.strip().replace("\\", "/")
                        ).parent.parts
                        out_subdir = (
                            self.output.joinpath(*rel_parts) if rel_parts else self.output
                        )
                        out_subdir.mkdir(parents=True, exist_ok=True)
                        # det 元素 → LabelMe 形状
                        shapes = self._build_shapes(
                            items, f"{txt.name} 第 {line_no} 行"
                        )
                        if not shapes:
                            # 无有效框：与现有导入链路一致，图片转 background
                            empty_images.append((img_path, out_subdir))
                            continue
                        # 生成 LabelMe JSON（imagePath=图片文件名，宽高取实际读图）
                        doc = empty_document(img_path.name, image_width, image_height)
                        doc["shapes"] = shapes
                        save_document(doc, out_subdir / f"{img_path.stem}.json")
                        # 复制图片到输出子目录（与 JSON 同层）
                        _safe_copy(img_path, out_subdir / img_path.name)
                        json_count += 1
            # 无有效框图片转 background/images（按各自输出子目录归档，
            # 与现有导入链路一致）
            for img_path, out_subdir in empty_images:
                background_dir = out_subdir / "background" / "images"
                background_dir.mkdir(parents=True, exist_ok=True)
                _safe_copy(img_path, background_dir / img_path.name)
            LOGGER.info(
                f"PPOCR 导入完成: 生成 JSON {json_count} 个，无效行 {bad_lines}，"
                f"图片缺失 {missing_images}，无框图片 {len(empty_images)}"
            )
            return True
        except Exception as ex:
            LOGGER.error(f"PPOCR 标注导入失败：{str(ex)}")
            return False
