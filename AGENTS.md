# AGENTS.md — VAI_E_SmartAnnotator AI 编码助手项目规则

> 本文档是 AI 编码助手（Trae / Cursor / Copilot 等）操作本项目的**强制性规则文件**。
> 助手在本项目内执行任何任务前，必须先完整阅读本文档并严格遵守。
> 文档中的所有路径均相对项目根目录 `e:\VAI_E\VAI_E_SmartAnnotator`。

---

## 1. 概述

| 项       | 内容                                                                              |
| -------- | --------------------------------------------------------------------------------- |
| 项目名称 | VAI_E_SmartAnnotator                                                              |
| 产品版本 | 1.2.0（固定），文件版本 `年.月.日.构建次数` 自动递增                              |
| 定位     | 基于 PySide6 的智能数据标注工具：LabelMe ↔ YOLO 格式转换 + ONNX/TensorRT 自动标注 |
| 语言     | Python 3.12.10（严格锁定，禁止其他版本）                                          |
| GUI 框架 | PySide6 6.11.1（Qt for Python）                                                   |
| 推理后端 | ONNX Runtime（CPU）/ TensorRT 10.x（GPU，经 `cuda-python` 绑定）                  |
| 平台     | Windows 10/11 x64                                                                 |
| 作者     | BaiBinnan                                                                         |

**核心功能**：
- 自动标注：加载 ONNX/TensorRT 模型批量推理，输出 LabelMe 格式标注（DETECT/POSE/SEGMENT）
- 检测类别选择：模型加载后解析元数据类别，支持全选/取消全选与按类别过滤
- 格式转换：LabelMe(JSON) ↔ YOLO(TXT) 双向转换，含数据集划分与目录结构导出

---

## 2. 配置说明

### 2.1 Python 环境与虚拟环境

**环境要求**（不限定具体环境名与路径，任何满足以下条件的 conda/venv 虚拟环境均可）：

| 项                       | 要求                                                                                                           |
| ------------------------ | -------------------------------------------------------------------------------------------------------------- |
| Python 解释器            | **3.12.10**（严格锁定，含补丁版本也不允许）                                                                    |
| CPU 依赖                 | [requirements.txt](requirements.txt) 全量安装                                                                  |
| GPU 构建（`--mode gpu`） | 额外满足 [requirements-gpu.txt](requirements-gpu.txt)：TensorRT **10.x**（10.13 验证通过）+ `cuda-python` 绑定 |

**创建环境示例**（conda）：

```bash
# 创建满足要求的新环境（环境名自定，此处以 vai_annotator 为例）
conda create -n vai_annotator python=3.12.10
conda activate vai_annotator

# 离线安装依赖（GPU 构建另需安装 requirements-gpu.txt）
pip install --no-index --find-links=./VAI_Packages -r requirements.txt
```

**注意**：
- 禁止使用 TensorRT 8.x 的环境构建 GPU 版（与本项目 TRT 10.x API 不兼容，如 `set_tensor_address`）
- GPU 模式构建必须在含 TensorRT 10.x + cuda-python 的环境中执行（需收集该环境的 TensorRT/cuda DLL）
- 环境是否满足要求可通过以下命令自检：

```bash
python --version                    # 应输出 3.12.10
python -c "import tensorrt; print(tensorrt.__version__)"   # GPU 构建：应 >= 10.0
```

### 2.2 依赖锁定（禁止自行升级/降级）

完整列表见 [requirements.txt](requirements.txt)，GPU 额外依赖见 [requirements-gpu.txt](requirements-gpu.txt)。

| 依赖          | 版本      | 用途                                         |
| ------------- | --------- | -------------------------------------------- |
| PySide6       | 6.11.1    | GUI 框架                                     |
| numpy         | 2.4.6     | 数值计算                                     |
| opencv-python | 4.13.0.92 | 图像/视频处理                                |
| onnxruntime   | 1.28.0    | CPU 推理（GPU 版为 onnxruntime-gpu==1.28.0） |
| onnx          | 1.19.0    | 模型元数据轻量解析                           |
| pywin32       | 312       | Windows API                                  |
| pyinstaller   | 6.21.0    | 打包                                         |

