# -*- coding: utf-8 -*-
"""
打包构建脚本 - 使用 PyInstaller 非 onefile 模式打包 VAI_E_SmartAnnotator

位于项目根目录，构建产物输出到 build/ 子目录（已 gitignore）。
支持 CPU/GPU 分包打包，生成离线安装器与在线安装器。

构建流程:
    1. 调用 VersionManager 生成文件版本号（年.月.日.生成次数），产品版本固定 1.2.0.0
    2. 动态生成 version_info.txt（PyInstaller Windows 版本资源）
    3. 调用 PyInstaller 打包（非 onefile，生成目录模式）
       - 排除 matplotlib 及未使用的 PySide6 模块（减小体积）
       - GPU 模式: 保留 onnxruntime-gpu + TensorRT（完整 GPU 推理）
       - CPU 模式: 额外排除 tensorrt/cuda/pynvml，删除 nvinfer DLL
    4. 清理未使用的 Qt DLL（保留 imageformats/iconengines 插件）
    5. 在输出目录生成 py_packages_list.txt（依赖目录完整文件清单）
    6. 创建 zip 压缩包（用于 Gitee Release 在线分发）
    7. 调用 Inno Setup 编译离线安装器（CPU/GPU 各一个）
    8. 编译在线安装器（从 Gitee Release 下载对应版本）

使用方式（在项目根目录执行）:
    python build.py --mode all      # 同时构建 CPU + GPU + 在线安装器（默认）
    python build.py --mode cpu      # 仅构建 CPU 离线安装器
    python build.py --mode gpu      # 仅构建 GPU 离线安装器
    python build.py --mode online   # 仅编译在线安装器（上传 zip 到 Gitee 后使用）

作者: BaiBinnan
创建日期: 2026-08-10
更新: 2026-08-11 迁移至项目根目录，新增 --mode online 选项
更新: 2026-08-25 GPU 模式优化：完整复制 cuda/tensorrt 原生绑定包修复 CUDA 检测；
      删除冗余 CUDA DLL（onnxruntime CUDA EP/cuDNN/cuBLAS/cuFFT，GPU 推理走 TensorRT），
      打包体积从约 2.6 GB 降至约 730 MB
更新: 2026-08-26 CPU 模式修复：清理 exe 根目录混入的 CUDA DLL（约 1 GB，
      构建机 onnxruntime-gpu 依赖链引入，原清理逻辑仅遍历依赖子目录未覆盖根目录）
"""
import argparse
import configparser
import os
import sys
import shutil
import zipfile
import subprocess
from datetime import datetime
from pathlib import Path

# 将项目根目录添加到 sys.path（build.py 位于项目根目录）
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 构建产物输出目录（dist_*, build_temp_*, installer_output, packages 等均在此目录下）
BUILD_DIR = PROJECT_ROOT / "build"

from smart_annotator.version_manager import VersionManager


# ===== 依赖包目录命名（与 VAI_MemGenerator 的 VAI_PY_Packages 区分）=====
PACKAGES_DIR_NAME = "VAI_E_SmartAnnotator"

# ===== 需要排除的模块（减小打包体积）=====
# 注意：不排除 numpy/opencv/onnx/onnxruntime/PIL/yaml/psutil（运行时必需）
# 仅排除 matplotlib（COLORS 已 numpy 化）与未使用的 PySide6 模块
EXCLUDED_MODULES = [
    # matplotlib（COLORS 已改为 numpy HSV 调色板，不再依赖）
    "matplotlib",
    # PySide6 中未使用的模块（工具仅用 QtCore/QtGui/QtWidgets）
    "PySide6.QtNetwork",
    "PySide6.QtSql",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtSerialPort",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtSensors",
    "PySide6.QtNfc",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtUiTools",
    "PySide6.QtHelp",
    "PySide6.QtPrintSupport",
    "PySide6.QtTest",
    "PySide6.QtConcurrent",
    "PySide6.QtAxContainer",
    "PySide6.QtDBus",
    "PySide6.QtDesigner",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech",
    "PySide6.QtVirtualKeyboard",
    # 其他不需要的标准库模块
    "tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "difflib",
]

# ===== CPU 模式额外排除的模块（GPU 推理相关）=====
# 这些模块仅在 GPU 模式下需要，CPU 模式排除可节省约 470 MB
CPU_EXTRA_EXCLUDED_MODULES = [
    "tensorrt",
    "cuda",
    "cuda.bindings",
    "cuda.bindings.driver",
    "cuda.bindings.runtime",
    "cuda.cuda",
    "cuda.cudart",
    "pynvml",
]

# ===== CPU 模式需要删除的 DLL 文件模式（前缀匹配，递归遍历整个依赖目录）=====
# 这些 DLL 仅 GPU 推理需要，CPU 模式删除可大幅减小体积：
# - nvinfer_10.dll (414 MB), nvinfer_plugin_10.dll (52 MB) 等: TensorRT 推理引擎
# - onnxruntime_providers_cuda.dll (252.9 MB): onnxruntime CUDA 加速后端
#   位于 onnxruntime/capi/ 子目录下，需递归遍历才能匹配
CPU_EXCLUDED_DLL_PATTERNS = [
    "nvinfer",
    "nvonnxparser",
    "nvinfer_plugin",
    "nvinfer_builder_resource",
    "onnxruntime_providers_cuda",
    "onnxruntime_providers_shared",
]

