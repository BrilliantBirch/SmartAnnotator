# -*- coding: utf-8 -*-
"""
在线更新核心逻辑（无 Qt 依赖）

通过 Gitee Release API 检查新版本并下载在线安装器，由 Inno Setup
安装器以静默模式完成覆盖安装（应用自身不替换运行中的 exe）。

发布流程（发版时人工执行）：
    1. 升版本：smart_annotator/__init__.py 的 __version__ 与
       version_manager.py 的 PRODUCT_VERSION/PRODUCT_VERSION_TUPLE 同步升级
       （如 2.1.1）；
    2. 项目根目录执行 python build.py --mode all；
    3. Gitee 创建 Release，tag 命名 v{版本号}（如 v2.1.1），上传
       build/installer_output/BrilliantAnnotator_OnlineSetup.exe。

作者: BaiBinnan
创建日期: 2026-09-09
更新: 2026-09-09 修正仓库地址为实际发布仓库 vai_-e_-smart-annotator
"""

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

# ========================== 常量定义 ==========================
# Gitee Release API（公开仓库无需认证）；发版仓库变更时同步修改
UPDATE_API_URL = "https://gitee.com/api/v5/repos/baibinnan/vai_-e_-smart-annotator/releases/latest"
# Release 网页地址（"查看发布页"入口，与 UPDATE_API_URL 同仓库）
RELEASE_PAGE_URL = "https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases"
# 在线安装器附件名关键字（assets 中按此匹配下载 URL）
SETUP_ASSET_KEYWORD = "BrilliantAnnotator_OnlineSetup"
# 网络请求超时（秒）
NETWORK_TIMEOUT = 10
# 下载分块大小（64KB）
DOWNLOAD_CHUNK_SIZE = 64 * 1024
# HTTP 请求头（Gitee 要求带 User-Agent）
HTTP_HEADERS = {"User-Agent": "BrilliantAnnotator-Updater"}


class UpdaterError(Exception):
    """更新流程异常（网络失败 / 响应格式不符 / 附件缺失等）。"""


@dataclass
class ReleaseInfo:
    """最新 Release 信息。

    Attributes:
        tag_name: Release 标签名（如 "v2.1.1"）。
        version: 解析后的版本元组（如 (2, 1, 1)）。
        setup_url: 在线安装器附件下载 URL。
        setup_size: 附件大小（字节，未知时为 0）。
    """

    tag_name: str
    version: Tuple[int, ...]
    setup_url: str
    setup_size: int = 0


def parse_version(tag: str) -> Tuple[int, ...]:
    """解析版本标签为可比较的整数元组。

    支持 "v2.1.1"、"2.1.1" 两种格式。

    Args:
        tag: 版本标签字符串。

    Returns:
        版本号元组，如 (2, 1, 1)。

    Raises:
        UpdaterError: 标签格式非法（非数字段等）。
    """
    # 剥可选的 v/V 前缀后按点切分
    text = tag.strip().lstrip("vV")
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError as exc:
        raise UpdaterError(f"版本标签格式非法: {tag!r}") from exc


