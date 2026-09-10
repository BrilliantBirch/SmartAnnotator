# BrilliantAnnotator v1.2.0

基于 PySide6 的智能标注工具，提供 LabelMe ↔ YOLO 格式转换与 ONNX 自动标注（CPU / CUDA GPU）功能。

## 1. 功能概述

| 功能             | 说明                                                                           |
| ---------------- | ------------------------------------------------------------------------------ |
| **标注编辑器**   | 三栏式（工具栏/画布/信息栏）标注编辑器，矩形/点/多边形绘制、属性编辑、撤销重做 |
| **格式转换**     | LabelMe JSON ↔ YOLO TXT 双向转换（导出/导入），支持目标检测/姿态估计/实例分割  |
| **自动标注**     | 加载 ONNX 模型批量推理（CPU / onnxruntime CUDA EP），输出 LabelMe 标注文件     |
| **视频标注**     | 视频抽帧标注（帧间隔/差异阈值可调），含预览播放器与损坏视频保护                |
| **检测类别选择** | 模型加载后自动解析元数据类别，支持复选/全选/取消全选，按类别过滤推理结果       |
| **数据集分析**   | 一键分析数据集标签/任务/方向，数据集按 train/val/test 比例分层划分             |
| **配置管理**     | JSON 格式导入/导出，兼容旧版 camelCase 键                                      |

### 支持的任务模式

| 模式      | 说明               | 转换 | 标注     |
| --------- | ------------------ | ---- | -------- |
| `DETECT`  | 目标检测           | ✓    | ✓        |
| `POSE`    | 姿态估计（关键点） | ✓    | ✓        |
| `SEGMENT` | 实例分割           | ✓    | ✓        |
| `OCR`     | 光学字符识别       | ✓    | 未来版本 |

## 2. 技术栈

| 项目          | 版本                |
| ------------- | ------------------- |
| Python        | 3.12.10（严格锁定） |
| PySide6       | 6.11.1              |
| numpy         | 2.4.6               |
| opencv-python | 4.13.0.92           |
| onnxruntime   | 1.28.0              |
| pywin32       | 312                 |

完整依赖见 [requirements.txt](requirements.txt)，GPU 额外依赖见 [requirements-gpu.txt](requirements-gpu.txt)。

## 3. 项目结构

```
BrilliantAnnotator/
├── smart_annotator/              # 主包
│   ├── __init__.py               # 应用常量
│   ├── __main__.py               # python -m smart_annotator 入口
│   ├── main.py                   # QApplication 入口
│   ├── app.py                    # MainWindow 主窗口（三栏标注编辑器）
│   ├── styles.py                 # 全局 QSS 样式表
│   ├── config.py                 # dataclass 配置 + 枚举
│   ├── version_manager.py        # 版本号管理
│   ├── pages/                    # 页面层（base/convert/annotate）
│   ├── widgets/                  # 公共控件（画布/右栏/对话框/文件列表模型等）
│   ├── workers/                  # QThread 工作线程
│   ├── core/                     # 业务逻辑（转换/标注算法，无 Qt 依赖）
│   └── utils/                    # 工具（日志/文件/路径/颜色/渲染配置）
├── build.py                      # PyInstaller 打包脚本（项目根目录）
├── installer.iss                 # Inno Setup 离线安装器脚本
├── installer_online.iss          # Inno Setup 在线安装器脚本
├── download_config.ini           # Gitee Release 下载 URL 配置
├── app.ico                       # 应用图标
├── docs/                         # 文档（用户说明书 + PDF 生成脚本）
├── requirements.txt              # 依赖列表
├── requirements-gpu.txt          # GPU 额外依赖
├── AGENTS.md                     # AI 编码助手项目规则
└── README.md
```

## 4. 安装与运行

### 4.1 环境准备

```bash
# 创建 conda 虚拟环境（Python 3.12.10）
conda create -n BrilliantAnnotator python=3.12.10
conda activate BrilliantAnnotator

# 安装依赖
pip install -r requirements.txt

# GPU 推理需额外安装（onnxruntime-gpu + nvidia 运行库，源码运行用）
pip install -r requirements-gpu.txt
```

