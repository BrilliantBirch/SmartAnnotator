# -*- coding: utf-8 -*-
"""
单张自动标注线程 - SingleAnnotateWorker

在后台线程中对单张图片执行推理，返回 labelme 形状字典列表（不写文件），
供标注编辑器（主窗口）直接展示到画布。与批量 AnnotationWorker 复用同一
Annotator，保证与批量自动标注的类别过滤/格式化/坐标换算行为完全一致。

支持 OCR 仅识别模式（rec_only=True）：跳过检测，对调用方传入的画布实时
形状区域执行文本识别并回写 description/score——输入取画布实时状态
（深拷贝）而非磁盘 JSON，未保存的删除/新增不会被磁盘旧状态覆盖；
无可识别形状时不发射 shapes_ready（画布保持原状，不清空标注）。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-03 中止后不再发射推理结果（加载/推理完成后检查停止标志）；
      模型加载与推理阶段分别发射进度描述
更新: 2026-09-11 仅识别支持：set_task 增加 canvas_shapes（画布实时形状
      深拷贝）与 rec_only 参数；rec_only 无形状时提示并不发射结果
      （修复空结果清空画布、磁盘旧状态覆盖未保存修改两处缺陷）
"""

from typing import Dict, List, Optional

from PySide6.QtCore import Signal, QMutexLocker

from smart_annotator.config import SysConfig
from smart_annotator.utils import LOGGER
from .base_worker import BaseWorker
from smart_annotator.core.annotate.annotator import Annotator


class SingleAnnotateWorker(BaseWorker):
    """单张自动标注线程。

    Signals:
        shapes_ready(list): 推理完成，返回 labelme 形状字典列表。
    """

    shapes_ready = Signal(list)

    def __init__(self):
        """初始化单张标注线程。"""
        super().__init__()
        self.config: "SysConfig | None" = None
        self.image_path: str = ""
        # 仅识别任务参数：画布实时形状（深拷贝）与模式开关
        self.canvas_shapes: Optional[List[Dict]] = None
        self.rec_only: bool = False

    def set_task(
        self,
        config: SysConfig,
        image_path: str,
        canvas_shapes: Optional[List[Dict]] = None,
        rec_only: bool = False,
    ) -> None:
        """设置推理配置与目标图片路径。

        Args:
            config: 推理配置（含模型/任务类型/类别过滤等）。
            image_path: 待标注图片路径。
            canvas_shapes: 画布实时形状列表（深拷贝），仅识别模式的
                识别输入；普通标注模式忽略。
            rec_only: 是否执行 OCR 仅识别（跳过检测，对已标注区域识别）。
        """
        self.config = config
        self.image_path = image_path
        self.canvas_shapes = canvas_shapes
        self.rec_only = rec_only

    def run(self) -> None:
        """线程主逻辑：构建 Annotator 并对单张图片推理。"""
        try:
            with QMutexLocker(self.mutex):
                if self.config is None:
                    raise ValueError("标注配置未设置")
                if self.stopped:
                    return

            # 模型加载阶段（engine 反序列化耗时较长）
            self.progress_desc.emit("正在加载模型...")
            annotator = Annotator(self.config)
            with QMutexLocker(self.mutex):
                if self.stopped:
                    self.progress_desc.emit("单张标注已中止")
                    return

            if self.rec_only:
                # ===== OCR 仅识别：画布实时形状为识别输入 =====
                if not self.canvas_shapes:
                    # 无可识别形状：提示且不发射结果（画布保持原状，
                    # 修复空结果经 set_shapes([]) 清空画布的缺陷）
                    self.progress_desc.emit(
                        "仅识别需要已有标注：请先标注文本框（当前图片无标注）"
                    )
                    LOGGER.warning("仅识别中止：当前图片无已标注 shape")
                    return
                self.progress_desc.emit(
                    f"正在识别 {len(self.canvas_shapes)} 个标注区域..."
                )
                shapes = annotator.annotate_image(
                    self.image_path,
                    rec_only=True,
                    existing_shapes=self.canvas_shapes,
                )
                # None 哨兵（无可识别内容）同样不回填画布
                if shapes is None:
                    self.progress_desc.emit("仅识别完成：无有效标注区域")
                    return
            else:
                # ===== 普通推理 =====
                self.progress_desc.emit("正在推理...")
                shapes = annotator.annotate_image(self.image_path)

            # 中止后丢弃结果（不回填画布）
            with QMutexLocker(self.mutex):
                if self.stopped:
                    self.progress_desc.emit("单张标注已中止")
                    return
            self.shapes_ready.emit(shapes)
            if self.rec_only:
                self.progress_desc.emit(f"仅识别完成，共更新 {len(shapes)} 个标注文本")
            else:
                self.progress_desc.emit(f"单张标注完成，共 {len(shapes)} 个对象")

        except ValueError as e:
            LOGGER.error(f"标注配置错误: {str(e)}")
            self.error_occurred.emit(f"配置错误: {str(e)}")
        except RuntimeError as e:
            LOGGER.error(f"模型加载失败: {str(e)}")
            self.error_occurred.emit(f"模型加载失败: {str(e)}")
        except Exception as e:
            error_msg = f"单张标注异常: {str(e)}"
            LOGGER.error(error_msg)
            self.error_occurred.emit(error_msg)
        finally:
            self.task_finished.emit()
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False