# ===== 隐藏导入（PyInstaller 无法静态检测的动态导入）=====
HIDDEN_IMPORTS = [
    "onnxruntime",
    "onnxruntime.capi",
    "cv2",
    "numpy",
    "PIL",
    "PIL._tkinter_finder",
    "yaml",
    "concurrent.futures",
    "ctypes",
    "psutil",
    # SmartAnnotator 自身模块（确保算法层被收集）
    "smart_annotator.core.annotate.vision.yolo",
    "smart_annotator.core.annotate.vision.onnxbackend",
    "smart_annotator.core.annotate.vision.tensorrtbackend",
    "smart_annotator.core.annotate.vision.onnx2engine",
    "smart_annotator.core.annotate.formatters.factory",
]

# ===== GPU 模式额外的隐藏导入 =====
# cuda-python 包内部 Cython 模块（from cuda import cuda, cudart 时动态加载）
# PyInstaller 无法自动检测，必须显式声明，否则打包后报
# "No module named 'cuda.bindings.cydriver'"
GPU_EXTRA_HIDDEN_IMPORTS = [
    "pynvml",
    "tensorrt",
    "cuda",
    "cuda.bindings",
    "cuda.bindings.driver",
    "cuda.bindings.runtime",
    "cuda.bindings.cydriver",
    "cuda.bindings.cyruntime",
    "cuda.cuda",
    "cuda.cudart",
    # cuda-python 的 DLL 加载器（cuda/bindings/_lib/windll.pxd）依赖
    # ctypes.wintypes，PyInstaller 的 ctypes hook 不会自动收集
    "ctypes.wintypes",
]

# ===== GPU 模式需要完整复制的 Python 原生绑定包 =====
# 这些包含大量动态加载的 Cython 子模块（.pyd）与 __init__.py 引导逻辑，
# PyInstaller 的静态分析只能收集到部分 .pyd，会遗漏关键子包导致运行时报错：
# - cuda: 缺 cuda.bindings._bindings（from cuda import cuda, cudart 失败）
# - tensorrt: 缺 __init__.py 与 plugin/（import 变成空命名空间包，调用必挂）
GPU_NATIVE_PACKAGES = ["cuda", "tensorrt"]

# ===== GPU 模式需要删除的冗余 CUDA DLL（前缀匹配，递归遍历整个打包目录）=====
# GPU 推理完全走 TensorRT 引擎（yolo.py: engine 加载 / onnx→engine 转换），
# onnxruntime 仅在 CPU 模式使用（CPUExecutionProvider 内置于 onnxruntime.dll 主库），
# 因此以下 DLL 可安全删除（经 PE 静态导入表分析确认 TensorRT 10 链路不依赖它们）：
# - onnxruntime_providers_cuda.dll (306 MB): onnxruntime CUDA 后端（含静态链接的 cuDNN）
# - onnxruntime_providers_shared.dll: provider 动态加载器壳
# - onnxruntime_providers_tensorrt.dll: onnxruntime TRT 后端（直接用 tensorrt 包）
# - cudnn*.dll / cublas*.dll / cufft*.dll: 仅 CUDA EP 需要，TensorRT 10 不依赖
# 注意：cudart64_*.dll、nvinfer*.dll、nvonnxparser*.dll 为必需，不得删除
GPU_REDUNDANT_DLL_PATTERNS = [
    "onnxruntime_providers_cuda",
    "onnxruntime_providers_shared",
    "onnxruntime_providers_tensorrt",
    "cudnn",
    "cublas",
    "cufft",
]

# ===== CPU 模式需要删除的冗余 CUDA DLL（前缀匹配，递归遍历整个打包目录）=====
# CPU 推理仅用 onnxruntime.dll 内置的 CPUExecutionProvider，所有 CUDA DLL 均无用。
# PyInstaller 会因构建机 onnxruntime-gpu / PATH 中的 CUDA Toolkit 将以下 DLL 收集到
# exe 根目录（实测: cublasLt64_12.dll 636MB / cufft64_11.dll 274MB / cublas64_12.dll 98MB），
# 必须以 exe 目录为根递归清理（_cleanup_gpu_dlls 只遍历依赖子目录，覆盖不到根目录）。
# GPU_REDUNDANT_DLL_PATTERNS 之外额外增加 cudart（CPU 模式无任何 CUDA 调用）。
CPU_REDUNDANT_DLL_PATTERNS = GPU_REDUNDANT_DLL_PATTERNS + [
    "cudart",
    "cupti",
    "nvrtc",
    "nvjit",
    "nvvm",
]