> GPU 模式说明：推理走 onnxruntime CUDA Execution Provider。
> - **源码运行**：requirements-gpu.txt 内的 nvidia-*-cu12 pip 包提供 CUDA 运行库，
>   程序启动时自动注册（见 `smart_annotator/core/annotate/vision/onnxbackend.py`
>   的 `_ensure_cuda_dlls`），无需系统级 CUDA Toolkit。
> - **打包 GPU 版**：安装包**不携带** CUDA 运行库（2026-09-10 起采用 X-AnyLabeling
>   同款瘦身策略，体积约 650 MB），用户需自备 **CUDA Toolkit 12.9 + cuDNN 9.x**
>   （cuDNN 的 bin 目录需在 PATH 中，或通过 conda 安装 nvidia 组件）。

### 4.2 运行

```bash
# 方式一：模块入口
python -m smart_annotator

# 方式二：直接运行
python smart_annotator/main.py
```

## 5. 配置文件格式

### 5.1 格式转换配置（convert_config.json）

```json
{
  "classes": ["cat", "dog"],
  "kpt": { "nose_point0": { "isChecked": true, "bbox_size": 10 } },
  "visualize": false,
  "export": false,
  "train_ratio": 0.8,
  "val_ratio": 0.1,
  "test_ratio": 0.1
}
```

> 输入/输出目录为运行期状态，不序列化（导出输入固定为当前工作路径，
> 导入时可指定输入与输出目录）。

### 5.2 自动标注配置（annotate_config.json）

```json
{
  "device": "GPU",
  "model_path": "",
  "image_path": "",
  "dataset_path": "",
  "conf": 0.25,
  "kpt_conf": 0.5,
  "nms": 0.7,
  "frame_interval": 30,
  "diff_threshold": 10.0,
  "task_type": "DETECT",
  "selected_classes": [0, 1, 2]
}
```

> 配置导入兼容旧版 camelCase 键名（如 `modelPath` → `model_path`）。
> `selected_classes` 为用户选择检测的类别 id 列表，空列表表示不过滤（检测所有类别）。
> `model_path` 仅支持 `.onnx`（GPU 经 onnxruntime CUDA EP 推理，无需模型转换）。

## 6. 打包

```bash
# 在项目根目录执行（GPU 模式需在含 TensorRT 10.x 的 conda 环境中运行，见 AGENTS.md 2.1 节）
python build.py --mode all      # 构建 CPU + GPU 离线安装器 + 在线安装器
python build.py --mode cpu      # 仅构建 CPU 离线安装器
python build.py --mode gpu      # 仅构建 GPU 离线安装器
python build.py --mode online   # 仅编译在线安装器（上传 zip 到 Gitee 后使用）
```

打包产物位于 `build/dist_{mode}/BrilliantAnnotator/`：
- `BrilliantAnnotator.exe` — 可执行文件
- `BrilliantAnnotator/` — 依赖包目录  
- `py_packages_list.txt` — 依赖文件清单

安装程序输出到 `build/installer_output/`，zip 分发包输出到 `build/packages/`。

### CPU / GPU 构建模式与环境隔离（2026-09-07 起）

构建系统按 `--mode` 参数严格区分 CPU/GPU 配置，**不受构建机本机 CUDA 安装状态干扰**：

| 模式                                    | 环境隔离                                                                                                                               | 产物内容                                                                                                                                                                                           | 运行时行为                                                                                                                           |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `--mode cpu`                            | 剔除 PyInstaller 子进程的 `CUDA_PATH` 等环境变量与 PATH 中 CUDA Toolkit/nvidia 目录（`_build_isolated_env`），从源头阻止 CUDA DLL 混入 | 零 CUDA 组件（清理模式含 `nvidia/nvml` 前缀兜底），exe 目录写入 `build_mode.txt = cpu` 标志                                                                                                        | 启动时读取标志，**跳过 CUDA 检测并禁用 GPU 选项**（提示"CPU 版本：仅支持 CPU 推理"），即使运行在带 NVIDIA 显卡的机器上也不会推荐 GPU |
| `--mode gpu`                            | 同样剔除 PyInstaller 子进程的 CUDA 环境变量与 PATH 中 CUDA Toolkit/nvidia 目录（`_build_isolated_env`，与 CPU 一致）                   | **移除内置 CUDA 运行库**（2026-09-10 起）：仅携带 onnxruntime_providers_cuda 本体（约 650 MB），清理 TensorRT 残留（nvinfer/nvonnxparser）与 cuDNN/cuBLAS/cuFFT/nvrtc，写入 `build_mode.txt = gpu` | 用户环境自备 CUDA Toolkit 12.9 + cuDNN 9.x（PATH 生效）后正常 GPU 推理；无 N 卡或未装 CUDA 时自动回退 CPU 推理                       |
| 开发模式（`python -m smart_annotator`） | —                                                                                                                                      | —                                                                                                                                                                                                  | 无标志文件，按 CUDA 可用性正常联动                                                                                                   |