离线安装方式：`pip install --no-index --find-links=./VAI_Packages -r requirements.txt`

### 2.3 运行期配置文件

| 文件                   | 管理者                    | 说明                                                        |
| ---------------------- | ------------------------- | ----------------------------------------------------------- |
| `annotate_config.json` | 用户导入/导出             | 自动标注配置（`AnnotateConfig.to_dict()` 产物，见下文 3.2） |
| `convert_config.json`  | 用户导入/导出             | 格式转换配置（`ConvertConfig.to_dict()` 产物）              |
| `download_config.ini`  | `build.py` 构建时自动写入 | Gitee Release 下载 URL 与分卷数，供在线安装器使用           |
| `VAI_Packages/`        | 人工维护                  | 离线依赖包目录                                              |

---

## 3. 接口定义（代码库地图）

### 3.1 目录结构与模块职责

```
smart_annotator/
├── main.py / __main__.py        # QApplication 入口（无 CLI 子命令）
├── app.py                       # MainWindow 主窗口（侧边栏/底部标签栏响应式切换）
├── config.py                    # dataclass 配置 + 枚举（全部配置的唯一定义处）
├── version_manager.py           # VersionManager：文件版本号生成
├── styles.py                    # 全局 QSS 样式表
├── pages/                       # 页面层（继承 base_page.BasePage）
│   ├── welcome_page.py          # 欢迎页（功能入口）
│   ├── convert_page.py          # 格式转换页
│   └── annotate_page.py         # 自动标注页（6 卡片布局）
├── widgets/                     # 公共控件
│   ├── class_selector.py        # ClassSelectorWidget：类别复选列表 + 全选/取消全选
│   ├── drag_list.py             # DragDropListWidget：拖拽排序列表（保留 itemWidget）
│   ├── fields.py / buttons.py / cards.py / dialogs.py / preview.py
├── workers/                     # QThread 工作线程（任务运行期禁用导航）
│   ├── base_worker.py           # 工作线程基类（进度/日志/错误信号）
│   ├── annotate_worker.py       # AnnotationWorker → Annotator
│   ├── convert_worker.py        # ConvertWorker → Converter
│   └── analyze_worker.py        # AnalyzeWorker → analyze_dataset（数据集一键分析）
├── core/                        # 业务逻辑（无 Qt 依赖）
│   ├── annotate/
│   │   ├── annotator.py         # Annotator：批量推理 + 类别过滤 + 输出
│   │   ├── vision/
│   │   │   ├── yolo.py          # YoloV8Predictor 等预测器（metadata["names"] 解析）
│   │   │   ├── onnxbackend.py   # ONNXInfer：onnxruntime CPU 会话
│   │   │   ├── tensorrtbackend.py # TensorRTInfer：TRT 10.x（set_tensor_address）
│   │   │   └── onnx2engine.py   # Onnx2Engine：ONNX→engine 转换（含 metadata 写入）
│   │   ├── formatters/          # 策略模式：base/detect/pose/segment/factory
│   │   └── video_processor.py   # 视频抽帧（cv2.VideoCapture，依赖 ffmpeg DLL）
│   └── convert/
│       ├── converter.py         # Converter：格式转换编排（策略模式工厂）
│       ├── dataset_analyzer.py  # analyze_dataset：数据集一键分析（标签/任务/方向）
│       ├── json_converter.py    # LabelMe JSON → YOLO TXT
│       └── txt_converter.py     # YOLO TXT → LabelMe JSON
└── utils/                       # 工具（logger/files/paths/colors/tool/qt_logger）
    └── files.py                 # getModelClasses()：onnx/engine 类别元数据解析
```