def _cleanup_unused_qt_dlls(pyside_dir: Path) -> int:
    """清理 PySide6 目录中未使用的 Qt DLL 和资源文件。

    工具仅使用 QtCore/QtGui/QtWidgets，以下文件可安全删除：
    - opengl32sw.dll: 软件 OpenGL 渲染器（19.7 MB）
    - Qt6Quick.dll / Qt6Qml.dll: QML/Quick 模块
    - Qt6Pdf.dll: PDF 模块
    - Qt6Network.dll: 网络模块
    - 各 3D/Charts/DataVisualization/WebEngine 等模块
    - translations/ qml/ resources/ examples/ 目录

    注意：保留 plugins/imageformats 与 plugins/iconengines 插件，
    应用需加载 png/jpeg/ico 等图片格式。

    Args:
        pyside_dir: PySide6 目录路径。

    Returns:
        已删除文件的总字节数。
    """
    if not pyside_dir.exists():
        return 0

    # 需要删除的 DLL 文件名模式（前缀匹配）
    unused_dll_patterns = [
        "opengl32sw",
        "Qt6Quick",
        "Qt6Qml",
        "Qt6Pdf",
        "Qt6Network",
        "Qt6OpenGL",
        "Qt6DataVisualization",
        "Qt6Charts",
        "Qt6VirtualKeyboard",
        "Qt6Multimedia",
        "Qt6WebEngine",
        "Qt6WebChannel",
        "Qt6WebSockets",
        "Qt6SerialPort",
        "Qt6Bluetooth",
        "Qt6Positioning",
        "Qt6Location",
        "Qt6Sensors",
        "Qt6Nfc",
        "Qt6Scxml",
        "Qt6StateMachine",
        "Qt6Test",
        "Qt6Concurrent",
        "Qt6Help",
        "Qt6RemoteObjects",
        "Qt6SpatialAudio",
        "Qt6TextToSpeech",
        "Qt6Sql",
        "Qt6Svg",
        "Qt6PrintSupport",
        "Qt6Designer",
        "Qt6AxContainer",
        "Qt6DBus",
        "Qt6UiTools",
        "Qt63D",
    ]

    # 需要删除的目录
    unused_dirs = ["translations", "qml", "resources", "examples"]

    removed_size = 0

    # 删除未使用的 DLL
    for dll in pyside_dir.glob("*.dll"):
        dll_name = dll.stem  # 不含扩展名
        for pattern in unused_dll_patterns:
            if dll_name.startswith(pattern):
                removed_size += dll.stat().st_size
                dll.unlink()
                break

    # 删除未使用的 .pyd 文件
    for pyd in pyside_dir.glob("*.pyd"):
        pyd_name = pyd.stem
        for pattern in unused_dll_patterns:
            if pyd_name.startswith(pattern):
                removed_size += pyd.stat().st_size
                pyd.unlink()
                break

    # 删除未使用的目录
    for dir_name in unused_dirs:
        dir_path = pyside_dir / dir_name
        if dir_path.exists() and dir_path.is_dir():
            for f in dir_path.rglob("*"):
                if f.is_file():
                    removed_size += f.stat().st_size
            shutil.rmtree(dir_path)

    # 清理 plugins 目录中未使用的插件
    # 保留 platforms（窗口系统必需）、styles（样式）、imageformats（png/jpeg）、iconengines（图标）
    plugins_dir = pyside_dir / "plugins"
    if plugins_dir.exists():
        unused_plugin_dirs = [
            "bearer", "networkinformation", "position", "sensors",
            "sqldrivers", "tls", "multimedia", "playlistformats",
            "audio", "video", "printsupport",
            "geometryloaders", "sceneparsers",
            "renderplugins", "scxml", "texttospeech", "canbus",
            "webview",
        ]
        for plugin_subdir in unused_plugin_dirs:
            plugin_path = plugins_dir / plugin_subdir
            if plugin_path.exists() and plugin_path.is_dir():
                for f in plugin_path.rglob("*"):
                    if f.is_file():
                        removed_size += f.stat().st_size
                shutil.rmtree(plugin_path)

    return removed_size


def _cleanup_gpu_dlls(packages_dir: Path) -> int:
    """CPU 模式专用：递归删除 GPU 推理相关的 DLL 文件与 Python 包目录。

    CPU 模式不需要 GPU 推理，以下文件可安全删除以大幅减小体积：
    - TensorRT 推理引擎 DLL（根目录）: nvinfer_10.dll (414 MB) 等
    - onnxruntime CUDA 后端 DLL（onnxruntime/capi/ 子目录）:
      onnxruntime_providers_cuda.dll (252.9 MB)
    - tensorrt / cuda Python 包目录

    注意：DLL 文件分布在依赖目录的多个子目录中（如 onnxruntime/capi/），
    必须递归遍历整个依赖目录才能全部匹配。

    Args:
        packages_dir: 依赖包目录路径（VAI_E_SmartAnnotator 子目录）。

    Returns:
        已删除文件的总字节数。
    """
    if not packages_dir.exists():
        return 0

    removed_size = 0

    # 递归遍历依赖目录中的所有 DLL 文件（含子目录如 onnxruntime/capi/）
    for dll in packages_dir.rglob("*.dll"):
        dll_name = dll.stem  # 不含扩展名
        for pattern in CPU_EXCLUDED_DLL_PATTERNS:
            if dll_name.startswith(pattern):
                removed_size += dll.stat().st_size
                dll.unlink()
                break

    # 删除 tensorrt Python 包目录（CPU 模式不需要）
    tensorrt_dir = packages_dir / "tensorrt"
    if tensorrt_dir.exists() and tensorrt_dir.is_dir():
        for f in tensorrt_dir.rglob("*"):
            if f.is_file():
                removed_size += f.stat().st_size
        shutil.rmtree(tensorrt_dir)

    # 删除 cuda Python 包目录
    cuda_dir = packages_dir / "cuda"
    if cuda_dir.exists() and cuda_dir.is_dir():
        for f in cuda_dir.rglob("*"):
            if f.is_file():
                removed_size += f.stat().st_size
        shutil.rmtree(cuda_dir)

    # 删除 pynvml Python 包目录（GPU 监控，CPU 模式不需要）
    pynvml_dir = packages_dir / "pynvml"
    if pynvml_dir.exists() and pynvml_dir.is_dir():
        for f in pynvml_dir.rglob("*"):
            if f.is_file():
                removed_size += f.stat().st_size
        shutil.rmtree(pynvml_dir)

    return removed_size


