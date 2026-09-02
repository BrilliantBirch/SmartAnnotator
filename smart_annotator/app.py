# -*- coding: utf-8 -*-
"""
主窗口 - MainWindow（三栏式标注编辑器）

按需求对前端生态全面重构，采用经典三栏布局（参考 labelme / X-Anylabel）：
    - 左侧：快捷操作栏（LeftToolbar）—— 文件操作 + 自动标注 + 标注工具
    - 中间：标注画布（Canvas）—— 图像显示 + 标注绘制/编辑/预览
    - 右侧：信息栏（RightPanel）—— 标签/对象/文件/关键点列表

同时提供标准菜单栏（文件/编辑/工具/帮助），菜单动作与左侧工具栏共享同一套
处理函数。自动标注（单张/批量）与格式转换通过对话框复用原有 AnnotatePage /
ConvertPage 页面逻辑，标注数据完全复用 labelme JSON 格式（core/labelme_io.py）。

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-09-02 全面重构为三栏式标注编辑器，删除欢迎页与侧边栏/底部标签栏
"""

from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QInputDialog,
)

from . import __appname__, __version__
from .styles import GLOBAL_QSS
from .config import SysConfig, MODE
from .core import labelme_io
from .utils import LOGGER, getImageFilesInDir, getJsonFilesInDir
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
from .pages.annotate_page import AnnotatePage
from .pages.convert_page import ConvertPage
from .workers.annotate_worker import AnnotationWorker
from .workers.convert_worker import ConvertWorker
from .workers.single_annotate_worker import SingleAnnotateWorker

# 工具名 -> 菜单动作/工具栏之间共用的显示文案
_TOOL_LABELS = {
    TOOL_SELECT: "选择",
    TOOL_RECTANGLE: "矩形",
    TOOL_POINT: "点",
    TOOL_POLYGON: "多边形",
}


