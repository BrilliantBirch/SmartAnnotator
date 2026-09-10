# -*- coding: utf-8 -*-
"""
主窗口 - MainWindow（标注编辑器）

主体布局（参考 labelme / X-Anylabel）：
    - 顶部：快捷操作栏（LeftToolbar，QToolBar）—— 文件操作/标注工具
    - 中央：标注画布（Canvas）—— 图像显示 + 标注绘制/编辑
    - 右侧：三个列表 Dock（QDockWidget 分别承载 LabelSection/
      ObjectSection/FileSection，纵向堆叠）——堆叠高度由 Dock 间分隔条
      拖拽调节、挂靠左右边界时宽度由 Dock 与中央控件间分隔条拖拽调节，
      可移动/浮动/关闭；Dock 布局（位置/尺寸/显隐）随渲染配置
      dock_state 持久化

标准菜单栏（文件/编辑/视图/工具/统计/帮助）+ 快捷键体系：
    - 文件：打开文件夹 Ctrl+O、打开文件 Ctrl+Shift+O、保存 Ctrl+S、
      另存为 Ctrl+Shift+S、自动保存（勾选后切换图片时自动保存）
    - 编辑：编辑模式 Ctrl+E、撤销 Ctrl+Z、重做 Ctrl+Shift+Z、删除选中标注、
      清空标注、Delete 按焦点上下文删除、删除图片及标注 Shift+Delete
    - 视图：渲染开关与档位、对象面板开关与三分区显隐
    - 工具：标注工具（编辑/矩形/点/多边形）、加载模型、自动标注单张/
      全部/视频、导出/导入标注（自动标注入口唯一收敛于此菜单）
    - 图片浏览：A 上一张、D 下一张

标注数据完全复用 labelme JSON（core/labelme_io.py）。目录校验、后台标签
扫描（修复打开目录卡死）、绘制完成属性弹窗、类别颜色一致性均在此实现。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-03 labelme 风格属性弹窗、画布右键完整上下文菜单、移除预览模式、
      画布多选同步对象列表选中
更新: 2026-09-03 空 label 形状静默丢弃、标签单一数据源、Delete 焦点路由、画布完整右键菜单、移除删除标注文件与标签新增按钮
更新: 2026-09-03 修复 Delete 焦点路由对象列表分支 selectedItems 误调 row() 导致的崩溃
更新: 2026-09-03 新增视图菜单（渲染开关与线宽/不透明度/字号档位，配置持久化 %APPDATA%/BrilliantAnnotator）、对象列表显示组号
更新: 2026-09-03 画布与右栏之间加水平分栏（宽度可拖拽）、右栏列表垂直分栏
      （高度可拖拽），布局尺寸持久化到 render_config.json（防抖落盘）
更新: 2026-09-04 ONNX → engine 转换结果由状态栏消息改为弹窗提醒（成功/
      失败），转换进行中重复保存配置时弹窗拦截避免并发转换
更新: 2026-09-04 GPU 推理切换为 onnxruntime CUDA EP：移除 TensorRT
      转换链路（_maybe_convert_onnx_to_engine/_convert_notify/
      _engine_converting 及预检 engine 检查），模型格式预检改为仅 .onnx
更新: 2026-09-03 修复初次打开大目录标签列表长时间为空：_start_label_scan
      清空后立即按当前画布重建标签列表；扫描支持逐文件中断与进度提示
      （状态栏），停止后不再发射过期结果；标签强制转字符串防混合类型崩溃
更新: 2026-09-03 列表复选框接线（对象/关键点列表可见性控制、point 形状分流关键点列表、文件列表只读已标注复选框、Delete 路由关键点分支）
更新: 2026-09-03 模型加载窗口精简：仅保留模型加载（GPU 下 onnx 经用户确认
      关窗后转 engine）与推理参数；任务类型按模型元数据自动推导（失败可手动选）
更新: 2026-09-03 扫描手动化：新增统计菜单（扫描并统计/自动扫描开关持久化），
      扫描弹出进度对话框（可中止），完成后弹统计表格；默认打开文件夹
      不自动扫描（标签按已读图片累加、不合并大小写，仅扫描结果合并）
更新: 2026-09-03 标注入口统一：单张标注改常驻 worker（修复局部变量被
      回收导致的 QThread 闪退）；"标注所有图片"不再重复打开模型设置窗
      （资源预检 + 跳过/覆盖选项 + 覆盖前清理老标注文件）；新增"标注
      视频"（菜单+导航栏，抽帧间隔默认 10 帧）；标注统一为模态进度
      窗口（进度条 + 日志 + 可中止），期间禁止预览与编辑
更新: 2026-09-03 视频标注升级为独立窗口（输入路径/帧间隔/输出默认
      Input/Output；文件列表 QTimer 分批动态遍历防大目录卡死；预览
      播放器支持播放暂停/快进后退/变速/进度拖动；抽帧文件以
      "视频名+帧Id"命名；损坏视频帧位停滞/空帧强制终止防死循环）
更新: 2026-09-04 格式转换入口拆分为"导出标注 (JSON → YOLO)"与
      "导入标注 (YOLO → JSON)"（ConvertPage direction 参数化）；导入
      完成后自动打开输出路径作为工作路径（_open_workdir 复用）
更新: 2026-09-04 扫描统计缓存（_label_stats_cache：labels/keypoints/
      shape_counts）随四参数 labels_ready 更新、切换工作路径时清空；
      导出对话框前置检查（工作路径/图片/JSON 标注）并传参
      work_path + stats 复用统计预填（删除旧 input_field 预填代码）
更新: 2026-09-04 右栏文件列表 QListView 化（RightPanel 内嵌 FileListModel，
      UI 虚拟化大目录不卡顿）；Delete 路由文件列表分支改用 currentIndex
更新: 2026-09-07 对象列表合并：全部形状（含 point）统一进对象列表并按
      组色/标签色传入圆点颜色；移除关键点列表维护（_refresh_keypoints、
      关键点信号连接、Delete 关键点焦点分支）；分栏高度记忆改为三组列表
更新: 2026-09-07 布局收口：快捷工具栏改挂顶部 QToolBar（锁定顶部区域），
      画布直接作为中央控件（移除水平分栏与左栏固定宽度）；右栏改由
      QDockWidget"对象面板"承载（可移动/浮动/关闭），窗口布局状态经
      QMainWindow saveState/restoreState 持久化到渲染配置（dock_state
      base64 字段，替代原右栏宽度字段）；视图菜单新增右栏三分区显隐与
      对象面板开关；删除左栏"自动标注"分组（按钮/信号/禁用方法），
      自动标注入口唯一收敛到工具菜单 QAction
更新: 2026-09-07 文件检索支持：打开工作路径后经 QTimer 分批惰性读取标注
      JSON 的标签集合填充文件列表模型（每批 150 个，列表重建时终止旧
      批次再重启防串目录）；保存标注后同步当前文件标签集合；批量标注
      收尾重启填充（纳入新写入的标签）
更新: 2026-09-07 修复 saveState 警告：右栏 QDockWidget 补设
      objectName（rightPanelDock），确保布局状态可序列化与恢复
更新: 2026-09-07 颜色回归标签制：移除 color_for_group 引用，对象列表
      圆点颜色统一 color_for_label（与画布描边/文本一致）；对象列表
      组号文本 "[G3]" 改 "[3]"；删除三组列表高度记忆链路（
      set_section_heights 调用、_on_right_sizes_changed 方法、
      sizes_changed 信号连接），配合已删 RenderConfig 高度字段防
      运行时 AttributeError
更新: 2026-09-07 视图菜单新增"适应窗口"（Ctrl+0 → canvas.fit_to_window）
      与"关键点大小"档位子菜单（point_size）；绘制中 Ctrl+Z 分流撤销
      草稿末顶点（_on_undo/_on_redo 按 canvas.is_drawing 分流，草稿不
      入全局撤销栈故绘制中忽略重做）；破坏性删除统一确认助手
      _confirm_destructive（删除选中/清空标注/删除图片及标注/对象列表
      删除四入口，可勾选"不再提醒"按操作类型记忆到渲染配置并即时落盘）
更新: 2026-09-07 右侧三分区独立 Dock 化：删除 RightPanel 聚合面板与旧
      rightPanelDock，三分区控件（LabelSection/ObjectSection/
      FileSection）分别装入 labelDock/objectDock/fileDock（右区依次
      addDockWidget 纵向堆叠）；视图菜单删除右栏分区显隐三 QAction 与
      "显示对象面板"开关，改为三个 Dock 的 toggleViewAction（"显示
      标签列表/显示对象列表/显示文件列表"，勾选态随 dock_state 持久化）
更新: 2026-09-07 自定义快捷键系统集成：新增模块级 _ACTION_DEFS 动作定义表
      与 _apply_shortcuts 集中应用（QAction setShortcut + QShortcut 懒创建
      缓存 _shortcut_objs，非法键序列回退 DEFAULT_SHORTCUTS 并告警）；删除
      各处硬编码 setShortcut 字面量、直连 QShortcut 与模块级工具快捷键
      字典（默认值唯一来源收敛到 config.DEFAULT_SHORTCUTS）；工具菜单新增
      "自定义快捷键..."入口（ShortcutDialog 确定后应用并持久化
      shortcuts.json）；关于对话框快捷键清单改为可配置提示文案
更新: 2026-09-08 右栏回归聚合面板：三分区装入单一 RightPanel（rightPanelDock
      承载），视图菜单恢复"显示对象面板"开关并新增三分区显隐三 QAction；
      恢复三分区高度记忆（sizes_changed → RenderConfig 三高度字段防抖
      落盘、启动恢复）；自动保存默认开启并持久化（RenderConfig.auto_save，
      勾选态随配置落盘）；置脏根因修复（新增 _loading 程序性加载守卫，
      打开图片/标注/删图重载/自动标注回填的 set_shapes/clear_shapes 不再
      误置脏）；新增未保存防呆 _confirm_discard_changes（切图/打开/关闭前
      保存-不保存-取消三选确认，自动保存开启时静默落盘）；文件列表双击
      编辑（file_edit_requested → 加载该图并进入编辑模式）；工具栏按钮
      tooltip 快捷键提示随绑定同步（refresh_shortcut_hints）、
      fit_requested 接入画布适应窗口
更新: 2026-09-08 面板宽度自定义迭代：RightPanel 宽度边界 clamp
      （PANEL_MIN_WIDTH=220 / PANEL_MAX_WIDTH=800，Dock 分隔条拖拽
      即时受约束）；新增 RenderConfig.right_panel_width 字段（钳制
      [220, 800]），启动经 resizeDocks 恢复宽度、closeEvent 落盘
      right_panel.width()，布局偏好重启后完整还原
更新: 2026-09-08 三分区再次独立 Dock 化：删除 RightPanel 聚合面板与
      rightPanelDock，三分区控件（LabelSection/ObjectSection/
      FileSection）分别装入 labelDock/objectDock/fileDock（右区依次
      addDockWidget 纵向堆叠，Dock 间分隔条拖拽调堆叠高度、挂靠左右
      边界时 Dock 与中央控件间分隔条拖拽调宽度）；视图菜单改为三个
      Dock 的 toggleViewAction（"显示标签列表/显示对象列表/显示文件
      列表"，勾选态随 dock_state 持久化）；删除三分区高度记忆与
      right_panel_width 链路（_on_right_sizes_changed/resizeDocks
      恢复/closeEvent 落盘），布局位置/尺寸/显隐统一由 dock_state
      承担，无记忆状态时经 resizeDocks 设默认初始尺寸
更新: 2026-09-08 对象列表交互增强：双击条目进入编辑模式（复用
      edit_object_requested → _on_edit_object 链路：切编辑模式 + 属性
      弹窗）；新增拖拽排序链路 objects_reordered → _on_objects_reordered
      → canvas.reorder_shapes（列表顺序即画布形状顺序，置脏与列表
      刷新经 shapes_changed 自动完成，画布选中集合保持）
更新: 2026-09-08 视图菜单新增"阴影不透明度"档位子菜单（0/20/40/60/
      80/100，控制形状文本阴影清晰度；0=无阴影），档位写入
      RenderConfig.text_shadow_opacity 随配置持久化，启动自动恢复
更新: 2026-09-09 删除确认统一为会话级提醒：_confirm_destructive 的
      "不再提醒"改记运行期集合 _confirm_skipped（不再持久化，重启
      恢复默认提醒）；补齐画布右键删除与 Delete 快捷键对象列表分支/
      默认画布分支的确认链路（统一收敛到 _confirm_destructive）；
      "关键点大小"档位最小值下调至 1px 并新增 2px
更新: 2026-09-09 新增在线更新：帮助菜单"检查更新"+ 启动后静默检查
      （后台线程请求 Gitee Release 比对版本），发现新版本经确认后
      下载在线安装器并随主窗口关闭拉起静默安装（closeEvent 收尾）
更新: 2026-09-10 快捷键体系新增三个自动标注动作：annotate_single（标注
      当前图片 Ctrl+1）/annotate_all（标注所有图片 Ctrl+2）/clear_shapes
      （清空当前标注 Ctrl+Shift+C），经 _apply_shortcuts 挂 QShortcut 复用
      现有菜单槽函数（槽内自带防呆/确认框，全标注模式通用）；新增模块级
      _RESERVED_SHORTCUTS 固定保留键表（画布 Esc），快捷键设置对话框
      传入 reserved 增强冲突检测（与不可配置固定键冲突时阻止保存）
"""

import json
import sys
import tempfile
import webbrowser
from copy import deepcopy
from pathlib import Path
from typing import Dict

from PySide6.QtCore import Qt, QTimer, QByteArray
from PySide6.QtGui import QAction, QKeySequence, QActionGroup, QIcon, QShortcut, QCursor
from PySide6.QtWidgets import (
    QMainWindow,
    QVBoxLayout,
    QLabel,
    QDialog,
    QFileDialog,
    QDialogButtonBox,
    QMessageBox,
    QMenu,
    QCheckBox,
    QApplication,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QDockWidget,
    QProgressDialog,
)