def _fix_gpu_native_packages(packages_dir: Path) -> int:
    """GPU 模式专用：从当前 Python 环境完整复制原生绑定包，替换 PyInstaller 的不完整收集。

    PyInstaller 静态分析无法收集 cuda / tensorrt 包中动态加载的 Cython 子模块，
    典型缺失：
    - cuda/bindings/_bindings/ 子包与 __init__.py（导致 cuda-python 导入失败）
    - tensorrt/__init__.py 与 plugin/（导致 import 后为空命名空间包）

    处理方式：删除依赖目录中的残缺包，从 site-packages 完整复制（跳过 __pycache__）。

    同时将 PyInstaller 收集到 exe 根目录的 TensorRT DLL 移入 tensorrt.libs/ 子目录：
    tensorrt 10.x 的 __init__.py 通过 find_lib 加载 DLL，仅搜索 PATH 与
    <包目录>/../tensorrt.libs 两处。DLL 留在 exe 根目录时，用户机器上
    （无 CUDA Toolkit，PATH 不含 TensorRT）会报 "Could not find: nvinfer_10.dll"。

    Args:
        packages_dir: 依赖包目录路径（VAI_E_SmartAnnotator 子目录）。

    Returns:
        复制的文件总字节数。
    """
    import sysconfig

    site_packages = Path(sysconfig.get_paths()["purelib"])
    copied_size = 0

    for pkg_name in GPU_NATIVE_PACKAGES:
        src_dir = site_packages / pkg_name
        dst_dir = packages_dir / pkg_name
        if not src_dir.exists():
            print(f"  [警告] site-packages 中未找到 {pkg_name} 包: {src_dir}")
            continue

        # 删除 PyInstaller 收集的残缺版本
        if dst_dir.exists():
            shutil.rmtree(dst_dir)

        # 完整复制（忽略 __pycache__ 与 Cython 源文件，减小体积）
        def _copy_tree(src: Path, dst: Path) -> None:
            nonlocal copied_size
            dst.mkdir(parents=True, exist_ok=True)
            for item in src.iterdir():
                if item.name == "__pycache__":
                    continue
                target = dst / item.name
                if item.is_dir():
                    _copy_tree(item, target)
                elif item.suffix in (".pyd", ".py", ".dll"):
                    copied_size += item.stat().st_size
                    shutil.copy2(item, target)

        _copy_tree(src_dir, dst_dir)
        print(f"  已完整复制 {pkg_name} 包（累计 {copied_size / 1024 / 1024:.1f} MB）")

    # ===== 将 TensorRT DLL 移入 tensorrt.libs/（修复用户机器加载失败）=====
    # PyInstaller 从构建机 PATH（CUDA Toolkit lib 目录）收集 nvinfer*.dll，
    # 放置位置不确定（exe 根目录或 contents 目录均出现过），
    # 但 tensorrt 的 find_lib 只搜索 PATH 与 <包>/../tensorrt.libs，必须统一移入
    trt_libs_dir = packages_dir / "tensorrt.libs"
    trt_libs_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for base in (packages_dir, packages_dir.parent):
        for dll in list(base.glob("nvinfer*.dll")) + list(base.glob("nvonnxparser*.dll")):
            shutil.move(str(dll), str(trt_libs_dir / dll.name))
            moved += 1
    if moved:
        print(f"  已移动 {moved} 个 TensorRT DLL 到 tensorrt.libs/（nvinfer/nvonnxparser）")

    return copied_size


def _cleanup_gpu_redundant_dlls(exe_dir: Path) -> int:
    """GPU 模式专用：递归删除冗余的 CUDA 推理 DLL，大幅减小打包体积。

    GPU 推理完全走 TensorRT 引擎，onnxruntime 的 CUDA EP 及其 cuDNN/cuBLAS/cuFFT
    依赖均不被使用（onnxruntime 仅保留 CPU EP 用于 CPU 模式与回退）。
    删除内容参见 GPU_REDUNDANT_DLL_PATTERNS 注释。

    注意：DLL 分布在打包目录的多个位置（exe 根目录、onnxruntime/capi/ 等），
    必须对整个 exe 目录递归遍历。

    Args:
        exe_dir: 打包输出目录路径（dist_{mode}/VAI_E_SmartAnnotator）。

    Returns:
        已删除文件的总字节数。
    """
    return _remove_dlls_by_patterns(exe_dir, GPU_REDUNDANT_DLL_PATTERNS)


def _cleanup_cpu_redundant_dlls(exe_dir: Path) -> int:
    """CPU 模式专用：递归删除所有 CUDA 相关 DLL。

    CPU 推理仅使用 onnxruntime.dll 内置的 CPUExecutionProvider，
    打包目录中的全部 CUDA DLL（cudart/cublas/cufft/cudnn/nvrtc 等）均无用。
    PyInstaller 会因构建机的 onnxruntime-gpu 依赖链或 PATH 中的 CUDA Toolkit
    将这些 DLL 收集到 exe 根目录（实测混入约 1 GB），必须整体清理。

    Args:
        exe_dir: 打包输出目录路径（dist_{mode}/VAI_E_SmartAnnotator）。

    Returns:
        已删除文件的总字节数。
    """
    return _remove_dlls_by_patterns(exe_dir, CPU_REDUNDANT_DLL_PATTERNS)


def _remove_dlls_by_patterns(root_dir: Path, patterns: list) -> int:
    """按文件名前缀模式递归删除目录中的 DLL 文件。

    Args:
        root_dir: 递归遍历的根目录路径。
        patterns: DLL 文件名（不含扩展名）前缀模式列表。

    Returns:
        已删除文件的总字节数。
    """
    if not root_dir.exists():
        return 0

    removed_size = 0
    for dll in root_dir.rglob("*.dll"):
        dll_name = dll.stem  # 不含扩展名
        for pattern in patterns:
            if dll_name.startswith(pattern):
                removed_size += dll.stat().st_size
                dll.unlink()
                break

    return removed_size