class MainWindow(QMainWindow):
    """应用主窗口 - 三栏标注编辑器 + 标准菜单栏。

    Attributes:
        left_toolbar: 左侧快捷操作栏。
        canvas: 中间标注画布。
        right_panel: 右侧信息栏。
        annotate_worker: 批量自动标注后台线程（复用页面逻辑）。
        convert_worker: 格式转换后台线程（复用页面逻辑）。
        annotate_config: 当前已加载的自动标注配置（None 表示未加载模型）。
    """

    def __init__(self):
        """初始化主窗口，构建菜单栏、三栏布局并连接信号。"""
        super().__init__()
        self.setWindowTitle(__appname__)
        self.setMinimumSize(960, 640)

        # 启动尺寸：屏幕可用区 80%
        screen = self.screen().availableGeometry()
        self.resize(int(screen.width() * 0.8), int(screen.height() * 0.8))

        # 工作目录与文件列表状态
        self._work_dir: str = ""
        self._image_files: list = []
        self._current_index: int = -1
        self._dirty: bool = False

        # 自动标注配置（加载模型后可用）
        self.annotate_config: "SysConfig | None" = None

        # 后台线程（批量标注 / 格式转换，生命周期与窗口一致）
        self.annotate_worker = AnnotationWorker()
        self.convert_worker = ConvertWorker()

        # 构建界面
        self._build_menubar()
        self._build_ui()
        self._connect_signals()

        # 应用全局样式
        self.setStyleSheet(GLOBAL_QSS)

        # 状态栏
        self._status_label = QLabel("未打开文件夹")
        self.statusBar().addWidget(self._status_label)

        self._refresh_labels()
        self._refresh_keypoints()

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

        self.act_save = QAction("保存", self)
        self.act_save.setShortcut(QKeySequence("Ctrl+S"))
        self.act_save.triggered.connect(self._on_save)
        menu_file.addAction(self.act_save)

        self.act_save_as = QAction("另存为", self)
        self.act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_save_as.triggered.connect(self._on_save_as)
        menu_file.addAction(self.act_save_as)

        menu_file.addSeparator()
        self.act_exit = QAction("退出", self)
        self.act_exit.triggered.connect(self.close)
        menu_file.addAction(self.act_exit)

        # ===== 编辑 =====
        menu_edit = menu_bar.addMenu("编辑(&E)")
        self.act_delete = QAction("删除选中", self)
        self.act_delete.setShortcut(QKeySequence("Delete"))
        self.act_delete.triggered.connect(self._on_delete)
        menu_edit.addAction(self.act_delete)

        self.act_clear = QAction("清空标注", self)
        self.act_clear.triggered.connect(self._on_clear)
        menu_edit.addAction(self.act_clear)

        # ===== 工具 =====
        menu_tool = menu_bar.addMenu("工具(&T)")

        # 标注工具（互斥）
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

        self.act_annotate_single = QAction("自动标注单张", self)
        self.act_annotate_single.triggered.connect(self._on_annotate_single)
        menu_tool.addAction(self.act_annotate_single)

        self.act_annotate_all = QAction("自动标注全部", self)
        self.act_annotate_all.triggered.connect(self._open_annotate_dialog)
        menu_tool.addAction(self.act_annotate_all)

        menu_tool.addSeparator()
        self.act_convert = QAction("格式转换", self)
        self.act_convert.triggered.connect(self._open_convert_dialog)
        menu_tool.addAction(self.act_convert)

        # ===== 帮助 =====
        menu_help = menu_bar.addMenu("帮助(&H)")
        self.act_about = QAction("关于", self)
        self.act_about.triggered.connect(self._on_about)
        menu_help.addAction(self.act_about)

    # -------------------------- 三栏布局 --------------------------
    def _build_ui(self) -> None:
        """构建三栏式主体布局：左侧工具栏 + 中间画布 + 右侧信息栏。"""
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.left_toolbar = LeftToolbar()
        self.canvas = Canvas()
        self.right_panel = RightPanel()

        root.addWidget(self.left_toolbar)
        root.addWidget(self.canvas, 1)
        root.addWidget(self.right_panel)

    # -------------------------- 信号连接 --------------------------
    def _connect_signals(self) -> None:
        """连接左右栏、画布与菜单动作之间的信号。"""
        # 左侧工具栏
        self.left_toolbar.open_requested.connect(self._on_open_folder)
        self.left_toolbar.save_requested.connect(self._on_save)
        self.left_toolbar.save_as_requested.connect(self._on_save_as)
        self.left_toolbar.delete_requested.connect(self._on_delete)
        self.left_toolbar.load_model_requested.connect(self._open_annotate_dialog)
        self.left_toolbar.annotate_single_requested.connect(self._on_annotate_single)
        self.left_toolbar.annotate_all_requested.connect(self._open_annotate_dialog)
        self.left_toolbar.tool_selected.connect(self._on_tool_selected)

        # 画布
        self.canvas.shapes_changed.connect(self._on_shapes_changed)
        self.canvas.shape_selected.connect(self._on_canvas_shape_selected)

        # 右侧信息栏
        self.right_panel.label_selected.connect(self._on_label_selected)
        self.right_panel.object_selected.connect(self._on_object_selected)
        self.right_panel.file_selected.connect(self._on_file_selected)
        self.right_panel.keypoint_selected.connect(self._on_label_selected)
        self.right_panel.add_label_requested.connect(self._on_add_label)

    # -------------------------- 文件操作 --------------------------
    def _on_open_folder(self) -> None:
        """打开工作文件夹：扫描图片并加载第一张。"""
        directory = chooseDir(self._work_dir)
        if not directory:
            return
        images = sorted(getImageFilesInDir(directory))
        if not images:
            showMessageBox(QMessageBox.Icon.Warning, "该目录未扫描到图片（jpg/jpeg/png/bmp）")
            return
        self._work_dir = directory
        self._image_files = images
        self._current_index = -1
        self.right_panel.set_files(images)
        self._load_image_by_index(0)
        self._refresh_labels()
        LOGGER.info(f"已打开文件夹: {directory}，共 {len(images)} 张图片")

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

    def _load_image_by_index(self, index: int) -> None:
        """加载指定下标的图片及其同名标注。

        Args:
            index: 图片在文件列表中的下标。
        """
        if not (0 <= index < len(self._image_files)):
            return
        path = self._image_files[index]
        if not self.canvas.load_image(path):
            showMessageBox(QMessageBox.Icon.Warning, f"无法加载图片: {path}")
            return
        self._current_index = index
        self._dirty = False

        # 读取同名 labelme JSON 标注（存在则回填到画布）
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
        self._update_status()
        self._set_dirty_check_stale()

    def _on_file_selected(self, index: int) -> None:
        """右侧文件列表选中切换当前图片（仅在确实变化时加载）。"""
        if index != self._current_index:
            self._load_image_by_index(index)

    def _on_save(self) -> None:
        """保存当前标注到同名 labelme JSON。"""
        img = self._current_image_path()
        if not img:
            showMessageBox(QMessageBox.Icon.Warning, "请先打开图片")
            return
        json_path = self._current_json_path()
        self._write_annotation(json_path)
        self._refresh_labels()

    def _on_save_as(self) -> None:
        """另存为：选择目标 JSON 路径后写入当前标注。"""
        img = self._current_image_path()
        if not img:
            showMessageBox(QMessageBox.Icon.Warning, "请先打开图片")
            return
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "另存为标注", Path(img).with_suffix(".json").name, "LabelMe JSON (*.json)"
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
        LOGGER.info(f"标注已保存: {json_path}")

    # -------------------------- 编辑操作 --------------------------
    def _on_delete(self) -> None:
        """删除当前选中的标注。"""
        self.canvas.delete_selected()

    def _on_clear(self) -> None:
        """清空当前图片全部标注。"""
        self.canvas.clear_shapes()

    # -------------------------- 工具切换 --------------------------
    def _on_tool_selected(self, tool: str) -> None:
        """切换标注工具并同步画布、工具栏与菜单选中态。

        Args:
            tool: 工具名（select/rectangle/point/polygon）。
        """
        # 工具栏按钮与菜单动作互相同步
        self.left_toolbar.set_tool(tool)
        act = self._tool_actions.get(tool)
        if act is not None:
            act.setChecked(True)
        # select 对应画布的选择模式（None），其余为绘制工具
        self.canvas.set_tool(None if tool == TOOL_SELECT else tool)

    # -------------------------- 自动标注 --------------------------
    def _open_annotate_dialog(self) -> None:
        """打开自动标注设置对话框（复用 AnnotatePage + 批量 worker）。

        用户可在对话框内配置模型/任务类型/类别/参数并执行批量标注；
        点击"保存设置"后收集配置，供"自动标注单张"使用。
        """
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

        # 预填上次配置
        if self.annotate_config is not None:
            page.apply_config(self.annotate_config)

        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            cfg = SysConfig()
            try:
                page.collect_config(cfg)
            except Exception as e:
                LOGGER.error(f"收集标注配置失败: {e}")
                return
            self.annotate_config = cfg
            self.left_toolbar.set_annotate_enabled(bool(cfg.annotate_config.model_path))
            self._refresh_labels()
            self._refresh_keypoints()
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
        worker.error_occurred.connect(
            lambda msg: showMessageBox(QMessageBox.Icon.Critical, msg)
        )
        worker.task_finished.connect(worker.deleteLater)
        self.left_toolbar.set_annotate_enabled(False)
        worker.start()

    def _on_single_shapes_ready(self, shapes: list) -> None:
        """单张标注完成：结果回填画布并刷新右侧列表。

        Args:
            shapes: labelme 形状字典列表。
        """
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

    # -------------------------- 右侧栏联动 --------------------------
    def _on_shapes_changed(self) -> None:
        """画布形状变化：标记未保存、刷新对象与标签列表。"""
        self._dirty = True
        self._refresh_objects()
        self._update_status()

    def _on_canvas_shape_selected(self, shape) -> None:
        """画布选中形状变化时联动对象列表选中态。

        Args:
            shape: 选中的形状字典或 None。
        """
        if shape is None:
            self.right_panel.clear_object_selection()
            return
        shapes = self.canvas.shapes()
        for i, s in enumerate(shapes):
            if s is shape:
                self.right_panel.select_object(i)
                return

    def _on_object_selected(self, index: int) -> None:
        """右侧对象列表选中时联动画布选中。

        Args:
            index: 对象下标。
        """
        self.canvas.select_shape_by_index(index)

    def _on_label_selected(self, label: str) -> None:
        """选中/双击标签：设为当前绘制标签。

        Args:
            label: 标签名。
        """
        self.canvas.set_current_label(label)
        self._status_label.setText(f"当前标签: {label}")

    def _on_add_label(self) -> None:
        """新增标签并设为当前绘制标签。"""
        text, ok = QInputDialog.getText(self, "新增标签", "标签名称:")
        if not ok or not text.strip():
            return
        label = text.strip()
        self.canvas.set_current_label(label)
        self._refresh_labels()
        self._status_label.setText(f"当前标签: {label}")

    # -------------------------- 列表刷新 --------------------------
    def _refresh_labels(self) -> None:
        """汇总工作目录下全部标注中的标签，填充右侧标签列表。"""
        labels: set = set()
        if self._work_dir:
            for json_file in getJsonFilesInDir(self._work_dir):
                try:
                    doc = labelme_io.load_document(json_file)
                    labels.update(labelme_io.document_labels(doc))
                except Exception as e:
                    LOGGER.warning(f"读取标签失败 {json_file}: {e}")
        self.right_panel.set_labels(sorted(labels))

    def _refresh_objects(self) -> None:
        """刷新当前图片对象列表（描述形如 'person (rectangle)'）。"""
        descriptions = []
        for shape in self.canvas.shapes():
            label = shape.get("label", "")
            shape_type = shape.get("shape_type", "")
            descriptions.append(f"{label} ({shape_type})")
        self.right_panel.set_objects(descriptions)

    def _refresh_keypoints(self) -> None:
        """刷新关键点列表的可见性与内容（仅 POSE 任务显示）。

        关键点名称从当前工作目录标注中的 point 类型标签去重提取。
        """
        is_pose = self.annotate_config is not None and self.annotate_config.task_type == MODE.POSE
        self.right_panel.set_kpt_visible(is_pose)
        if not is_pose:
            return
        keypoints: set = set()
        for shape in self.canvas.shapes():
            if shape.get("shape_type") == labelme_io.SHAPE_POINT:
                keypoints.add(shape.get("label", ""))
        if self._work_dir:
            for json_file in getJsonFilesInDir(self._work_dir):
                try:
                    doc = labelme_io.load_document(json_file)
                    for shape in labelme_io.document_shapes(doc):
                        if shape.get("shape_type") == labelme_io.SHAPE_POINT:
                            keypoints.add(shape.get("label", ""))
                except Exception:
                    continue
        self.right_panel.set_keypoints(sorted(keypoints))

    def _update_status(self) -> None:
        """更新状态栏：当前图片序号与未保存标记。"""
        if self._current_index < 0:
            self._status_label.setText("未打开文件夹")
            return
        total = len(self._image_files)
        dirty = "（未保存）" if self._dirty else ""
        name = Path(self._current_image_path()).name
        self._status_label.setText(f"{self._current_index + 1}/{total}  {name}{dirty}")

    def _set_dirty_check_stale(self) -> None:
        """加载图片后刷新未保存标记（占位，实际由 _update_status 处理）。"""
        self._update_status()

    # -------------------------- 帮助 --------------------------
    def _on_about(self) -> None:
        """显示关于对话框。"""
        showMessageBox(
            QMessageBox.Icon.Information,
            f"{__appname__} v{__version__}\n\n"
            "智能数据标注工具：自动标注 + 标注预览 + 格式转换\n"
            "标注格式完全复用 labelme JSON。",
        )

    # -------------------------- 关闭处理 --------------------------
    def closeEvent(self, event) -> None:
        """关闭窗口时停止运行中的 worker 并等待退出。

        Args:
            event: 关闭事件。
        """
        for worker in (self.annotate_worker, self.convert_worker):
            if worker.isRunning():
                worker.stop()
        self.annotate_worker.wait(3000)
        self.convert_worker.wait(3000)
        event.accept()

    # -------------------------- 图标 --------------------------
    def set_window_icon(self, icon: QIcon) -> None:
        """设置窗口图标（由 main.py 调用，兼容打包路径）。

        Args:
            icon: 已构造的 QIcon。
        """
        self.setWindowIcon(icon)