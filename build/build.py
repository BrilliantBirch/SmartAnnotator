# -*- coding: utf-8 -*-
"""
打包构建脚本 - 使用 PyInstaller 非 onefile 模式打包 VAI_E_SmartAnnotator

构建流程:
    1. 调用 VersionManager 生成文件版本号（年.月.日.生成次数），产品版本固定 1.2.0.0
    2. 动态生成 version_info.txt（PyInstaller Windows 版本资源）
    3. 调用 PyInstaller 打包（非 onefile，生成目录模式）
       - 排除 matplotlib 及未使用的 PySide6 模块（减小体积）
       - 保留 numpy/opencv/onnx/onnxruntime/PIL/yaml/pynvml/psutil（运行时必需）
       - 使用自定义 icon 图标
       - 依赖包目录命名为 VAI_E_SmartAnnotator
    4. 清理未使用的 Qt DLL（保留 imageformats/iconengines 插件，应用需加载 png/jpeg/ico）
    5. 在输出目录生成 py_packages_list.txt（依赖目录完整文件清单）

使用方式:
    cd build
    python build.py

移植自 VAI_MemGenerator/build/build.py，调整为 SmartAnnotator 的依赖与目录命名。

作者: BaiBinnan
创建日期: 2026-08-10
"""
import os
import sys
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

# 将项目根目录添加到 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from smart_annotator.version_manager import VersionManager


# ===== 依赖包目录命名（与 VAI_MemGenerator 的 VAI_PY_Packages 区分）=====
PACKAGES_DIR_NAME = "VAI_E_SmartAnnotator"

# ===== 需要排除的模块（减小打包体积）=====
# 注意：不排除 numpy/opencv/onnx/onnxruntime/PIL/yaml/pynvml/psutil（运行时必需）
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
    "pynvml",
    "psutil",
    # SmartAnnotator 自身模块（确保算法层被收集）
    "smart_annotator.core.annotate.vision.yolo",
    "smart_annotator.core.annotate.vision.onnxbackend",
    "smart_annotator.core.annotate.vision.tensorrtbackend",
    "smart_annotator.core.annotate.vision.onnx2engine",
    "smart_annotator.core.annotate.formatters.factory",
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


def main() -> None:
    """执行完整打包流程。"""
    print("=" * 60)
    print("  VAI_E_SmartAnnotator 打包构建")
    print("=" * 60)

    build_dir = Path(__file__).parent

    # ===== 步骤 1: 生成文件版本号 =====
    print("\n[步骤 1] 生成版本号...")
    # 计数文件位于 build 目录下
    vm = VersionManager(counter_file=str(build_dir / "version_counter.txt"))
    file_version = vm.generate_file_version()
    print(f"  文件版本: {file_version}")
    print(f"  产品版本: {vm.PRODUCT_VERSION} (固定)")

    # ===== 步骤 2: 生成 version_info.txt =====
    print("\n[步骤 2] 生成 PyInstaller 版本信息文件...")
    version_info_path = build_dir / "version_info.txt"
    version_info_content = vm.generate_version_info_text(file_version)
    version_info_path.write_text(version_info_content, encoding="utf-8")
    print(f"  已生成: {version_info_path}")

    # ===== 步骤 3: 调用 PyInstaller 打包 =====
    print("\n[步骤 3] 调用 PyInstaller 打包（非 onefile 模式）...")

    main_py = PROJECT_ROOT / "smart_annotator" / "main.py"
    icon_path = build_dir / "app.ico"
    dist_dir = build_dir / "dist"
    work_dir = build_dir / "build_temp"

    # 清理旧构建
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)

    # 构建 PyInstaller 命令
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",                              # 无控制台窗口
        "--name", vm.PROGRAM_NAME,                 # 程序名称: VAI_E_SmartAnnotator
        "--version-file", str(version_info_path),  # Windows 版本信息
        "--distpath", str(dist_dir),
        "--workpath", str(work_dir),
        "--specpath", str(build_dir),
        "--paths", str(PROJECT_ROOT),              # 添加项目根目录到搜索路径
        "--contents-directory", PACKAGES_DIR_NAME, # 依赖包目录命名
    ]

    # 添加 icon（EXE 图标 + 运行时窗口/任务栏图标）
    if icon_path.exists():
        pyinstaller_cmd.extend(["--icon", str(icon_path)])
        # 同时将图标作为数据文件打包，供运行时 setWindowIcon 使用
        pyinstaller_cmd.extend(["--add-data", f"{icon_path};."])
        print(f"  使用图标: {icon_path}")
    else:
        print(f"  [警告] 图标文件不存在: {icon_path}")

    # 添加排除模块
    for mod in EXCLUDED_MODULES:
        pyinstaller_cmd.extend(["--exclude-module", mod])

    # 添加隐藏导入
    for mod in HIDDEN_IMPORTS:
        pyinstaller_cmd.extend(["--hidden-import", mod])

    # 收集实际使用的 PySide6 模块
    pyinstaller_cmd.extend([
        "--collect-submodules", "PySide6.QtCore",
        "--collect-submodules", "PySide6.QtGui",
        "--collect-submodules", "PySide6.QtWidgets",
    ])

    # 入口脚本
    pyinstaller_cmd.append(str(main_py))

    print(f"  排除模块数: {len(EXCLUDED_MODULES)}")
    print(f"  隐藏导入数: {len(HIDDEN_IMPORTS)}")
    print(f"  命令: {' '.join(pyinstaller_cmd[:10])} ... (共 {len(pyinstaller_cmd)} 参数)")
    result = subprocess.run(pyinstaller_cmd, cwd=str(build_dir))

    if result.returncode != 0:
        print("\n  打包失败! 请检查 PyInstaller 输出。")
        sys.exit(1)

    # ===== 步骤 4: 清理未使用的 Qt DLL（减小体积）=====
    print("\n[步骤 4] 清理未使用的 Qt DLL...")
    exe_dir = dist_dir / vm.PROGRAM_NAME
    pyside_dir = exe_dir / PACKAGES_DIR_NAME / "PySide6"
    removed_size = _cleanup_unused_qt_dlls(pyside_dir)
    print(f"  已清理未使用 DLL，释放 {removed_size / 1024 / 1024:.1f} MB")

    # ===== 步骤 5: 生成 py_packages_list.txt 到输出目录 =====
    print("\n[步骤 5] 生成 py_packages_list.txt...")
    packages_dir = exe_dir / PACKAGES_DIR_NAME
    packages_list_content = _build_packages_list(packages_dir)
    packages_list_path = exe_dir / "py_packages_list.txt"
    packages_list_path.write_text(packages_list_content, encoding="utf-8")
    print(f"  已生成: {packages_list_path}")

    # ===== 完成 =====
    print("\n" + "=" * 60)
    print("  打包完成!")
    print(f"  输出目录: {exe_dir}")
    print(f"  可执行文件: {exe_dir / (vm.PROGRAM_NAME + '.exe')}")
    print(f"  文件版本: {file_version}")
    print(f"  产品版本: {vm.PRODUCT_VERSION}")
    print(f"  公司: {vm.COMPANY_NAME}")
    print(f"  产品: {vm.PRODUCT_NAME}")
    print("=" * 60)


if __name__ == "__main__":
    main()
