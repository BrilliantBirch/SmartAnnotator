# -*- coding: utf-8 -*-
"""
转换线程 - 避免阻塞 UI 线程

在后台线程中运行格式转换任务。移植自旧版 core/convert/__init__.py，
仅改 PyQt5 → PySide6、cfg → smart_annotator.config 导入。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-04 转换前新增格式校验阶段（无效文件剔除并汇总报告）
更新: 2026-09-04 格式校验的源格式改由 cc.direction 推导
      （direction_to_source_format），不再读取已删除的 source_format 字段
"""

from smart_annotator.config import SysConfig
from smart_annotator.utils import LOGGER
from .base_worker import BaseWorker
from smart_annotator.core.convert.converter import (
    Converter,
    direction_to_source_format,
)
from smart_annotator.core.convert.validator import validate_annotation_files
from PySide6.QtCore import QMutexLocker


class ConvertWorker(BaseWorker):
    """转换线程 - 在后台线程中运行格式转换任务，避免阻塞 UI。"""

    def __init__(self):
        """初始化转换线程。"""
        super().__init__()
        self.config: "SysConfig | None" = None

    def setConfig(self, config: SysConfig) -> None:
        """设置转换配置。

        Args:
            config: 系统配置对象。
        """
        self.config = config

    def run(self) -> None:
        """线程主逻辑（安全响应暂停/停止）。"""
        try:
            # 初始检查：配置是否设置 + 是否已被停止
            with QMutexLocker(self.mutex):
                if self.config is None:
                    raise ValueError("转换配置未设置")
                if self.stopped:
                    return

            # ===== 转换前格式校验：逐文件检查输入格式，无效文件剔除并汇总报告 =====
            cc = self.config.convert_config
            kpt_count = len(cc.kpt) if cc.kpt else 0
            self.progress_desc.emit("开始格式校验...")
            valid_files, invalid_reports = validate_annotation_files(
                cc.annotation_files,
                direction_to_source_format(cc.direction, self.config.task_type),
                self.config.task_type,
                kpt_count,
                self.run_callback,
            )

            # 校验期间被手动停止：与转换中停止的处理保持一致，直接走终止路径
            with QMutexLocker(self.mutex):
                if self.stopped:
                    self.progress_desc.emit("转换任务手动终止")
                    self.progress_updated.emit(0.0)
                    return

            # 无效文件明细汇总（最多列 50 条，防日志爆炸）
            total = len(cc.annotation_files)
            if invalid_reports:
                for report in invalid_reports[:50]:
                    self.progress_desc.emit(f"[校验] 无效文件 {report}")
                if len(invalid_reports) > 50:
                    self.progress_desc.emit(
                        f"[校验] ...另有 {len(invalid_reports) - 50} 个无效文件未列出"
                    )
            self.progress_desc.emit(
                f"格式校验完成: 共 {total} 个文件, "
                f"有效 {len(valid_files)}, 无效 {len(invalid_reports)}"
            )

            # 剔除无效文件；全部无效则中止任务
            if valid_files:
                cc.annotation_files = valid_files
            else:
                if total > 0:
                    self.error_occurred.emit("所有输入文件均未通过格式校验，任务中止")
                    return

            # 初始化转换器并执行任务
            converter = Converter(self.config)
            continue_running = converter.run(self.run_callback)

            # 任务结束：区分正常完成和被停止
            with QMutexLocker(self.mutex):
                if self.stopped:
                    self.progress_desc.emit("转换任务手动终止")
                    self.progress_updated.emit(0.0)
                elif continue_running:
                    self.progress_desc.emit("转换任务完成")
                    self.progress_updated.emit(1.0)
                else:
                    self.progress_desc.emit("转换任务异常中断")

        except ValueError as e:
            LOGGER.error(f"转换配置错误: {str(e)}")
            self.error_occurred.emit(f"配置错误: {str(e)}")
        except Exception as e:
            error_msg = f"转换线程执行异常: {str(e)}"
            LOGGER.error(error_msg)
            self.error_occurred.emit(error_msg)
        finally:
            self.task_finished.emit()
            # 清理工作：重置标志位（方便线程复用）
            with QMutexLocker(self.mutex):
                self.paused = False
                self.stopped = False