def fetch_latest_release(timeout: float = NETWORK_TIMEOUT) -> ReleaseInfo:
    """请求 Gitee 最新 Release 并解析在线安装器附件信息。

    Args:
        timeout: 网络请求超时（秒）。

    Returns:
        ReleaseInfo：最新 Release 的版本与安装器下载信息。

    Raises:
        UpdaterError: 网络失败、响应非 JSON、字段缺失或附件不存在。
    """
    # ===== 发起 GET 请求（带 User-Agent 与超时） =====
    request = urllib.request.Request(UPDATE_API_URL, headers=HTTP_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise UpdaterError(f"请求更新信息失败: {exc}") from exc

    # ===== 解析 tag_name（缺失视为响应异常） =====
    tag_name = payload.get("tag_name")
    if not tag_name:
        raise UpdaterError("Release 响应缺少 tag_name 字段")

    # ===== 在 assets 中查找在线安装器附件 =====
    setup_url = ""
    setup_size = 0
    for asset in payload.get("assets", []) or []:
        name = asset.get("name", "")
        if SETUP_ASSET_KEYWORD in name and name.lower().endswith(".exe"):
            setup_url = asset.get("browser_download_url", "")
            setup_size = int(asset.get("size", 0))
            break
    if not setup_url:
        raise UpdaterError(f"Release {tag_name} 未找到在线安装器附件（{SETUP_ASSET_KEYWORD}*.exe）")

    return ReleaseInfo(
        tag_name=tag_name,
        version=parse_version(tag_name),
        setup_url=setup_url,
        setup_size=setup_size,
    )


def download_file(
    url: str,
    dest: Path,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
) -> Path:
    """下载文件到指定路径（流式分块，支持进度回调与中断）。

    先写临时文件（dest + ".part"），成功后原子重命名，避免残留半截文件。

    Args:
        url: 下载 URL。
        dest: 目标文件路径。
        progress_cb: 进度回调 (已下载字节, 总字节)；总字节未知时为 0。
        stop_check: 中断检查回调，返回 True 时中止下载并删除临时文件。

    Returns:
        目标文件路径。

    Raises:
        UpdaterError: 网络失败或被中断。
    """
    temp_path = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers=HTTP_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT) as response, \
                open(temp_path, "wb") as out_file:
            # Content-Length 可能缺失（分块传输），此时总数记 0
            total = int(response.headers.get("Content-Length", 0))
            done = 0
            while True:
                # 每块写入前检查中断标志
                if stop_check is not None and stop_check():
                    raise UpdaterError("下载已取消")
                chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                out_file.write(chunk)
                done += len(chunk)
                if progress_cb is not None:
                    progress_cb(done, total)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # 清理残留的临时文件
        temp_path.unlink(missing_ok=True)
        raise UpdaterError(f"下载失败: {exc}") from exc

    # 下载完成：临时文件重命名为目标文件
    temp_path.replace(dest)
    return dest


def detect_install_mode(exe_dir: Path) -> str:
    """检测当前安装的版本模式（CPU / GPU）。

    优先读取安装目录下的 install_mode.txt 标记（在线安装器写入）；
    标记缺失时按 TensorRT 运行库存在性启发式判断。

    Args:
        exe_dir: 应用 exe 所在目录。

    Returns:
        "CPU" 或 "GPU"。
    """
    # 1. 安装器写入的模式标记文件（最可靠）
    marker = exe_dir / "install_mode.txt"
    if marker.exists():
        try:
            text = marker.read_text(encoding="utf-8").strip().upper()
            if text in ("CPU", "GPU"):
                return text
        except OSError:
            pass  # 标记读取失败时回退启发式

    # 2. 启发式：GPU 版独有 tensorrt.libs 目录或 nvinfer*.dll
    if (exe_dir / "tensorrt.libs").exists():
        return "GPU"
    if any(exe_dir.glob("nvinfer*.dll")):
        return "GPU"
    return "CPU"


def run_installer(installer_path: Path, mode: str) -> None:
    """以分离进程拉起在线安装器（静默模式）。

    安装器参数：
        /SILENT：显示进度窗口但无需用户交互；
        /SUPPRESSMSGBOXES：抑制消息弹窗；
        /NORESTART：不重启系统；
        /MODE=CPU|GPU：静默模式下的版本选择（installer_online.iss 自定义支持）。

    Args:
        installer_path: 在线安装器 exe 路径。
        mode: 安装模式（"CPU" 或 "GPU"）。

    Raises:
        UpdaterError: 进程启动失败。
    """
    # 分离进程标志：主程序退出后安装器继续运行
    creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            [
                str(installer_path),
                "/SILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/MODE={mode.upper()}",
            ],
            creationflags=creation_flags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdaterError(f"启动安装器失败: {exc}") from exc
