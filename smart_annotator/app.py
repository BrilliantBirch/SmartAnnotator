# -*- coding: utf-8 -*-
"""
主窗口 - MainWindow（三栏式标注编辑器）

三栏布局（参考 labelme / X-Anylabel）：
    - 左侧：快捷操作栏（LeftToolbar）—— 文件/自动标注/标注工具
    - 中间：标注画布（Canvas）—— 图像显示 + 标注绘制/编辑
    - 右侧：信息栏（RightPanel）—— 标签/对象/文件/关键点列表
      （画布与右栏宽度、右栏各列表高度均可拖拽调节并持久化）

标准菜单栏（文件/编辑/视图/工具/帮助）+ 快捷键体系：
    - 文件：打开文件夹 Ctrl+O、打开文件 Ctrl+Shift+O、保存 Ctrl+S、
      另存为 Ctrl+Shift+S、自动保存（勾选后切换图片时自动保存）
    - 编辑：编辑模式 Ctrl+E、撤销 Ctrl+Z、重做 Ctrl+Shift+Z、删除选中标注、
      清空标注、Delete 按焦点上下文删除、删除图片及标注 Shift+Delete
    - 工具：加载模型、自动标注单张/全部、格式转换
    - 标注工具：编辑 V、矩形 R、点 P、多边形 G
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
更新: 2026-09-03 列表复选框接线（对象/关键点列表可见性控制、point 形状分流关键点列表、文件列表只读已标注复选框、Delete 路由关键点分支）
"""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QActionGroup, QIcon, QShortcut, QCursor
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QDialog,
    QFileDialog,
    QDialogButtonBox,
    QMessageBox,
    QMenu,
    QApplication,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QSplitter,
)

from . import __appname__, __version__
from .styles import GLOBAL_QSS
from .config import SysConfig, RenderConfig
from .core import labelme_io
from .utils import LOGGER, getImageFilesInDir, getJsonFilesInDir
from .utils.render_store import load_render_config, save_render_config
from .widgets.dialogs import chooseDir, showMessageBox
from .widgets.left_toolbar import (
    LeftToolbar,
    TOOL_SELECT,
    TOOL_RECTANGLE,
    TOOL_POINT,
    TOOL_POLYGON,
)
from .widgets.right_panel import RightPanel
from .widgets.canvas import Canvas
from .widgets.shape_dialog import ShapeDialog
from .pages.annotate_page import AnnotatePage
from .pages.convert_page import ConvertPage
from .workers.annotate_worker import AnnotationWorker
from .workers.convert_worker import ConvertWorker
from .workers.single_annotate_worker import SingleAnnotateWorker
from .workers.label_scan_worker import LabelScanWorker

# 工具名 -> 显示文案
_TOOL_LABELS = {
    TOOL_SELECT: "编辑",
    TOOL_RECTANGLE: "矩形",
    TOOL_POINT: "点",
    TOOL_POLYGON: "多边形",
}

# 工具名 -> 快捷键
_TOOL_SHORTCUTS = {
    TOOL_SELECT: "V",
    TOOL_RECTANGLE: "R",
    TOOL_POINT: "P",
    TOOL_POLYGON: "G",
}


