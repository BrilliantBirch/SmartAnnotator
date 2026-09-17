# -*- coding: utf-8 -*-
"""
感知区（ROI）导出线程 - RoiExportWorker

在后台线程中按给定图片列表批量导出感知区裁剪结果，避免大批量裁剪阻塞
UI 线程：逐张图片从磁盘读取同名 labelme JSON，解析顶层感知区（ROI）列表，
调用 core.roi_export.export_image_rois 裁剪原图与标注，并向 UI 上报进度
（progress_updated/progress_desc）与最终汇总（summary_ready）。

无 JSON / JSON 无感知区 / JSON 解析失败等情况均按图片计数汇总，单张图片
异常不中断整批；支持暂停/中止（经 BaseWorker 的 pause/stop 原语）。

作者: BaiBinnan
创建日期: 2026-09-17
更新: 2026-09-17 新建：后台批量裁剪感知区，上报进度与汇总，支持暂停/中止
"""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QMutexLocker, Signal

from smart_annotator.core.labelme_io import document_rois, load_document
from smart_annotator.core.roi_export import export_image_rois
from smart_annotator.utils import LOGGER
from .base_worker import BaseWorker

# 汇总中最多保留的错误条目数（防日志/UI 爆炸）
_MAX_ERRORS = 20


class RoiExportWorker(BaseWorker):
    """感知区导出线程：逐图读取 JSON 中的 ROI 并裁剪导出，回传进度与汇总。

    Signals:
        summary_ready(object): 导出结束（含被中止）时发射，参数为汇总字典，
            键固定为 total_images / processed / exported / skipped / failed /
            no_roi_images / out_dir / errors；
            （progress_updated / progress_desc / error_occurred / task_finished
            继承自 BaseWorker）。
    """

    # 导出汇总（参数为 dict，见类 docstring）
    summary_ready = Signal(object)

    def __init__(self):
        """初始化感知区导出线程。"""
        super().__init__()
        # 任务参数（set_task 填充；_out_dir 为 None 表示任务未设置）
        self._image_paths: List[str] = []
        self._out_dir: Optional[str] = None
        self._work_dir: str = ""

    def set_task(self, image_paths, out_dir: str, work_dir: str) -> None:
        """设置导出任务参数。

        Args:
            image_paths: 待导出的图片路径列表（可迭代，相对路径按 work_dir 解析）。
            out_dir: 裁剪结果输出目录。
            work_dir: 数据集工作目录（解析相对图片路径的基目录）。
        """
        self._image_paths = [str(p) for p in image_paths]
        self._out_dir = str(out_dir)
        self._work_dir = str(work_dir)

    def run(self) -> None:
        """线程主逻辑：逐图裁剪感知区并回传汇总（可暂停/中止）。

        每张图片处理完毕后上报进度；中止请求（stop）时提前退出循环，仍发射
        汇总（已处理部分的结果对用户有效）；单图异常计入 failed 不中断整批。
        """
        try:
            # 初始检查：任务参数是否设置 + 是否已被停止
            with QMutexLocker(self.mutex):
                if self._out_dir is None:
                    raise ValueError("感知区导出任务未设置")
                if self.stopped:
                    return
                image_paths = list(self._image_paths)
                out_dir = self._out_dir
                work_dir = self._work_dir

            # ===== 计数累加器 =====
            total_images = len(image_paths)
            processed = 0  # 已处理图片数
            exported = 0  # 成功导出的 ROI 总数
            skipped = 0  # 跳过的 ROI 总数（越界/编码失败等）
            failed = 0  # 处理失败的图片数
            no_roi_images = 0  # 无 JSON 或无感知区的图片数
            errors: List[str] = []  # 错误明细（最多保留 _MAX_ERRORS 条）

            self.progress_desc.emit(f"开始导出感知区: 共 {total_images} 张图片")

            # ===== 逐图处理 =====
            for image in image_paths:
                # 相对路径按工作目录解析（绝对路径原样使用）
                img_path = Path(image)
                if not img_path.is_absolute() and work_dir:
                    img_path = Path(work_dir) / img_path
                try:
                    json_path = img_path.with_suffix(".json")
                    if not json_path.exists():
                        # 无同名 JSON：无感知区数据，计入无感知区图片
                        no_roi_images += 1
                    else:
                        rois = document_rois(load_document(json_path))
                        if not rois:
                            # JSON 存在但无感知区：同样无需导出
                            no_roi_images += 1
                        else:
                            # 逐 ROI 裁剪原图与标注（返回值含 exported/skipped/error）
                            result = export_image_rois(
                                img_path, json_path, rois, out_dir
                            )
                            exported += int(result.get("exported", 0))
                            skipped += int(result.get("skipped", 0))
                            if result.get("error"):
                                failed += 1
                                errors.append(f"{img_path.name}: {result['error']}")
                except Exception as exc:
                    # 单图异常（JSON 解析失败等）：计入 failed，不中断整批
                    failed += 1
                    errors.append(f"{img_path.name}: {exc}")
                    LOGGER.error(f"导出感知区失败 {img_path}: {exc}")

                processed += 1
                # 每张图处理后上报进度与描述；暂停时阻塞、被停止时提前退出循环
                if not self.run_callback(
                    f"正在导出感知区: {img_path.name}",
                    processed / total_images if total_images else 0.0,
                ):
                    break

            # ===== 汇总（含被中止的情况）=====
            summary = {
                "total_images": total_images,
                "processed": processed,
                "exported": exported,
                "skipped": skipped,
                "failed": failed,
                "no_roi_images": no_roi_images,
                "out_dir": str(out_dir),
                "errors": errors[:_MAX_ERRORS],
            }
            LOGGER.info(
                f"感知区导出汇总: 共 {total_images} 张, 已处理 {processed}, "
                f"成功 {exported}, 跳过 {skipped}, 无感知区 {no_roi_images}, "
                f"失败 {failed}, 输出目录 {out_dir}"
            )
            self.summary_ready.emit(summary)

            # 任务结束：区分正常完成和被停止
            with QMutexLocker(self.mutex):
                if self.stopped:
                    self.progress_desc.emit("感知区导出任务手动终止")
                    self.progress_updated.emit(0.0)
                else:
                    self.progress_desc.emit(
                        f"感知区导出完成: 成功 {exported}, 跳过 {skipped}, "
                        f"无感知区 {no_roi_images}, 失败 {failed}"
                    )
                    self.progress_updated.emit(1.0)

        except ValueError as e:
            LOGGER.error(f"感知区导出配置错误: {str(e)}")
            self.error_occurred.emit(f"配置错误: {str(e)}")
        except Exception as e:
            error_msg = f"感知区导出线程执行异常: {str(e)}"
            LOGGER.error(error_msg)
            self.error_occurred.emit(error_msg)
        finally:
            self.task_finished.emit()
            # 清理工作：重置标志位（方便线程复用）
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False