# -*- coding: utf-8 -*-
"""
视频抽帧模块 - 支持智能抽帧和冗余帧过滤（迭代器模式）

作者: BaiBinnan
创建日期: 2026-07-07
移植日期: 2026-08-10
更新: 2026-09-03 抽帧文件命名改为"视频名+帧Id"（帧在视频中的原始序号，
      同一视频不同间隔重跑不冲突）；增加损坏视频防护（ret 恒为 True
      但帧位不前进/空帧时强制终止，避免死循环）
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Generator

# 损坏视频判定：连续读取 N 帧位不前进即视为损坏（防死循环）
_STUCK_POS_LIMIT = 5


class VideoProcessor:
    """视频处理器，负责从视频中提取关键帧（迭代器模式）。

    Attributes:
        frame_interval: 抽帧间隔（帧数），默认 30 帧（约 1 秒）。
        diff_threshold: 帧间差异阈值，低于此值视为冗余帧，默认 10.0。
        extracted_count: 总抽取帧数。
        skipped_count: 跳过的冗余帧数。
    """

    def __init__(self, frame_interval: int = 30, diff_threshold: float = 10.0):
        """初始化视频处理器。

        Args:
            frame_interval: 抽帧间隔（帧数），默认 30 帧（约 1 秒）。
            diff_threshold: 帧间差异阈值，低于此值视为冗余帧，默认 10.0。
        """
        self.frame_interval = frame_interval
        self.diff_threshold = diff_threshold
        self.extracted_count = 0
        self.skipped_count = 0

    def extract_frames_iter(
        self, video_path: Path, output_dir: Path
    ) -> Generator[str, None, None]:
        """从视频中提取关键帧（迭代器模式）。

        每次生成一个帧文件路径，边抽边处理，避免内存占用过大。

        Args:
            video_path: 视频文件路径。
            output_dir: 输出目录。

        Yields:
            提取的帧文件路径（字符串）。

        Raises:
            RuntimeError: 无法打开视频文件时抛出。
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频文件: {video_path}")

        video_name = video_path.stem

        self.extracted_count = 0
        self.skipped_count = 0
        prev_frame_gray = None
        frame_index = 0
        # 损坏视频防护状态：上次帧位 + 连续不前进计数
        last_pos = -1
        stuck_count = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # 损坏视频防护 1：ret 为 True 但帧数据为空 → 强制终止
                if frame is None or frame.size == 0:
                    break

                # 损坏视频防护 2：帧位不前进（恒读同一帧）→ 连续超限即终止
                pos = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                if pos == last_pos:
                    stuck_count += 1
                    if stuck_count >= _STUCK_POS_LIMIT:
                        break
                else:
                    stuck_count = 0
                    last_pos = pos

                if frame_index % self.frame_interval == 0:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    gray = cv2.resize(gray, (320, 240))

                    if prev_frame_gray is not None:
                        diff = self._calculate_frame_diff(gray, prev_frame_gray)
                        if diff < self.diff_threshold:
                            self.skipped_count += 1
                            frame_index += 1
                            continue

                    # 命名规则：视频名 + 帧Id（帧在视频中的原始序号）
                    frame_filename = f"{video_name}_frame{frame_index:06d}.jpg"
                    frame_path = output_dir / frame_filename
                    cv2.imwrite(str(frame_path), frame)
                    prev_frame_gray = gray
                    self.extracted_count += 1

                    yield str(frame_path)

                frame_index += 1
        finally:
            cap.release()

    def extract_frames(
        self, video_path: Path, output_dir: Path
    ) -> Tuple[List[str], int, int]:
        """从视频中提取关键帧（列表模式，兼容旧接口）。

        Args:
            video_path: 视频文件路径。
            output_dir: 输出目录。

        Returns:
            Tuple[提取的帧文件路径列表, 总抽取帧数, 跳过的冗余帧数]。
        """
        frames = list(self.extract_frames_iter(video_path, output_dir))
        return frames, self.extracted_count, self.skipped_count

    def _calculate_frame_diff(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """计算两帧之间的差异值。

        Args:
            frame1: 第一帧（灰度图）。
            frame2: 第二帧（灰度图）。

        Returns:
            帧间差异值（绝对值差的平均值）。
        """
        diff = cv2.absdiff(frame1, frame2)
        return np.mean(diff)

    @staticmethod
    def get_video_info(video_path: Path) -> dict:
        """获取视频文件信息。

        Args:
            video_path: 视频文件路径。

        Returns:
            视频信息字典，包含帧率、总帧数、时长等；无法打开时返回空字典。
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {}

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps > 0 else 0

        cap.release()

        return {
            "fps": fps,
            "total_frames": total_frames,
            "width": width,
            "height": height,
            "duration": duration,
        }