def _build_packages_list(packages_dir: Path) -> str:
    """递归遍历依赖目录，生成完整包清单文本。

    清单每条记录: 相对路径|字节大小（相对路径以 / 分隔，相对 packages_dir）。
    以 # 开头的为注释头，便于人工阅读与机器解析通用。

    Args:
        packages_dir: 依赖包目录路径。

    Returns:
        包清单文本内容。
    """
    files = []
    for f in packages_dir.rglob("*"):
        if f.is_file():
            rel = f.relative_to(packages_dir).as_posix()
            files.append((rel, f.stat().st_size))

    lines = [
        f"# {PACKAGES_DIR_NAME} 包清单",
        f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# 文件总数: {len(files)}",
        "# 格式: 相对路径|字节大小",
        "# ---- 以下为文件条目 ----",
    ]
    for rel, size in sorted(files):
        lines.append(f"{rel}|{size}")
    return "\n".join(lines) + "\n"


def _create_zip(source_dir: Path, zip_path: Path) -> int:
    """将源目录打包为 zip 压缩文件。

    用于生成在线安装器下载的分发包。

    Args:
        source_dir: 源目录路径（打包内容的根目录）。
        zip_path: 输出 zip 文件路径。

    Returns:
        zip 文件的字节大小。
    """
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir)
                zf.write(file_path, arcname)

    return zip_path.stat().st_size


# Gitee Release 单文件限制 100 MB，留 5 MB 余量
MAX_PART_SIZE = 95 * 1024 * 1024


def _split_zip(zip_path: Path, max_part_size: int = MAX_PART_SIZE) -> int:
    """将大 zip 文件分割成多个分卷，以适应 Gitee Release 单文件 100 MB 限制。

    分卷命名格式: filename.zip.part001, filename.zip.part002, ...
    原始 zip 文件在分卷后删除，仅保留分卷文件。

    Args:
        zip_path: 原始 zip 文件路径。
        max_part_size: 每个分卷最大字节数（默认 95 MB）。

    Returns:
        分卷数量。如果不需要分卷（文件 <= max_part_size），返回 1（保留原文件）。
    """
    file_size = zip_path.stat().st_size
    if file_size <= max_part_size:
        return 1  # 不需要分卷

    num_parts = (file_size + max_part_size - 1) // max_part_size
    print(f"  zip 文件 {file_size / 1024 / 1024:.1f} MB 超过 {max_part_size / 1024 / 1024:.0f} MB 限制，分割为 {num_parts} 个分卷")

    with open(zip_path, "rb") as f:
        data = f.read()

    for i in range(num_parts):
        start = i * max_part_size
        end = min(start + max_part_size, file_size)
        part_path = zip_path.parent / f"{zip_path.name}.part{i + 1:03d}"
        with open(part_path, "wb") as f:
            f.write(data[start:end])
        print(f"  分卷 {i + 1}/{num_parts}: {part_path.name} ({(end - start) / 1024 / 1024:.1f} MB)")

    # 删除原始 zip 文件（分卷已生成）
    # 容错处理：杀毒软件/索引服务可能短暂锁定文件，重试后再失败仅告警不中断构建
    for attempt in range(5):
        try:
            zip_path.unlink()
            break
        except (FileNotFoundError, PermissionError) as e:
            if attempt == 4:
                print(f"  [警告] 原始 zip 删除失败（{e}），可手动删除: {zip_path}")
            else:
                import time
                time.sleep(1)
    return num_parts


def _read_download_config() -> dict:
    """从 download_config.ini 读取 Gitee Release 下载配置。

    配置文件位于项目根目录，格式:
        [urls]
        cpu_url = https://gitee.com/.../CPU_1.2.0.zip      ; parts=1 时为完整 URL
        cpu_parts = 1
        gpu_url = https://gitee.com/.../GPU_1.2.0.zip.part  ; parts>1 时为基础 URL（追加 001/002/...）
        gpu_parts = 6

    Returns:
        dict: {"cpu_url": str|None, "gpu_url": str|None, "cpu_parts": int, "gpu_parts": int}
    """
    config_path = PROJECT_ROOT / "download_config.ini"
    if not config_path.exists():
        print(f"  [警告] 下载配置文件不存在: {config_path}")
        return {"cpu_url": None, "gpu_url": None, "cpu_parts": 1, "gpu_parts": 1}

    cp = configparser.ConfigParser()
    cp.read(config_path, encoding="utf-8")

    cpu_url = cp.get("urls", "cpu_url", fallback=None)
    gpu_url = cp.get("urls", "gpu_url", fallback=None)
    cpu_parts = cp.getint("urls", "cpu_parts", fallback=1)
    gpu_parts = cp.getint("urls", "gpu_parts", fallback=1)

    # 检测占位符（用户尚未替换实际 Gitee 账号）
    for url in (cpu_url, gpu_url):
        if url and "your-account" in url:
            print(f"  [警告] 下载 URL 仍为占位符，请编辑 download_config.ini 替换 'your-account'")
            print(f"         当前 URL: {url}")
            return {"cpu_url": None, "gpu_url": None, "cpu_parts": 1, "gpu_parts": 1}

    return {"cpu_url": cpu_url, "gpu_url": gpu_url, "cpu_parts": cpu_parts, "gpu_parts": gpu_parts}