### 3.2 关键数据结构（smart_annotator/config.py）

```python
# AnnotateConfig 字段（to_dict() 序列化为 annotate_config.json）
device: DEVICE            # CPU / GPU
model_path: str           # .onnx 或 .engine
selected_classes: list    # 选定类别 id；空列表 = 不过滤（检测所有类别）
conf / nms / kpt_conf     # 置信度 / NMS / 关键点阈值
frame_interval / diff_threshold  # 视频抽帧参数
task_type: MODE           # DETECT / POSE / SEGMENT / OCR
```

枚举定义：`MODE`（L25-31）、`DEVICE`、`Format` 均在 config.py，是**唯一定义处**，禁止在他处重复定义。

### 3.3 关键链路（修改前必读）

**类别选择链路**（2026-08-26 实现）：

```
模型路径变化 → utils/files.py:getModelClasses()
    ├─ .onnx: onnx.load(load_external_data=False) 解析 metadata_props["names"]
    └─ .engine: 解析文件头 [4字节长度][metadata JSON]（onnx2engine 写入），
                失败回退同名 .onnx
→ widgets/class_selector.py:ClassSelectorWidget.set_classes()（默认全选）
→ AnnotateConfig.selected_classes
→ core/annotate/annotator.py:Annotator._filter_by_classes()
    （同步过滤 bboxs/scores/labels/keypoints ndarray 与 boundary_points list）
```

**engine 文件格式**（onnx2engine.py 写入、tensorrtbackend.py / files.py 读取）：

```
[4 字节小端有符号长度][metadata JSON 字节][TensorRT 序列化数据]
```

注意：metadata 中 `"names"` 的值经过一次 `json.dumps`，是双层字符串，解析时需先 `json.loads` 解开一层。

**GPU 推理链路**：GPU 模式完全走 TensorRT 引擎（`tensorrtbackend.py`），**不依赖** onnxruntime CUDA Execution Provider——CUDA 检测逻辑（`annotate_page.py:_cuda_available()`）只检查 tensorrt + cuda-python 导入，不得添加对 `CUDAExecutionProvider` 的依赖。

### 3.4 打包体系（build.py）

| 函数                                       | 职责                                                                        |
| ------------------------------------------ | --------------------------------------------------------------------------- |
| `_build_package(vm, mode, ...)`            | 单模式打包主流程（PyInstaller + 清理 + zip + 配置）                         |
| `_remove_dlls_by_patterns(root, patterns)` | 按前缀递归删除 DLL（CPU/GPU 清理共用）                                      |
| `_cleanup_cpu_redundant_dlls(exe_dir)`     | CPU 模式：清理全部 CUDA DLL（模式表 `CPU_REDUNDANT_DLL_PATTERNS`）          |
| `_cleanup_gpu_redundant_dlls(exe_dir)`     | GPU 模式：清理 CUDA EP/cuDNN/cuBLAS/cuFFT（保留 cudart/nvinfer）            |
| `_fix_gpu_native_packages(packages_dir)`   | GPU 模式：完整复制 cuda/tensorrt 原生包 + nvinfer DLL 移入 `tensorrt.libs/` |
| `_split_zip / _create_zip`                 | zip 分卷（Gitee 100MB 限制）                                                |
| `_compile_installer`                       | 调用 Inno Setup（ISCC.exe）编译安装器                                       |

**DLL 清理铁律**：清理必须以 **exe 目录为根**递归遍历（PyInstaller 会把 CUDA 传递依赖放在 exe 根目录，只遍历依赖子目录会漏删——CPU 包曾因此混入 1GB 冗余 DLL）。

**不得删除的 DLL**（GPU 模式）：`cudart64_*.dll`、`nvinfer*.dll`、`nvonnxparser*.dll`。

### 3.5 文档体系

