# -*- coding: utf-8 -*-
"""
视频标注窗口 - VideoAnnotateDialog

视频标注任务配置窗口（独立对话框，替代原 QInputDialog 简易弹窗）：
    1. 输入路径：视频文件所在目录（PathField 浏览选择）
    2. 输出路径：默认输入路径下的 Output 子目录（可修改）
    3. 视频列表：动态遍历（os.scandir 迭代器 + QTimer 分批入列，
       大目录不卡 UI），复选框勾选待标注视频（默认全选）
    4. 帧间隔：抽帧间隔帧数（默认 10）
    5. 预览播放器：QTimer 驱动 cv2 逐帧播放，支持播放/暂停、
       后退/快进（±1 秒）、变速（0.25x-4x）、进度条拖动定位
损坏视频防护：播放器单帧读取不进死循环；抽帧侧防护见
video_processor.py（帧位不前进/空帧强制终止）。

作者: BaiBinnan
创建日期: 2026-09-03
"""

import os
from pathlib import Path

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..utils import LOGGER
from .buttons import PrimaryButton, SecondaryButton
from .fields import LabeledSpin, PathField

# 视频文件扩展名（与 utils/files.getVideoFilesInDir 保持一致）
_VIDEO_EXTS = {".mp4", ".avi", ".mov"}
# 动态遍历：每批处理的目录条目数（ QTimer 分批，避免大目录卡死 UI）
_SCAN_BATCH = 200