from . import __appname__, __version__
from .styles import GLOBAL_QSS
from .config import SysConfig, RenderConfig, DEFAULT_SHORTCUTS
from .core import labelme_io
from .core.updater import (
    RELEASE_PAGE_URL,
    UpdaterError,
    detect_install_mode,
    run_installer,
)
from .utils import LOGGER, getImageFilesInDir, getJsonFilesInDir, getVideoFilesInDir
from .utils.render_store import load_render_config, save_render_config, load_shortcuts, save_shortcuts
from .widgets.dialogs import chooseDir, showMessageBox
from .widgets.annotate_dialogs import AnnotateOptionsDialog, AnnotateProgressDialog
from .widgets.video_annotate_dialog import VideoAnnotateDialog
from .widgets.left_toolbar import (
    LeftToolbar,
    TOOL_SELECT,
    TOOL_RECTANGLE,
    TOOL_POINT,
    TOOL_POLYGON,
)
from .widgets import FileSection, LabelSection, ObjectSection
from .widgets.canvas import Canvas, color_for_label
from .widgets.shape_dialog import ShapeDialog
from .widgets.scan_stats_dialog import ScanProgressDialog, ScanStatsDialog
from .widgets.manual_dialog import ManualDialog
from .widgets.shortcut_dialog import ShortcutDialog
from .pages.annotate_page import AnnotatePage
from .pages.convert_page import ConvertPage
from .workers.annotate_worker import AnnotationWorker
from .workers.convert_worker import ConvertWorker
from .workers.single_annotate_worker import SingleAnnotateWorker
from .workers.label_scan_worker import LabelScanWorker
from .workers.update_worker import UpdateCheckWorker, UpdateDownloadWorker

# 工具名 -> 显示文案
_TOOL_LABELS = {
    TOOL_SELECT: "编辑",
    TOOL_RECTANGLE: "矩形",
    TOOL_POINT: "点",
    TOOL_POLYGON: "多边形",
}

# 动作定义表（action_id -> 中文描述，顺序即快捷键设置对话框中的显示顺序；
# 键与 config.DEFAULT_SHORTCUTS 一一对应，默认键值唯一来源为 DEFAULT_SHORTCUTS）
_ACTION_DEFS: Dict[str, str] = {
    "open": "打开文件夹",
    "open_file": "打开文件",
    "save": "保存标注",
    "save_as": "另存为标注",
    "edit_mode": "切换编辑模式",
    "undo": "撤销",
    "redo": "重做",
    "copy": "复制选中标注",
    "paste": "粘贴标注",
    "tool_select": "编辑工具",
    "tool_rectangle": "矩形工具",
    "tool_point": "点工具",
    "tool_polygon": "多边形工具",
    "delete": "删除选中标注",
    "delete_image": "删除图片及标注",
    "prev_image": "上一张图片",
    "next_image": "下一张图片",
    "fit_window": "适应窗口",
    "annotate_single": "标注当前图片",
    "annotate_all": "标注所有图片",
    "clear_shapes": "清空当前标注",
}

# 固定保留键（不可配置，QKeySequence PortableText → 固定功能描述）：
# 画布 Esc 经 keyPressEvent 处理（取消绘制/框选/端点拖动），QShortcut
# 会先于按键事件拦截同键，若分配给可配置动作将导致画布取消失效，
# 故快捷键设置对话框必须阻止用户绑定该键
_RESERVED_SHORTCUTS: Dict[str, str] = {
    "Esc": "画布取消绘制/拖动",
}

# 标签惰性填充每批处理的标注 JSON 数（事件循环分批间让出 UI，万级目录不卡顿）
_TAG_FILL_BATCH_SIZE = 150


