# -*- coding: utf-8 -*-
"""
格式转换页 - ConvertPage

按 UI 文档 §5.2 与计划 §2.6：基础卡 + 数据集分析卡 + 高级卡 + 预览卡 + 进度卡。
按方向构建两种实例：导出（JSON→任务数据集，源为只读工作路径）与
导入（任务数据集→JSON，自由选择输入目录）。"任务数据集"按任务类型
分发：DETECT/POSE/SEGMENT → YOLO TXT（含数据集划分），OCR → PaddleOCR
det/rec 标注。

数据集分析（2026-09-02 新增）：
    - 一键分析输入目录：提取 LabelMe 标签、推断任务类型（shape 特征 +
      文本证据）、自动识别转换方向（json→数据集 / 数据集→json）
    - 类别列表支持拖拽排序，行首数字即转换后的类别索引

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-02 新增"一键分析数据集"功能模块；类别列表升级为拖拽排序
更新: 2026-09-02 目录层级识别（label/image/dataset 层级自动解析标注与图片目录）；
      TXT→JSON 方向未配置类别时自动以类别索引作为标签名
更新: 2026-09-02 一键分析 POSE 推断结果自动填充关键点列表（按标注格式
      反推关键点数，默认名 kpt{i}_point{i}）
更新: 2026-09-02 类别/关键点列表高度自适应（按条目数与实际行高调整，
      最多显示 5/4 行后滚动），替代固定 200/140px 最小高度
更新: 2026-09-02 一键分析 LabelMe 方向 POSE 数据集时，point 类型标签
      归入关键点类别集合并自动填充关键点列表（不再混入普通类别列表）
更新: 2026-09-04 导出/导入方向拆分支持：__init__ 新增 direction 参数
      （"export" 锁定源格式 LabelMe / "import" 锁定 YOLO，锁定时一键分析
      不再自动改动源格式）；新增 import_finished(str) 信号（导入方向任务
      成功后发射输出目录）；set_worker 重复绑定时先断开旧连接（修复对话框
      多次打开日志重复输出），qt_handler 父对象改传主窗口；任务类型下拉
      追加禁用的 OCR 占位项；导出方向无 JSON 标注时拦截启动
更新: 2026-09-04 按方向精简页面 UI：删除源/目标格式下拉与 _on_source_changed，
      构造签名改为 (parent, direction, work_path, stats) 并按方向构建基础卡
      （导出=只读工作路径，导入=输入目录）；分割比例与 YOLO 目录结构导出
      选项仅导出方向显示，文件列表与图像预览卡仅导入方向显示；collect_config
      写入 direction/input_dir/output_dir（导出输入取工作路径），apply_config
      不再回填格式与路径；新增 stats 统计预填（类别/关键点/任务类型推断）
更新: 2026-09-04 _apply_stats 参照一键分析逻辑剔除关键点标签（stats 含
      非空 keypoints 时按小写集合过滤 labels 后再填类别列表，日志类别数
      同步用剔除后数量）；_on_import_config docstring 更新为 from_dict
      白名单过滤说明（废弃键/运行期字段键静默忽略，仅恢复有效字段）
更新: 2026-09-04 预览列表仅显示图片文件（不再混入标注文件，标注无预览价值）
更新: 2026-09-10 启用 OCR 任务类型（导出 JSON→PPOCR det/rec、导入 PPOCR det→JSON
      两方向均可选）；新增 OCR 专属参数区（"生成识别数据集 (rec)" 与
      "字典包含空格字符 (use_space_char)" 两个复选框，默认勾选），仅导出
      方向且任务类型为 OCR 时显示；collect_config 纳入 ocr_gen_rec/
      ocr_use_space_char 两键（随 ConvertConfig 序列化白名单持久化）
更新: 2026-09-10 一键分析与统计预填适配 OCR：task_names 补 OCR 名称，
      OCR 任务下方向文案显示"LabelMe (JSON) → PaddleOCR (det/rec)"；
      _apply_stats 透传 text_shape_count（box 类形状 description 非空
      个数）至推断规则，OCR 数据集自动推断为文字识别任务
更新: 2026-09-11 转换语义升级：页面定位从"YOLO↔JSON 互转"改为"任务
      相关数据集结构 ↔ JSON 互转"（DETECT/POSE/SEGMENT → YOLO TXT，
      OCR → PPOCR det/rec）；导出方向 OCR 任务隐藏分割比例行与"导出
      YOLO 数据集目录结构"复选框（PPOCR 结构无划分，隐藏时同步取消
      勾选防状态残留），显隐统一收敛到 _on_task_changed（方向+任务双
      条件）；相关注释语义同步清理
更新: 2026-09-11 修复 apply_config 回填顺序绕过防残留：chk_export 勾选
      在 _on_task_changed 之后写入，末尾统一重跑任务联动；direction
      参数改为必填（移除 None 默认值，与构造校验一致，全库调用点
      app.py 两处均已显式传参）
更新: 2026-09-11 新增暂停/恢复：基础卡新增"暂停"按钮（"暂停"↔"恢复"
      文案切换），经 BaseWorker 既有 pause/resume 原语挂起/唤醒任务
      （run_callback 阻塞等待，当前文件处理完成后挂起，不中断）；
      任务启动复位、结束/中止后按钮复位禁用
"""
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QLabel,
    QComboBox,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QProgressBar,
    QPlainTextEdit,
    QMessageBox,
    QWidget,
    QFrame,
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Signal

from .base_page import BasePage
from ..widgets.buttons import PrimaryButton, SecondaryButton
from ..widgets.cards import Card
from ..widgets.drag_list import DragDropListWidget
from ..widgets.fields import PathField, LabeledSpin, CustomItemWidget, apply_click_to_focus
from ..widgets.preview import FilePreviewWidget
from ..widgets.dialogs import showMessageBox
from ..workers.analyze_worker import AnalyzeWorker
from ..core.convert.dataset_analyzer import DatasetAnalysis, _infer_task_from_shapes
from ..config import SysConfig, ConvertConfig, MODE, Format
from ..utils import LOGGER, scan_dataset_files
from ..utils.qt_logger import add_qt_handler


