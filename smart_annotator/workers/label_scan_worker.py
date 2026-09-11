# -*- coding: utf-8 -*-
"""
后台标签扫描线程 - LabelScanWorker

在后台线程中批量解析目录下全部 labelme JSON 标注文件，汇总类别标签与
关键点名称，避免在 UI 线程同步遍历大量标注文件导致界面卡死（打开包含
标注文件的文件夹时尤为明显）。

大目录（数千标注）冷缓存时逐文件读取可能耗时数十秒，扫描支持逐文件
中断检查（切换文件夹重启扫描时及时终止旧任务）与进度上报（状态栏提示
"正在扫描标注 n/total"）；被停止的扫描不再发射过期结果。

作者: BaiBinnan
创建日期: 2026-09-02
更新: 2026-09-03 接入逐文件中断检查与进度上报；扫描被停止后不再发射
      过期结果（修复扫描不可中断导致任务重启失效与退出崩溃问题）
更新: 2026-09-03 labels_ready 扩展三参数（新增实例计数二元组列表，按个数降序）；
      进度同时上报 progress_updated（0-1 浮点）驱动进度条
更新: 2026-09-04 labels_ready 扩展四参数（新增 shape_counts 分组计数字典），
      供主窗口缓存统计结果并复用于导出对话框预填
更新: 2026-09-10 labels_ready 扩展五参数（新增 text_shape_count：box 类
      形状中 description 非空的个数，OCR 推断文本证据），随统计缓存传递
      至导出对话框任务类型预填
更新: 2026-09-11 注释修正：run() docstring 补全 labels_ready 第五参数
      说明（box 类形状 description 非空个数）
"""

from PySide6.QtCore import Signal, QMutexLocker

from smart_annotator.core.labelme_io import collect_labels_from_files
from smart_annotator.utils import LOGGER
from .base_worker import BaseWorker


class LabelScanWorker(BaseWorker):
    """后台标签扫描线程。

    Signals:
        labels_ready(list, list, list, dict, int): 扫描完成，参数为
            (标签列表, 关键点列表, [标签, 实例个数] 二元组列表（按个数降序）,
             shape 分组计数字典 {"rectangle": n, "point": n, "polygon": n},
             box 类形状中 description 非空的个数（OCR 推断证据）)。
    """

    labels_ready = Signal(list, list, list, dict, int)

    def __init__(self):
        """初始化标签扫描线程。"""
        super().__init__()
        self.json_paths: list = []

    def set_task(self, json_paths) -> None:
        """设置待扫描的 JSON 标注文件路径列表。

        Args:
            json_paths: JSON 文件路径列表（可迭代）。
        """
        self.json_paths = list(json_paths)

    def run(self) -> None:
        """线程主逻辑：批量解析 JSON 并汇总标签/关键点/实例计数/shape 分组计数（可中断、带进度）。

        扫描完成后经 labels_ready 发射 (标签列表, 关键点列表, [标签, 实例个数]
        二元组列表（按个数降序）, shape 分组计数字典, box 类形状中
        description 非空的个数（OCR 推断证据）)；进度同时上报
        progress_updated（0-1 浮点，驱动进度条）与 progress_desc（状态栏文字）。
        """
        try:
            with QMutexLocker(self.mutex):
                if self.stopped:
                    return
                paths = list(self.json_paths)

            # 逐文件中断检查：Python bool 读取为原子操作，无需加锁（高频调用避免锁竞争）
            # 进度上报：同时驱动进度条（0-1 浮点）与状态栏文字（total 为 0 时记 0，避免除零）
            result = collect_labels_from_files(
                paths,
                should_stop=lambda: self.stopped,
                on_progress=lambda done, total: (
                    self.progress_updated.emit(done / total if total else 0.0),
                    self.progress_desc.emit(f"正在扫描标注 {done}/{total}"),
                ),
            )

            # 扫描被停止：结果已过期（新任务即将重启），不再发射
            with QMutexLocker(self.mutex):
                if self.stopped:
                    return

            # counts 转为 [标签, 个数] 二元组列表（按个数降序、同数按标签字典序）；
            # shape_counts 复制一份再发射（避免跨线程共享可变对象）
            counts_items = sorted(
                result.get("counts", {}).items(),
                key=lambda kv: (-kv[1], kv[0]),
            )
            shape_counts = dict(result.get("shape_counts", {}))
            self.labels_ready.emit(
                result["labels"],
                result["keypoints"],
                [list(kv) for kv in counts_items],
                shape_counts,
                int(result.get("text_shape_count", 0)),
            )

        except Exception as e:
            LOGGER.error(f"标签扫描异常: {str(e)}")
            self.error_occurred.emit(f"标签扫描异常: {str(e)}")
        finally:
            self.task_finished.emit()
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False