class MainWindow(QMainWindow):
    """应用主窗口 - 标注编辑器（顶部工具栏 + 中央画布 + 右侧对象面板）。"""

    def __init__(self):
        """初始化主窗口，构建菜单栏、主体布局并连接信号。"""
        super().__init__()
        self.setWindowTitle(__appname__)
        self.setMinimumSize(960, 640)
        screen = self.screen().availableGeometry()
        self.resize(int(screen.width() * 0.8), int(screen.height() * 0.8))

        # 工作目录与文件列表状态
        self._work_dir: str = ""
        self._image_files: list = []
        self._current_index: int = -1
        self._dirty: bool = False
        # 程序性加载守卫：打开图片/标注回填期间置 True，画布 set_shapes/
        # clear_shapes 触发的 shapes_changed 不误置脏（try/finally 保证复位）
        self._loading: bool = False
        # 删除确认"不再提醒"的会话级记忆（操作类型集合）：不持久化，
        # 应用重启后恢复默认提醒状态
        self._confirm_skipped: set = set()

        # 自动标注配置（加载模型后可用）
        self.annotate_config: "SysConfig | None" = None
        # 后台扫描汇总的标签
        self._all_labels: list = []
        # 扫描统计缓存（当前工作路径的扫描结果，供导出对话框预填）：
        # {"labels": [...], "keypoints": [...], "shape_counts": {...}}；
        # 切换工作路径时清空，扫描完成后更新，None 表示无可用统计
        self._label_stats_cache: "dict | None" = None
        # 画布渲染配置（视图菜单可调，持久化于 %APPDATA%/BrilliantAnnotator）
        self._render_config: RenderConfig = load_render_config()
        # 自动保存（文件菜单勾选项）：切换图片时自动保存当前标注
        # （初值取自渲染配置持久化开关，默认开启；加载在前保证可读取）
        self._auto_save: bool = self._render_config.auto_save
        # 渲染配置防抖落盘定时器（分栏拖拽等高频变更合并为一次写盘）
        self._render_save_timer = QTimer(self)
        self._render_save_timer.setSingleShot(True)
        self._render_save_timer.setInterval(500)
        self._render_save_timer.timeout.connect(self._save_render_config_now)
        # 标签扫描进度对话框（扫描期间存在，非模态；中止/完成后关闭并置空）
        self._scan_progress_dlg: "ScanProgressDialog | None" = None
        # 分批惰性标签填充：打开工作路径后逐批读取标注 JSON 的标签集合
        # （每批 _TAG_FILL_BATCH_SIZE 个，事件循环间让出 UI；队列下标与
        # _image_files 对齐，列表重建时经 _start_tag_fill 终止旧批次再重启）
        self._tag_fill_timer = QTimer(self)
        self._tag_fill_timer.setInterval(0)  # 每轮事件循环处理一批
        self._tag_fill_timer.timeout.connect(self._fill_next_tag_batch)
        self._tag_fill_queue: list[int] = []  # 待填充文件下标队列
        # 使用说明书阅读窗（非模态；已打开时重复触发置前而非重复创建）
        self._manual_dlg: "ManualDialog | None" = None
        # 自动标注运行状态（模态进度对话框 / 任务模式 / 最近错误）
        self._annotate_progress_dlg: "AnnotateProgressDialog | None" = None
        self._annotate_mode: str = ""  # single / all / video（空 = 无任务）
        self._annotate_error: str = ""

        # 后台线程（单张 worker 常驻主窗口，避免局部变量被回收导致
        # "QThread: Destroyed while thread is still running" 闪退）
        self.annotate_worker = AnnotationWorker()
        self.convert_worker = ConvertWorker()
        self.label_scan_worker = LabelScanWorker()
        self.single_annotate_worker = SingleAnnotateWorker()
        # 在线更新线程（常驻复用：检查更新 / 下载安装器，低频任务）
        self._update_check_worker = UpdateCheckWorker()
        self._update_download_worker = UpdateDownloadWorker()
        # 在线更新运行期状态：
        # _update_quiet：本次检查是否静默（启动检查=True，菜单检查=False）
        # _update_dlg：下载进度对话框（下载期间存在，非模态）
        # _pending_update_installer：待拉起的安装器路径（确认关闭后由
        #   closeEvent 收尾启动，复用其脏数据确认与 worker 清理链路）
        self._update_quiet: bool = False
        self._update_dlg: "QProgressDialog | None" = None
        self._pending_update_installer: "Path | None" = None

        # 构建界面
        self._build_menubar()
        self._build_ui()
        self._connect_signals()

        # 应用持久化的渲染配置到画布
        self.canvas.set_render_config(self._render_config)

        # 自定义快捷键体系：加载持久化配置（%APPDATA%/BrilliantAnnotator/
        # shortcuts.json，缺失自动创建默认）并集中应用到 QAction/QShortcut；
        # QShortcut 对象懒创建缓存于 _shortcut_objs，重复应用经 setKey
        # 复用实例，天然幂等不叠加
        self._shortcut_objs: dict = {}
        self._shortcuts_cfg = load_shortcuts()
        self._apply_shortcuts()

        self.setStyleSheet(GLOBAL_QSS)

        self._status_label = QLabel("未打开文件夹")
        self.statusBar().addWidget(self._status_label)

        # 初始目录校验：未打开目录时禁用编辑功能
        self._update_edit_state()

    # -------------------------- 菜单栏 --------------------------
    def _build_menubar(self) -> None:
        """构建菜单栏：文件 / 编辑 / 视图 / 工具 / 统计 / 帮助。"""
        menu_bar = self.menuBar()

        # ===== 文件 =====
        menu_file = menu_bar.addMenu("文件(&F)")
        self.act_open = QAction("打开文件夹", self)
        self.act_open.triggered.connect(self._on_open_folder)
        menu_file.addAction(self.act_open)

        self.act_open_file = QAction("打开文件", self)
        self.act_open_file.triggered.connect(self._on_open_file)
        menu_file.addAction(self.act_open_file)

        menu_file.addSeparator()
        self.act_save = QAction("保存", self)
        self.act_save.triggered.connect(self._on_save)
        menu_file.addAction(self.act_save)

        self.act_save_as = QAction("另存为", self)
        self.act_save_as.triggered.connect(self._on_save_as)
        menu_file.addAction(self.act_save_as)

        # 自动保存：勾选后每次切换图片自动保存当前标注（勾选态随渲染配置
        # 持久化；先 setChecked 再 connect，防构建期 toggled 误触发落盘）
        self.act_autosave = QAction("自动保存", self)
        self.act_autosave.setCheckable(True)
        self.act_autosave.setChecked(self._render_config.auto_save)
        self.act_autosave.toggled.connect(self._on_autosave_toggled)
        menu_file.addAction(self.act_autosave)

        menu_file.addSeparator()
        self.act_exit = QAction("退出", self)
        self.act_exit.triggered.connect(self.close)
        menu_file.addAction(self.act_exit)

        # ===== 编辑 =====
        menu_edit = menu_bar.addMenu("编辑(&E)")
        # 编辑模式：仅编辑模式允许拖拽/端点缩放/属性修改（快捷键经 _apply_shortcuts 统一应用）
        self.act_edit_mode = QAction("编辑模式", self)
        self.act_edit_mode.triggered.connect(self._enter_edit_mode)
        menu_edit.addAction(self.act_edit_mode)

        menu_edit.addSeparator()
        self.act_undo = QAction("撤销", self)
        self.act_undo.triggered.connect(self._on_undo)
        menu_edit.addAction(self.act_undo)

        self.act_redo = QAction("重做", self)
        self.act_redo.triggered.connect(self._on_redo)
        menu_edit.addAction(self.act_redo)

        menu_edit.addSeparator()
        self.act_delete = QAction("删除选中标注", self)
        self.act_delete.triggered.connect(self._on_delete)
        menu_edit.addAction(self.act_delete)

        self.act_clear = QAction("清空标注", self)
        self.act_clear.triggered.connect(self._on_clear)
        menu_edit.addAction(self.act_clear)

        menu_edit.addSeparator()

        self.act_delete_image = QAction("删除图片及标注", self)
        self.act_delete_image.triggered.connect(self._on_delete_image_and_annotation)
        menu_edit.addAction(self.act_delete_image)

        # ===== 视图 =====
        # 引用保留到 self：_build_ui 中向该菜单追加三个列表 Dock 开关动作
        self._menu_view = menu_bar.addMenu("视图(&V)")
        menu_view = self._menu_view

        # 渲染内容开关（checkable）
        self.act_show_label = QAction("显示标签", self)
        self.act_show_label.setCheckable(True)
        self.act_show_label.setChecked(self._render_config.show_label)
        self.act_show_label.toggled.connect(lambda on: self._on_render_option_changed("show_label", on))
        menu_view.addAction(self.act_show_label)

        self.act_show_group = QAction("显示组号", self)
        self.act_show_group.setCheckable(True)
        self.act_show_group.setChecked(self._render_config.show_group)
        self.act_show_group.toggled.connect(lambda on: self._on_render_option_changed("show_group", on))
        menu_view.addAction(self.act_show_group)

        self.act_show_description = QAction("显示描述", self)
        self.act_show_description.setCheckable(True)
        self.act_show_description.setChecked(self._render_config.show_description)
        self.act_show_description.toggled.connect(lambda on: self._on_render_option_changed("show_description", on))
        menu_view.addAction(self.act_show_description)

        menu_view.addSeparator()

        # 框线宽度档位（互斥单选）
        menu_view.addMenu(self._build_render_option_menu(
            "框线宽度",
            [("1px", 1.0), ("2px", 2.0), ("3px", 3.0), ("4px", 4.0)],
            "pen_width",
        ))

        # 填充不透明度档位（互斥单选）
        menu_view.addMenu(self._build_render_option_menu(
            "填充不透明度",
            [("10%", 0.1), ("20%", 0.2), ("30%", 0.3), ("50%", 0.5), ("70%", 0.7)],
            "opacity",
        ))

        # 字体大小档位（互斥单选）
        menu_view.addMenu(self._build_render_option_menu(
            "字体大小",
            [("10", 10), ("12", 12), ("14", 14), ("16", 16), ("20", 20)],
            "font_size",
        ))

        # 阴影不透明度档位（互斥单选，控制形状文本阴影清晰度；0 = 无阴影）
        menu_view.addMenu(self._build_render_option_menu(
            "阴影不透明度",
            [("0", 0), ("20%", 20), ("40%", 40), ("60%", 60), ("80%", 80), ("100%", 100)],
            "text_shadow_opacity",
        ))

        # 关键点大小档位（互斥单选，控制关键点屏幕像素基准半径；
        # 最小 1px，渲染时与画布缩放反向联动）
        menu_view.addMenu(self._build_render_option_menu(
            "关键点大小",
            [("1px", 1.0), ("2px", 2.0), ("3px", 3.0), ("4px", 4.0),
             ("5px", 5.0), ("6px", 6.0), ("8px", 8.0)],
            "point_size",
        ))

        menu_view.addSeparator()

        # 适应窗口（fit 缩放为基准视图，不受缩放档位钳制；
        # 菜单构建早于画布创建，触发时经 lambda 延迟解析 canvas）
        self.act_fit_window = QAction("适应窗口", self)
        self.act_fit_window.triggered.connect(lambda: self.canvas.fit_to_window())
        menu_view.addAction(self.act_fit_window)

        # ===== 工具 =====
        menu_tool = menu_bar.addMenu("工具(&T)")

        # 标注工具（互斥单选；快捷键由 _apply_shortcuts 统一应用）
        self._tool_action_group = QActionGroup(self)
        self._tool_action_group.setExclusive(True)
        self._tool_actions: dict = {}
        for tool in (TOOL_SELECT, TOOL_RECTANGLE, TOOL_POINT, TOOL_POLYGON):
            act = QAction(_TOOL_LABELS[tool], self)
            act.setCheckable(True)
            act.triggered.connect(lambda checked=False, t=tool: self._on_tool_selected(t))
            self._tool_action_group.addAction(act)
            menu_tool.addAction(act)
            self._tool_actions[tool] = act
        self._tool_actions[TOOL_SELECT].setChecked(True)

        menu_tool.addSeparator()
        self.act_load_model = QAction("加载模型 / 自动标注设置", self)
        self.act_load_model.triggered.connect(self._open_annotate_dialog)
        menu_tool.addAction(self.act_load_model)

        self.act_annotate_single = QAction("标注当前图片", self)
        self.act_annotate_single.triggered.connect(self._on_annotate_single)
        menu_tool.addAction(self.act_annotate_single)

        self.act_annotate_all = QAction("标注所有图片", self)
        self.act_annotate_all.triggered.connect(self._on_annotate_all)
        menu_tool.addAction(self.act_annotate_all)

        self.act_annotate_video = QAction("标注视频", self)
        self.act_annotate_video.triggered.connect(self._on_annotate_video)
        menu_tool.addAction(self.act_annotate_video)

        # 自动标注入口动作集合（原左栏自动标注按钮的替代）：无模型时统一
        # 禁用/恢复；"加载模型"不纳入集合——无模型时必须保持可用以便配置
        self._annotate_actions = [
            self.act_annotate_single,
            self.act_annotate_all,
            self.act_annotate_video,
        ]

        self.act_export = QAction("导出标注", self)
        self.act_export.triggered.connect(self._open_export_dialog)
        menu_tool.addAction(self.act_export)

        self.act_import = QAction("导入标注(非json格式->json)", self)
        self.act_import.triggered.connect(self._open_import_dialog)
        menu_tool.addAction(self.act_import)

        # 自定义快捷键设置入口：对话框确定后应用新绑定并持久化 shortcuts.json
        self.act_shortcut_settings = QAction("自定义快捷键...", self)
        self.act_shortcut_settings.triggered.connect(self._on_shortcut_settings)
        menu_tool.addAction(self.act_shortcut_settings)

        # ===== 统计 =====
        menu_stats = menu_bar.addMenu("统计(&S)")

        # 扫描并统计：对当前工作目录启动后台扫描（显式入口）
        self.act_scan_stats = QAction("扫描并统计", self)
        self.act_scan_stats.triggered.connect(self._start_label_scan)
        menu_stats.addAction(self.act_scan_stats)

        # 自动扫描开关：开启后打开文件夹即自动扫描（偏好持久化）
        self.act_auto_scan = QAction("自动扫描", self)
        self.act_auto_scan.setCheckable(True)
        self.act_auto_scan.setChecked(self._render_config.auto_scan_labels)
        self.act_auto_scan.toggled.connect(self._on_auto_scan_toggled)
        menu_stats.addAction(self.act_auto_scan)

        # ===== 帮助 =====
        menu_help = menu_bar.addMenu("帮助(&H)")
        self.act_check_update = QAction("检查更新", self)
        # lambda 固定 quiet=False（菜单手动检查），避免 triggered 的 checked
        # 参数误传给槽的 quiet 形参
        self.act_check_update.triggered.connect(lambda: self._on_check_update(quiet=False))
        menu_help.addAction(self.act_check_update)

        self.act_manual = QAction("使用说明书", self)
        self.act_manual.triggered.connect(self._on_manual)
        menu_help.addAction(self.act_manual)

        menu_help.addSeparator()
        self.act_about = QAction("关于", self)
        self.act_about.triggered.connect(self._on_about)
        menu_help.addAction(self.act_about)

    def _build_render_option_menu(self, title: str, options: list, attr: str) -> QMenu:
        """构建渲染档位子菜单（互斥单选，当前档位打勾）。

        Args:
            title: 子菜单标题。
            options: (显示文本, 配置值) 元组列表。
            attr: RenderConfig 字段名。

        Returns:
            子菜单。
        """
        menu = QMenu(title, self)
        group = QActionGroup(self)
        group.setExclusive(True)
        current = getattr(self._render_config, attr)
        for text, value in options:
            act = QAction(text, self)
            act.setCheckable(True)
            act.setChecked(abs(float(current) - float(value)) < 1e-9)
            act.triggered.connect(
                lambda checked=False, v=value, a=attr: self._on_render_option_changed(a, v)
            )
            group.addAction(act)
            menu.addAction(act)
        return menu

    def _on_render_option_changed(self, attr: str, value) -> None:
        """渲染设置变更：更新配置、应用到画布并即时持久化。

        Args:
            attr: RenderConfig 字段名。
            value: 新配置值。
        """
        setattr(self._render_config, attr, value)
        self.canvas.set_render_config(self._render_config)
        self._save_render_config_now()
        self.statusBar().showMessage(f"渲染设置已更新: {attr} = {value}", 1500)

    def _on_auto_scan_toggled(self, checked: bool) -> None:
        """自动扫描开关切换：更新偏好配置并防抖持久化。

        Args:
            checked: 是否开启（打开文件夹后自动扫描统计）。
        """
        self._render_config.auto_scan_labels = checked
        self._schedule_render_save()
        state = "开启" if checked else "关闭"
        self.statusBar().showMessage(f"自动扫描已{state}：打开文件夹时将{'自动' if checked else '不'}启动标签扫描", 2500)

    # -------------------------- 快捷键体系 --------------------------
    def _resolve_shortcut(self, action_id: str) -> str:
        """解析动作的当前键序列字符串，非法值回退默认绑定。

        Args:
            action_id: 动作 id（须为 DEFAULT_SHORTCUTS 的键）。

        Returns:
            合法的键序列字符串（QKeySequence 可解析且非空）。
        """
        seq = self._shortcuts_cfg.bindings.get(action_id, "")
        # 非法判定：空串，或 QKeySequence 解析为空序列，或解析结果无法
        # 序列化回文本（Qt 对不可识别键名 isEmpty() 可能为 False 但
        # toString() 返回空串，故以 toString 回读双重校验）
        parsed = QKeySequence(seq) if seq else QKeySequence()
        if not seq or parsed.isEmpty() or not parsed.toString():
            LOGGER.warning(f"快捷键 '{seq}' 非法（动作 {action_id}），回退默认绑定")
            seq = DEFAULT_SHORTCUTS[action_id]
            # 回写内存配置保持一致（不主动落盘，落盘仍由设置对话框/save_shortcuts 触发）
            self._shortcuts_cfg.bindings[action_id] = seq
        return seq

    def _apply_shortcuts(self) -> None:
        """将当前快捷键配置集中应用到 QAction 与 QShortcut。

        QAction 类动作直接 setShortcut；QShortcut 类动作懒创建并缓存于
        _shortcut_objs（重复调用复用实例 setKey，天然幂等不叠加）。
        delete 动作固定走 QShortcut 焦点路由，绝不给 act_delete.setShortcut，
        防止同键经 QAction 与 QShortcut 双触发两次确认框。
        """
        # ===== QAction 类动作映射（action_id -> QAction 实例） =====
        qaction_map = {
            "open": self.act_open,
            "open_file": self.act_open_file,
            "save": self.act_save,
            "save_as": self.act_save_as,
            "edit_mode": self.act_edit_mode,
            "undo": self.act_undo,
            "redo": self.act_redo,
            "delete_image": self.act_delete_image,
            "tool_select": self._tool_actions[TOOL_SELECT],
            "tool_rectangle": self._tool_actions[TOOL_RECTANGLE],
            "tool_point": self._tool_actions[TOOL_POINT],
            "tool_polygon": self._tool_actions[TOOL_POLYGON],
            "fit_window": self.act_fit_window,
        }
        # ===== QShortcut 类动作映射（action_id -> 触发槽函数） =====
        # context 保持默认 WindowShortcut，与原直连实现行为一致；
        # 自动标注三动作复用菜单槽函数（槽内自带防呆/确认框，全模式安全）
        qshortcut_slots = {
            "copy": self.canvas.copy_selected,
            "paste": self.canvas.paste_clipboard,
            "delete": self._on_delete_shortcut,
            "prev_image": self._prev_image,
            "next_image": self._next_image,
            "annotate_single": self._on_annotate_single,
            "annotate_all": self._on_annotate_all,
            "clear_shapes": self._on_clear,
        }
        # 应用 QAction 类快捷键（非法键序列已在 _resolve_shortcut 中回退）
        for action_id, act in qaction_map.items():
            act.setShortcut(QKeySequence(self._resolve_shortcut(action_id)))
        # 应用 QShortcut 类快捷键（首次调用创建并挂槽，之后复用实例 setKey）
        for action_id, slot in qshortcut_slots.items():
            if action_id not in self._shortcut_objs:
                shortcut = QShortcut(self)
                shortcut.activated.connect(slot)
                self._shortcut_objs[action_id] = shortcut
            self._shortcut_objs[action_id].setKey(QKeySequence(self._resolve_shortcut(action_id)))
        # 工具栏按钮 tooltip 的快捷键提示随绑定同步（覆盖构造时占位提示）
        self.left_toolbar.refresh_shortcut_hints(self._shortcuts_cfg.bindings, _ACTION_DEFS)

    def _on_shortcut_settings(self) -> None:
        """打开自定义快捷键对话框，确定后应用并持久化。

        对话框内检测两类冲突并阻止保存：可配置动作之间的键冲突、
        与固定保留键（_RESERVED_SHORTCUTS，如画布 Esc）的冲突。
        """
        new_bindings = ShortcutDialog.get_shortcuts(
            _ACTION_DEFS,
            self._shortcuts_cfg.bindings,
            self,
            reserved=_RESERVED_SHORTCUTS,
        )
        if new_bindings is None:
            return
        self._shortcuts_cfg.bindings = new_bindings
        save_shortcuts(self._shortcuts_cfg)
        self._apply_shortcuts()

    # -------------------------- 主体布局 --------------------------
    def _build_ui(self) -> None:
        """构建主体布局：顶部工具栏 + 中央画布 + 右侧对象面板 Dock。"""
        # 顶部快捷工具栏（QToolBar）：挂到主窗口顶部区域并锁定（不放入中央布局）
        self.left_toolbar = LeftToolbar()
        self.left_toolbar.setAllowedAreas(Qt.ToolBarArea.TopToolBarArea)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.left_toolbar)

        # 中央控件：画布直接承载（无额外布局容器与边距，与菜单/工具栏视觉贴合）
        self.canvas = Canvas()
        self.setCentralWidget(self.canvas)

        # 右侧三个列表 Dock：三分区控件分别由独立 QDockWidget 承载，
        # 纵向堆叠于右区——堆叠高度由 Dock 间分隔条拖拽调节，挂靠左右
        # 边界时宽度由 Dock 与中央控件间分隔条拖拽调节（QMainWindow
        # 原生行为）；可移动/浮动/关闭。
        # objectName 为 saveState/restoreState 序列化布局的唯一标识，
        # 缺失会告警且无法恢复
        self.label_section = LabelSection()
        self.object_section = ObjectSection()
        self.file_section = FileSection()
        # Dock 特性统一：可移动/浮动/关闭（用户可自由重排三列表布局）
        dock_features = (
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.label_dock = QDockWidget("标签列表", self)
        self.label_dock.setObjectName("labelDock")
        self.object_dock = QDockWidget("对象列表", self)
        self.object_dock.setObjectName("objectDock")
        self.file_dock = QDockWidget("文件列表", self)
        self.file_dock.setObjectName("fileDock")
        for dock, section in (
            (self.label_dock, self.label_section),
            (self.object_dock, self.object_section),
            (self.file_dock, self.file_section),
        ):
            dock.setFeatures(dock_features)
            dock.setWidget(section)
            # 右区依次加入：同区域多 Dock 默认纵向堆叠
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        # 三个列表 Dock 显隐开关（QDockWidget 自带 toggleViewAction）加入
        # 视图菜单，勾选态随 QMainWindow 布局状态（dock_state）持久化
        for dock, text, tip in (
            (self.label_dock, "显示标签列表", "显示/隐藏标签列表（Dock）"),
            (self.object_dock, "显示对象列表", "显示/隐藏对象列表（Dock）"),
            (self.file_dock, "显示文件列表", "显示/隐藏文件列表（Dock）"),
        ):
            toggle = dock.toggleViewAction()
            toggle.setText(text)
            toggle.setToolTip(tip)
            self._menu_view.addAction(toggle)

        # 应用持久化的窗口布局状态
        self._apply_panel_sizes()

    # -------------------------- 界面布局尺寸 --------------------------
    def _apply_panel_sizes(self) -> None:
        """应用持久化的窗口布局状态（工具栏与三个列表 Dock 的位置/尺寸）。

        dock_state 恢复后 Dock 的位置、堆叠高度、挂靠宽度与显隐一并
        还原（QMainWindow saveState 序列化完整布局）；首次运行（配置
        无状态字节）时按默认布局设初始尺寸：右区纵向堆叠三个 Dock
        （高度 180/180/280）、面板宽度 320。
        """
        self._restore_window_state()
        # 无记忆状态（首次运行）：设默认初始尺寸（有记忆时不得覆盖
        # restoreState 还原的用户自定义布局）
        if not self._render_config.dock_state:
            # 堆叠高度：右区纵向三 Dock 按序分配（与分区最小高度 96 双保险）
            self.resizeDocks(
                [self.label_dock, self.object_dock, self.file_dock],
                [180, 180, 280],
                Qt.Orientation.Vertical,
            )
            # 挂靠宽度：Dock 与中央画布间分隔条拖拽调节，此处设初始宽度
            self.resizeDocks(
                [self.label_dock, self.object_dock, self.file_dock],
                [320, 320, 320],
                Qt.Orientation.Horizontal,
            )

    def _restore_window_state(self) -> None:
        """从渲染配置恢复 QMainWindow 布局状态（工具栏/Dock 位置与尺寸）。

        配置无状态字节（首次运行或旧版配置文件）时保持默认布局；
        状态数据非法或恢复失败仅告警，不影响其余配置生效。
        """
        b64 = self._render_config.dock_state
        if not b64:
            return
        # base64 解码为 QByteArray（非法数据回退默认布局）
        try:
            state = QByteArray.fromBase64(b64.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as e:
            LOGGER.warning(f"窗口布局状态数据非法，使用默认布局: {e}")
            return
        if not self.restoreState(state):
            LOGGER.warning("窗口布局状态恢复失败，使用默认布局")

    def _schedule_render_save(self) -> None:
        """防抖调度渲染配置落盘（500ms 内的连续拖拽合并为一次写入）。"""
        self._render_save_timer.start()

    def _save_render_config_now(self) -> None:
        """立即保存渲染配置到磁盘（防抖到期或窗口关闭时调用）。"""
        try:
            save_render_config(self._render_config)
        except OSError as e:
            LOGGER.warning(f"渲染配置保存失败: {e}")

    # -------------------------- 信号连接 --------------------------
    def _connect_signals(self) -> None:
        """连接工具栏、右栏、画布与菜单动作之间的信号。"""
        # 左侧工具栏（文件操作与标注工具；自动标注入口在工具菜单）
        self.left_toolbar.open_requested.connect(self._on_open_folder)
        self.left_toolbar.open_file_requested.connect(self._on_open_file)
        self.left_toolbar.save_requested.connect(self._on_save)
        self.left_toolbar.save_as_requested.connect(self._on_save_as)
        self.left_toolbar.delete_requested.connect(self._on_delete)
        self.left_toolbar.delete_image_requested.connect(self._on_delete_image_and_annotation)
        self.left_toolbar.tool_selected.connect(self._on_tool_selected)
        # 工具栏"适应窗口"：画布适应窗口（连接时 canvas 已创建，无需延迟解析）
        self.left_toolbar.fit_requested.connect(self.canvas.fit_to_window)

        # 画布
        self.canvas.shapes_changed.connect(self._on_shapes_changed)
        self.canvas.selection_changed.connect(self._on_canvas_selection_changed)
        self.canvas.shape_created.connect(self._on_shape_created)
        # 编辑模式右键（空白/对象）：弹出上下文菜单进入编辑模式
        self.canvas.context_menu_requested.connect(self._on_canvas_context_menu)

        # 标签列表 Dock
        self.label_section.label_selected.connect(self._on_label_selected)
        # 对象列表 Dock
        self.object_section.objects_selected.connect(self._on_objects_selected)
        # 复选框可见性：隐藏/恢复对应形状的画布渲染（纯视图，不标脏）
        self.object_section.shape_visibility_requested.connect(self._on_shape_visibility_requested)
        # 对象列表（a）右键菜单：编辑属性 / 删除 / 进入编辑模式
        self.object_section.edit_object_requested.connect(self._on_edit_object)
        self.object_section.delete_objects_requested.connect(self._on_delete_objects)
        self.object_section.enter_edit_mode_requested.connect(self._enter_edit_mode)
        # 对象列表拖拽排序：按新顺序重排画布形状（列表顺序即标注保存顺序）
        self.object_section.objects_reordered.connect(self._on_objects_reordered)
        # 文件列表 Dock
        self.file_section.file_selected.connect(self._on_file_selected)
        # 文件列表双击：加载该图片并进入编辑模式
        self.file_section.file_edit_requested.connect(self._on_file_edit_requested)

        # 后台标签扫描
        self.label_scan_worker.labels_ready.connect(self._on_labels_scanned)
        # 扫描进度：驱动进度对话框（进度条 + 文字）；状态栏同步提示
        self.label_scan_worker.progress_updated.connect(self._on_scan_progress)
        self.label_scan_worker.progress_desc.connect(
            lambda msg: self.statusBar().showMessage(msg, 3000)
        )

        # 批量标注 worker（所有图片/视频）：进度/错误/完成信号
        self.annotate_worker.progress_updated.connect(self._on_annotate_progress)
        self.annotate_worker.progress_desc.connect(self._on_annotate_progress_desc)
        self.annotate_worker.error_occurred.connect(self._on_annotate_error)
        self.annotate_worker.task_finished.connect(self._on_annotate_task_finished)

        # 单张标注 worker（当前画布图片）
        self.single_annotate_worker.progress_updated.connect(self._on_annotate_progress)
        self.single_annotate_worker.progress_desc.connect(self._on_annotate_progress_desc)
        self.single_annotate_worker.error_occurred.connect(self._on_annotate_error)
        self.single_annotate_worker.task_finished.connect(self._on_annotate_task_finished)
        self.single_annotate_worker.shapes_ready.connect(self._on_single_shapes_ready)

        # 在线更新 worker：检查结果 / 下载进度 / 下载完成（quiet 标志存
        # 成员变量，连接一次避免重复触发）
        self._update_check_worker.update_found.connect(self._on_update_found)
        self._update_check_worker.up_to_date.connect(self._on_update_up_to_date)
        self._update_check_worker.error_occurred.connect(self._on_update_check_error)
        self._update_download_worker.progress_updated.connect(self._on_update_download_progress)
        self._update_download_worker.error_occurred.connect(self._on_update_download_error)
        self._update_download_worker.download_done.connect(self._on_installer_downloaded)

        # 启动后延时静默检查更新（窗口不可见时跳过，避免关闭竞态）
        QTimer.singleShot(5000, self._startup_check_update)

    def _startup_check_update(self) -> None:
        """启动后 5 秒的静默更新检查入口：仅窗口可见时执行。"""
        if self.isVisible():
            self._on_check_update(quiet=True)

    # -------------------------- 文件操作 --------------------------
    def _on_open_folder(self) -> None:
        """打开工作文件夹：选择目录并加载。"""
        directory = chooseDir(self._work_dir)
        if not directory:
            return
        self._open_workdir(directory)

    def _open_workdir(self, directory: str) -> None:
        """加载指定目录作为工作路径（扫描图片并显示第一张）。

        供打开文件夹对话框与导入标注完成后的工作路径接管复用。

        Args:
            directory: 目标目录路径。
        """
        images = sorted(getImageFilesInDir(directory))
        if not images:
            showMessageBox(QMessageBox.Icon.Warning, f"该目录未扫描到图片（jpg/jpeg/png/bmp）:\n{directory}")
            self._update_edit_state()
            return
        # 未保存防呆：有未保存修改且未开自动保存时先确认，取消则中止切换
        if not self._confirm_discard_changes():
            return
        self._work_dir = directory
        # 工作路径切换：清空旧路径的扫描统计缓存（新路径尚未扫描）
        self._label_stats_cache = None
        self._image_files = images
        self._current_index = -1
        self.file_section.set_files(images, self._file_annotated_flags())
        # 文件列表重建：重启分批惰性标签填充（供检索按标签过滤）
        self._start_tag_fill()
        self._load_image_by_index(0)
        # 自动扫描开启时立即扫描统计；默认不自动扫描（标签按已读图片累加）
        if self._render_config.auto_scan_labels:
            self._start_label_scan()
        LOGGER.info(f"已打开文件夹: {directory}，共 {len(images)} 张图片")

    def _on_open_file(self) -> None:
        """打开单个文件（图片或标注 JSON）并自动关联。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开文件",
            self._work_dir or "",
            "图片或标注文件 (*.json *.jpg *.jpeg *.png *.bmp);;LabelMe JSON (*.json);;图片 (*.jpg *.jpeg *.png *.bmp)",
        )
        if not path:
            return
        if path.lower().endswith(".json"):
            self._open_annotation_file(path)
        else:
            self._open_image_file(path)

    def _open_image_file(self, image_path: str) -> None:
        """打开单个图片文件，并尝试加载同名标注。

        Args:
            image_path: 图片文件路径。
        """
        # 未保存防呆：有未保存修改且未开自动保存时先确认，取消则中止打开
        if not self._confirm_discard_changes():
            return
        if not self.canvas.load_image(image_path):
            showMessageBox(QMessageBox.Icon.Warning, f"无法加载图片: {image_path}")
            return
        # 程序性加载守卫：回填期间画布形状信号不误置脏（finally 保证复位）
        self._loading = True
        try:
            self._work_dir = str(Path(image_path).parent)
            # 工作路径切换：清空旧路径的扫描统计缓存（新路径尚未扫描）
            self._label_stats_cache = None
            self._image_files = [image_path]
            self._current_index = 0
            self._dirty = False
            json_path = Path(image_path).with_suffix(".json")
            if json_path.exists():
                try:
                    doc = labelme_io.load_document(json_path)
                    self.canvas.set_shapes(labelme_io.document_shapes(doc))
                except Exception:
                    self.canvas.clear_shapes()
            else:
                self.canvas.clear_shapes()
            self.file_section.set_files([image_path], self._file_annotated_flags())
            self.file_section.select_file(0)
            # 文件列表重建：重启分批惰性标签填充（单文件即时读出标签）
            self._start_tag_fill()
            self._refresh_objects()
            # 标签按已读图片累加：并入当前画布标签（默认不自动扫描）
            self._refresh_labels()
            self._update_edit_state()
        finally:
            self._loading = False
        # 自动扫描开启时立即扫描统计；默认不自动扫描（标签按已读图片累加）
        if self._render_config.auto_scan_labels:
            self._start_label_scan()
        self._update_status()
        LOGGER.info(f"已打开图片: {image_path}")

    def _open_annotation_file(self, json_path: str) -> None:
        """解析单个标注文件并加载其关联图像。

        Args:
            json_path: labelme JSON 标注文件路径。
        """
        # 未保存防呆：有未保存修改且未开自动保存时先确认，取消则中止打开
        if not self._confirm_discard_changes():
            return
        try:
            doc = labelme_io.load_document(json_path)
        except Exception as e:
            showMessageBox(QMessageBox.Icon.Critical, f"无法解析标注文件: {e}")
            return

        image_path = self._resolve_linked_image(json_path, doc)
        if not image_path:
            showMessageBox(
                QMessageBox.Icon.Critical,
                "未找到标注文件对应的图片：\n"
                f"imagePath 字段为 \"{doc.get('imagePath', '')}\"，"
                "根据该路径未找到图片，且同目录下也无同名图片。",
            )
            return
        if not self.canvas.load_image(image_path):
            showMessageBox(QMessageBox.Icon.Warning, f"无法加载图像: {image_path}")
            return

        # 程序性加载守卫：回填期间画布形状信号不误置脏（finally 保证复位）
        self._loading = True
        try:
            self.canvas.set_shapes(labelme_io.document_shapes(doc))
            json_dir = str(Path(json_path).parent)
            self._work_dir = json_dir
            # 工作路径切换：清空旧路径的扫描统计缓存（新路径尚未扫描）
            self._label_stats_cache = None
            self._image_files = [image_path]
            self._current_index = 0
            self._dirty = False
            self.file_section.set_files([image_path], self._file_annotated_flags())
            self.file_section.select_file(0)
            # 文件列表重建：重启分批惰性标签填充（单文件即时读出标签）
            self._start_tag_fill()
            self._refresh_objects()
            # 标签按已读图片累加：并入当前画布标签（默认不自动扫描）
            self._refresh_labels()
            self._update_edit_state()
        finally:
            self._loading = False
        # 自动扫描开启时立即扫描统计；默认不自动扫描（标签按已读图片累加）
        if self._render_config.auto_scan_labels:
            self._start_label_scan()
        self._update_status()
        LOGGER.info(f"已打开标注文件: {json_path}")

    @staticmethod
    def _resolve_linked_image(json_path: str, doc) -> str:
        """根据标注文件解析关联图像路径（imagePath 相对标注意义或同名图片）。

        Args:
            json_path: 标注 JSON 文件路径。
            doc: 已解析的 labelme 文档字典。

        Returns:
            图像绝对路径；未找到返回空字符串。
        """
        json_dir = Path(json_path).parent
        image_name = doc.get("imagePath", "")
        if image_name:
            candidate = Path(image_name)
            if not candidate.is_absolute():
                candidate = json_dir / image_name
            if candidate.is_file():
                return str(candidate)
        # 回退：与标注同名的图片文件
        base = Path(json_path).with_suffix("")
        for ext in (".jpg", ".jpeg", ".png", ".bmp"):
            candidate = Path(str(base) + ext)
            if candidate.is_file():
                return str(candidate)
        return ""

    def _current_image_path(self) -> str:
        """返回当前图片路径（未加载返回空字符串）。"""
        if 0 <= self._current_index < len(self._image_files):
            return self._image_files[self._current_index]
        return ""

    def _current_json_path(self) -> str:
        """返回当前图片同名的 labelme JSON 标注路径。"""
        img = self._current_image_path()
        if not img:
            return ""
        return str(Path(img).with_suffix(".json"))

    def _file_annotated_flags(self) -> list:
        """探测文件列表中各图片是否已有同名 labelme JSON 标注文件。

        Returns:
            与 self._image_files 等长的布尔列表（True = 已标注）。
        """
        return [
            Path(img).with_suffix(".json").is_file()
            for img in self._image_files
        ]

    # -------------------------- 文件标签惰性填充 --------------------------
    def _start_tag_fill(self) -> None:
        """（重）启动分批惰性标签填充（队列对齐当前文件列表）。

        文件列表任何重建（打开文件夹/图片/标注文件、删除图片、视频标注
        重扫、批量标注收尾）后必须调用：终止旧批次并按当前
        self._image_files 重建队列，防止旧队列下标串目录/串列表。
        """
        self._tag_fill_timer.stop()
        self._tag_fill_queue = list(range(len(self._image_files)))
        if self._tag_fill_queue:
            self._tag_fill_timer.start()

    def _fill_next_tag_batch(self) -> None:
        """定时器回调：读取一批图片的标注 JSON 标签集合并填充列表模型。

        每批处理 _TAG_FILL_BATCH_SIZE 个文件：仅抽取 shapes[].label
        （轻量 json 解析，不构建完整文档）；文件缺失/解析失败按空标签
        集合处理。队列耗尽后停止定时器。
        """
        if not self._tag_fill_queue:
            self._tag_fill_timer.stop()
            return
        # 取出一批并从队列移除
        batch = self._tag_fill_queue[:_TAG_FILL_BATCH_SIZE]
        del self._tag_fill_queue[:_TAG_FILL_BATCH_SIZE]
        total = len(self._image_files)
        for row in batch:
            if row >= total:
                continue  # 列表已收缩的残留下标（正常经 _start_tag_fill 重建避免）
            tags: set = set()
            json_path = Path(self._image_files[row]).with_suffix(".json")
            if json_path.is_file():
                try:
                    # 轻量解析：仅取 shapes[].label（读取失败/损坏 JSON 按空标签处理）
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                    for shape in data.get("shapes") or []:
                        label = shape.get("label") if isinstance(shape, dict) else None
                        if label:
                            tags.add(str(label))
                except (OSError, ValueError):
                    tags = set()
            self.file_section.set_file_tags(row, tags)
        if not self._tag_fill_queue:
            self._tag_fill_timer.stop()  # 读取完毕即停

    def _load_image_by_index(self, index: int) -> None:
        """加载指定下标的图片及其同名标注。

        未保存防呆：有未保存修改且未开自动保存时先弹窗确认；
        自动保存开启时，加载新图前先保存当前图片的全部标注。

        Args:
            index: 图片在文件列表中的下标。
        """
        if not (0 <= index < len(self._image_files)):
            return
        # 未保存防呆：有未保存修改且未开自动保存时先确认，取消则中止切换
        if not self._confirm_discard_changes():
            return
        # 自动保存：切换图片前保存当前图片的标注（含标签/形状/属性）
        if index != self._current_index:
            self._auto_save_current()
        path = self._image_files[index]
        if not self.canvas.load_image(path):
            showMessageBox(QMessageBox.Icon.Warning, f"无法加载图片: {path}")
            return
        # 程序性加载守卫：回填期间画布形状信号不误置脏（finally 保证复位）
        self._loading = True
        try:
            self._current_index = index
            self._dirty = False

            json_path = Path(path).with_suffix(".json")
            if json_path.exists():
                try:
                    doc = labelme_io.load_document(json_path)
                    self.canvas.set_shapes(labelme_io.document_shapes(doc))
                except Exception as e:
                    LOGGER.warning(f"读取标注失败 {json_path}: {e}")
                    self.canvas.clear_shapes()
            else:
                self.canvas.clear_shapes()

            self.file_section.select_file(index)
            self._refresh_objects()
            # 标签按已读图片累加：浏览/打开图片时并入当前画布标签
            self._refresh_labels()
            self._update_edit_state()
        finally:
            self._loading = False
        self._update_status()

    def _on_file_selected(self, index: int) -> None:
        """右侧文件列表选中切换当前图片。"""
        if index != self._current_index:
            self._load_image_by_index(index)

    def _on_file_edit_requested(self, index: int) -> None:
        """文件列表双击：加载该图片并进入编辑模式。

        act_edit_mode 为触发式动作（非 checkable 持久态），trigger() 重复
        触发幂等（重新切换为编辑工具），此处直接触发即可。

        Args:
            index: 文件在源模型中的下标。
        """
        self._load_image_by_index(index)
        self.act_edit_mode.trigger()
        self.statusBar().showMessage("已进入编辑模式", 2000)

    def _on_save(self) -> None:
        """保存当前标注到同名 labelme JSON。"""
        if not self._current_image_path():
            showMessageBox(QMessageBox.Icon.Warning, "请先打开图片")
            return
        self._write_annotation(self._current_json_path())
        self._refresh_labels()

    def _on_save_as(self) -> None:
        """另存为：选择目标 JSON 路径后写入当前标注。"""
        img = self._current_image_path()
        if not img:
            showMessageBox(QMessageBox.Icon.Warning, "请先打开图片")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为标注", str(Path(img).with_suffix(".json")), "LabelMe JSON (*.json)"
        )
        if not path:
            return
        self._write_annotation(path)
        self._refresh_labels()

    def _write_annotation(self, json_path: str) -> None:
        """将当前画布形状写入 labelme JSON 文件。

        Args:
            json_path: 输出 JSON 文件路径。
        """
        doc = labelme_io.empty_document(
            Path(self._current_image_path()).name,
            self.canvas.image_width(),
            self.canvas.image_height(),
        )
        labelme_io.set_document_shapes(doc, self.canvas.shapes())
        labelme_io.save_document(doc, json_path)
        self._dirty = False
        self._update_status()
        # 保存到当前图片同名标注文件：文件列表复选框标记为已标注，
        # 并从内存 shapes 同步该文件标签集合（检索按标签过滤即时生效）
        if json_path == self._current_json_path() and 0 <= self._current_index < len(self._image_files):
            self.file_section.set_file_annotated(self._current_index, True)
            tags = {
                str(s.get("label", "") or "")
                for s in self.canvas.shapes()
                if str(s.get("label", "") or "").strip()
            }
            self.file_section.set_file_tags(self._current_index, tags)

    # -------------------------- 编辑操作 --------------------------
    def _on_undo(self) -> None:
        """撤销上一步（绘制草稿进行中优先撤销草稿顶点）。

        多边形/矩形草稿绘制中：Ctrl+Z 撤销草稿末顶点（矩形等价取消
        草稿）；草稿不入全局撤销栈，故此时不触发画布全局撤销。
        """
        if self.canvas.is_drawing():
            self.canvas.undo_draft_vertex()
            return
        self.canvas.undo()

    def _on_redo(self) -> None:
        """重做上一步（绘制草稿进行中忽略）。

        草稿不入全局撤销栈、无对应重做记录，绘制中忽略重做避免语义混乱。
        """
        if self.canvas.is_drawing():
            return
        self.canvas.redo()

    def _confirm_destructive(self, kind: str, title: str, text: str) -> bool:
        """破坏性删除统一确认（含"不再提醒"会话级记忆，按操作类型分别记忆）。

        勾选"不再提醒"后仅记录到运行期集合 _confirm_skipped（不写
        RenderConfig、不落盘），应用重启后恢复默认提醒状态。

        Args:
            kind: 操作类型标识（如 "confirm_clear"）；本会话内已勾选
                "不再提醒"的操作类型直接放行。
            title: 确认框标题。
            text: 确认框正文。

        Returns:
            用户确认（或本会话已选择不再提醒）返回 True；取消返回 False。
        """
        # 该操作类型本会话已勾选"不再提醒"：直接放行
        if kind in self._confirm_skipped:
            return True
        msg = QMessageBox(
            QMessageBox.Icon.Question,
            title,
            text,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            self,
        )
        # "不再提醒"勾选框：勾选并确认后按操作类型会话级记忆（不持久化）
        check = QCheckBox("不再提醒")
        msg.setCheckBox(check)
        if msg.exec() != QMessageBox.StandardButton.Ok:
            return False
        if check.isChecked():
            self._confirm_skipped.add(kind)
        return True

    def _on_delete(self) -> None:
        """删除当前选中的标注（先确认，可勾选"不再提醒"按操作类型记忆）。

        删除记录撤销快照，可通过 Ctrl+Z 撤销。
        """
        count = len(self.canvas.selected_shapes())
        if not count:
            return
        if not self._confirm_destructive(
            "confirm_delete_shapes",
            "确认删除",
            f"确定删除选中的 {count} 个标注？\n（可通过 Ctrl+Z 撤销）",
        ):
            return
        self.canvas.delete_selected()

    def _on_clear(self) -> None:
        """清空当前图片全部标注（先确认，可勾选"不再提醒"按操作类型记忆）。

        清空直接整体替换形状列表，不入撤销栈、不可通过 Ctrl+Z 撤销。
        """
        if not self.canvas.shapes():
            return
        if not self._confirm_destructive(
            "confirm_clear",
            "确认清空",
            "确定清空当前图像的全部标注？\n（此操作不可恢复）",
        ):
            return
        self.canvas.clear_shapes()

    def _on_delete_shortcut(self) -> None:
        """Delete 快捷键：按当前焦点控件路由删除业务。

        路由顺序：文本输入控件不拦截 → 对象列表删选中对象（统一确认）
        → 文件列表删选中图像及标注（统一确认）→ 默认删画布选中形状
        （统一确认）。三条删除路径均经 _confirm_destructive 确认框。
        """
        fw = QApplication.focusWidget()
        # 焦点在文本输入控件：不拦截，保留正常文本删除行为
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return
        # 焦点在对象列表：删除列表选中对象（映射下标，复用含确认框的删除链路）
        obj_list = self.object_section.list
        if fw is obj_list or (fw is not None and obj_list.isAncestorOf(fw)):
            indices = self.object_section.selected_object_indices()
            if indices:
                self._on_delete_objects(indices)
            return
        # 焦点在文件列表：删除选中图像及同名标注（复用含确认框的健壮删除逻辑）
        file_list = self.file_section.list
        if fw is file_list or (fw is not None and file_list.isAncestorOf(fw)):
            cur = file_list.currentIndex()
            if self._has_workspace() and cur.isValid() and cur.row() >= 0:
                self._on_delete_image_and_annotation()
            return
        # 默认（画布或其他控件）：删除画布选中形状（统一确认链路）
        self._on_delete()

    # -------------------------- 文件删除 --------------------------
    def _on_delete_image_and_annotation(self) -> None:
        """删除当前图片及其同名标注文件（Shift+Delete 键）。

        删除前确认（可勾选"不再提醒"按操作类型记忆到渲染配置）；
        删除后同步更新文件列表并加载下一张（或清空画布），
        防止下标越界与 NoneType 错误。
        """
        img_path = self._current_image_path()
        if not img_path:
            showMessageBox(QMessageBox.Icon.Warning, "当前无图片可删除")
            return
        json_path = self._current_json_path()
        files_to_delete = [img_path]
        if json_path and Path(json_path).exists():
            files_to_delete.append(json_path)
        msg = "确定要删除以下文件?\n" + "\n".join(files_to_delete)
        if not self._confirm_destructive("confirm_delete_file", "确认删除", msg):
            return
        # 执行文件删除（缺失文件静默跳过）
        for f in files_to_delete:
            Path(f).unlink(missing_ok=True)

        # 从文件列表移除当前项，避免下标越界；删除确认已隐含丢弃被删图的
        # 未保存修改，清脏防止后续重载路径误弹"未保存"确认
        self._dirty = False
        if 0 <= self._current_index < len(self._image_files):
            self._image_files.pop(self._current_index)
        self.file_section.set_files(self._image_files, self._file_annotated_flags())
        # 文件列表重建：重启分批惰性标签填充（旧队列下标已失效）
        self._start_tag_fill()

        if not self._image_files:
            # 无剩余图片：清空工作区状态（程序性清空守卫，画布信号不误置脏）
            self._loading = True
            try:
                self._current_index = -1
                self.canvas.clear_shapes()
            finally:
                self._loading = False
        else:
            # 加载列表中下标一致（或最后一张）的图片，保持连续性
            # （_load_image_by_index 内部自带 _loading 守卫与防呆确认）
            new_idx = min(self._current_index, len(self._image_files) - 1)
            self._load_image_by_index(new_idx)
        self._update_edit_state()
        self._update_status()
        LOGGER.info(f"已删除文件: {files_to_delete}")

    # -------------------------- 工具切换 --------------------------
    def _on_tool_selected(self, tool: str) -> None:
        """切换标注工具并同步画布、工具栏与菜单选中态。"""
        self.left_toolbar.set_tool(tool)
        act = self._tool_actions.get(tool)
        if act is not None:
            act.setChecked(True)
        self.canvas.set_tool(None if tool == TOOL_SELECT else tool)

    # -------------------------- 自动标注 --------------------------
    def _open_annotate_dialog(self) -> None:
        """打开模型加载与推理参数设置对话框（精简版 AnnotatePage）。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("模型加载 / 自动标注设置")
        dialog.resize(560, 640)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        page = AnnotatePage()
        layout.addWidget(page, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存设置")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("关闭")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if self.annotate_config is not None:
            page.apply_config(self.annotate_config)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        cfg = SysConfig()
        try:
            page.collect_config(cfg)
        except Exception as e:
            LOGGER.error(f"收集标注配置失败: {e}")
            return
        self.annotate_config = cfg
        # 模型就绪状态同步到工具菜单自动标注入口（原左栏按钮禁用逻辑的等价迁移）
        has_model = bool(cfg.annotate_config.model_path)
        for act in self._annotate_actions:
            act.setEnabled(has_model)
        LOGGER.info("已保存自动标注配置")

    # -------------------------- 自动标注（统一入口） --------------------------
    def _precheck_annotate(
        self,
        need_current: bool = False,
        need_images: bool = False,
        need_videos: bool = False,
    ) -> bool:
        """标注前资源预检（模型已加载 / 工作区就绪）。

        Args:
            need_current: 需要当前画布有图片（单张标注）。
            need_images: 需要已打开包含图片的文件夹（批量标注）。
            need_videos: 需要工作路径下存在视频文件（视频标注）。

        Returns:
            预检通过返回 True；不通过时已弹窗提示并返回 False。
        """
        # 模型已加载
        if self.annotate_config is None or not self.annotate_config.annotate_config.model_path:
            showMessageBox(QMessageBox.Icon.Warning, "请先加载模型（工具 → 加载模型 / 自动标注设置）")
            return False
        ac = self.annotate_config.annotate_config
        model_path = Path(ac.model_path)
        if not model_path.exists():
            showMessageBox(QMessageBox.Icon.Warning, f"模型文件不存在: {ac.model_path}")
            return False
        # 模型格式检查（CPU/GPU 均使用 onnxruntime，仅支持 .onnx）
        if model_path.suffix.lower() != ".onnx":
            showMessageBox(
                QMessageBox.Icon.Warning,
                f"仅支持 onnx 模型推理，当前模型格式为 {model_path.suffix}，请重新选择",
            )
            return False
        # 工作区检查
        if need_current and not self._current_image_path():
            showMessageBox(QMessageBox.Icon.Warning, "请先打开图片")
            return False
        if need_images and not self._image_files:
            showMessageBox(QMessageBox.Icon.Warning, "请先打开包含图片的文件夹")
            return False
        if need_videos:
            videos = getVideoFilesInDir(self._work_dir) if self._work_dir else []
            if not videos:
                showMessageBox(QMessageBox.Icon.Warning, "当前工作路径下未找到视频文件（mp4/avi/mov）")
                return False
        return True

    def _annotate_worker_busy(self) -> bool:
        """检查标注线程是否正在执行（执行中阻止新任务）。

        Returns:
            忙碌返回 True（已弹窗提示），空闲返回 False。
        """
        if self.annotate_worker.isRunning() or self.single_annotate_worker.isRunning():
            showMessageBox(QMessageBox.Icon.Warning, "标注任务正在执行，请等待完成或先中止")
            return True
        return False

    def _run_annotate_with_dialog(self, worker, mode: str, title: str, target: str) -> None:
        """启动标注 worker 并弹出模态进度对话框阻塞等待结束。

        模态对话框保证标注期间主窗口不可预览/编辑；worker 的进度/
        错误/完成信号驱动对话框日志、进度条与收尾逻辑（_on_annotate_*）。

        Args:
            worker: 已配置好任务的标注线程（AnnotationWorker /
                SingleAnnotateWorker，调用前已完成 setConfig/set_task）。
            mode: 任务模式（single / all / video，收尾逻辑按此分派）。
            title: 进度窗口标题。
            target: 任务目标描述（进度窗口顶部灰字展示）。
        """
        dlg = AnnotateProgressDialog(title, target, self)
        self._annotate_progress_dlg = dlg
        self._annotate_mode = mode
        self._annotate_error = ""
        dlg.canceled.connect(self._on_annotate_dialog_canceled)
        worker.start()
        dlg.exec()

    def _on_annotate_dialog_canceled(self) -> None:
        """用户中止标注：停止对应 worker（线程内逐批检查停止标志）。"""
        if self._annotate_mode == "single":
            if self.single_annotate_worker.isRunning():
                self.single_annotate_worker.stop()
        elif self.annotate_worker.isRunning():
            self.annotate_worker.stop()
        self.statusBar().showMessage("正在中止标注...", 2000)

    def _on_annotate_single(self) -> None:
        """对当前画布图片执行单张自动标注（模态进度窗口，结果回填画布）。"""
        if not self._precheck_annotate(need_current=True):
            return
        if self._annotate_worker_busy():
            return
        img = self._current_image_path()
        self.single_annotate_worker.set_task(self.annotate_config, img)
        self._run_annotate_with_dialog(
            self.single_annotate_worker,
            "single",
            "自动标注 - 当前图片",
            f"目标: {Path(img).name}",
        )

    def _on_annotate_all(self) -> None:
        """标注工作路径中的全部图片（跳过/覆盖两种模式，模态进度窗口）。"""
        if not self._precheck_annotate(need_images=True):
            return
        if self._annotate_worker_busy():
            return

        images = list(self._image_files)
        # 已有标注文件时由用户选择处理方式（跳过 / 覆盖）
        annotated = [p for p in images if Path(p).with_suffix(".json").is_file()]
        if annotated:
            mode = AnnotateOptionsDialog.get_mode(self)
            if mode is None:
                return
            if mode == "skip":
                # 跳过模式：仅标注尚无标注文件的图片
                images = [p for p in images if not Path(p).with_suffix(".json").is_file()]
                if not images:
                    showMessageBox(QMessageBox.Icon.Information, "所有图片均已标注，无需重新标注")
                    return
            else:
                # 覆盖模式：先清理老标注文件（避免无检测结果时残留旧标注）
                for p in images:
                    Path(p).with_suffix(".json").unlink(missing_ok=True)

        # 组装运行配置（深拷贝，不污染已保存的模型设置）
        cfg = deepcopy(self.annotate_config)
        ac = cfg.annotate_config
        ac.image_path = self._work_dir
        # 输出到工作目录：标注与图片同名存放于同目录，且不重复复制图片
        ac.dataset_path = self._work_dir
        ac.annotation_files = images
        ac.video_files = []
        self.annotate_worker.setConfig(cfg)
        self._run_annotate_with_dialog(
            self.annotate_worker,
            "all",
            "自动标注 - 所有图片",
            f"共 {len(images)} 张图片 · 输出目录: {self._work_dir}",
        )

    def _on_annotate_video(self) -> None:
        """标注视频：打开视频标注窗口（输入路径/帧间隔/文件列表/预览播放器）。"""
        if not self._precheck_annotate():
            return
        if self._annotate_worker_busy():
            return

        # 视频标注窗口（默认输入路径 = 当前工作目录；输出默认 Input/Output）
        config = VideoAnnotateDialog.get_config(
            default_input=self._work_dir or "", parent=self
        )
        if config is None:
            return

        videos = config["videos"]
        output_dir = config["output_dir"]
        interval = config["frame_interval"]

        cfg = deepcopy(self.annotate_config)
        ac = cfg.annotate_config
        ac.image_path = config["input_dir"]
        # 抽帧图片与标注输出到用户设定的输出目录（默认输入路径/Output）
        ac.dataset_path = output_dir
        ac.frame_interval = interval
        ac.annotation_files = []
        ac.video_files = videos
        self.annotate_worker.setConfig(cfg)
        self._run_annotate_with_dialog(
            self.annotate_worker,
            "video",
            "自动标注 - 视频",
            f"共 {len(videos)} 个视频 · 抽帧间隔 {interval} 帧 · 输出目录: {output_dir}",
        )

    def _on_annotate_progress(self, ratio: float) -> None:
        """标注进度更新：刷新进度对话框进度条。"""
        if self._annotate_progress_dlg is not None:
            self._annotate_progress_dlg.update_progress(ratio)

    def _on_annotate_progress_desc(self, msg: str) -> None:
        """标注进度描述：追加到进度对话框日志区。"""
        if self._annotate_progress_dlg is not None:
            self._annotate_progress_dlg.append_log(msg)

    def _on_annotate_error(self, msg: str) -> None:
        """标注 worker 出错：记录并写入进度日志（任务结束时弹窗提示）。"""
        self._annotate_error = msg
        if self._annotate_progress_dlg is not None:
            self._annotate_progress_dlg.append_log(f"[错误] {msg}")

    def _on_annotate_task_finished(self) -> None:
        """标注任务结束（完成/中止/出错统一入口）：按模式收尾后关闭对话框。"""
        mode = self._annotate_mode
        self._annotate_mode = ""
        # 收尾处理（中止/出错同样执行，保证界面状态一致）
        try:
            if mode == "all":
                self._after_annotate_images()
            elif mode == "video":
                self._after_annotate_video()
            # single 模式结果由 shapes_ready 回填画布，无需文件收尾
        except Exception as e:
            LOGGER.warning(f"标注收尾处理失败: {e}")
        self._close_annotate_dialog()
        # 任务期间发生错误：对话框关闭后弹窗提示
        error = self._annotate_error
        self._annotate_error = ""
        if error:
            showMessageBox(QMessageBox.Icon.Critical, error)

    def _close_annotate_dialog(self) -> None:
        """关闭标注进度对话框（先断开 canceled，避免误触发中止逻辑）。"""
        if self._annotate_progress_dlg is None:
            return
        dlg = self._annotate_progress_dlg
        self._annotate_progress_dlg = None
        try:
            dlg.canceled.disconnect(self._on_annotate_dialog_canceled)
        except RuntimeError:
            pass  # 连接已断开（对话框已由用户关闭）
        dlg.close()

    def _after_annotate_images(self) -> None:
        """批量图片标注收尾：刷新已标注复选框并重载当前图片标注。"""
        flags = self._file_annotated_flags()
        for i, flag in enumerate(flags):
            self.file_section.set_file_annotated(i, flag)
        # 重载当前图片标注（同下标不触发自动保存，画布同步为新标注）
        if 0 <= self._current_index < len(self._image_files):
            self._load_image_by_index(self._current_index)

    def _after_annotate_video(self) -> None:
        """视频标注收尾：重扫工作目录图片（纳入新增抽帧图片）并保持当前图片。"""
        current = self._current_image_path()
        images = sorted(getImageFilesInDir(self._work_dir)) if self._work_dir else []
        if not images:
            return
        self._image_files = images
        self.file_section.set_files(images, self._file_annotated_flags())
        # 文件列表重建：重启分批惰性标签填充（供检索按标签过滤）
        self._start_tag_fill()
        # 尽量保持当前图片不变（找不到时回到第一张）
        idx = images.index(current) if current in images else 0
        self._load_image_by_index(idx)
        self._update_edit_state()
        self._update_status()

    def _on_single_shapes_ready(self, shapes: list) -> None:
        """单张标注完成：结果回填画布并刷新右侧列表。

        程序性回填经 _loading 守卫抑制 shapes_changed 的误置脏，
        未保存状态由本方法的显式 _dirty = True 标记。
        """
        # 程序性加载守卫：回填期间画布形状信号不误置脏（finally 保证复位）
        self._loading = True
        try:
            self.canvas.set_shapes(shapes)
        finally:
            self._loading = False
        # 自动标注结果视为未保存修改（显式置脏）
        self._dirty = True
        self._refresh_objects()
        self._refresh_labels()
        self._update_status()

    # -------------------------- 格式转换 --------------------------
    def _open_export_dialog(self) -> None:
        """打开导出标注对话框（工作路径 JSON → YOLO，源格式锁定 LabelMe）。

        前置检查（任一不满足直接提示并返回，不再弹出对话框）：
            1. 未打开工作路径（_work_dir 为空）；
            2. 工作路径下无图片（jpg/jpeg/png/bmp）；
            3. 工作路径下无 LabelMe JSON 标注（无标注则无从导出）。
        通过后以 work_path + 统计缓存构造导出页（缓存为 None 时页面
        自行处理，仅不预填类别/关键点/任务类型）。
        """
        # 前置检查 1：未打开工作路径
        if not self._work_dir:
            showMessageBox(
                QMessageBox.Icon.Warning,
                "未打开工作路径，请先通过 文件 → 打开文件夹 选择要导出的标注目录。",
            )
            return
        # 前置检查 2：工作路径下无图片（导出需图片尺寸换算坐标）
        if not getImageFilesInDir(self._work_dir):
            showMessageBox(
                QMessageBox.Icon.Warning,
                f"当前工作路径下未找到图片文件（jpg/jpeg/png/bmp）:\n{self._work_dir}",
            )
            return
        # 前置检查 3：工作路径下无 LabelMe JSON 标注（无标注无从导出）
        if not getJsonFilesInDir(self._work_dir):
            showMessageBox(
                QMessageBox.Icon.Warning,
                f"当前工作路径下未找到 LabelMe JSON 标注文件（.json）:\n{self._work_dir}",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("导出标注")
        dialog.resize(980, 720)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        # 构造导出页：工作路径 + 扫描统计缓存（预填类别/关键点/任务类型）
        page = ConvertPage(
            direction="export",
            work_path=self._work_dir,
            stats=self._label_stats_cache,
        )
        page.set_worker(self.convert_worker)
        layout.addWidget(page, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()

    def _open_import_dialog(self) -> None:
        """打开导入标注对话框（YOLO → JSON，完成后自动打开输出路径为工作路径）。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("导入标注")
        dialog.resize(980, 720)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        page = ConvertPage(direction="import")
        page.set_worker(self.convert_worker)
        # 导入成功后自动打开输出目录作为工作路径（对话框关闭前接管）
        page.import_finished.connect(self._open_workdir)
        layout.addWidget(page, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()

    # -------------------------- 绘制完成属性弹窗 --------------------------
    def _on_shape_created(self, shape) -> None:
        """单个对象绘制完成：弹出属性编辑窗；label 为空时静默丢弃该形状（不弹窗）。"""
        labels = self._all_labels[:]
        result = ShapeDialog.get_shape_props(labels, shape, self._canvas_group_ids(), self)
        if result is None:
            # 取消弹窗：无预填标签（未预设当前标签）时同样视为无 label，静默丢弃
            if not str(shape.get("label", "")).strip():
                self.canvas.discard_shape(shape)
                self.statusBar().showMessage("未设置标签，已取消该标注", 2000)
            return
        label, description, group_id = result
        if not label:
            # 空 label：形状不生效，静默丢弃（无弹窗提醒）
            self.canvas.discard_shape(shape)
            self.statusBar().showMessage("未设置标签，已取消该标注", 2000)
            return
        shape["label"] = label
        shape["description"] = description
        shape["group_id"] = group_id
        self.canvas.refresh()
        self._dirty = True
        self._refresh_objects()
        self._refresh_labels()

    # -------------------------- 图片浏览快捷键 --------------------------
    def _prev_image(self) -> None:
        """A 键：切换至上一张图片。"""
        if 0 < self._current_index < len(self._image_files):
            self._load_image_by_index(self._current_index - 1)

    def _next_image(self) -> None:
        """D 键：切换至下一张图片。"""
        if 0 <= self._current_index < len(self._image_files) - 1:
            self._load_image_by_index(self._current_index + 1)

    # -------------------------- 自动保存 --------------------------
    def _on_autosave_toggled(self, checked: bool) -> None:
        """自动保存选项切换（同步内存开关并随渲染配置持久化）。

        Args:
            checked: 是否勾选自动保存。
        """
        self._auto_save = checked
        # 勾选态写入渲染配置并即时落盘（下次启动恢复）
        self._render_config.auto_save = checked
        self._save_render_config_now()
        state = "开启" if checked else "关闭"
        LOGGER.info(f"自动保存已{state}")
        self.statusBar().showMessage(f"自动保存已{state}", 2000)

    def _confirm_discard_changes(self) -> bool:
        """破坏性切换/关闭前确认：未保存修改提醒（保存/不保存/取消）。

        无未保存修改直接放行；自动保存开启时静默落盘后放行；否则弹窗
        三选。"保存"分支复用 _on_save 的默认路径逻辑（当前图片同名
        JSON；无当前图片时与 _on_save 一致提示并中止）。

        Returns:
            True=继续切换/关闭；False=用户取消。
        """
        if not self._dirty:
            return True
        # 自动保存开启：静默落盘当前标注后放行（落盘即清脏）
        if self._auto_save:
            self._auto_save_current()
            return True
        # 三选确认框（保存 / 不保存 / 取消）
        msg = QMessageBox(
            QMessageBox.Icon.Warning,
            "未保存的修改",
            "当前标注尚未保存，是否保存？",
            QMessageBox.StandardButton.NoButton,
            self,
        )
        save_btn = msg.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = msg.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is save_btn:
            # 与 _on_save 行为一致：无当前图片时提示无法保存并中止切换
            if not self._current_image_path():
                showMessageBox(QMessageBox.Icon.Warning, "请先打开图片")
                return False
            self._write_annotation(self._current_json_path())
            self._refresh_labels()
            return True
        if clicked is discard_btn:
            # 不保存：丢弃未保存修改并放行
            return True
        return False

    def _auto_save_current(self) -> None:
        """切换图片前自动保存当前图片的全部标注（标签/形状/属性）。

        仅在自动保存开启且有当前图片时执行；无修改且磁盘无标注文件时
        跳过，避免生成空标注文件。结果通过状态栏临时消息反馈。
        """
        if not self._auto_save:
            return
        img = self._current_image_path()
        if not img:
            return
        json_path = self._current_json_path()
        if not self._dirty and not Path(json_path).exists():
            return
        try:
            self._write_annotation(json_path)
            self.statusBar().showMessage(f"自动保存成功: {json_path}", 3000)
        except Exception as e:
            LOGGER.warning(f"自动保存失败 {json_path}: {e}")
            self.statusBar().showMessage(f"自动保存失败: {e}", 3000)

    # -------------------------- 编辑模式 --------------------------
    def _enter_edit_mode(self) -> None:
        """进入编辑模式（工具切换为"编辑"，允许拖拽/端点缩放/属性修改）。"""
        self._on_tool_selected(TOOL_SELECT)

    def _on_canvas_context_menu(self, shape) -> None:
        """画布右键完整上下文菜单（空白或对象，无绘制草稿时）。

        菜单项：编辑属性/删除/复制/粘贴/撤销/重做/创建矩形/创建点/
        创建多边形/编辑模式/清空标注；按当前状态启用/禁用。
        菜单项不绑定快捷键（避免与菜单栏动作歧义）。

        Args:
            shape: 右键命中的形状字典，空白处为 None。
        """
        # 无工作区（未打开图像）不弹出菜单
        if not self._has_workspace():
            return
        # 命中对象未选中时先单选之（保证删除/编辑属性作用于该对象）
        if shape is not None and not any(s is shape for s in self.canvas.selected_shapes()):
            self.canvas.select_shape(shape)
        selected = self.canvas.selected_shapes()

        menu = QMenu(self)
        # 对象操作区
        act_edit = menu.addAction("编辑属性")
        act_edit.setEnabled(len(selected) == 1)
        act_del = menu.addAction("删除")
        act_del.setEnabled(bool(selected))
        act_copy = menu.addAction("复制")
        act_copy.setEnabled(bool(selected))
        act_paste = menu.addAction("粘贴")
        act_paste.setEnabled(self.canvas.has_clipboard())
        menu.addSeparator()
        # 历史操作区
        act_undo = menu.addAction("撤销")
        act_undo.setEnabled(self.canvas.can_undo())
        act_redo = menu.addAction("重做")
        act_redo.setEnabled(self.canvas.can_redo())
        menu.addSeparator()
        # 工具切换区（当前工具打勾）
        act_rect = menu.addAction("创建矩形")
        act_rect.setCheckable(True)
        act_rect.setChecked(self.canvas.tool() == labelme_io.SHAPE_RECTANGLE)
        act_point = menu.addAction("创建点")
        act_point.setCheckable(True)
        act_point.setChecked(self.canvas.tool() == labelme_io.SHAPE_POINT)
        act_polygon = menu.addAction("创建多边形")
        act_polygon.setCheckable(True)
        act_polygon.setChecked(self.canvas.tool() == labelme_io.SHAPE_POLYGON)
        act_edit_mode = menu.addAction("编辑模式")
        act_edit_mode.setCheckable(True)
        act_edit_mode.setChecked(self.canvas.tool() is None)
        menu.addSeparator()
        # 危险操作区
        act_clear = menu.addAction("清空标注")
        act_clear.setEnabled(bool(self.canvas.shapes()))

        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return
        if chosen is act_edit:
            self._on_edit_object(self._shape_index(selected[0]))
        elif chosen is act_del:
            # 画布右键删除：走统一确认链路（_on_delete 内含确认框）
            self._on_delete()
        elif chosen is act_copy:
            self.canvas.copy_selected()
        elif chosen is act_paste:
            self.canvas.paste_clipboard()
        elif chosen is act_undo:
            self.canvas.undo()
        elif chosen is act_redo:
            self.canvas.redo()
        elif chosen is act_rect:
            self._on_tool_selected(TOOL_RECTANGLE)
        elif chosen is act_point:
            self._on_tool_selected(TOOL_POINT)
        elif chosen is act_polygon:
            self._on_tool_selected(TOOL_POLYGON)
        elif chosen is act_edit_mode:
            self._enter_edit_mode()
        elif chosen is act_clear:
            self._on_clear()

    def _shape_index(self, shape) -> int:
        """返回形状在画布形状列表中的下标（未找到返回 -1）。

        Args:
            shape: 形状字典。

        Returns:
            下标或 -1。
        """
        for i, s in enumerate(self.canvas.shapes()):
            if s is shape:
                return i
        return -1

    def _selected_shape_indices(self) -> list:
        """返回画布当前全部选中形状的下标列表。

        Returns:
            下标列表（可能为空）。
        """
        ids = {id(s) for s in self.canvas.selected_shapes()}
        return [i for i, s in enumerate(self.canvas.shapes()) if id(s) in ids]

    # -------------------------- 对象列表（a）编辑与删除 --------------------------
    def _canvas_group_ids(self) -> list:
        """返回画布全部形状已有 group_id（去重、升序，供属性弹窗下拉框）。"""
        gids = {s.get("group_id") for s in self.canvas.shapes()}
        return sorted(g for g in gids if isinstance(g, int) and g >= 0)

    def _on_edit_object(self, index: int) -> None:
        """编辑对象列表中指定对象的属性（复用属性弹窗）。

        属性修改仅编辑模式允许：先进入编辑模式再弹窗。

        Args:
            index: 对象在形状列表中的下标。
        """
        shapes = self.canvas.shapes()
        if not (0 <= index < len(shapes)):
            return
        shape = shapes[index]
        # 需求：属性修改仅编辑模式允许 → 先切换到编辑模式
        self._enter_edit_mode()
        labels = self._all_labels[:]
        result = ShapeDialog.get_shape_props(labels, shape, self._canvas_group_ids(), self)
        if result is None:
            return
        label, description, group_id = result
        shape["label"] = label
        shape["description"] = description
        shape["group_id"] = group_id
        self.canvas.refresh()
        self._dirty = True
        self._refresh_objects()
        self._refresh_labels()
        self._update_status()

    def _on_delete_objects(self, indices: list) -> None:
        """删除对象列表中选中的全部对象（支持多选批量删除）。

        删除前确认（可勾选"不再提醒"按操作类型记忆到渲染配置）。

        Args:
            indices: 对象下标列表。
        """
        if not indices:
            return
        if not self._confirm_destructive(
            "confirm_delete_shapes",
            "确认删除",
            f"确定删除选中的 {len(indices)} 个标注？\n（可通过 Ctrl+Z 撤销）",
        ):
            return
        self.canvas.delete_shapes_at(indices)

    # -------------------------- 右侧栏联动 --------------------------
    def _on_shapes_changed(self) -> None:
        """画布形状变化：标记未保存、刷新对象列表。

        程序性加载（打开图片/标注回填/自动标注回填）期间 _loading 为
        True，画布 set_shapes/clear_shapes 触发的本信号不置脏。
        """
        if not self._loading:
            self._dirty = True
        self._refresh_objects()
        self._update_status()

    def _on_canvas_selection_changed(self, shapes: list) -> None:
        """画布选中集合变化（含多选）时联动对象列表选中态。

        Args:
            shapes: 选中形状字典列表（可为空）。
        """
        if not shapes:
            self.object_section.clear_object_selection()
            return
        ids = {id(s) for s in shapes}
        indices = [i for i, s in enumerate(self.canvas.shapes()) if id(s) in ids]
        self.object_section.select_objects(indices)

    def _on_objects_selected(self, indices: list) -> None:
        """对象列表选中集合（含多选）变化时联动画布多选。

        Args:
            indices: 对象下标列表。
        """
        self.canvas.select_shapes_by_indices(indices)

    def _on_objects_reordered(self, new_order: list) -> None:
        """对象列表拖拽排序完成：按新顺序重排画布形状。

        列表新顺序即画布形状新顺序（标注 JSON 保存顺序随之变化）；
        reorder_shapes 保持形状字典对象身份不变（画布选中集合不丢），
        内部发射 shapes_changed → 自动置脏并刷新对象列表（重建为
        与画布一致的恒等映射）。

        Args:
            new_order: 新视觉顺序的形状下标列表（new_order[i] = 重排后
                第 i 个形状在原列表中的下标）。
        """
        self.canvas.reorder_shapes(new_order)

    def _on_shape_visibility_requested(self, index: int, visible: bool) -> None:
        """列表复选框切换：设置对应形状的渲染可见性（纯视图状态）。

        Args:
            index: 形状在画布形状列表中的下标。
            visible: 是否渲染。
        """
        shapes = self.canvas.shapes()
        if not (0 <= index < len(shapes)):
            return
        self.canvas.set_shape_visible(shapes[index], visible)
        self._status_label.setText(
            f"{'显示' if visible else '隐藏'}: {shapes[index].get('label', '')}"
        )

    def _on_label_selected(self, label: str) -> None:
        """选中/双击标签：设为当前绘制标签。"""
        self.canvas.set_current_label(label)
        self._status_label.setText(f"当前标签: {label}")

    # -------------------------- 列表刷新 --------------------------
    def _start_label_scan(self) -> None:
        """显式启动后台标签扫描统计（统计菜单/自动扫描入口）。

        弹出非模态进度对话框（进度条 + 随时中止）；扫描正常完成后标签
        列表同步扫描结果（合并大小写同名标签）并弹出统计结果窗口。
        重复触发时先中止旧任务，再按当前目录新建进度对话框；中止丢弃
        部分结果（不更新标签列表）。
        """
        if not self._work_dir:
            return
        # 停止旧扫描（collect 逐文件检查停止标志，可及时中断）后重启
        if self.label_scan_worker.isRunning():
            self.label_scan_worker.stop()
            self.label_scan_worker.wait(1500)
            if self.label_scan_worker.isRunning():
                LOGGER.warning("标签扫描线程未能在超时内停止，本次扫描任务可能被跳过")
                return
        # 关闭旧进度对话框（先断开 canceled 避免误触发中止逻辑；此时旧
        # worker 已停止），随后按当前目录新建（重置目录与进度显示）
        if self._scan_progress_dlg is not None:
            self._scan_progress_dlg.canceled.disconnect(self._on_scan_canceled)
            self._scan_progress_dlg.close()
        self._scan_progress_dlg = ScanProgressDialog(self._work_dir, self)
        self._scan_progress_dlg.canceled.connect(self._on_scan_canceled)
        self._scan_progress_dlg.show()
        # 启动扫描任务（进度信号驱动对话框进度条）
        self.label_scan_worker.set_task(getJsonFilesInDir(self._work_dir))
        self.label_scan_worker.start()

    def _on_scan_canceled(self) -> None:
        """用户中止扫描：停止 worker 并丢弃部分结果（不更新标签列表）。"""
        if self.label_scan_worker.isRunning():
            self.label_scan_worker.stop()
        self._scan_progress_dlg = None
        self.statusBar().showMessage("扫描已中止", 2500)

    def _on_labels_scanned(self, labels: list, keypoints: list, counts: list, shape_counts: dict) -> None:
        """后台扫描完成：同步标签列表、缓存统计结果并弹出统计窗口。

        扫描结果已合并大小写同名标签（拼写取首次出现）；中止路径不进入
        本回调。当前画布标签与扫描结果取并集后刷新列表。统计结果
        （labels/keypoints/shape_counts）缓存到 _label_stats_cache，
        供导出标注对话框预填类别/关键点/任务类型（复用扫描结论）。

        Args:
            labels: 标签名列表（合并大小写后）。
            keypoints: 关键点标签名列表。
            counts: [标签, 实例个数] 二元组列表（按个数降序）。
            shape_counts: shape 分组计数字典 {"rectangle": n, "point": n, "polygon": n}。
        """
        self._all_labels = list(labels)
        # 缓存统计结果（导出对话框预填用；列表/字典复制，避免与信号源共享引用）
        self._label_stats_cache = {
            "labels": list(labels),
            "keypoints": list(keypoints),
            "shape_counts": dict(shape_counts),
        }
        self._refresh_labels()
        # 关闭进度对话框（先断开 canceled，避免正常完成被误判为中止）
        if self._scan_progress_dlg is not None:
            self._scan_progress_dlg.canceled.disconnect(self._on_scan_canceled)
            self._scan_progress_dlg.close()
            self._scan_progress_dlg = None
        # 弹出统计结果窗口（非模态，不阻塞继续标注）
        dlg = ScanStatsDialog(self._work_dir, self)
        dlg.set_counts(counts, file_total=len(self.label_scan_worker.json_paths))
        dlg.show()

    def _on_scan_progress(self, ratio: float) -> None:
        """扫描进度更新：按比例换算文件数并刷新进度对话框。

        Args:
            ratio: 进度比例（0-1，由 worker 按 done/total 发射）。
        """
        if self._scan_progress_dlg is None:
            return
        # 反算文件数以复用 update_progress 的 n/total 文本格式
        total = len(self.label_scan_worker.json_paths)
        done = int(round(ratio * total)) if total else 0
        self._scan_progress_dlg.update_progress(done, total)

    def _refresh_labels(self) -> None:
        """刷新标签列表并回写 _all_labels（扫描结果 ∪ 画布标签，标签唯一数据源）。

        属性弹窗与右侧标签列表共用 _all_labels，保证两处列表完全同步。
        画布标签强制转字符串（兼容数字标签的标注数据，避免混合类型排序崩溃）。
        注意：累加路径不合并大小写不同的同名标签（"Person" 与 "person"
        并存，按用户要求保持原拼写）；仅显式扫描的结果由扫描链路预合并
        大小写（collect_labels_from_files 的合并口径），二者取并集。
        """
        labels = set(self._all_labels)
        for shape in self.canvas.shapes():
            label = str(shape.get("label", "") or "")
            if label:
                labels.add(label)
        self._all_labels = sorted(labels)
        self.label_section.set_labels(self._all_labels)

    def _refresh_objects(self) -> None:
        """刷新对象列表（全部形状统一，不再按 shape_type 拆分关键点列表）。

        条目文本为 "label [组号]"（有非负整数 group_id 时）或 "label"，
        不带形状类型后缀；圆点颜色按标签色计算（color_for_label，与画布
        描边/文本一致）；复选框状态取自 shape 运行时键 "_visible"（缺省
        可见）。填充后按画布当前选中集合重新同步列表选中态。
        """
        items = []
        for idx, shape in enumerate(self.canvas.shapes()):
            label = shape.get("label", "")
            gid = shape.get("group_id")
            # 有分组时显示组号（恒显示，不受画布渲染开关影响）
            if isinstance(gid, int) and gid >= 0:
                text = f"{label} [{gid}]"
            else:
                text = label
            # 圆点颜色：标签色（与画布描边/文本一致）
            color = color_for_label(str(label))
            items.append((idx, text, label, shape.get("_visible", True), color))
        self.object_section.set_objects(items)
        # 同步画布选中集合到列表（select_objects 按映射分派，不发射信号）
        indices = self._selected_shape_indices()
        if indices:
            self.object_section.select_objects(indices)

    # -------------------------- 目录状态控制 --------------------------
    def _has_workspace(self) -> bool:
        """返回是否已有可编辑的图像工作区。"""
        return self._current_index >= 0 and bool(self.canvas.image_path())

    def _update_edit_state(self) -> None:
        """统一更新编辑相关控件的可用性（目录校验）。"""
        has_image = self._has_workspace()

        # 工具栏
        self.left_toolbar.set_edit_enabled(has_image)
        self.left_toolbar.set_file_ops_enabled(has_image)

        # 菜单动作
        self.act_save.setEnabled(has_image)
        self.act_save_as.setEnabled(has_image)
        self.act_delete.setEnabled(has_image)
        self.act_clear.setEnabled(has_image)
        self.act_undo.setEnabled(has_image)
        self.act_redo.setEnabled(has_image)
        self.act_delete_image.setEnabled(has_image)
        # 扫描并统计：有工作区（已打开目录/图片）才可扫描
        self.act_scan_stats.setEnabled(has_image)
        for act in self._tool_actions.values():
            act.setEnabled(has_image)

    def _update_status(self) -> None:
        """更新状态栏：当前图片序号与未保存标记。"""
        if self._current_index < 0:
            self._status_label.setText("未打开文件夹")
            return
        total = len(self._image_files)
        dirty = "（未保存）" if self._dirty else ""
        name = Path(self._current_image_path()).name
        self._status_label.setText(f"{self._current_index + 1}/{total}  {name}{dirty}")

    # -------------------------- 帮助 --------------------------
    def _on_manual(self) -> None:
        """打开内置使用说明书阅读窗（非模态；已打开时置前激活）。"""
        if self._manual_dlg is not None and self._manual_dlg.isVisible():
            self._manual_dlg.raise_()
            self._manual_dlg.activateWindow()
            return
        dlg = ManualDialog(self)
        dlg.show()
        self._manual_dlg = dlg

    def _on_about(self) -> None:
        """显示关于对话框。"""
        showMessageBox(
            QMessageBox.Icon.Information,
            f"{__appname__} v{__version__}\n\n"
            "智能数据标注工具：自动标注 + 标注预览 + 格式转换\n"
            "标注格式完全复用 labelme JSON。\n\n"
            "快捷键：默认快捷键见各菜单显示（如 Ctrl+O 打开 / Ctrl+S 保存 / "
            "V/R/P/G 切换工具 / Ctrl+0 适应窗口 / Ctrl+滚轮 缩放画布）\n"
            "可在 工具 → 自定义快捷键... 中按个人习惯修改",
        )

    # -------------------------- 在线更新 --------------------------
    def _on_check_update(self, quiet: bool = False) -> None:
        """发起检查更新（后台线程），结果经信号回传。

        Args:
            quiet: 静默模式（启动自动检查=True）：无更新/失败仅记日志
                不弹窗；菜单手动检查=False 时全程弹窗反馈。
        """
        # 防重入：检查已在进行时提示（静默模式直接忽略）
        if self._update_check_worker.isRunning():
            if not quiet:
                showMessageBox(QMessageBox.Icon.Warning, "正在检查更新，请稍候")
            return
        self._update_quiet = quiet
        if not quiet:
            self.statusBar().showMessage("正在检查更新...", 3000)
        self._update_check_worker.start()

    def _on_update_up_to_date(self) -> None:
        """检查结果：当前已是最新版本。"""
        if self._update_quiet:
            LOGGER.info(f"检查更新：当前版本 v{__version__} 已是最新")
        else:
            showMessageBox(
                QMessageBox.Icon.Information,
                f"当前已是最新版本（v{__version__}）",
            )

    def _on_update_check_error(self, message: str) -> None:
        """检查结果：网络失败或响应异常。

        Args:
            message: 错误描述。
        """
        # 静默模式仅记日志（worker 内已记 warning），不打扰用户
        if self._update_quiet:
            return
        showMessageBox(
            QMessageBox.Icon.Warning,
            f"检查更新失败：\n{message}\n\n请检查网络连接后重试",
        )

    def _on_update_found(self, info) -> None:
        """检查结果：发现新版本，弹窗询问是否更新。

        Args:
            info: ReleaseInfo（远端最新版本与安装器下载信息）。
        """
        LOGGER.info(f"发现新版本: {info.tag_name}（当前 v{__version__}）")
        # 三选弹窗：立即更新 / 查看发布页 / 取消（静默检查同样弹窗，仅在有更新时打扰）
        msg = QMessageBox(
            QMessageBox.Icon.Information,
            "发现新版本",
            f"发现新版本 {info.tag_name}（当前 v{__version__}）。\n\n"
            "是否立即更新？更新将通过在线安装器自动完成，\n"
            "下载完成后程序将关闭并启动安装程序。",
            QMessageBox.StandardButton.NoButton,
            self,
        )
        update_btn = msg.addButton("立即更新", QMessageBox.ButtonRole.AcceptRole)
        page_btn = msg.addButton("查看发布页", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is update_btn:
            self._start_installer_download(info)
        elif clicked is page_btn:
            # 打开浏览器前往 Release 发布页（标准库 webbrowser，无 Qt 依赖）
            webbrowser.open(RELEASE_PAGE_URL)

    def _start_installer_download(self, info) -> None:
        """开始下载在线安装器到临时目录（后台线程 + 进度对话框）。

        Args:
            info: ReleaseInfo（安装器下载 URL 与大小）。
        """
        # 防重入：下载已在进行时提示
        if self._update_download_worker.isRunning():
            showMessageBox(QMessageBox.Icon.Warning, "更新安装器正在下载中，请稍候")
            return
        # 保存路径：系统临时目录（带版本标签避免多版本残留混淆）
        dest = Path(tempfile.gettempdir()) / f"BrilliantAnnotator_OnlineSetup_{info.tag_name}.exe"
        self._update_download_worker.set_task(info.setup_url, dest)
        # 进度对话框：不确定进度模式（0,0 显示滚动动画），禁用取消
        dlg = QProgressDialog("正在下载更新安装器...", None, 0, 0, self)
        dlg.setWindowTitle("在线更新")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.setMinimumWidth(320)
        dlg.show()
        self._update_dlg = dlg
        self._update_download_worker.start()

    def _on_update_download_progress(self, ratio: float) -> None:
        """下载进度回调：更新进度对话框文本（未知大小时仅显示滚动动画）。

        Args:
            ratio: 已下载比例（0-1，总大小未知时为 0）。
        """
        if self._update_dlg is not None and ratio > 0:
            self._update_dlg.setLabelText(f"正在下载更新安装器... {ratio * 100:.0f}%")

    def _on_update_download_error(self, message: str) -> None:
        """下载失败：关闭进度对话框并提示。

        Args:
            message: 错误描述。
        """
        self._close_update_progress_dlg()
        showMessageBox(
            QMessageBox.Icon.Critical,
            f"下载更新安装器失败：\n{message}",
        )

    def _on_installer_downloaded(self, path_str: str) -> None:
        """下载完成：关闭进度框，确认后登记待安装器并关闭主程序。

        主窗口经 closeEvent 正常走脏数据确认/配置落盘/worker 清理，
        确认关闭后（event.accept）由 closeEvent 收尾拉起静默安装器。

        Args:
            path_str: 已下载的安装器本地路径。
        """
        self._close_update_progress_dlg()
        # 二次确认：更新将关闭程序
        msg = QMessageBox(
            QMessageBox.Icon.Question,
            "下载完成",
            "更新安装器已下载完成。\n\n"
            "立即安装将关闭程序并启动安装程序（安装完成后可重新启动）。\n"
            "是否继续？",
            QMessageBox.StandardButton.NoButton,
            self,
        )
        install_btn = msg.addButton("立即安装", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("稍后再说", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        if msg.clickedButton() is not install_btn:
            return
        # 登记待安装路径，走正常关闭流程（closeEvent 收尾拉起安装器）
        self._pending_update_installer = Path(path_str)
        self.close()
        # 关闭被用户取消（脏数据确认选取消等）时清除登记，避免残留状态
        if self.isVisible():
            self._pending_update_installer = None

    def _close_update_progress_dlg(self) -> None:
        """关闭并释放下载进度对话框（若存在）。"""
        if self._update_dlg is not None:
            self._update_dlg.close()
            self._update_dlg = None

    def _launch_pending_installer(self) -> None:
        """closeEvent 收尾：拉起待安装的静默安装器（进程退出前启动）。

        安装模式按当前安装目录检测（install_mode.txt 标记优先，回退
        TensorRT 运行库启发式）；启动失败弹窗提示但不阻塞退出。
        """
        installer_path = self._pending_update_installer
        self._pending_update_installer = None
        if installer_path is None:
            return
        # 安装目录：打包环境取 exe 所在目录；源码运行时取工作目录（仅调试用）
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).parent
        else:
            exe_dir = Path.cwd()
        mode = detect_install_mode(exe_dir)
        try:
            run_installer(installer_path, mode)
        except UpdaterError as e:
            showMessageBox(QMessageBox.Icon.Critical, str(e))

    # -------------------------- 关闭处理 --------------------------
    def closeEvent(self, event) -> None:
        """关闭窗口时确认未保存修改、落盘渲染配置并停止运行中的 worker。"""
        # 未保存防呆：有未保存修改且未开自动保存时先确认，取消则忽略关闭
        if not self._confirm_discard_changes():
            event.ignore()
            return
        # 记录窗口布局状态（工具栏/三个列表 Dock 的位置、堆叠高度、
        # 挂靠宽度与显隐）随配置落盘，启动时经 restoreState 完整还原
        self._render_config.dock_state = bytes(self.saveState().toBase64()).decode("ascii")
        # 防抖兜底：拖拽分栏后立即关闭窗口时确保尺寸配置落盘
        if self._render_save_timer.isActive():
            self._render_save_timer.stop()
            self._save_render_config_now()
        # 关闭扫描进度对话框（若存在）：canceled 联动停止扫描 worker
        if self._scan_progress_dlg is not None:
            self._scan_progress_dlg.close()
            self._scan_progress_dlg = None
        # 关闭更新下载进度对话框（若存在）
        self._close_update_progress_dlg()
        for worker in (
            self.annotate_worker,
            self.convert_worker,
            self.label_scan_worker,
            self.single_annotate_worker,
            self._update_check_worker,
            self._update_download_worker,
        ):
            if worker.isRunning():
                worker.stop()
        self.annotate_worker.wait(3000)
        self.convert_worker.wait(3000)
        self.label_scan_worker.wait(1500)
        self.single_annotate_worker.wait(3000)
        # 更新线程停止请求后短等待（网络请求阻塞时由超时自然结束，不阻塞退出）
        self._update_check_worker.wait(1000)
        self._update_download_worker.wait(1000)
        event.accept()
        # 在线更新收尾：主窗口确认关闭后拉起静默安装器（必须在进程
        # 退出前启动，故放在 event.accept 之后、返回事件循环之前）
        self._launch_pending_installer()

    # -------------------------- 图标 --------------------------
    def set_window_icon(self, icon: QIcon) -> None:
        """设置窗口图标（由 main.py 调用，兼容打包路径）。"""
        self.setWindowIcon(icon)