| 文件                                                                                 | 说明                            |
| ------------------------------------------------------------------------------------ | ------------------------------- |
| [README.md](README.md)                                                               | 项目说明（结构/配置/打包/架构） |
| [docs/manual.md](docs/manual.md)                                                     | 用户说明书源文件（Markdown）    |
| [docs/generate_manual_pdf.py](docs/generate_manual_pdf.py)                           | 说明书 PDF 生成脚本             |
| [docs/VAI_E_SmartAnnotator_用户说明书.pdf](docs/VAI_E_SmartAnnotator_用户说明书.pdf) | 最终 PDF（5 页）                |

**修改 manual.md 后必须重新生成 PDF**：
`python docs/generate_manual_pdf.py`（在满足 2.1 节要求的环境中执行）。

---

## 4. 使用示例（常用命令）

### 4.1 运行程序

```bash
# 在满足 2.1 节要求的虚拟环境中，项目根目录执行
python -m smart_annotator
```

### 4.2 构建（项目根目录执行）

```bash
python build.py --mode all      # CPU + GPU 离线安装器 + 在线安装器（默认）
python build.py --mode cpu      # 仅 CPU 离线安装器
python build.py --mode gpu      # 仅 GPU 离线安装器（必须在含 TensorRT 10.x 的环境，见 2.1 节）
python build.py --mode online   # 仅在线安装器（上传 zip 到 Gitee 后）
```

产物位置：
- 打包目录：`build/dist_{cpu|gpu}/VAI_E_SmartAnnotator/`
- 安装器：`build/installer_output/VAI_E_SmartAnnotator_Setup_{CPU|GPU}.exe`
- zip 分卷：`build/packages/`

体积基线（2026-08-26）：CPU 安装器 61.6MB，GPU 安装器 220MB，CPU 打包目录 244.6MB，GPU 737MB。

### 4.3 验证命令

```bash
# 模块导入验证（代码修改后的最低验证要求）
python -c "import smart_annotator"

# 语法检查
python -m py_compile <修改的文件>
```

测试**不强制运行**（项目规则，2026-08-25 起生效），仅用户明确要求时执行：
`python -m pytest tests/ -v --tb=short`

---

## 5. 引用规范（编码强制规则）

### 5.1 反幻觉编程（最高优先级）

1. **先读后写**：修改任何文件前必须先用 Read 工具读取当前内容，禁止凭记忆修改
2. **禁止编造 API**：类名/方法名/属性名/配置键名必须在代码库中 Grep 确认存在，或从已读文件中明确看到定义
3. **禁止假设文件路径**：所有路径必须 Glob/Grep 确认存在后再使用
4. **禁止假设依赖行为**：第三方库 API 以 `VAI_Packages/` 实际版本为准

### 5.2 文件头注释（每个 .py 文件强制）

```python
# -*- coding: utf-8 -*-
"""
<文件功能描述>

作者: BaiBinnan
创建日期: YYYY-MM-DD
更新: YYYY-MM-DD <本次修改内容摘要>
"""
```

已有文件修改时必须追加"更新"行；新建文件必须完整包含上述头。

### 5.3 代码风格

- 全部代码注释、docstring、日志、UI 提示信息使用**中文**
- 函数必须带 docstring，包含 Args / Returns / Raises（有异常时）
- 代码块的开始、结束、关键步骤需有注释
- 禁用 Python 3.12 已弃用的语法与标准库特性

### 5.4 架构约定

- **配置唯一定义处**：`config.py` 的 dataclass；页面 `collect_config()` 收集 / `apply_config()` 回填
- **线程模型**：耗时任务放 `workers/` 的 QThread 子类，经信号回传（禁止在 UI 线程执行推理/转换）
- **core 无 Qt 依赖**：`smart_annotator/core/` 下禁止 import PySide6
- **策略模式**：标注格式化经 `formatters/factory.py` 分发，新增任务类型时扩展而非 if-else
- **完整采纳新机制**：重构时禁止保留向前兼容的过渡方案
- **清理**：开发完成后必须清理冗余代码、注释、临时测试文件与未用依赖

