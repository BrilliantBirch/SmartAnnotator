# -*- coding: utf-8 -*-
"""
渲染配置持久化模块 - render_store

负责 RenderConfig 在 %APPDATA%/BrilliantAnnotator/render_config.json 的
加载与保存：目录不存在自动创建；首次运行（文件不存在）自动创建默认
配置文件；文件损坏回退默认配置（记录警告）。

作者: BaiBinnan
创建日期: 2026-09-03
更新: 2026-09-03 首次运行（配置文件不存在）时自动创建默认配置文件
"""

import json
import os
from pathlib import Path
from typing import Optional

from ..config import RenderConfig
from . import LOGGER

# 配置目录名（与应用名一致，见 main.py setApplicationName）
_APP_DIR_NAME = "BrilliantAnnotator"
# 渲染配置文件名
RENDER_CONFIG_FILENAME = "render_config.json"


def config_dir() -> Path:
    """返回渲染配置目录（%APPDATA%/BrilliantAnnotator，不存在则创建）。

    Returns:
        配置目录 Path。

    Raises:
        OSError: 目录创建失败（无写权限等）。
    """
    # 优先读取 APPDATA 环境变量（Windows 平台项目）
    appdata = os.environ.get("APPDATA")
    if appdata:
        directory = Path(appdata) / _APP_DIR_NAME
    else:
        # APPDATA 缺失（环境异常）时回退用户主目录下的点目录
        directory = Path.home() / f".{_APP_DIR_NAME}"
        LOGGER.warning(f"APPDATA 环境变量缺失，渲染配置目录回退到 {directory}")
    # 存在性宽容地创建目录（已存在不报错）
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load_render_config(path: Optional[Path] = None) -> RenderConfig:
    """加载渲染配置；文件缺失时创建默认配置文件，损坏时回退默认配置。

    首次运行（文件不存在）会立即以默认值创建配置文件，便于用户查看
    与手工编辑；文件缺失/损坏均回退默认配置（永不抛出）。

    Args:
        path: 配置文件路径，缺省为 %APPDATA%/BrilliantAnnotator/render_config.json
            （测试时可传入临时路径）。

    Returns:
        RenderConfig 实例。
    """
    # ===== 解析目标文件路径（未指定时用 config_dir 与文件名组合） =====
    file_path = Path(path) if path is not None else config_dir() / RENDER_CONFIG_FILENAME
    # 文件不存在视为首次运行：以默认值创建配置文件后返回默认配置
    if not file_path.is_file():
        default_cfg = RenderConfig()
        try:
            save_render_config(default_cfg, file_path)
            LOGGER.info(f"首次运行，已创建默认渲染配置: {file_path}")
        except OSError as ex:
            # 创建失败（如目录只读）不影响启动，仅记录警告
            LOGGER.warning(f"默认渲染配置文件创建失败: {ex}")
        return default_cfg
    # ===== 读取并解析 JSON，任一环节失败均回退默认配置 =====
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as ex:
        LOGGER.warning(f"渲染配置文件 {file_path} 读取或解析失败，回退默认配置: {ex}")
        return RenderConfig()
    # 解析结果不是 JSON 对象同样回退默认配置
    if not isinstance(data, dict):
        LOGGER.warning(f"渲染配置文件 {file_path} 内容不是 JSON 对象，回退默认配置")
        return RenderConfig()
    # 正常场景：from_dict 内部已做逐字段校验与钳制
    return RenderConfig.from_dict(data)


def save_render_config(cfg: RenderConfig, path: Optional[Path] = None) -> None:
    """保存渲染配置到磁盘（UTF-8 JSON）。

    Args:
        cfg: 渲染配置。
        path: 目标文件路径，缺省为 %APPDATA%/BrilliantAnnotator/render_config.json
            （测试时可传入临时路径）。

    Raises:
        OSError: 写入失败。
    """
    # ===== 解析目标文件路径（未指定时用 config_dir 与文件名组合） =====
    file_path = Path(path) if path is not None else config_dir() / RENDER_CONFIG_FILENAME
    # 以 UTF-8 编码写入 JSON（indent=2 便于人工阅读与编辑）
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, ensure_ascii=False, indent=2)