class ConvertPage(BasePage):
    """格式转换页 - LabelMe ↔ 任务相关双向转换。

    Signals:
        task_started: 任务开始（用于禁用导航）。
        task_finished: 任务结束（用于恢复导航）。
        import_finished: 导入方向（任务→JSON）任务成功完成时发射（携带输出目录）。
    """

    task_started = Signal()
    task_finished = Signal()
    import_finished = Signal(str)

    def __init__(self, parent=None, *, direction: str,
                 work_path: str = "", stats: dict | None = None):
        """初始化格式转换页（按方向构建，构造后方向不可更改）。

        Args:
            parent: 父控件。
            direction: 转换方向（必填关键字参数，无默认值）："export"=导出
                JSON→YOLO / "import"=导入 YOLO→JSON；非法值抛 ValueError。
            work_path: 导出方向的只读工作路径（主窗口传入）。
            stats: 导出方向的统计预填数据，键为 "labels"（类别名列表）、
                "keypoints"（关键点名列表）、"shape_counts"（shape 分组
                计数 {"rectangle": n, "polygon": n, "point": n}）；
                为 None 或空时不预填。

        Raises:
            ValueError: direction 非 "export"/"import" 时抛出。
        """
        # 方向必填校验（构造即锁定，页面全生命周期不变）
        if direction not in ("export", "import"):
            raise ValueError(f"不支持的转换方向: {direction}")
        super().__init__(parent)
        self._worker = None
        self._analyze_worker = None  # 数据集分析线程（一次性，用后销毁）
        self._class_items = []  # 类别 CustomItemWidget 引用
        self._kpt_items = []  # 关键点 CustomItemWidget 引用
        self._direction = direction  # 转换方向（"export" / "import"）
        self._work_path = work_path or ""  # 导出方向的只读工作路径
        self._task_success = False  # 本次任务是否成功（供 import_finished 判定）
        self._bound_worker = None  # 已连接信号的 worker（防重复连接用）
        self._log_handler = None  # 已连接 log_signal 的 qt_handler（防重复连接用）

        self._build_basic_card()
        self._build_analysis_card()
        self._build_advanced_card()
        self._build_preview_card()
        self._build_progress_card()

        # 按方向统一显隐（分割比例/导出选项仅导出方向，预览卡仅导入方向）
        self._apply_direction_visibility()
        # 初始状态：任务类型联动（关键点列表仅 POSE 显示）
        self._on_task_changed()
        # 焦点策略：所有数值控件改为点击获焦，防止悬停滚轮误改值
        apply_click_to_focus(self)

        # 导出方向：无输入目录控件，直接扫描工作路径显示文件计数
        if self._direction == "export" and self._work_path:
            self._on_input_changed(self._work_path)
        # 导出方向：复用主窗口扫描统计结果预填类别/关键点/任务类型
        if self._direction == "export" and stats:
            self._apply_stats(stats)

    def _apply_direction_visibility(self) -> None:
        """按转换方向统一设置控件显隐。

        导出方向：文件列表与图像预览卡隐藏；导入方向相反。可视化复选框
        与类别/关键点列表两方向均保留显示。分割比例行与"导出 YOLO 数据
        集目录结构"复选框的显隐由 _on_task_changed 统一管理（既依赖方向
        也依赖任务类型：仅导出方向且非 OCR 任务显示——OCR 导出 PPOCR
        标注结构，无 train/val/test 划分与 images/labels 目录）。
        """
        is_export = self._direction == "export"
        self.preview_card.setVisible(not is_export)
        # 比例行/目录结构复选框依赖"方向 + 任务类型"双条件，统一走任务联动
        self._on_task_changed()

    def _build_basic_card(self) -> None:
        """构建基础卡：任务类型、输入/输出路径（按方向）、开始/停止。

        导出方向无输入目录控件，改为只读工作路径展示（主窗口传入）；
        导入方向保留输入目录选择控件。
        """
        self.basic_card = Card("基础设置")

        # 任务类型
        task_row = QHBoxLayout()
        task_row.addWidget(QLabel("任务类型"))
        self.task_combo = QComboBox()
        self.task_combo.addItem("目标检测 (DETECT)", MODE.DETECT)
        self.task_combo.addItem("姿态估计 (POSE)", MODE.POSE)
        self.task_combo.addItem("实例分割 (SEGMENT)", MODE.SEGMENT)
        # OCR 任务：导出方向 JSON→PPOCR det/rec，导入方向 PPOCR det→JSON
        self.task_combo.addItem("文字识别 (OCR)", MODE.OCR)
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)
        task_row.addWidget(self.task_combo)
        task_row.addStretch()
        self.basic_card.addLayout(task_row)

        # 输入路径：导出=只读工作路径 / 导入=输入目录选择
        if self._direction == "export":
            self.work_label = QLabel(self._work_path or "（未设置工作路径）")
            self.work_label.setWordWrap(True)
            self.work_label.setStyleSheet("color: #71717a;")
            self.basic_card.addWidget(self._labeled("工作路径", self.work_label))
        else:
            self.input_field = PathField(browse_type="dir", placeholder="选择标注/图片所在目录")
            self.input_field.path_changed.connect(self._on_input_changed)
            self.basic_card.addWidget(self._labeled("输入目录", self.input_field))

        # 输出目录（两方向均保留）
        self.output_field = PathField(browse_type="dir", placeholder="选择输出目录")
        self.basic_card.addWidget(self._labeled("输出目录", self.output_field))

        # 文件计数 + 开始/暂停/停止
        action_row = QHBoxLayout()
        self.count_label = QLabel("未选择目录")
        self.count_label.setStyleSheet("color: #71717a;")
        action_row.addWidget(self.count_label)
        action_row.addStretch()
        self.btn_start = PrimaryButton("开始转换")
        self.btn_pause = SecondaryButton("暂停")
        self.btn_pause.setEnabled(False)
        self._paused = False  # 暂停状态（按钮文案切换依据）
        self.btn_stop = SecondaryButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_stop.clicked.connect(self._on_stop)
        action_row.addWidget(self.btn_pause)
        action_row.addWidget(self.btn_stop)
        action_row.addWidget(self.btn_start)
        self.basic_card.addLayout(action_row)

        self.add_widget(self.basic_card)

    def _build_analysis_card(self) -> None:
        """构建数据集分析卡：一键分析按钮 + 进度条 + 结果摘要。

        分析自动完成：转换方向识别、任务类型推断、标签提取（填入类别列表）。
        """
        self.analysis_card = Card("数据集分析")

        # 操作行：分析按钮 + 进度条
        action_row = QHBoxLayout()
        self.btn_analyze = PrimaryButton("一键分析数据集")
        self.btn_analyze.clicked.connect(self._on_analyze)
        action_row.addWidget(self.btn_analyze)
        self.analysis_progress = QProgressBar()
        self.analysis_progress.setRange(0, 100)
        self.analysis_progress.setValue(0)
        self.analysis_progress.setMaximumWidth(240)
        action_row.addWidget(self.analysis_progress)
        action_row.addStretch()
        self.analysis_card.addLayout(action_row)

        # 结果摘要（多行富文本）
        self.analysis_summary = QLabel(
            "点击按钮分析输入目录：自动识别转换方向、推断任务类型、提取标签列表。"
        )
        self.analysis_summary.setWordWrap(True)
        self.analysis_summary.setStyleSheet("color: #3f3f46;")
        self.analysis_card.addWidget(self.analysis_summary)

        # 拖拽排序提示
        hint = QLabel(
            "提示：分析后类别列表自动填充至下方高级设置，支持拖拽调整顺序，"
            "行首数字即转换后的类别索引。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #71717a;")
        self.analysis_card.addWidget(hint)

        self.add_widget(self.analysis_card)

    # -------------------------- 数据集分析 --------------------------
    def _on_analyze(self) -> None:
        """启动数据集分析线程（后台执行，避免阻塞界面）。

        输入路径按方向取值：导出=工作路径 / 导入=输入目录。
        """
        # 输入路径按方向取值：导出=只读工作路径 / 导入=输入目录
        path = self._work_path if self._direction == "export" else self.input_field.path()
        if not path or not Path(path).exists():
            hint = (
                "工作路径无效，无法分析"
                if self._direction == "export"
                else "请先选择有效的输入目录"
            )
            showMessageBox(QMessageBox.Icon.Warning, hint)
            return
        # 防重复启动
        if self._analyze_worker is not None and self._analyze_worker.isRunning():
            return
        self.btn_analyze.setEnabled(False)
        self.analysis_progress.setValue(0)
        self.append_log(f"[分析] 开始分析数据集: {path}")
        self._analyze_worker = AnalyzeWorker(path)
        self._analyze_worker.progress_updated.connect(
            lambda p: self.analysis_progress.setValue(int(p * 100))
        )
        self._analyze_worker.progress_desc.connect(self.append_log)
        self._analyze_worker.analysis_finished.connect(self._on_analysis_finished)
        self._analyze_worker.error_occurred.connect(self._on_analysis_error)
        self._analyze_worker.task_finished.connect(self._on_analyze_done)
        self._analyze_worker.start()

    def _on_analyze_done(self) -> None:
        """分析线程结束（含异常终止）：恢复分析按钮。"""
        self.btn_analyze.setEnabled(True)

    def _on_analysis_error(self, message: str) -> None:
        """分析线程异常回调。"""
        self.append_log(f"[错误] {message}")
        showMessageBox(QMessageBox.Icon.Critical, f"数据集分析失败:\n{message}")

    def _on_analysis_finished(self, result: DatasetAnalysis) -> None:
        """分析完成回调：应用任务类型并填充类别列表。

        识别出的标注格式仅用于摘要展示（页面方向由构造参数锁定，
        任何下拉不再被自动改动）；任务类型与标签填充结果均为界面
        默认值，用户可手动覆盖。

        Args:
            result: 数据集分析结果对象。
        """
        # 无标注文件：仅提示，不改动任何设置
        if result.json_count == 0 and result.txt_count == 0:
            self.analysis_summary.setText(
                f"未检测到标注文件（JSON/TXT 均为 0），请检查输入目录。"
                f"当前目录仅含图片 {result.image_count} 张。"
            )
            self.append_log("[分析] 未检测到任何标注文件")
            return

        # ===== 1. 标注格式识别（仅用于摘要展示，页面方向由构造参数锁定）=====
        if result.source_format == Format.LABELME:
            # OCR 任务输出 PaddleOCR 标注（det/rec），非 YOLO TXT
            direction_text = (
                "LabelMe (JSON) → PaddleOCR (det/rec)"
                if result.task_type == MODE.OCR
                else "LabelMe (JSON) → YOLO (TXT)"
            )
        else:
            direction_text = "YOLO (TXT) → LabelMe (JSON)"

        # ===== 2. 任务类型推断 =====
        task_idx = self.task_combo.findData(result.task_type)
        if task_idx >= 0:
            self.task_combo.setCurrentIndex(task_idx)  # 触发 _on_task_changed
        task_names = {
            MODE.DETECT: "目标检测 (DETECT)",
            MODE.POSE: "姿态估计 (POSE)",
            MODE.SEGMENT: "实例分割 (SEGMENT)",
            MODE.OCR: "文字识别 (OCR)",
        }
        shape_text = "、".join(
            f"{k} {v} 个" for k, v in result.shape_counts.items()
        )

        # ===== 3. 标签提取：填充类别列表与关键点类别集合 =====
        if result.labels or result.kpt_labels:
            # LabelMe 方向：直接使用标注中的标签名。
            # POSE 数据集：point 类型标签属于关键点类别集合，单独填充
            # 关键点列表，不混入普通类别列表（否则转换时关键点全部丢失）
            if result.kpt_labels:
                kpt_lower = {k.lower() for k in result.kpt_labels}
                box_labels = [
                    l for l in result.labels if l.lower() not in kpt_lower
                ]
                self._fill_class_list(box_labels)
                self._fill_kpt_list(result.kpt_labels)
                labels_text = (
                    f"提取类别 {len(box_labels)} 个、关键点 {len(result.kpt_labels)} 个，"
                    f"已分别填充至类别列表与关键点列表（可修改）"
                )
            elif result.labels:
                self._fill_class_list(result.labels)
                labels_text = (
                    f"提取标签 {len(result.labels)} 个: " + ", ".join(result.labels)
                )
            else:
                labels_text = "仅提取到关键点标签，未检测到普通类别（矩形框）"
        elif result.source_format == Format.YOLO:
            # TXT 方向：标注不含标签名，类别列表为空时按类别索引自动填充
            # （默认使用索引作为标签名，用户可在下方列表中修改）
            if self._collect_classes():
                labels_text = "已保留当前类别列表（可在高级设置中修改名称与顺序）"
            else:
                index_names = [str(i) for i in range(result.max_class_id + 1)]
                if index_names:
                    self._fill_class_list(index_names)
                    labels_text = (
                        f"TXT 标注不含标签名，已按类别索引自动填充 {len(index_names)} 个类别，"
                        f"请在转换前按实际需求修改名称"
                    )
                else:
                    labels_text = "TXT 标注为空，未填充类别"
        else:
            labels_text = "未从标注中提取到标签"

        # ===== 3.5 POSE 任务：按推断关键点数自动填充关键点列表 =====
        kpt_text = ""
        if (
            result.source_format == Format.YOLO
            and result.task_type == MODE.POSE
            and result.kpt_count > 0
            and not self._collect_kpt()
        ):
            # 关键点名称须以 _point{序号} 结尾（默认 kpt{i}_point{i}，可修改）
            self._fill_kpt_list(
                [f"kpt{i}_point{i}" for i in range(result.kpt_count)]
            )
            kpt_text = (
                f"已按标注格式推断关键点 {result.kpt_count} 个并自动填充，"
                f"请按实际含义修改名称（须以 _point{{序号}} 结尾）"
            )

        # ===== 4. 汇总展示 =====
        lines = [
            f"目录层级: {result.structure_desc}",
            f"检测到 JSON 标注 {result.json_count} 个、TXT 标注 {result.txt_count} 个、"
            f"图片 {result.image_count} 张",
            f"识别标注格式: {direction_text}",
            f"任务类型（自动推断）: {task_names.get(result.task_type, '未知')}"
            + (f"（标注形状: {shape_text}）" if shape_text else ""),
            labels_text,
        ]
        if kpt_text:
            lines.append(kpt_text)
        if result.orphan_annotations:
            lines.append(
                f"警告: 检测到 {len(result.orphan_annotations)} 个孤立标注文件"
                f"（缺失对应图片，无法转换），详细信息已输出至日志"
            )
        if result.error_files:
            lines.append(
                f"警告: {len(result.error_files)} 个标注文件解析失败（已跳过），详见日志"
            )
            for err_file in result.error_files[:5]:
                self.append_log(f"[分析] 解析失败: {err_file}")
            showMessageBox(
                QMessageBox.Icon.Warning,
                f"{len(result.error_files)} 个标注文件格式异常已跳过：\n"
                + "\n".join(Path(f).name for f in result.error_files[:5])
                + ("..." if len(result.error_files) > 5 else ""),
            )
        self.analysis_summary.setText("\n".join(lines))
        self.append_log(f"[分析] 完成: 方向={direction_text}, "
                        f"任务={result.task_type.name}, 标签数={len(result.labels)}")

    def _fill_class_list(self, labels: list) -> None:
        """用分析出的标签列表重填类别编辑器（带行首索引）。

        Args:
            labels: 标签名列表（列表顺序即类别索引顺序）。
        """
        self.class_list.clear()
        self._class_items.clear()
        for name in labels:
            self._on_add_class()
            self._class_items[-1].edit.setText(name)
        self.class_list.refresh_indices()

    def _fill_kpt_list(self, names: list) -> None:
        """用关键点名称列表重填关键点编辑器。

        Args:
            names: 关键点名称列表（顺序即关键点索引顺序）。
        """
        self.kpt_list.clear()
        self._kpt_items.clear()
        for name in names:
            self._on_add_kpt()
            self._kpt_items[-1].edit.setText(name)

    def _apply_stats(self, stats: dict) -> None:
        """应用主窗口统计结果预填（仅导出方向调用）。

        填充类别列表与关键点列表（keypoints 非空才填，且此时参照一键
        分析逻辑剔除 labels 中的关键点标签，避免混入普通类别列表），
        并按 shape 分组特征与文本证据推断任务类型（point>0→POSE，
        box 类形状过半携带非空 description→OCR，polygon>0→SEGMENT，
        否则 DETECT）。

        Args:
            stats: 统计数据，键为 "labels"（类别名列表，含关键点标签）、
                "keypoints"（关键点名列表）、"shape_counts"（{"rectangle":
                n, "polygon": n, "point": n}）、"text_shape_count"（box 类
                形状中 description 非空的个数，OCR 推断证据，可选）。
        """
        labels = stats.get("labels") or []
        keypoints = stats.get("keypoints") or []
        shape_counts = stats.get("shape_counts") or {}
        text_shape_count = int(stats.get("text_shape_count") or 0)
        # 类别列表预填：keypoints 非空时按一键分析同样逻辑剔除关键点标签
        # （大小写不敏感比较），防止关键点标签混入普通类别列表导致转换丢失
        box_labels = labels
        if labels:
            if keypoints:
                kpt_lower = {k.lower() for k in keypoints}
                box_labels = [l for l in labels if l.lower() not in kpt_lower]
            self._fill_class_list(box_labels)
        # 关键点列表预填
        if keypoints:
            self._fill_kpt_list(keypoints)
        # 任务类型推断：复用数据集分析的 shape 特征与文本证据推断规则
        task_type = _infer_task_from_shapes(shape_counts, text_shape_count)
        task_idx = self.task_combo.findData(task_type)
        if task_idx >= 0:
            self.task_combo.setCurrentIndex(task_idx)
        # 索引未变化时 currentIndexChanged 不触发，显式同步关键点列表显隐
        self._on_task_changed()
        # 日志说明（类别数用剔除关键点标签后的数量）
        kpt_part = f"、{len(keypoints)} 个关键点" if keypoints else ""
        self.append_log(
            f"[统计] 已复用主窗口扫描统计结果预填 {len(box_labels)} 个类别{kpt_part}"
        )

    def _build_advanced_card(self) -> None:
        """构建高级卡：类别/关键点编辑器、分割比例、可视化/导出、配置导入导出。

        分割比例行与"导出 YOLO 数据集目录结构"复选框仅导出方向显示
        （见 _apply_direction_visibility）。
        """
        self.advanced_card = Card("高级设置")

        # 类别编辑器（支持拖拽排序：行首数字即转换后的类别索引）
        class_row = QHBoxLayout()
        class_row.addWidget(QLabel("类别列表"))
        class_row.addStretch()
        self.btn_add_class = SecondaryButton("+ 添加类别")
        self.btn_add_class.clicked.connect(self._on_add_class)
        class_row.addWidget(self.btn_add_class)
        self.advanced_card.addLayout(class_row)

        self.class_list = DragDropListWidget()
        # 高度自适应：随条目数调整（见 _adjust_list_height），最多显示 5 行
        self.advanced_card.addWidget(self.class_list)

        # 关键点编辑器（仅 POSE 显示，整体包装为容器便于显隐）
        self.kpt_container = QFrame()
        self.kpt_container.setStyleSheet("QFrame { border: 0; }")
        kpt_layout = QVBoxLayout(self.kpt_container)
        kpt_layout.setContentsMargins(0, 0, 0, 0)
        kpt_layout.setSpacing(8)
        self.kpt_label = QLabel("关键点列表（须以 _point{idx} 结尾）")
        self.kpt_label.setStyleSheet("color: #71717a;")
        kpt_layout.addWidget(self.kpt_label)
        kpt_row = QHBoxLayout()
        kpt_row.addStretch()
        self.btn_add_kpt = SecondaryButton("+ 添加关键点")
        self.btn_add_kpt.clicked.connect(self._on_add_kpt)
        kpt_row.addWidget(self.btn_add_kpt)
        kpt_layout.addLayout(kpt_row)
        self.kpt_list = QListWidget()
        # 高度自适应：随条目数调整（见 _adjust_list_height），最多显示 4 行
        kpt_layout.addWidget(self.kpt_list)
        self.advanced_card.addWidget(self.kpt_container)

        # 列表行结构变化（增删/拖拽排序/重填）时同步调整高度
        self.class_list.model().rowsInserted.connect(self._adjust_list_height)
        self.class_list.model().rowsRemoved.connect(self._adjust_list_height)
        self.kpt_list.model().rowsInserted.connect(self._adjust_list_height)
        self.kpt_list.model().rowsRemoved.connect(self._adjust_list_height)
        # 初始高度（空列表最小高度）
        self._adjust_list_height()

        # 分割比例（包装为容器便于按方向整体显隐：仅导出方向显示）
        self.ratio_container = QWidget()
        ratio_layout = QHBoxLayout(self.ratio_container)
        ratio_layout.setContentsMargins(0, 0, 0, 0)
        self.spin_train = LabeledSpin("训练集", "double", 0, 1, 0.05, 0.8)
        self.spin_val = LabeledSpin("验证集", "double", 0, 1, 0.05, 0.1)
        self.spin_test = LabeledSpin("测试集", "double", 0, 1, 0.05, 0.1)
        ratio_layout.addWidget(self.spin_train)
        ratio_layout.addWidget(self.spin_val)
        ratio_layout.addWidget(self.spin_test)
        self.advanced_card.addWidget(self.ratio_container)

        # 可视化 / 导出
        opt_row = QHBoxLayout()
        self.chk_visualize = QCheckBox("可视化标注结果")
        self.chk_export = QCheckBox("导出 YOLO 数据集目录结构")
        opt_row.addWidget(self.chk_visualize)
        opt_row.addWidget(self.chk_export)
        opt_row.addStretch()
        self.advanced_card.addLayout(opt_row)

        # OCR 专属参数区（包装为容器便于显隐：仅导出方向且任务类型为 OCR
        # 时显示，见 _on_task_changed）；两个参数对应 ConvertConfig 的
        # ocr_gen_rec / ocr_use_space_char 字段，默认均勾选
        self.ocr_container = QWidget()
        ocr_layout = QHBoxLayout(self.ocr_container)
        ocr_layout.setContentsMargins(0, 0, 0, 0)
        self.chk_ocr_gen_rec = QCheckBox("生成识别数据集 (rec)")
        self.chk_ocr_gen_rec.setChecked(True)
        self.chk_ocr_use_space_char = QCheckBox("字典包含空格字符 (use_space_char)")
        self.chk_ocr_use_space_char.setChecked(True)
        ocr_layout.addWidget(self.chk_ocr_gen_rec)
        ocr_layout.addWidget(self.chk_ocr_use_space_char)
        ocr_layout.addStretch()
        self.advanced_card.addWidget(self.ocr_container)

        # 导入/导出配置
        cfg_row = QHBoxLayout()
        cfg_row.addStretch()
        self.btn_import = SecondaryButton("导入配置")
        self.btn_export = SecondaryButton("导出配置")
        self.btn_import.clicked.connect(self._on_import_config)
        self.btn_export.clicked.connect(self._on_export_config)
        cfg_row.addWidget(self.btn_import)
        cfg_row.addWidget(self.btn_export)
        self.advanced_card.addLayout(cfg_row)

        self.add_widget(self.advanced_card)

    def _build_preview_card(self) -> None:
        """构建文件列表与图像预览卡。

        扫描输入目录后展示标注文件与图片文件列表，支持选择预览。
        预览区自适应缩放，适配不同屏幕分辨率。
        """
        self.preview_card = Card("文件列表与图像预览")
        self.preview_widget = FilePreviewWidget()
        self.preview_widget.setMinimumHeight(280)
        self.preview_card.addWidget(self.preview_widget)
        self.add_widget(self.preview_card)

    def _build_progress_card(self) -> None:
        """构建进度与日志卡。"""
        self.progress_card = Card("进度与日志")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_card.addWidget(self.progress_bar)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 10))
        self.log_edit.setMinimumHeight(160)
        self.progress_card.addWidget(self.log_edit)
        self.add_widget(self.progress_card)

    def _labeled(self, text: str, widget: QWidget) -> QWidget:
        """包装标签 + 控件为水平行容器。"""
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(text)
        lab.setMinimumWidth(72)
        lay.addWidget(lab)
        lay.addWidget(widget)
        return container

    # -------------------------- 任务类型与输入联动 --------------------------
    def _on_task_changed(self) -> None:
        """任务类型变化时切换关键点编辑器、OCR 参数区与 YOLO 结构选项。

        显隐规则：
            - 关键点列表仅 POSE 任务显示；
            - OCR 专属参数区（rec 数据集 / use_space_char 字典）仅导出
              方向且任务类型为 OCR 时显示，导入方向 PPOCR det→JSON 不
              生成识别数据集故恒隐藏；
            - 分割比例行与"导出 YOLO 数据集目录结构"复选框仅导出方向
              且非 OCR 任务显示（DETECT/POSE/SEGMENT 的 YOLO TXT 导出
              才有 train/val/test 划分与 images/labels 结构；OCR 导出
              PPOCR 标注结构不适用），隐藏时同步取消勾选防残留状态。
        """
        mode = self.task_combo.currentData()
        is_pose = mode == MODE.POSE
        is_ocr = mode == MODE.OCR
        self.kpt_container.setVisible(is_pose)
        # OCR 参数区：仅导出方向 + OCR 任务显示（导入方向不适用）
        self.ocr_container.setVisible(is_ocr and self._direction == "export")
        # YOLO 数据集结构选项：仅导出方向且非 OCR 任务显示
        show_yolo_opts = self._direction == "export" and not is_ocr
        self.ratio_container.setVisible(show_yolo_opts)
        self.chk_export.setVisible(show_yolo_opts)
        if not show_yolo_opts:
            # 隐藏时取消勾选，防止历史勾选状态经 collect_config 残留到
            # OCR 转换配置（PPOCR 导出链路不消费该值，此处保证语义干净）
            self.chk_export.setChecked(False)

    def _on_input_changed(self, path: str) -> None:
        """输入路径变化时统计文件数量并填充预览列表。

        导入方向由输入目录控件信号触发；导出方向由构造函数对工作路径
        直接调用（无输入目录控件）。按数据集目录层级自动识别
        （label/image/dataset 层级或平铺），标注与图片分别从解析出的
        对应目录扫描。
        """
        if not path or not Path(path).exists():
            self.count_label.setText("未选择目录")
            self.preview_widget.clear()
            return
        # 目录层级识别 + 分目录扫描（label 层级自动找兄弟 images 目录等）
        scan = scan_dataset_files(path)
        # 标注文件类型按方向选择（导出→JSON / 导入→TXT）
        if self._direction == "export":
            anno_files, label = scan["json_files"], "JSON 标注"
        else:
            anno_files, label = scan["txt_files"], "TXT 标注"
        image_files = scan["image_files"]
        self.count_label.setText(
            f"[{scan['structure']}] 已扫描到 {len(anno_files)} 个 {label}，"
            f"{len(image_files)} 张图片"
        )
        # 预览列表仅显示图片（标注文件无预览价值，不再混入）
        self.preview_widget.set_files(sorted(set(image_files)))

    # -------------------------- 类别/关键点编辑器 --------------------------
    def _adjust_list_height(self, *args) -> None:
        """按条目数自适应调整类别/关键点列表高度。

        高度 = min(条目数, 最大可见行数) × 实际行高 + 内边距，
        超出部分由列表内部滚动；行高取自实际渲染度量，随分辨率/DPI
        缩放自然适配。超过最大可见行数时列表可滚动。

        Args:
            *args: 兼容 Qt 行结构信号的位置参数（忽略）。
        """
        # (列表, 最大可见行数, 空列表时的最小高度)
        configs = [
            (self.class_list, 5, 44),
            (self.kpt_list, 4, 44),
        ]
        for lst, max_visible, min_h in configs:
            count = lst.count()
            if count == 0:
                lst.setFixedHeight(min_h)
                continue
            # 取首/末行的实际渲染行高（随字体与 DPI 缩放）
            row_h = max(lst.sizeHintForRow(0), lst.sizeHintForRow(count - 1))
            if row_h <= 0:
                row_h = lst.itemWidget(lst.item(0)).sizeHint().height()
            visible = min(count, max_visible)
            # +12px：列表上下内边距与边框
            lst.setFixedHeight(max(min_h, visible * row_h + 12))

    def _on_add_class(self) -> None:
        """添加一个类别编辑项（带行首索引标签，支持拖拽排序）。"""
        item = QListWidgetItem()
        widget = CustomItemWidget("", self.class_list, check=False, show_index=True)
        item.setSizeHint(widget.sizeHint())
        self.class_list.addItem(item)
        self.class_list.setItemWidget(item, widget)
        self._class_items.append(widget)

    def _on_add_kpt(self) -> None:
        """添加一个关键点编辑项。"""
        item = QListWidgetItem()
        widget = CustomItemWidget("", self.kpt_list, check=True, checked=False)
        item.setSizeHint(widget.sizeHint())
        self.kpt_list.addItem(item)
        self.kpt_list.setItemWidget(item, widget)
        self._kpt_items.append(widget)

    def _collect_classes(self) -> list:
        """收集类别列表。"""
        classes = []
        for i in range(self.class_list.count()):
            item = self.class_list.item(i)
            widget = self.class_list.itemWidget(item)
            if widget and widget.get_text().strip():
                classes.append(widget.get_text().strip())
        return classes

    def _collect_kpt(self) -> dict:
        """收集关键点配置 {name: {"isChecked": bool, "bbox_size": int}}。"""
        kpt = {}
        for i in range(self.kpt_list.count()):
            item = self.kpt_list.item(i)
            widget = self.kpt_list.itemWidget(item)
            if widget and widget.get_text().strip():
                name = widget.get_text().strip()
                try:
                    bbox_size = int(widget.get_check_size())
                except (ValueError, AttributeError):
                    bbox_size = 10
                kpt[name] = {"isChecked": widget.get_check_status(), "bbox_size": bbox_size}
        return kpt

    # -------------------------- 配置读写 --------------------------
    def collect_config(self, sys_config: SysConfig) -> None:
        """从界面收集配置写入 sys_config。

        Args:
            sys_config: 系统配置对象（就地更新）。
        """
        sys_config.task_type = self.task_combo.currentData()
        cc = sys_config.convert_config
        cc.direction = self._direction
        # 输入目录：导出=只读工作路径 / 导入=界面输入目录
        cc.input_dir = (
            self._work_path if self._direction == "export" else self.input_field.path()
        )
        cc.output_dir = self.output_field.path()
        cc.classes = self._collect_classes()
        cc.kpt = self._collect_kpt()
        cc.visualize = self.chk_visualize.isChecked()
        cc.export = self.chk_export.isChecked()
        # OCR 专属参数（导出 JSON→PPOCR 时生成 rec 识别数据集与字典空格字符）
        cc.ocr_gen_rec = self.chk_ocr_gen_rec.isChecked()
        cc.ocr_use_space_char = self.chk_ocr_use_space_char.isChecked()
        cc.train_ratio = self.spin_train.value()
        cc.val_ratio = self.spin_val.value()
        cc.test_ratio = self.spin_test.value()
        # 扫描输入目录的标注与图片文件
        self._scan_input_files(cc)

    def _scan_input_files(self, cc: ConvertConfig) -> None:
        """扫描输入目录的标注与图片文件，填入运行期字段。

        按目录层级识别结果分目录扫描（label 层级自动取兄弟 images 目录
        的图片、image 层级自动取兄弟 labels 目录的标注等）。

        Args:
            cc: 转换配置对象。
        """
        cc.annotation_files = []
        cc.image_files = []
        if not cc.input_dir or not Path(cc.input_dir).exists():
            return
        scan = scan_dataset_files(cc.input_dir)
        # 标注文件类型按方向选择（导出→JSON / 导入→TXT）
        if cc.direction == "export":
            cc.annotation_files = scan["json_files"]
        else:
            cc.annotation_files = scan["txt_files"]
        cc.image_files = scan["image_files"]

    def apply_config(self, sys_config: SysConfig) -> None:
        """从 sys_config 回填界面控件。

        序列化配置不再包含格式与路径（方向由页面构造参数决定，输入/
        输出目录由用户在界面上选择），仅回填任务类型、类别、关键点、
        分割比例与选项。

        Args:
            sys_config: 系统配置对象。
        """
        cc = sys_config.convert_config
        # 任务类型
        tidx = self.task_combo.findData(sys_config.task_type)
        if tidx >= 0:
            self.task_combo.setCurrentIndex(tidx)
        self._on_task_changed()
        # 类别
        self.class_list.clear()
        self._class_items.clear()
        for name in cc.classes:
            self._on_add_class()
            self._class_items[-1].edit.setText(name)
        # 关键点
        self.kpt_list.clear()
        self._kpt_items.clear()
        for name, info in cc.kpt.items():
            self._on_add_kpt()
            w = self._kpt_items[-1]
            w.edit.setText(name)
            if w.check:
                w.check.setChecked(info.get("isChecked", False))
            if w.checkEdit:
                w.checkEdit.setText(str(info.get("bbox_size", 10)))
        # 比例与选项
        self.spin_train.set_value(cc.train_ratio)
        self.spin_val.set_value(cc.val_ratio)
        self.spin_test.set_value(cc.test_ratio)
        self.chk_visualize.setChecked(cc.visualize)
        self.chk_export.setChecked(cc.export)
        # 末尾重跑任务联动：chk_export 的勾选在 _on_task_changed 之后写入，
        # OCR/导入方向下显隐规则（隐藏时取消勾选防残留）会被绕过，故统一
        # 复位一次（非 OCR 导出方向时勾选状态原样保留，无副作用）
        self._on_task_changed()

    # -------------------------- 配置导入导出 --------------------------
    def _on_import_config(self) -> None:
        """导入 JSON 配置文件并回填界面。

        兼容旧版配置（参考 D:\\data\\CCA\\convert_config.json）：
            - ``mode`` 键作为任务类型（旧版），``task_type`` 键（新版），两者均接受
            - 旧版废弃键（``source_format``/``target_format`` 等）与运行期
              字段键（``input_dir``/``output_dir`` 等）由
              ConvertConfig.from_dict 按序列化字段白名单过滤静默忽略，
              仅恢复有效字段（classes/kpt/visualize/export/比例）
            - 旧版 camelCase 键（``visualized``）自动迁移为 ``visualize``
        """
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            None, "导入转换配置", "", "JSON 配置 (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cc = ConvertConfig.from_dict(data)
            sys_config = SysConfig()
            sys_config.convert_config = cc
            # 任务类型兼容：优先 task_type（新版），回退 mode（旧版参考标准）
            from ..config import _coerce_mode

            if "task_type" in data:
                sys_config.task_type = _coerce_mode(data["task_type"])
            elif "mode" in data:
                sys_config.task_type = _coerce_mode(data["mode"])
            self.apply_config(sys_config)
            self.append_log(f"[配置] 已导入配置: {path}")
        except Exception as e:
            LOGGER.error(f"导入转换配置失败: {e}")
            self.append_log(f"[错误] 导入配置失败: {e}")
            showMessageBox(QMessageBox.Icon.Critical, f"导入配置失败:\n{e}")

    def _on_export_config(self) -> None:
        """收集界面配置并导出为 JSON 文件。

        同时写入 ``mode`` 与 ``task_type`` 以兼容旧版与新版配置读取。
        """
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            None, "导出转换配置", "convert_config.json", "JSON 配置 (*.json)"
        )
        if not path:
            return
        try:
            sys_config = SysConfig()
            self.collect_config(sys_config)
            data = sys_config.convert_config.to_dict()
            # 同时写入 mode（旧版兼容）与 task_type（新版）
            data["mode"] = sys_config.task_type.name
            data["task_type"] = sys_config.task_type.name
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.append_log(f"[配置] 已导出配置至: {path}")
        except Exception as e:
            LOGGER.error(f"导出转换配置失败: {e}")
            self.append_log(f"[错误] 导出配置失败: {e}")

    # -------------------------- worker 集成 --------------------------
    def set_worker(self, worker) -> None:
        """绑定转换 worker 并连接信号（重复绑定时先断开旧连接）。

        常驻 worker 可能随对话框多次打开被重复绑定，直接 connect 会造成
        信号重复连接（日志重复输出）：绑定同一 worker 时先断开旧连接再重连。
        注意 PySide6 6.11 对未连接的 disconnect 仅输出告警而不抛异常，
        故记录上次绑定对象、仅在确有旧连接时才 disconnect。

        Args:
            worker: ConvertWorker 实例。
        """
        self._worker = worker
        # 同一 worker 重复绑定 → 先断开旧连接（try 兜底未连接的情况）；
        # 首次绑定或更换 worker 时旧连接随旧 worker 失效，直接连接即可
        if worker is not None and self._bound_worker is worker:
            for sig, slot in (
                (worker.progress_updated, self.update_progress),
                (worker.progress_desc, self.append_log),
                (worker.error_occurred, self._on_error),
                (worker.task_finished, self._on_task_finished),
            ):
                try:
                    sig.disconnect(slot)
                except RuntimeError:
                    pass  # 未连接，无需断开
        worker.progress_updated.connect(self.update_progress)
        worker.progress_desc.connect(self.append_log)
        worker.error_occurred.connect(self._on_error)
        worker.task_finished.connect(self._on_task_finished)
        self._bound_worker = worker
        # 接入 Qt 日志处理器，将 LOGGER 输出推送到日志面板；
        # parent 传主窗口（长生命周期），避免页面随临时对话框销毁后 handler 失效
        qt_handler = add_qt_handler(parent=self.window(), max_lines=500)
        if qt_handler is not None:
            # 同一 handler 重复绑定 → 先断开旧连接再重连（handler 失效
            # 重建后为新实例、无旧连接，直接连接即可）
            if self._log_handler is qt_handler:
                try:
                    qt_handler.log_signal.disconnect(self.append_log)
                except RuntimeError:
                    pass  # 未连接，无需断开
            qt_handler.log_signal.connect(self.append_log)
        self._log_handler = qt_handler

    def _on_start(self) -> None:
        """开始转换任务。"""
        if self._worker is None:
            return
        sys_config = SysConfig()
        self.collect_config(sys_config)
        # 校验必填项：导入方向检查输入/输出目录，导出方向仅检查输出目录
        # （输入由主窗口前置检查保证，且下方校验 annotation_files 非空）
        cc = sys_config.convert_config
        if self._direction == "import" and not cc.input_dir:
            showMessageBox(QMessageBox.Icon.Warning, "请选择输入目录")
            return
        if not cc.output_dir:
            showMessageBox(QMessageBox.Icon.Warning, "请选择输出目录")
            return
        # 导出方向（json→txt）必须提供类别列表（生成类别索引映射）；
        # 导入方向（txt→json）允许为空：转换器自动以类别索引作为标签名（可在转换前于界面修改）
        if not cc.classes and self._direction == "export":
            showMessageBox(QMessageBox.Icon.Warning, "请至少添加一个类别（可使用一键分析自动填充）")
            return
        # 导出方向（JSON→YOLO）拦截：collect_config 内部已扫描输入目录，
        # 扫描不到任何 JSON 标注时直接终止，避免空任务
        if self._direction == "export" and not cc.annotation_files:
            showMessageBox(QMessageBox.Icon.Warning, "当前工作路径下没有 JSON 格式标注")
            return
        self._worker.setConfig(sys_config)
        self.progress_bar.setValue(0)
        self.log_edit.clear()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        # 暂停按钮复位（新任务从运行态开始）
        self._paused = False
        self.btn_pause.setText("暂停")
        self.btn_pause.setEnabled(True)
        self.task_started.emit()
        self._task_success = True  # 默认视为成功，出错时在 _on_error 置 False
        self._worker.start()

    def _on_pause(self) -> None:
        """暂停/恢复转换任务（切换文案，经 BaseWorker 原语挂起/唤醒）。

        暂停经 BaseWorker.run_callback 的 QWaitCondition 阻塞实现——
        当前文件处理完成后挂起，任务不中断；恢复后从断点继续。
        """
        if self._worker is None:
            return
        self._paused = not self._paused
        if self._paused:
            self._worker.pause()
            self.btn_pause.setText("恢复")
        else:
            self._worker.resume()
            self.btn_pause.setText("暂停")

    def _on_stop(self) -> None:
        """停止转换任务。"""
        if self._worker is not None:
            self._worker.stop()

    def update_progress(self, progress: float) -> None:
        """更新进度条。

        Args:
            progress: 进度值 0-1。
        """
        self.progress_bar.setValue(int(progress * 100))

    def append_log(self, message: str) -> None:
        """追加一行日志并自动滚动到底部。

        Args:
            message: 日志文本。
        """
        self.log_edit.appendPlainText(message)
        self.log_edit.verticalScrollBar().setValue(
            self.log_edit.verticalScrollBar().maximum()
        )

    def _on_error(self, message: str) -> None:
        """处理错误信号。"""
        self._task_success = False  # 任务出错，标记本次任务失败
        self.append_log(f"[错误] {message}")
        showMessageBox(QMessageBox.Icon.Critical, message)

    def _on_task_finished(self) -> None:
        """任务结束回调。

        导入方向（YOLO→JSON）且本次任务成功时，发射 import_finished
        信号（携带输出目录），供外部刷新标注列表等后续处理。
        """
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        # 暂停按钮复位（任务结束/中止后不可再恢复）
        self._paused = False
        self.btn_pause.setText("暂停")
        self.btn_pause.setEnabled(False)
        # 导入方向任务成功完成：通知外部（输出目录为界面当前输出路径）
        if self._direction == "import" and self._task_success:
            self.import_finished.emit(self.output_field.path())
        self.task_finished.emit()

    def title(self) -> str:
        """返回页面标题。"""
        return "格式转换"