因此：在已安装 CUDA 的机器上构建 CPU 版本，产物同样纯净（仅 CPU 组件、体积最小）；
CPU 版本分发到任何机器都不会出现"检测到 CUDA，推荐使用 GPU"的误导提示。

GPU 模式构建说明（2026-09-10 起，X-AnyLabeling 式瘦身）：
- GPU 推理走 onnxruntime CUDA Execution Provider（TensorRT / cuda-python 链路已移除）
- 构建时**移除**内置 CUDA 运行库（cuDNN/cuBLAS/cuFFT/nvrtc 约 2.2 GB），GPU 包仅
  携带 onnxruntime_providers_cuda 本体，体积约 650 MB（可进 Gitee 附件额度）
- **终端用户需自备 CUDA 运行库**：安装 CUDA Toolkit 12.9 + cuDNN 9.x（bin 入 PATH）
- 清理构建机混入的冗余 TensorRT DLL（nvinfer/nvonnxparser 等）

版本号策略：
- 文件版本：`年.月.日.构建次数`（如 `26.8.10.0`），自动递增
- 产品版本：`2.1.0`（唯一来源 `smart_annotator/__init__.py` 的 `__version__`，发版时仅改此一处）

## 7. 架构设计

### 7.1 分层架构

```
pages/（界面层）→ workers/（线程层）→ core/（算法层）
     ↑                ↑                  ↑
     └── widgets/     └── base_worker    └── utils/
```

- **界面层**（pages/）：BasePage 基类，通过 Signal 与 worker 通信
- **线程层**（workers/）：BaseWorker(QThread) 提供进度/日志/错误信号，耗时任务不阻塞 UI
- **算法层**（core/）：纯 Python 算法，无 Qt 依赖，可独立测试
- **工具层**（utils/）：日志（LOGGER 纯 Python 控制台 + QtLogHandler Qt 适配）、文件扫描、路径解析

### 7.2 配置管理

基于 `@dataclass` 的配置类（`ConvertConfig`/`AnnotateConfig`/`SysConfig`），支持 `to_dict()`/`from_dict()` 序列化与旧版 camelCase 键迁移。

### 7.3 标注编辑器（主界面）

三栏式布局：左侧快捷操作栏（文件/自动标注/标注工具）+ 中间标注画布
（图像显示与形状绘制/编辑）+ 右侧信息栏（标签/对象/文件/关键点列表）。
文件列表采用 QListView + FileListModel 实现 UI 虚拟化，万级目录秒开。

### 7.4 类别选择链路

```
模型路径选择 → getModelClasses()（onnx 解析 metadata["names"]）
→ ClassSelectorWidget（复选列表）
→ AnnotateConfig.selected_classes → Annotator._filter_by_classes()
→ 推理结果按类别过滤（bboxs/scores/labels/keypoints/boundary_points 同步）
```

## 8. 文档

- 用户使用说明书：[docs/BrilliantAnnotator_用户说明书.pdf](docs/BrilliantAnnotator_用户说明书.pdf)    
  （源文件 [docs/manual.md](docs/manual.md)，修改后需运行 `python docs/generate_manual_pdf.py` 重新生成）

## 9. 贡献规范

- 遵循 [AGENTS.md](AGENTS.md) 项目规则（分支策略、代码风格、验证清单）
- Python 版本严格锁定 3.12.10，依赖版本见 requirements.txt（禁止自行升级/降级）
- 提交信息格式：`<type>(<scope>): <subject>`（type: feat/fix/refactor/docs/chore）
- 修改后最低验证：`python -m py_compile <文件>` + `python -c "import <模块>"`
- 涉及 manual.md 的修改必须重新生成 PDF

## 10. 作者

BaiBnnan