### 5.5 禁止事项

- 禁止更新 `optimize=2`（-OO）打包选项（会剥离 numpy 依赖的 docstring）
- 禁止对 nvinfer DLL 使用 UPX（破坏 NVIDIA 签名，触发杀软误报）
- 禁止排除标准库 urllib/email/socket/inspect/zipfile（PyInstaller 运行时钩子依赖）
- 禁止将 `tests/` 提交到 git（已设置忽略）

---

## 6. 故障排除

| 症状                                             | 原因                                                                                                   | 解决                                                                                                              |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| 打包后 GPU 版报 `Could not find: nvinfer_10.dll` | TRT 10.x 的 `find_lib` 只搜索 PATH 与 `tensorrt/../tensorrt.libs`；PyInstaller 把 DLL 收集到了错误位置 | 确认 `_fix_gpu_native_packages` 将 nvinfer DLL 移入 `tensorrt.libs/`；必要时同时搜索 exe 目录与 contents 目录两处 |
| 打包后报 `No module named 'cuda.bindings'`       | PyInstaller 静态分析收集不全 cuda-python 的 Cython 子模块                                              | `_fix_gpu_native_packages` 从 site-packages 完整复制；确认 `GPU_EXTRA_HIDDEN_IMPORTS` 含 `ctypes.wintypes`        |
| CPU 安装包体积异常大（>300MB）                   | PyInstaller 为 onnxruntime-gpu 收集的 CUDA 传递依赖落在 exe 根目录                                     | 确认 `_cleanup_cpu_redundant_dlls(exe_dir)` 以 exe 目录为根执行                                                   |
| Intel oneMKL 报错                                | 构建环境不对（numpy 依赖的 mkl_*.dll 未被收集）                                                        | 在满足 2.1 节要求、且已安装全部运行依赖的环境中运行 PyInstaller                                                   |
| 生成的 PDF 中文显示为方块                        | 脚本设置了 `QT_QPA_PLATFORM=offscreen`，该平台无字体数据库                                             | `generate_manual_pdf.py` 必须用默认 windows 平台运行                                                              |
| 安装器编译被跳过（提示 Inno Setup 脚本不存在）   | 在错误分支上构建                                                                                       | 确认在 `pyside_dev` 分支；ISCC.exe 位置见 `_find_iscc()`                                                          |
| inno 编译在线安装器 URL 不对                     | 分卷数变化后 `download_config.ini` 未同步                                                              | 重建 zip 后检查 `cpu_url`/`gpu_url` 的 `.part` 后缀与 `*_parts` 数值一致性                                        |
| zip 分卷删除失败                                 | 杀毒/索引服务锁定                                                                                      | `_split_zip` 已内置 5 次重试；仍失败仅告警，可手动删除                                                            |

---

## 7. 修改后验证清单

任何代码修改完成后（不强制跑测试，但需通过以下最低验证）：

1. `python -m py_compile <修改的文件>` —— 语法通过
2. `python -c "import <修改的模块>"` —— 导入通过（在满足 2.1 节要求的环境中）
3. 涉及 UI 的修改：确认 `import smart_annotator.pages.<页面模块>` 通过
4. 涉及打包的修改：确认 `python build.py --mode cpu` 构建成功且体积符合基线
5. 涉及 manual.md 的修改：重新运行 `python docs/generate_manual_pdf.py`

---

## 8. 修订历史

| 日期       | 内容                                                                                  |
| ---------- | ------------------------------------------------------------------------------------- |
| 2026-08-26 | 初版创建（作者: BaiBinnan）                                                           |
| 2026-09-01 | 2.1 节改为通用虚拟环境说明（不限定环境名与路径，按 Python/TensorRT 版本要求约束）     |
| 2026-09-02 | 新增数据集一键分析模块（convert 页）；记录 QListWidget 拖拽排序的 itemWidget 销毁陷阱 |