def _update_download_config_parts(mode: str, parts: int) -> None:
    """更新 download_config.ini 中指定模式的分卷数量。

    构建后自动写入，供后续 --mode online 读取。

    Args:
        mode: "cpu" 或 "gpu"。
        parts: 分卷数量。
    """
    config_path = PROJECT_ROOT / "download_config.ini"
    if not config_path.exists():
        return

    cp = configparser.ConfigParser()
    cp.read(config_path, encoding="utf-8")
    if not cp.has_section("urls"):
        cp.add_section("urls")
    cp.set("urls", f"{mode}_parts", str(parts))
    with open(config_path, "w", encoding="utf-8") as f:
        cp.write(f)


def _find_iscc() -> str | None:
    """查找 Inno Setup 编译器 ISCC.exe 的路径。

    搜索顺序:
        1. 用户目录 AppData\\Local\\Programs\\Inno Setup 6（winget 默认安装位置）
        2. Program Files\\Inno Setup 6（传统安装位置）
        3. Program Files (x86)\\Inno Setup 6（32 位安装位置）
        4. PATH 环境变量中的 iscc

    Returns:
        ISCC.exe 的完整路径，未找到则返回 None。
    """
    # 常见安装路径
    candidates = [
        Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
        Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    # 尝试 PATH
    return shutil.which("iscc")


def _compile_installer(
    iss_name: str, output_name: str, defines: dict[str, str] | None = None
) -> Path | None:
    """调用 Inno Setup 编译指定 .iss 脚本生成安装程序。

    .iss 脚本位于项目根目录（PROJECT_ROOT），ISCC 以项目根目录为工作目录运行，
    这样 .iss 中的相对路径（如 Source、SetupIconFile）能正确解析。
    安装程序输出到 BUILD_DIR/installer_output/。

    Args:
        iss_name: .iss 文件名（如 installer.iss, installer_online.iss）。
        output_name: 预期输出的 exe 文件名（不含路径）。
        defines: 传递给 ISCC 的预定义变量（/D 参数）。

    Returns:
        生成的 Setup.exe 路径，失败则返回 None。
    """
    iss_path = PROJECT_ROOT / iss_name
    if not iss_path.exists():
        print(f"  [跳过] Inno Setup 脚本不存在: {iss_path}")
        return None

    iscc = _find_iscc()
    if iscc is None:
        print("  [跳过] 未找到 Inno Setup 编译器（ISCC.exe），请安装 Inno Setup 6")
        print("         安装命令: winget install JRSoftware.InnoSetup")
        return None

    # 构建 ISCC 命令（含 /D 预定义变量）
    cmd = [iscc]
    if defines:
        for key, value in defines.items():
            cmd.append(f"/D{key}={value}")
    cmd.append(str(iss_path))

    print(f"  编译脚本: {iss_name}")
    if defines:
        print(f"  预定义变量: {defines}")

    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        print("  [失败] Inno Setup 编译失败!")
        # 输出最后 2000 字符的诊断信息
        print(result.stdout[-2000:] if result.stdout else "")
        print(result.stderr[-1000:] if result.stderr else "")
        return None

    # 输出目录由 .iss 的 OutputDir 指定（build/installer_output）
    setup_exe = BUILD_DIR / "installer_output" / output_name
    if setup_exe.exists():
        size_mb = setup_exe.stat().st_size / 1024 / 1024
        print(f"  安装程序已生成: {setup_exe.name} ({size_mb:.1f} MB)")
        return setup_exe

    print(f"  [警告] 编译成功但未找到输出文件: {setup_exe}")
    return None


def _build_package(
    vm: VersionManager,
    mode: str,
    version_info_path: Path,
) -> Path:
    """执行单个模式（CPU/GPU）的 PyInstaller 打包流程。

    打包产物输出到 BUILD_DIR/dist_{mode}/，图标从 PROJECT_ROOT/app.ico 读取。

    Args:
        vm: VersionManager 实例。
        mode: 打包模式，"cpu" 或 "gpu"。
        version_info_path: version_info.txt 文件路径。

    Returns:
        打包输出目录路径（BUILD_DIR/dist_{mode}/VAI_E_SmartAnnotator）。
    """
    mode_upper = mode.upper()
    print(f"\n{'='*60}")
    print(f"  构建 {mode_upper} 版")
    print(f"{'='*60}")

    main_py = PROJECT_ROOT / "smart_annotator" / "main.py"
    icon_path = PROJECT_ROOT / "app.ico"
    # 每个模式使用独立的 dist 目录，避免互相覆盖
    dist_dir = BUILD_DIR / f"dist_{mode}"
    work_dir = BUILD_DIR / f"build_temp_{mode}"

    # 清理旧构建
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)

    # 构建排除模块列表
    excluded = list(EXCLUDED_MODULES)
    if mode == "cpu":
        excluded.extend(CPU_EXTRA_EXCLUDED_MODULES)
        print(f"  [CPU] 额外排除 {len(CPU_EXTRA_EXCLUDED_MODULES)} 个 GPU 模块")

    # 构建隐藏导入列表
    hidden = list(HIDDEN_IMPORTS)
    if mode == "gpu":
        hidden.extend(GPU_EXTRA_HIDDEN_IMPORTS)

    # 构建 PyInstaller 命令
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",                              # 无控制台窗口
        "--name", vm.PROGRAM_NAME,                 # 程序名称: VAI_E_SmartAnnotator
        "--version-file", str(version_info_path),  # Windows 版本信息
        "--distpath", str(dist_dir),
        "--workpath", str(work_dir),
        "--specpath", str(BUILD_DIR),
        "--paths", str(PROJECT_ROOT),              # 添加项目根目录到搜索路径
        "--contents-directory", PACKAGES_DIR_NAME, # 依赖包目录命名
    ]

    # 添加 icon
    if icon_path.exists():
        pyinstaller_cmd.extend(["--icon", str(icon_path)])
        pyinstaller_cmd.extend(["--add-data", f"{icon_path};."])
    else:
        print(f"  [警告] 图标文件不存在: {icon_path}")

    # 添加排除模块
    for mod in excluded:
        pyinstaller_cmd.extend(["--exclude-module", mod])

    # 添加隐藏导入
    for mod in hidden:
        pyinstaller_cmd.extend(["--hidden-import", mod])

    # 收集实际使用的 PySide6 模块
    pyinstaller_cmd.extend([
        "--collect-submodules", "PySide6.QtCore",
        "--collect-submodules", "PySide6.QtGui",
        "--collect-submodules", "PySide6.QtWidgets",
    ])

    # 入口脚本
    pyinstaller_cmd.append(str(main_py))

    print(f"  排除模块数: {len(excluded)}")
    print(f"  隐藏导入数: {len(hidden)}")
    result = subprocess.run(pyinstaller_cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print(f"\n  {mode_upper} 打包失败! 请检查 PyInstaller 输出。")
        sys.exit(1)

    # ===== 清理未使用的 Qt DLL =====
    print(f"\n  [{mode_upper}] 清理未使用的 Qt DLL...")
    exe_dir = dist_dir / vm.PROGRAM_NAME
    pyside_dir = exe_dir / PACKAGES_DIR_NAME / "PySide6"
    removed_qt = _cleanup_unused_qt_dlls(pyside_dir)
    print(f"  已清理 Qt DLL，释放 {removed_qt / 1024 / 1024:.1f} MB")

    # ===== CPU 模式额外清理 GPU 推理相关 DLL =====
    if mode == "cpu":
        print(f"\n  [CPU] 清理 GPU 推理 DLL（TensorRT + onnxruntime CUDA provider）...")
        packages_dir = exe_dir / PACKAGES_DIR_NAME
        removed_gpu = _cleanup_gpu_dlls(packages_dir)
        print(f"  已清理 GPU 推理 DLL，释放 {removed_gpu / 1024 / 1024:.1f} MB")
        # 清理 exe 根目录混入的 CUDA DLL（构建机 onnxruntime-gpu 依赖链引入，约 1 GB）
        print(f"\n  [CPU] 清理 exe 根目录混入的 CUDA 冗余 DLL（cublas/cufft/cudart 等）...")
        removed_cuda = _cleanup_cpu_redundant_dlls(exe_dir)
        print(f"  已清理 CUDA 冗余 DLL，释放 {removed_cuda / 1024 / 1024:.1f} MB")

    # ===== GPU 模式修复 PyInstaller 收集不完整问题 + 清理冗余 CUDA DLL =====
    if mode == "gpu":
        print(f"\n  [GPU] 修复原生绑定包（cuda / tensorrt 完整复制）...")
        packages_dir = exe_dir / PACKAGES_DIR_NAME
        _fix_gpu_native_packages(packages_dir)
        print(f"\n  [GPU] 清理冗余 CUDA DLL（onnxruntime CUDA EP + cuDNN/cuBLAS/cuFFT）...")
        removed_redundant = _cleanup_gpu_redundant_dlls(exe_dir)
        print(f"  已清理冗余 CUDA DLL，释放 {removed_redundant / 1024 / 1024:.1f} MB")

    # ===== 生成 py_packages_list.txt =====
    print(f"\n  [{mode_upper}] 生成 py_packages_list.txt...")
    packages_dir = exe_dir / PACKAGES_DIR_NAME
    packages_list_content = _build_packages_list(packages_dir)
    packages_list_path = exe_dir / "py_packages_list.txt"
    packages_list_path.write_text(packages_list_content, encoding="utf-8")

    # ===== 创建 zip 压缩包（用于在线分发，超过 95 MB 自动分卷）=====
    print(f"\n  [{mode_upper}] 创建 zip 压缩包...")
    app_version = "1.2.0"
    zip_path = BUILD_DIR / "packages" / f"VAI_E_SmartAnnotator_{mode.upper()}_{app_version}.zip"
    zip_size = _create_zip(exe_dir, zip_path)
    print(f"  zip 文件: {zip_path.name} ({zip_size / 1024 / 1024:.1f} MB)")

    # 自动分卷（Gitee Release 单文件 100 MB 限制）
    num_parts = _split_zip(zip_path)
    if num_parts > 1:
        # 分卷后 URL 需追加 .part001/.part002/...，更新配置中的基础 URL
        _update_download_config_parts(mode, num_parts)
        # 更新 download_config.ini 中的 URL 为分卷基础 URL（以 .part 结尾）
        config_path = PROJECT_ROOT / "download_config.ini"
        if config_path.exists():
            cp = configparser.ConfigParser()
            cp.read(config_path, encoding="utf-8")
            old_url = cp.get("urls", f"{mode}_url", fallback="")
            if old_url and not old_url.endswith(".part"):
                cp.set("urls", f"{mode}_url", old_url + ".part")
                with open(config_path, "w", encoding="utf-8") as f:
                    cp.write(f)
                print(f"  已更新 download_config.ini: {mode}_url → 分卷基础 URL, {mode}_parts = {num_parts}")
    else:
        _update_download_config_parts(mode, 1)

    # 打印目录总大小
    total_size = sum(f.stat().st_size for f in exe_dir.rglob("*") if f.is_file())
    print(f"\n  [{mode_upper}] 打包目录总大小: {total_size / 1024 / 1024:.1f} MB")

    return exe_dir


def main() -> None:
    """执行完整打包流程。

    支持以下模式:
        --mode cpu:     仅构建 CPU 离线安装器
        --mode gpu:     仅构建 GPU 离线安装器
        --mode all:     同时构建 CPU + GPU 离线安装器 + 在线安装器（默认）
        --mode online:  仅编译在线安装器（上传 zip 到 Gitee Release 后使用）
    """
    parser = argparse.ArgumentParser(
        description="VAI_E_SmartAnnotator 打包构建脚本"
    )
    parser.add_argument(
        "--mode",
        choices=["cpu", "gpu", "all", "online"],
        default="all",
        help="打包模式: cpu=仅CPU版, gpu=仅GPU版, all=CPU+GPU+在线安装器, online=仅在线安装器 (默认: all)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  VAI_E_SmartAnnotator 打包构建")
    print(f"  模式: {args.mode}")
    print("=" * 60)

    # 确保构建输出目录存在
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # ===== 步骤 1: 生成文件版本号 =====
    print("\n[步骤 1] 生成版本号...")
    vm = VersionManager(counter_file=str(BUILD_DIR / "version_counter.txt"))
    file_version = vm.generate_file_version()
    print(f"  文件版本: {file_version}")
    print(f"  产品版本: {vm.PRODUCT_VERSION} (固定)")

    # ===== 步骤 2: 生成 version_info.txt =====
    print("\n[步骤 2] 生成 PyInstaller 版本信息文件...")
    version_info_path = BUILD_DIR / "version_info.txt"
    version_info_content = vm.generate_version_info_text(file_version)
    version_info_path.write_text(version_info_content, encoding="utf-8")
    print(f"  已生成: {version_info_path}")

    setup_exes: list[Path] = []
    built_dirs: dict[str, Path] = {}

    # ===== 步骤 3: PyInstaller 打包（online 模式跳过）=====
    if args.mode != "online":
        print("\n[步骤 3] 调用 PyInstaller 打包...")
        modes_to_build = ["cpu", "gpu"] if args.mode == "all" else [args.mode]
        for mode in modes_to_build:
            exe_dir = _build_package(vm, mode, version_info_path)
            built_dirs[mode] = exe_dir

        # ===== 步骤 4: 编译离线安装器 =====
        print("\n[步骤 4] 编译 Inno Setup 离线安装程序...")
        for mode, exe_dir in built_dirs.items():
            mode_upper = mode.upper()
            print(f"\n  --- {mode_upper} 离线安装器 ---")
            # 相对路径（相对于 PROJECT_ROOT，ISCC 以 PROJECT_ROOT 为 cwd）
            dist_rel = exe_dir.relative_to(PROJECT_ROOT)
            setup = _compile_installer(
                iss_name="installer.iss",
                output_name=f"VAI_E_SmartAnnotator_Setup_{mode_upper}.exe",
                defines={
                    "MyDistDir": str(dist_rel).replace("\\", "/"),
                    "OutputSuffix": f"_{mode_upper}",
                    "MyMode": mode_upper,
                },
            )
            if setup:
                setup_exes.append(setup)

    # ===== 编译在线安装器（all 或 online 模式）=====
    if args.mode in ("all", "online"):
        print(f"\n  --- 在线安装器 ---")
        # 从 download_config.ini 读取 Gitee Release 下载配置（URL + 分卷数）
        dl_config = _read_download_config()
        online_defines: dict[str, str] = {}
        if dl_config["cpu_url"]:
            online_defines["CPU_DOWNLOAD_URL"] = dl_config["cpu_url"]
            online_defines["CPU_PARTS"] = str(dl_config["cpu_parts"])
            print(f"  CPU 下载 URL: {dl_config['cpu_url']} (分卷: {dl_config['cpu_parts']})")
        if dl_config["gpu_url"]:
            online_defines["GPU_DOWNLOAD_URL"] = dl_config["gpu_url"]
            online_defines["GPU_PARTS"] = str(dl_config["gpu_parts"])
            print(f"  GPU 下载 URL: {dl_config['gpu_url']} (分卷: {dl_config['gpu_parts']})")
        if not online_defines:
            print("  [提示] 未配置实际下载 URL，将使用 installer_online.iss 中的占位符 URL")
            print("         上传 zip 到 Gitee Release 后，编辑 download_config.ini 替换 URL，重新编译")
        online_setup = _compile_installer(
            iss_name="installer_online.iss",
            output_name="VAI_E_SmartAnnotator_OnlineSetup.exe",
            defines=online_defines if online_defines else None,
        )
        if online_setup:
            setup_exes.append(online_setup)

    # ===== 完成 =====
    print("\n" + "=" * 60)
    print("  打包完成!")
    print(f"  文件版本: {file_version}")
    print(f"  产品版本: {vm.PRODUCT_VERSION}")
    print(f"  公司: {vm.COMPANY_NAME}")
    print(f"  产品: {vm.PRODUCT_NAME}")
    if setup_exes:
        print(f"\n  安装程序:")
        for setup in setup_exes:
            size_mb = setup.stat().st_size / 1024 / 1024
            print(f"    {setup.name} ({size_mb:.1f} MB)")
    print("\n  zip 分发包 (用于上传到 Gitee Release):")
    packages_dir = BUILD_DIR / "packages"
    if packages_dir.exists():
        for zip_file in packages_dir.glob("*.zip"):
            size_mb = zip_file.stat().st_size / 1024 / 1024
            print(f"    {zip_file.name} ({size_mb:.1f} MB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