class VideoAnnotateDialog(QDialog):
    """视频标注配置窗口：路径/帧间隔/动态文件列表/预览播放器。

    Signals:
        无（配置经 get_result() 静态方法返回）。
    """

    def __init__(self, default_input: str = "", parent=None):
        """初始化视频标注窗口。

        Args:
            default_input: 默认输入路径（通常为主窗口当前工作目录）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setWindowTitle("标注视频")
        self.setMinimumSize(860, 620)

        # ===== 运行状态 =====
        self._cap = None          # 预览 VideoCapture
        self._fps = 0.0           # 当前视频帧率
        self._total_frames = 0    # 当前视频总帧数
        self._playing = False     # 播放状态
        self._scan_iter = None    # 动态遍历迭代器（os.scandir）
        self._videos: list[str] = []  # 已发现的视频路径

        # ===== 动态遍历定时器（分批入列）=====
        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(10)
        self._scan_timer.timeout.connect(self._scan_tick)

        # ===== 播放定时器（按 fps/倍速 逐帧读取）=====
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._play_next_frame)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # ===== 路径区：输入路径 + 输出路径 + 帧间隔 =====
        path_row = QHBoxLayout()
        path_col = QVBoxLayout()
        path_col.setSpacing(8)

        in_row = QHBoxLayout()
        in_label = QLabel("输入路径:")
        in_label.setMinimumWidth(60)
        self.input_field = PathField(browse_type="dir", placeholder="选择视频所在目录")
        if default_input:
            self.input_field.set_path(default_input)
        self.input_field.path_changed.connect(self._on_input_changed)
        in_row.addWidget(in_label)
        in_row.addWidget(self.input_field)
        path_col.addLayout(in_row)

        out_row = QHBoxLayout()
        out_label = QLabel("输出路径:")
        out_label.setMinimumWidth(60)
        self.output_field = PathField(browse_type="dir", placeholder="默认为输入路径下的 Output 目录")
        self._output_customized = False  # 用户是否手动修改过输出路径
        self.output_field.path_changed.connect(self._on_output_changed)
        out_row.addWidget(out_label)
        out_row.addWidget(self.output_field)
        path_col.addLayout(out_row)

        interval_row = QHBoxLayout()
        self.interval_spin = LabeledSpin(
            "抽帧间隔(帧):", spin_type="int", minimum=1, maximum=10000, step=1, value=10
        )
        self.interval_spin.setMaximumWidth(260)
        interval_row.addWidget(self.interval_spin)
        interval_row.addStretch()
        # 扫描状态提示（动态遍历进行中/完成）
        self.scan_status = QLabel("")
        self.scan_status.setStyleSheet("color: #71717a;")
        interval_row.addWidget(self.scan_status)
        path_col.addLayout(interval_row)

        lay.addLayout(path_col)

        # ===== 主体：左视频列表 + 右预览播放器 =====
        body = QHBoxLayout()
        body.setSpacing(10)

        # 视频列表（复选框多选，默认全选）
        list_col = QVBoxLayout()
        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("视频文件:"))
        list_header.addStretch()
        self.btn_select_all = SecondaryButton("全选")
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_select_none = SecondaryButton("取消全选")
        self.btn_select_none.clicked.connect(self._select_none)
        list_header.addWidget(self.btn_select_all)
        list_header.addWidget(self.btn_select_none)
        list_col.addLayout(list_header)
        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(280)
        self.file_list.itemClicked.connect(self._on_video_selected)
        list_col.addWidget(self.file_list, 1)
        body.addLayout(list_col, 1)

        # 预览播放器
        body.addWidget(self._build_player(), 2)
        lay.addLayout(body, 1)

        # ===== 按钮区 =====
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("开始标注")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        # 初始：按默认输入路径设置默认输出（Input/Output）并启动动态遍历
        if default_input:
            self.output_field.set_path(str(Path(default_input) / "Output"))
            self._start_scan(default_input)

    # -------------------------- 播放器构建 --------------------------
    def _build_player(self) -> QWidget:
        """构建预览播放器（画面 + 控制条）。

        Returns:
            播放器容器控件。
        """
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)

        # 画面显示区（保持比例缩放）
        self.preview_label = QLabel("选择左侧视频进行预览")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(320)
        self.preview_label.setStyleSheet(
            "background-color: #18181b; color: #71717a; border-radius: 6px;"
        )
        col.addWidget(self.preview_label, 1)

        # 进度条（帧位滑块）
        self.pos_slider = QSlider(Qt.Orientation.Horizontal)
        self.pos_slider.setRange(0, 0)
        self.pos_slider.sliderMoved.connect(self._on_slider_moved)
        self.pos_slider.sliderPressed.connect(self._pause)
        col.addWidget(self.pos_slider)

        # 控制条：后退 | 播放/暂停 | 快进 | 变速 | 时间显示
        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)
        self.btn_backward = SecondaryButton("◀ 后退1s")
        self.btn_backward.clicked.connect(lambda: self._seek_seconds(-1))
        self.btn_play = PrimaryButton("播放")
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_forward = SecondaryButton("快进1s ▶")
        self.btn_forward.clicked.connect(lambda: self._seek_seconds(1))
        self.speed_combo = QComboBox()
        for s in ("0.25x", "0.5x", "1x", "2x", "4x"):
            self.speed_combo.addItem(s)
        self.speed_combo.setCurrentIndex(2)  # 默认 1x
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #71717a;")
        ctrl.addWidget(self.btn_backward)
        ctrl.addWidget(self.btn_play)
        ctrl.addWidget(self.btn_forward)
        ctrl.addWidget(QLabel("变速:"))
        ctrl.addWidget(self.speed_combo)
        ctrl.addStretch()
        ctrl.addWidget(self.time_label)
        col.addLayout(ctrl)

        return panel

    # -------------------------- 动态遍历 --------------------------
    def _on_input_changed(self, path: str) -> None:
        """输入路径变化：重置列表、更新默认输出路径并启动动态遍历。

        Args:
            path: 新的输入路径。
        """
        # 未手动定制输出路径时自动跟随输入路径（默认 Input/Output）
        if not self._output_customized:
            self.output_field.set_path(str(Path(path) / "Output"))
        self._start_scan(path)

    def _on_output_changed(self, path: str) -> None:
        """输出路径被用户修改：标记为手动定制（不再自动跟随输入路径）。

        Args:
            path: 新的输出路径。
        """
        self._output_customized = True

    def _start_scan(self, path: str) -> None:
        """启动动态遍历（os.scandir 迭代器 + QTimer 分批入列）。

        Args:
            path: 待遍历目录。
        """
        # 停止上一轮遍历
        self._scan_timer.stop()
        if self._scan_iter is not None:
            try:
                self._scan_iter.close()
            except Exception:
                pass
            self._scan_iter = None

        self.file_list.clear()
        self._videos = []
        if not path or not os.path.isdir(path):
            self.scan_status.setText("")
            return

        try:
            self._scan_iter = os.scandir(path)
        except OSError as e:
            LOGGER.error(f"视频目录遍历失败: {path} - {e}")
            self.scan_status.setText(f"目录读取失败: {e}")
            return
        self.scan_status.setText("正在扫描视频文件...")
        self._scan_timer.start()

    def _scan_tick(self) -> None:
        """定时遍历一批目录条目（每批 _SCAN_BATCH 条，防大目录卡死 UI）。"""
        batch = 0
        try:
            for entry in self._scan_iter:
                try:
                    if not entry.is_file():
                        continue
                    if Path(entry.name).suffix.lower() in _VIDEO_EXTS:
                        self._append_video(entry.path)
                except OSError:
                    continue  # 单条目读取失败跳过（权限/并发删除等）
                batch += 1
                if batch >= _SCAN_BATCH:
                    return  # 本批结束，等下一个 tick 继续
        except StopIteration:
            pass
        except OSError as e:
            LOGGER.error(f"视频目录遍历中断: {e}")
        # 遍历完成
        self._scan_timer.stop()
        if self._scan_iter is not None:
            try:
                self._scan_iter.close()
            except Exception:
                pass
            self._scan_iter = None
        n = len(self._videos)
        self.scan_status.setText(f"扫描完成，共 {n} 个视频" if n else "未找到视频文件（mp4/avi/mov）")

    def _append_video(self, path: str) -> None:
        """向列表追加一个视频项（复选框默认勾选）。

        Args:
            path: 视频文件路径。
        """
        self._videos.append(path)
        item = QListWidgetItem(Path(path).name)
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        self.file_list.addItem(item)

    def _select_all(self) -> None:
        """全选视频复选框。"""
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _select_none(self) -> None:
        """取消全选视频复选框。"""
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    # -------------------------- 预览播放器 --------------------------
    def _on_video_selected(self, item: QListWidgetItem) -> None:
        """列表选中视频：加载到播放器并显示首帧。

        Args:
            item: 被点击的列表项。
        """
        path = item.data(Qt.ItemDataRole.UserRole)
        self._load_video(path)

    def _load_video(self, path: str) -> None:
        """加载视频到播放器（读取信息 + 显示首帧）。

        Args:
            path: 视频文件路径。
        """
        self._pause()
        # 释放旧句柄
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            self.preview_label.clear()  # 先清除旧画面（clear 会同时清文本与图）
            self.preview_label.setText("无法打开该视频（文件损坏或格式不支持）")
            self.pos_slider.setRange(0, 0)
            self.time_label.setText("00:00 / 00:00")
            LOGGER.warning(f"预览播放器无法打开视频: {path}")
            return

        self._cap = cap
        self._fps = cap.get(cv2.CAP_PROP_FPS) or 25.0  # 异常 fps 回退 25
        self._total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.pos_slider.setRange(0, max(0, self._total_frames - 1))
        self.pos_slider.setValue(0)
        self._apply_speed()  # 按当前倍速设定播放间隔

        # 读取首帧显示（ret 为 True 但帧为空按损坏处理）
        ret, frame = cap.read()
        if not ret or frame is None or frame.size == 0:
            self.preview_label.clear()
            self.preview_label.setText("视频数据异常（无法读取帧）")
            self._cap.release()
            self._cap = None
            return
        self._show_frame(frame, 0)

    def _toggle_play(self) -> None:
        """播放/暂停切换。"""
        if self._cap is None:
            return
        if self._playing:
            self._pause()
        else:
            self._play()

    def _play(self) -> None:
        """开始播放（更新按钮文案并启动播放定时器）。"""
        if self._cap is None:
            return
        self._playing = True
        self.btn_play.setText("暂停")
        self._play_timer.start()

    def _pause(self) -> None:
        """暂停播放（保留当前画面）。"""
        self._playing = False
        self._play_timer.stop()
        if self.btn_play is not None:
            self.btn_play.setText("播放")

    def _play_next_frame(self) -> None:
        """播放定时器回调：读取下一帧显示，读到末尾自动暂停。

        损坏视频防护：ret 为 True 但帧为空、或帧位长期不前进时终止播放。
        """
        if self._cap is None:
            self._pause()
            return
        pos_before = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES))
        ret, frame = self._cap.read()
        if not ret or frame is None or frame.size == 0:
            self._pause()  # 播放到末尾或数据异常
            return
        pos_after = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES))
        if pos_after <= pos_before:
            # 帧位未前进（损坏视频），显示提示并暂停（定时器单次读帧不会死循环）
            self._pause()
            self.preview_label.setText("视频数据异常（帧位停滞），已暂停")
            return
        self._show_frame(frame, pos_after - 1)

    def _show_frame(self, frame, pos: int) -> None:
        """显示一帧画面并同步进度条/时间显示。

        Args:
            frame: BGR 帧数组（cv2 读取）。
            pos: 当前帧位（0 起）。
        """
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        scaled = QPixmap.fromImage(img).scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        # 同步进度条与时间（拖动中不回写，避免与用户操作冲突）
        if not self.pos_slider.isSliderDown():
            self.pos_slider.setValue(pos)
        self.time_label.setText(
            f"{self._fmt_time(pos / self._fps)} / {self._fmt_time(self._total_frames / self._fps)}"
        )

    def _seek_seconds(self, seconds: float) -> None:
        """相对定位（后退/快进按钮：按秒偏移当前帧位）。

        Args:
            seconds: 偏移秒数（负为后退）。
        """
        if self._cap is None or self._fps <= 0:
            return
        offset = int(seconds * self._fps)
        self._seek_to(self.pos_slider.value() + offset)

    def _on_slider_moved(self, pos: int) -> None:
        """进度条拖动定位：跳转到指定帧。"""
        self._seek_to(pos)

    def _seek_to(self, pos: int) -> None:
        """跳转到指定帧位（钳制到有效范围，读帧失败按末尾处理）。

        Args:
            pos: 目标帧位（0 起）。
        """
        if self._cap is None:
            return
        pos = max(0, min(pos, max(0, self._total_frames - 1)))
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = self._cap.read()
        if not ret or frame is None or frame.size == 0:
            self._pause()
            return
        self._show_frame(frame, pos)

    def _on_speed_changed(self) -> None:
        """倍速切换：更新播放定时器间隔。"""
        self._apply_speed()

    def _apply_speed(self) -> None:
        """按当前倍速计算并应用播放定时器间隔。"""
        speed = float(self.speed_combo.currentText().rstrip("x"))
        interval_ms = int(1000 / (self._fps * speed)) if self._fps > 0 else 40
        # 限定最小 10ms（高倍速 + 高帧率时避免定时器过载）
        self._play_timer.setInterval(max(10, interval_ms))

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """秒数格式化为 mm:ss。

        Args:
            seconds: 秒数。

        Returns:
            "mm:ss" 格式字符串。
        """
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    # -------------------------- 结果返回 --------------------------
    def _on_accept(self) -> None:
        """确定前校验：至少勾选一个视频且输出路径有效。"""
        if not self.checked_videos():
            self.scan_status.setText("请至少勾选一个视频文件")
            self.scan_status.setStyleSheet("color: #ef4444;")
            return
        if not self.output_field.path():
            self.scan_status.setText("请设置输出路径")
            self.scan_status.setStyleSheet("color: #ef4444;")
            return
        self.scan_status.setStyleSheet("color: #71717a;")
        self.accept()

    def checked_videos(self) -> list:
        """返回勾选的视频路径列表。

        Returns:
            勾选视频路径列表（空列表表示未勾选任何视频）。
        """
        result = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def result_config(self) -> dict:
        """返回窗口配置（调用方在 accept 后读取）。

        Returns:
            dict: {"input_dir", "output_dir", "frame_interval", "videos"}。
        """
        return {
            "input_dir": self.input_field.path(),
            "output_dir": self.output_field.path(),
            "frame_interval": int(self.interval_spin.value()),
            "videos": self.checked_videos(),
        }

    @staticmethod
    def get_config(default_input: str = "", parent=None):
        """弹出视频标注窗口并返回配置。

        Args:
            default_input: 默认输入路径。
            parent: 父控件。

        Returns:
            配置 dict（见 result_config()）；用户取消返回 None。
        """
        dlg = VideoAnnotateDialog(default_input, parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return dlg.result_config()

    # -------------------------- 资源清理 --------------------------
    def closeEvent(self, event) -> None:
        """关闭窗口：停止定时器并释放视频句柄。"""
        self._scan_timer.stop()
        if self._scan_iter is not None:
            try:
                self._scan_iter.close()
            except Exception:
                pass
            self._scan_iter = None
        self._pause()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        super().closeEvent(event)