class MainWindow(QMainWindow):
    """应用主窗口 - 三栏标注编辑器 + 标准菜单栏。"""

    def __init__(self):
        """初始化主窗口，构建菜单栏、三栏布局并连接信号。"""
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
        # 自动保存（文件菜单勾选项）：切换图片时自动保存当前标注
        self._auto_save: bool = False

        # 自动标注配置（加载模型后可用）
        self.annotate_config: "SysConfig | None" = None
        # 后台扫描汇总的标签与关键点（关键点列表显示由扫描结果自动识别）
        self._all_labels: list = []
        self._label_keypoints: list = []
        # 画布渲染配置（视图菜单可调，持久化于 %APPDATA%/BrilliantAnnotator）
        self._render_config: RenderConfig = load_render_config()
        # 渲染配置防抖落盘定时器（分栏拖拽等高频变更合并为一次写盘）
        self._render_save_timer = QTimer(self)
        self._render_save_timer.setSingleShot(True)
        self._render_save_timer.setInterval(500)
        self._render_save_timer.timeout.connect(self._save_render_config_now)

        # 后台线程
        self.annotate_worker = AnnotationWorker()
        self.convert_worker = ConvertWorker()
        self.label_scan_worker = LabelScanWorker()

        # 构建界面
        self._build_menubar()
        self._build_ui()
        self._connect_signals()

        # 应用持久化的渲染配置到画布
        self.canvas.set_render_config(self._render_config)

        # 图片浏览快捷键：A 上一张 / D 下一张
        QShortcut(QKeySequence("A"), self, self._prev_image)
        QShortcut(QKeySequence("D"), self, self._next_image)
        # Delete：按焦点上下文路由删除业务（对象列表/文件列表/画布选中）
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self._on_delete_shortcut)
        # 形状复制/粘贴（画布内部剪贴板）
        QShortcut(QKeySequence("Ctrl+C"), self, self.canvas.copy_selected)
        QShortcut(QKeySequence("Ctrl+V"), self, self.canvas.paste_clipboard)

        self.setStyleSheet(GLOBAL_QSS)

        self._status_label = QLabel("未打开文件夹")
        self.statusBar().addWidget(self._status_label)

        # 初始目录校验：未打开目录时禁用编辑功能
        self._update_edit_state()

    # -------------------------- 菜单栏 --------------------------
    def _build_menubar(self) -> None:
        """构建菜单栏：文件 / 编辑 / 工具 / 帮助。"""
        menu_bar = self.menuBar()

        # ===== 文件 =====
        menu_file = menu_bar.addMenu("文件(&F)")
        self.act_open = QAction("打开文件夹", self)
        self.act_open.setShortcut(QKeySequence("Ctrl+O"))
        self.act_open.triggered.connect(self._on_open_folder)
        menu_file.addAction(self.act_open)

        self.act_open_file = QAction("打开文件", self)
        self.act_open_file.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.act_open_file.triggered.connect(self._on_open_file)
        menu_file.addAction(self.act_open_file)

        menu_file.addSeparator()
        self.act_save = QAction("保存", self)
        self.act_save.setShortcut(QKeySequence("Ctrl+S"))
        self.act_save.triggered.connect(self._on_save)
        menu_file.addAction(self.act_save)

        self.act_save_as = QAction("另存为", self)
        self.act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_save_as.triggered.connect(self._on_save_as)
        menu_file.addAction(self.act_save_as)

        # 自动保存：勾选后每次切换图片自动保存当前标注
        self.act_autosave = QAction("自动保存", self)
        self.act_autosave.setCheckable(True)
        self.act_autosave.toggled.connect(self._on_autosave_toggled)
        menu_file.addAction(self.act_autosave)

        menu_file.addSeparator()
        self.act_exit = QAction("退出", self)
        self.act_exit.triggered.connect(self.close)
        menu_file.addAction(self.act_exit)

        # ===== 编辑 =====
        menu_edit = menu_bar.addMenu("编辑(&E)")
        # 编辑模式（快捷键 Ctrl+E）：仅编辑模式允许拖拽/端点缩放/属性修改
        self.act_edit_mode = QAction("编辑模式", self)
        self.act_edit_mode.setShortcut(QKeySequence("Ctrl+E"))
        self.act_edit_mode.triggered.connect(self._enter_edit_mode)
        menu_edit.addAction(self.act_edit_mode)

        menu_edit.addSeparator()
        self.act_undo = QAction("撤销", self)
        self.act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.act_undo.triggered.connect(self._on_undo)
        menu_edit.addAction(self.act_undo)

        self.act_redo = QAction("重做", self)
        self.act_redo.setShortcut(QKeySequence("Ctrl+Shift+Z"))
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
        self.act_delete_image.setShortcut(QKeySequence("Shift+Delete"))
        self.act_delete_image.triggered.connect(self._on_delete_image_and_annotation)
        menu_edit.addAction(self.act_delete_image)

        # ===== 视图 =====
        menu_view = menu_bar.addMenu("视图(&V)")

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

        # ===== 工具 =====
        menu_tool = menu_bar.addMenu("工具(&T)")

        # 标注工具（互斥 + 单字母快捷键）
        self._tool_action_group = QActionGroup(self)
        self._tool_action_group.setExclusive(True)
        self._tool_actions: dict = {}
        for tool in (TOOL_SELECT, TOOL_RECTANGLE, TOOL_POINT, TOOL_POLYGON):
            act = QAction(_TOOL_LABELS[tool], self)
            act.setCheckable(True)
            act.setShortcut(QKeySequence(_TOOL_SHORTCUTS[tool]))
            act.triggered.connect(lambda checked=False, t=tool: self._on_tool_selected(t))
            self._tool_action_group.addAction(act)
            menu_tool.addAction(act)
            self._tool_actions[tool] = act
        self._tool_actions[TOOL_SELECT].setChecked(True)

        menu_tool.addSeparator()
        self.act_load_model = QAction("加载模型 / 自动标注设置", self)
        self.act_load_model.triggered.connect(self._open_annotate_dialog)
        menu_tool.addAction(self.act_load_model)

        self.act_annotate_single = QAction("自动标注单张", self)
        self.act_annotate_single.triggered.connect(self._on_annotate_single)
        menu_tool.addAction(self.act_annotate_single)

        self.act_annotate_all = QAction("自动标注全部", self)
        self.act_annotate_all.triggered.connect(self._open_annotate_dialog)
        menu_tool.addAction(self.act_annotate_all)

        self.act_convert = QAction("格式转换", self)
        self.act_convert.triggered.connect(self._open_convert_dialog)
        menu_tool.addAction(self.act_convert)

        # ===== 帮助 =====
        menu_help = menu_bar.addMenu("帮助(&H)")
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

    # -------------------------- 三栏布局 --------------------------
    def _build_ui(self) -> None:
        """构建三栏式主体布局（画布与右栏宽度可拖拽调节）。"""
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.left_toolbar = LeftToolbar()
        self.canvas = Canvas()
        self.right_panel = RightPanel()

        # 中栏画布与右栏信息栏之间用水平分栏：拖拽分隔条调节第三栏宽度
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.canvas)
        self.main_splitter.addWidget(self.right_panel)
        # 画布随窗口伸缩（stretch=1），右栏保持用户设定宽度（stretch=0）
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(6)

        root.addWidget(self.left_toolbar)
        root.addWidget(self.main_splitter, 1)

        # 应用持久化的右栏宽度与各列表高度
        self._apply_panel_sizes()
        # 拖拽变更 → 更新配置（防抖落盘）
        self.main_splitter.splitterMoved.connect(self._on_main_splitter_moved)
        self.right_panel.sizes_changed.connect(self._on_right_sizes_changed)

    # -------------------------- 界面布局尺寸 --------------------------
    def _apply_panel_sizes(self) -> None:
        """应用持久化的右栏宽度与各列表高度到分栏控件。"""
        cfg = self._render_config
        # 右栏宽度：以当前窗口可用宽度为总量分配（画布占其余全部，
        # 保证右栏精确命中配置宽度；窗口过窄时按比例收缩）
        avail = max(self.width() - self.left_toolbar.width(), cfg.panel_width + 200)
        self.main_splitter.setSizes([avail - cfg.panel_width, cfg.panel_width])
        # 四组列表高度（关键点列表隐藏时不参与本次分配）
        self.right_panel.set_section_heights([
            cfg.label_list_height,
            cfg.object_list_height,
            cfg.file_list_height,
            cfg.kpt_list_height,
        ])

    def _on_main_splitter_moved(self, pos: int, index: int) -> None:
        """主分栏拖动：记录右栏宽度并防抖保存。

        Args:
            pos: 拖动位置（仅为信号签名，未使用）。
            index: 分隔条下标（仅为信号签名，未使用）。
        """
        self._render_config.panel_width = self.right_panel.width()
        self._schedule_render_save()

    def _on_right_sizes_changed(self, heights: list) -> None:
        """右栏各列表高度变化：记录并防抖保存。

        Args:
            heights: [标签, 对象, 文件, 关键点] 高度列表。
        """
        if len(heights) < 4:
            return
        self._render_config.label_list_height = heights[0]
        self._render_config.object_list_height = heights[1]
        self._render_config.file_list_height = heights[2]
        self._render_config.kpt_list_height = heights[3]
        self._schedule_render_save()

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
        """连接左右栏、画布与菜单动作之间的信号。"""
        # 左侧工具栏
        self.left_toolbar.open_requested.connect(self._on_open_folder)
        self.left_toolbar.open_file_requested.connect(self._on_open_file)
        self.left_toolbar.save_requested.connect(self._on_save)
        self.left_toolbar.save_as_requested.connect(self._on_save_as)
        self.left_toolbar.delete_requested.connect(self._on_delete)
        self.left_toolbar.delete_image_requested.connect(self._on_delete_image_and_annotation)
        self.left_toolbar.load_model_requested.connect(self._open_annotate_dialog)
        self.left_toolbar.annotate_single_requested.connect(self._on_annotate_single)
        self.left_toolbar.annotate_all_requested.connect(self._open_annotate_dialog)
        self.left_toolbar.tool_selected.connect(self._on_tool_selected)

        # 画布
        self.canvas.shapes_changed.connect(self._on_shapes_changed)
        self.canvas.selection_changed.connect(self._on_canvas_selection_changed)
        self.canvas.shape_created.connect(self._on_shape_created)
        # 编辑模式右键（空白/对象）：弹出上下文菜单进入编辑模式
        self.canvas.context_menu_requested.connect(self._on_canvas_context_menu)

        # 右侧信息栏
        self.right_panel.label_selected.connect(self._on_label_selected)
        self.right_panel.objects_selected.connect(self._on_objects_selected)
        self.right_panel.file_selected.connect(self._on_file_selected)
        # 复选框可见性：隐藏/恢复对应形状的画布渲染（纯视图，不标脏）
        self.right_panel.shape_visibility_requested.connect(self._on_shape_visibility_requested)
        # 关键点列表（point 形状）：选中联动与右键编辑/删除（与对象列表同语义）
        self.right_panel.keypoints_selected.connect(self._on_objects_selected)
        self.right_panel.edit_keypoint_requested.connect(self._on_edit_object)
        self.right_panel.delete_keypoints_requested.connect(self._on_delete_objects)
        # 对象列表（a）右键菜单：编辑属性 / 删除 / 进入编辑模式
        self.right_panel.edit_object_requested.connect(self._on_edit_object)
        self.right_panel.delete_objects_requested.connect(self._on_delete_objects)
        self.right_panel.enter_edit_mode_requested.connect(self._enter_edit_mode)

        # 后台标签扫描
        self.label_scan_worker.labels_ready.connect(self._on_labels_scanned)

    # -------------------------- 文件操作 --------------------------
    def _on_open_folder(self) -> None:
        """打开工作文件夹：扫描图片并加载第一张。"""
        directory = chooseDir(self._work_dir)
        if not directory:
            return
        images = sorted(getImageFilesInDir(directory))
        if not images:
            showMessageBox(QMessageBox.Icon.Warning, "该目录未扫描到图片（jpg/jpeg/png/bmp）")
            self._update_edit_state()
            return
        self._work_dir = directory
        self._image_files = images
        self._current_index = -1
        self.right_panel.set_files(images, self._file_annotated_flags())
        self._load_image_by_index(0)
        # 后台扫描目录下全部标注，汇总标签/关键点（不阻塞 UI）
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
        if not self.canvas.load_image(image_path):
            showMessageBox(QMessageBox.Icon.Warning, f"无法加载图片: {image_path}")
            return
        self._work_dir = str(Path(image_path).parent)
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
        self.right_panel.set_files([image_path], self._file_annotated_flags())
        self.right_panel.select_file(0)
        self._refresh_objects()
        self._update_edit_state()
        self._start_label_scan()
        self._update_status()
        LOGGER.info(f"已打开图片: {image_path}")

    def _open_annotation_file(self, json_path: str) -> None:
        """解析单个标注文件并加载其关联图像。

        Args:
            json_path: labelme JSON 标注文件路径。
        """
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

        self.canvas.set_shapes(labelme_io.document_shapes(doc))
        json_dir = str(Path(json_path).parent)
        self._work_dir = json_dir
        self._image_files = [image_path]
        self._current_index = 0
        self._dirty = False
        self.right_panel.set_files([image_path], self._file_annotated_flags())
        self.right_panel.select_file(0)
        self._refresh_objects()
        self._update_edit_state()
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

    def _load_image_by_index(self, index: int) -> None:
        """加载指定下标的图片及其同名标注。

        自动保存开启时，加载新图前先保存当前图片的全部标注。

        Args:
            index: 图片在文件列表中的下标。
        """
        if not (0 <= index < len(self._image_files)):
            return
        # 自动保存：切换图片前保存当前图片的标注（含标签/形状/属性）
        if index != self._current_index:
            self._auto_save_current()
        path = self._image_files[index]
        if not self.canvas.load_image(path):
            showMessageBox(QMessageBox.Icon.Warning, f"无法加载图片: {path}")
            return
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

        self.right_panel.select_file(index)
        self._refresh_objects()
        self._refresh_keypoints()
        self._update_edit_state()
        self._update_status()

    def _on_file_selected(self, index: int) -> None:
        """右侧文件列表选中切换当前图片。"""
        if index != self._current_index:
            self._load_image_by_index(index)

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
        # 保存到当前图片同名标注文件：文件列表复选框标记为已标注
        if json_path == self._current_json_path() and 0 <= self._current_index < len(self._image_files):
            self.right_panel.set_file_annotated(self._current_index, True)
        LOGGER.info(f"标注已保存: {json_path}")

    # -------------------------- 编辑操作 --------------------------
    def _on_undo(self) -> None:
        """撤销上一步。"""
        self.canvas.undo()

    def _on_redo(self) -> None:
        """重做上一步。"""
        self.canvas.redo()

    def _on_delete(self) -> None:
        """删除当前选中的标注。"""
        self.canvas.delete_selected()

    def _on_clear(self) -> None:
        """清空当前图片全部标注。"""
        self.canvas.clear_shapes()

    def _on_delete_shortcut(self) -> None:
        """Delete 快捷键：按当前焦点控件路由删除业务。

        路由顺序：文本输入控件不拦截 → 对象列表删选中对象 →
        关键点列表删选中 point 形状 → 文件列表删选中图像及标注
        （含确认框）→ 默认删画布选中形状。
        """
        fw = QApplication.focusWidget()
        # 焦点在文本输入控件：不拦截，保留正常文本删除行为
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return
        # 焦点在对象列表：删除列表选中对象（映射下标，与画布选中态双向同步）
        obj_list = self.right_panel.object_section.list
        if fw is obj_list or (fw is not None and obj_list.isAncestorOf(fw)):
            indices = self.right_panel.selected_object_indices()
            if indices:
                self.canvas.delete_shapes_at(indices)
            return
        # 焦点在关键点列表：删除列表选中 point 形状（映射下标）
        kpt_list = self.right_panel.kpt_section.list
        if fw is kpt_list or (fw is not None and kpt_list.isAncestorOf(fw)):
            indices = self.right_panel.selected_kpt_indices()
            if indices:
                self.canvas.delete_shapes_at(indices)
            return
        # 焦点在文件列表：删除选中图像及同名标注（复用含确认框的健壮删除逻辑）
        file_list = self.right_panel.file_section.list
        if fw is file_list or (fw is not None and file_list.isAncestorOf(fw)):
            if self._has_workspace() and file_list.currentRow() >= 0:
                self._on_delete_image_and_annotation()
            return
        # 默认（画布或其他控件）：删除画布选中形状（无选中则无操作）
        self.canvas.delete_selected()

    # -------------------------- 文件删除 --------------------------
    def _on_delete_image_and_annotation(self) -> None:
        """删除当前图片及其同名标注文件（Shift+Delete 键）。

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
        if QMessageBox.question(
            self, "确认删除", msg
        ) != QMessageBox.StandardButton.Yes:
            return
        # 执行文件删除（缺失文件静默跳过）
        for f in files_to_delete:
            Path(f).unlink(missing_ok=True)

        # 从文件列表移除当前项，避免下标越界
        if 0 <= self._current_index < len(self._image_files):
            self._image_files.pop(self._current_index)
        self.right_panel.set_files(self._image_files, self._file_annotated_flags())

        if not self._image_files:
            # 无剩余图片：清空工作区状态
            self._current_index = -1
            self.canvas.clear_shapes()
        else:
            # 加载列表中下标一致（或最后一张）的图片，保持连续性
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
        """打开自动标注设置对话框（复用 AnnotatePage + 批量 worker）。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("自动标注 / 模型加载")
        dialog.resize(980, 720)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        page = AnnotatePage()
        page.set_worker(self.annotate_worker)
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

        if dialog.exec() == QDialog.DialogCode.Accepted:
            cfg = SysConfig()
            try:
                page.collect_config(cfg)
            except Exception as e:
                LOGGER.error(f"收集标注配置失败: {e}")
                return
            self.annotate_config = cfg
            self.left_toolbar.set_annotate_enabled(bool(cfg.annotate_config.model_path))
            LOGGER.info("已保存自动标注配置")

    def _on_annotate_single(self) -> None:
        """对当前图片执行单张自动标注（后台线程推理，结果回填画布）。"""
        img = self._current_image_path()
        if not img:
            showMessageBox(QMessageBox.Icon.Warning, "请先打开图片")
            return
        if self.annotate_config is None or not self.annotate_config.annotate_config.model_path:
            showMessageBox(QMessageBox.Icon.Warning, "请先加载模型（工具 → 加载模型 / 自动标注设置）")
            return

        worker = SingleAnnotateWorker()
        worker.set_task(self.annotate_config, img)
        worker.shapes_ready.connect(self._on_single_shapes_ready)
        worker.error_occurred.connect(lambda msg: showMessageBox(QMessageBox.Icon.Critical, msg))
        worker.task_finished.connect(worker.deleteLater)
        self.left_toolbar.set_annotate_enabled(False)
        worker.start()

    def _on_single_shapes_ready(self, shapes: list) -> None:
        """单张标注完成：结果回填画布并刷新右侧列表。"""
        self.canvas.set_shapes(shapes)
        self._dirty = True
        self._refresh_objects()
        self._refresh_labels()
        self.left_toolbar.set_annotate_enabled(True)
        self._update_status()

    # -------------------------- 格式转换 --------------------------
    def _open_convert_dialog(self) -> None:
        """打开格式转换对话框（复用 ConvertPage + 批量 worker）。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("格式转换")
        dialog.resize(980, 720)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        page = ConvertPage()
        page.set_worker(self.convert_worker)
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
        """自动保存选项切换。

        Args:
            checked: 是否勾选自动保存。
        """
        self._auto_save = checked
        state = "开启" if checked else "关闭"
        LOGGER.info(f"自动保存已{state}")
        self.statusBar().showMessage(f"自动保存已{state}", 2000)

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
            self.canvas.delete_selected()
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

        Args:
            indices: 对象下标列表。
        """
        if not indices:
            return
        self.canvas.delete_shapes_at(indices)

    # -------------------------- 右侧栏联动 --------------------------
    def _on_shapes_changed(self) -> None:
        """画布形状变化：标记未保存、刷新对象列表。"""
        self._dirty = True
        self._refresh_objects()
        self._update_status()

    def _on_canvas_selection_changed(self, shapes: list) -> None:
        """画布选中集合变化（含多选）时联动对象/关键点列表选中态。

        select_objects 已泛化：按两列表的行号 → 形状下标映射分派，
        point 形状选中同步到关键点列表，其余同步到对象列表。

        Args:
            shapes: 选中形状字典列表（可为空）。
        """
        if not shapes:
            self.right_panel.clear_object_selection()
            return
        ids = {id(s) for s in shapes}
        indices = [i for i, s in enumerate(self.canvas.shapes()) if id(s) in ids]
        self.right_panel.select_objects(indices)

    def _on_objects_selected(self, indices: list) -> None:
        """对象列表选中集合（含多选）变化时联动画布多选。

        Args:
            indices: 对象下标列表。
        """
        self.canvas.select_shapes_by_indices(indices)

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
        """启动后台标签扫描（汇总工作目录下全部标注的类别/关键点）。

        扫描前先清空并隐藏关键点列表，避免切换文件夹后残留旧文件夹的关键点，
        仅当新文件夹扫描结果包含 point 类型 shape 时才重新显示（自动识别 pose）。
        """
        if not self._work_dir:
            return
        self._all_labels = []
        self._label_keypoints = []
        self._refresh_keypoints()
        paths = getJsonFilesInDir(self._work_dir)
        if self.label_scan_worker.isRunning():
            self.label_scan_worker.stop()
            self.label_scan_worker.wait(1500)
        self.label_scan_worker.set_task(paths)
        self.label_scan_worker.start()

    def _on_labels_scanned(self, labels: list, keypoints: list) -> None:
        """后台扫描完成：更新标签与关键点缓存并刷新界面。

        Args:
            labels: 标签名列表。
            keypoints: 关键点标签名列表。
        """
        self._all_labels = list(labels)
        self._label_keypoints = list(keypoints)
        self._refresh_labels()
        self._refresh_keypoints()

    def _refresh_labels(self) -> None:
        """刷新标签列表并回写 _all_labels（扫描结果 ∪ 画布标签，标签唯一数据源）。

        属性弹窗与右侧标签列表共用 _all_labels，保证两处列表完全同步。
        """
        labels = set(self._all_labels)
        for shape in self.canvas.shapes():
            label = shape.get("label", "")
            if label:
                labels.add(label)
        self._all_labels = sorted(labels)
        self.right_panel.set_labels(self._all_labels)

    def _refresh_objects(self) -> None:
        """刷新对象列表（非 point）与关键点列表（point），含复选框可见性。

        条目文本为 "label [G组号]"（有非负整数 group_id 时）或 "label"，
        不带形状类型后缀；point 形状进入关键点列表，其余进入对象列表，
        复选框状态取自 shape 运行时键 "_visible"（缺省可见）。
        关键点列表可见性：当前图像有 point 形状 或 扫描检测到关键点。
        填充后按画布当前选中集合重新同步列表选中态。
        """
        object_items = []
        kpt_items = []
        has_point = False
        for idx, shape in enumerate(self.canvas.shapes()):
            if shape.get("shape_type") == labelme_io.SHAPE_POINT:
                has_point = True
                target = kpt_items
            else:
                target = object_items
            label = shape.get("label", "")
            gid = shape.get("group_id")
            # 有分组时显示组号（对象/关键点列表恒显示，不受画布渲染开关影响）
            if isinstance(gid, int) and gid >= 0:
                text = f"{label} [G{gid}]"
            else:
                text = label
            target.append((idx, text, label, shape.get("_visible", True)))
        self.right_panel.set_objects(object_items)
        self.right_panel.set_keypoints(kpt_items)
        # 关键点列表可见性：当前图像有 point ∪ 扫描检测到关键点（pose 任务）
        self.right_panel.set_kpt_visible(has_point or bool(self._label_keypoints))
        # 同步画布选中集合到两列表（select_objects 按映射分派，不发射信号）
        indices = self._selected_shape_indices()
        if indices:
            self.right_panel.select_objects(indices)

    def _refresh_keypoints(self) -> None:
        """按"当前图像有 point 形状 ∪ 扫描检测到关键点"更新关键点列表可见性。

        列表内容由 _refresh_objects 按当前图像 point 形状填充（对象列表语义），
        此处仅处理扫描完成/切换文件夹后的可见性变化。
        """
        has_point = any(
            s.get("shape_type") == labelme_io.SHAPE_POINT
            for s in self.canvas.shapes()
        )
        self.right_panel.set_kpt_visible(has_point or bool(self._label_keypoints))

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
    def _on_about(self) -> None:
        """显示关于对话框。"""
        showMessageBox(
            QMessageBox.Icon.Information,
            f"{__appname__} v{__version__}\n\n"
            "智能数据标注工具：自动标注 + 标注预览 + 格式转换\n"
            "标注格式完全复用 labelme JSON。\n\n"
            "快捷键：V 编辑 / R 矩形 / P 点 / G 多边形\n"
            "Ctrl+E 进入编辑模式 / Ctrl+Z 撤销 / Ctrl+Shift+Z 重做\n"
            "Ctrl+C 复制 / Ctrl+V 粘贴 / Delete 按焦点删除（对象/文件/画布选中）\n"
            "A 上一张 / D 下一张 / Shift+Delete 删除图片及标注",
        )

    # -------------------------- 关闭处理 --------------------------
    def closeEvent(self, event) -> None:
        """关闭窗口时落盘渲染配置并停止运行中的 worker。"""
        # 防抖兜底：拖拽分栏后立即关闭窗口时确保尺寸配置落盘
        if self._render_save_timer.isActive():
            self._render_save_timer.stop()
            self._save_render_config_now()
        for worker in (self.annotate_worker, self.convert_worker, self.label_scan_worker):
            if worker.isRunning():
                worker.stop()
        self.annotate_worker.wait(3000)
        self.convert_worker.wait(3000)
        self.label_scan_worker.wait(1500)
        event.accept()

    # -------------------------- 图标 --------------------------
    def set_window_icon(self, icon: QIcon) -> None:
        """设置窗口图标（由 main.py 调用，兼容打包路径）。"""
        self.setWindowIcon(icon)